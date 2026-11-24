"""Puente con ComfyUI: manda prompts a la cola local y descarga las imágenes.

ComfyUI es el programa que genera las imágenes en tu PC (Stable Diffusion / SDXL).
Aquí NO se instala ni se arranca: solo hablamos con su API HTTP local
(por defecto ``http://127.0.0.1:8188``).

Flujo normal de una imagen:

1. :func:`construir_workflow` arma el "plano" de nodos que ComfyUI ejecutará.
2. :func:`encolar` lo mete en la cola y recibe un ``prompt_id``.
3. :func:`esperar_resultado` pregunta hasta que termina y devuelve los archivos.
4. :func:`descargar_imagen` baja el PNG resultante.

Todo se puede usar sin servidor: :func:`construir_workflow` no necesita red si
le pasas un checkpoint, y :func:`diagnostico` nunca lanza excepciones (sirve
para que la interfaz muestre "ComfyUI apagado" en vez de un traceback).
"""

from __future__ import annotations

import math
import random
import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from .config import IMAGES_DIR, settings
from .schemas import ImagePrompt

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
URL_POR_DEFECTO = "http://127.0.0.1:8188"
PREFIJO_POR_DEFECTO = "ytagent"

# Tiempos (segundos) de las llamadas cortas. La generación en sí puede tardar
# minutos: eso se controla con el `timeout` de `esperar_resultado`.
TIMEOUT_CORTO = 10.0
TIMEOUT_ENVIO = 15.0
TIMEOUT_DESCARGA = 60.0

# Caracteres que Windows no permite en un nombre de archivo.
_CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# ===========================================================================
# Error propio
# ===========================================================================
class ComfyUIError(RuntimeError):
    """Cualquier problema al hablar con ComfyUI, con un mensaje entendible.

    Se usa en vez de dejar escapar errores de red, JSON o de la API: la UI
    puede mostrar ``str(error)`` directamente al usuario.
    """


# ===========================================================================
# Utilidades internas
# ===========================================================================
def _url_base(url: str | None = None) -> str:
    """Devuelve la URL de ComfyUI sin barra final.

    Si no se pasa ``url``, usa ``settings.comfyui_url``; si también está vacía,
    cae al valor por defecto para no romper el programa.
    """
    base = (url or "").strip() or settings.comfyui_url.strip()
    return (base or URL_POR_DEFECTO).rstrip("/") or URL_POR_DEFECTO


def _mensaje_sin_conexion(base: str, detalle: str = "") -> str:
    """Mensaje amable para cuando ComfyUI no está escuchando."""
    mensaje = (
        f"No se pudo conectar con ComfyUI en {base}. "
        "Comprueba que ComfyUI esté abierto y que COMFYUI_URL "
        "(o settings.comfyui_url) apunte a su dirección correcta."
    )
    if detalle:
        mensaje = f"{mensaje} Detalle técnico: {detalle}"
    return mensaje


def _peticion(
    metodo: str,
    ruta: str,
    *,
    url: str | None = None,
    timeout: float = TIMEOUT_CORTO,
    **kwargs: Any,
) -> requests.Response:
    """Hace una petición HTTP a ComfyUI y convierte fallos de red en ComfyUIError."""
    base = _url_base(url)
    try:
        return requests.request(metodo, f"{base}{ruta}", timeout=timeout, **kwargs)
    except requests.exceptions.Timeout as exc:
        raise ComfyUIError(
            f"ComfyUI no respondió a tiempo ({timeout:.0f} s) en {base}. "
            "Puede estar saturado, bloqueado por el antivirus o a medio arrancar."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise ComfyUIError(_mensaje_sin_conexion(base, str(exc))) from exc
    except requests.RequestException as exc:
        raise ComfyUIError(f"Error de red hablando con ComfyUI ({base}): {exc}") from exc


def _json_de(respuesta: requests.Response, contexto: str) -> dict[str, Any]:
    """Lee la respuesta como objeto JSON y falla con un mensaje claro si no lo es."""
    try:
        datos = respuesta.json()
    except ValueError as exc:
        # ValueError cubre JSONDecodeError y también respuestas que no son JSON.
        texto = (respuesta.text or "").strip()
        trozo = f" Respuesta recibida: {texto[:200]!r}" if texto else ""
        raise ComfyUIError(
            f"ComfyUI devolvió una respuesta que no es JSON válido ({contexto}).{trozo}"
        ) from exc
    if not isinstance(datos, dict):
        raise ComfyUIError(
            f"ComfyUI devolvió un JSON inesperado ({contexto}): se esperaba un objeto."
        )
    return datos


def _extraer_error_json(datos: Any) -> str:
    """Convierte los errores de ComfyUI (``error`` / ``node_errors``) en texto legible.

    Es la parte que más ayuda a depurar: ComfyUI suele decir exactamente qué
    nodo falló y por qué (por ejemplo, un checkpoint que no existe).
    """
    if not isinstance(datos, dict):
        return ""

    partes: list[str] = []

    error = datos.get("error")
    if isinstance(error, dict):
        mensaje = error.get("message") or error.get("type")
        if mensaje:
            partes.append(str(mensaje))
    elif error:
        partes.append(str(error))

    node_errors = datos.get("node_errors")
    if isinstance(node_errors, dict):
        for nodo, info in node_errors.items():
            if not isinstance(info, dict):
                partes.append(f"nodo {nodo}: {info}")
                continue
            clase = info.get("class_type", "?")
            detalles: list[str] = []
            for item in info.get("errors") or []:
                if not isinstance(item, dict):
                    if item:
                        detalles.append(str(item))
                    continue
                texto = str(item.get("message") or item.get("type") or "").strip()
                extra = str(item.get("details") or "").strip()
                if extra:
                    texto = f"{texto} ({extra})" if texto else extra
                if texto:
                    detalles.append(texto)
            if not detalles:
                detalles = ["error desconocido"]
            partes.append(f"nodo {nodo} ({clase}): {'; '.join(detalles)}")
    elif node_errors:
        partes.append(str(node_errors))

    return " | ".join(parte for parte in partes if parte)


def _error_http(respuesta: requests.Response, contexto: str) -> ComfyUIError:
    """Construye un ComfyUIError con el mayor detalle posible de una respuesta HTTP."""
    detalle = ""
    try:
        datos = respuesta.json()
    except ValueError:
        datos = None
    if datos is not None:
        detalle = _extraer_error_json(datos)
    if not detalle:
        texto = (respuesta.text or "").strip()
        detalle = texto[:400] if texto else "sin detalle del servidor"
    return ComfyUIError(f"{contexto} (HTTP {respuesta.status_code}): {detalle}")


def _notificar(callback: Callable[[str], None] | None, mensaje: str) -> None:
    """Llama a ``on_progress`` sin dejar que un fallo de la UI corte la generación."""
    if callback is None:
        return
    try:
        callback(mensaje)
    except Exception:  # la interfaz no debe tumbar el proceso de imágenes
        pass


def _notificar_item(
    callback: Callable[[int, Path | str], None] | None,
    numero: int,
    valor: Path | str,
) -> None:
    """Llama a ``on_item`` con la ruta generada o el mensaje de error."""
    if callback is None:
        return
    try:
        callback(numero, valor)
    except Exception:  # igual que arriba: un callback roto no aborta el lote
        pass


def _semilla(seed: int | None) -> int:
    """Normaliza la seed a un entero sin signo de 64 bits (el rango de ComfyUI)."""
    try:
        numero = int(seed)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        try:
            numero = int(float(str(seed).strip()))
        except (TypeError, ValueError):
            raise ComfyUIError(
                f"Seed inválida: {seed!r}. Debe ser un número entero (por ejemplo 123456)."
            ) from exc
    return numero & 0xFFFFFFFFFFFFFFFF


def _entero(valor: Any, nombre: str, *, minimo: int, maximo: int) -> int:
    """Convierte a entero dentro de un rango; si no se puede, error claro."""
    try:
        numero = int(float(str(valor).strip()))
    except (TypeError, ValueError) as exc:
        raise ComfyUIError(f"Valor inválido para {nombre}: {valor!r}. Debe ser un número.") from exc
    return max(minimo, min(maximo, numero))


def _dimension(valor: Any, nombre: str) -> int:
    """Ancho/alto válido para SDXL: entre 64 y 4096 y múltiplo de 8."""
    numero = _entero(valor, nombre, minimo=64, maximo=4096)
    # Los modelos de difusión trabajan con múltiplos de 8; redondeamos hacia abajo
    # para no inventar píxeles que el modelo no sabe manejar.
    return max(64, (numero // 8) * 8)


def _cfg(valor: Any) -> float:
    """CFG (fuerza de obediencia al prompt) como número finito y razonable."""
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ComfyUIError(f"CFG inválido: {valor!r}. Debe ser un número.") from exc
    if not math.isfinite(numero):
        raise ComfyUIError(f"CFG inválido: {valor!r}. Debe ser un número finito.")
    return max(0.0, min(100.0, numero))


def _slug(texto: str, maximo: int = 48) -> str:
    """Convierte un texto libre en un trozo de nombre de archivo seguro.

    Quita acentos, deja solo letras/números y une las palabras con guiones.
    Así el nombre funciona igual en Windows, macOS y Linux.
    """
    limpio = unicodedata.normalize("NFKD", str(texto or ""))
    limpio = limpio.encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", limpio).strip("-").lower()
    return (limpio[:maximo].strip("-") or "imagen") if limpio else "imagen"


def _nombre_seguro(nombre: str, defecto: str = "imagen.png") -> str:
    """Quita caracteres prohibidos por Windows de un nombre de archivo."""
    limpio = _CARACTERES_INVALIDOS.sub("_", str(nombre or "")).strip().strip(".")
    return limpio or defecto


# ===========================================================================
# 1) Disponibilidad y checkpoints
# ===========================================================================
def disponible(url: str | None = None, timeout: float = 3.0) -> bool:
    """¿Hay un ComfyUI vivo en esa URL?

    Pregunta ``GET {url}/system_stats`` y considera que está disponible si
    responde 200. Nunca lanza excepción: devuelve ``False`` ante cualquier fallo.
    """
    base = _url_base(url)
    try:
        respuesta = requests.get(f"{base}/system_stats", timeout=timeout)
    except (requests.RequestException, ValueError):
        return False
    return respuesta.status_code == 200


def listar_checkpoints() -> list[str]:
    """Devuelve los modelos (.safetensors/.ckpt) que ComfyUI tiene instalados.

    Pregunta al nodo ``CheckpointLoaderSimple`` cuáles son sus opciones válidas.
    Si ComfyUI no responde o devuelve algo raro, lanza :class:`ComfyUIError`.
    """
    respuesta = _peticion("GET", "/object_info/CheckpointLoaderSimple", timeout=TIMEOUT_CORTO)
    if not respuesta.ok:
        raise _error_http(respuesta, "No se pudo leer la lista de checkpoints de ComfyUI")

    datos = _json_de(respuesta, "GET /object_info/CheckpointLoaderSimple")

    # Ruta exacta dentro de la respuesta de ComfyUI:
    # {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [[...], {...}]}}}}
    try:
        opciones = datos["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ComfyUIError(
            "ComfyUI respondió, pero no encontré la lista de checkpoints. "
            "¿Es una versión distinta o el nodo CheckpointLoaderSimple no está disponible?"
        ) from exc

    if not isinstance(opciones, list):
        raise ComfyUIError(
            "La lista de checkpoints que devolvió ComfyUI tiene un formato inesperado."
        )
    return [str(opcion) for opcion in opciones if str(opcion).strip()]


def _resolver_checkpoint(checkpoint: str | None) -> str:
    """Elige el checkpoint: parámetro -> configuración -> primero instalado -> error."""
    elegido = (checkpoint or "").strip() or settings.comfyui_checkpoint.strip()
    if elegido:
        return elegido

    instalados = listar_checkpoints()
    if not instalados:
        raise ComfyUIError(
            "No hay checkpoints instalados en ComfyUI. Copia un modelo "
            "(.safetensors o .ckpt) en ComfyUI/models/checkpoints, reinicia ComfyUI "
            "y vuelve a intentarlo; o define COMFYUI_CHECKPOINT en el archivo .env."
        )
    return instalados[0]


# ===========================================================================
# 2) Workflow (formato API de ComfyUI)
# ===========================================================================
def construir_workflow(
    prompt: str,
    negative: str = "",
    seed: int = 1,
    checkpoint: str | None = None,
    width: int = 1024,
    height: int = 576,
    steps: int = 20,
    cfg: float = 6.5,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    prefijo: str = "ytagent",
    lora: str | None = None,
    fuerza_lora: float = 1.0,
) -> dict[str, Any]:
    """Arma el workflow en el formato **API** de ComfyUI (el que acepta ``/prompt``).

    El formato API es un diccionario con IDs de nodo como texto ("1", "2", ...),
    cada nodo con ``class_type`` e ``inputs``. Los cables entre nodos se
    representan así: ``["ID_del_nodo_origen", indice_de_salida]``.

    Nodos que se crean:

    =====  =========================  =========================================
    Nodo   Clase                      Función
    =====  =========================  =========================================
    "1"    CheckpointLoaderSimple     carga el modelo + CLIP + VAE
    "2"    CLIPTextEncode             el prompt POSITIVO (lo que queremos ver)
    "3"    CLIPTextEncode             el prompt NEGATIVO (lo que NO queremos)
    "4"    EmptyLatentImage           el lienzo vacío (ancho x alto, 16:9)
    "5"    KSampler                   el "horno": convierte ruido en imagen
    "6"    VAEDecode                  pasa el resultado del modelo a píxeles
    "7"    SaveImage                  guarda el PNG en la carpeta output de ComfyUI
    "8"    LoraLoader                 (opcional) acelerador o estilo LoRA
    =====  =========================  =========================================

    Args:
        prompt: lo que debe aparecer en la imagen (en inglés funciona mejor).
        negative: lo que NO debe aparecer (texto, logos, manos deformadas...).
        seed: semilla; con la misma seed y los mismos ajustes sale la misma imagen.
        checkpoint: nombre exacto del modelo. Si está vacío usa
            ``settings.comfyui_checkpoint`` y, si tampoco hay, el primero instalado.
        width, height: tamaño del lienzo (por defecto 1024x576, 16:9).
        steps: pasos de muestreo (20 es un buen equilibrio en una RTX 4060 8 GB).
        cfg: escala de guiado (6.5 es lo habitual para SDXL).
        sampler: algoritmo de muestreo de ComfyUI.
        scheduler: planificador de ruido.
        prefijo: prefijo de los archivos que guardará ComfyUI.
        lora: nombre del archivo LoRA (por ejemplo ``sdxl_lightning_4step_lora.safetensors``).
            Si se indica, se inserta un nodo LoraLoader entre el checkpoint y el
            resto. Con el LoRA Lightning se recomienda ``steps=4, cfg=1.5``.
        fuerza_lora: intensidad del LoRA (1.0 = la recomendada por el autor).

    Raises:
        ComfyUIError: si no hay prompt, si el checkpoint no se puede resolver o si
            algún valor numérico es inválido.
    """
    texto_positivo = str(prompt or "").strip()
    if not texto_positivo:
        raise ComfyUIError(
            "El prompt de la imagen está vacío. Escribe una descripción antes de generar."
        )

    modelo = _resolver_checkpoint(checkpoint)
    usar_lora = bool(lora and str(lora).strip())

    # Si hay LoRA, el modelo y el CLIP salen del nodo 8; si no, del checkpoint (1).
    origen_modelo: list[Any] = ["1", 0]
    origen_clip: list[Any] = ["1", 1]

    workflow: dict[str, Any] = {
        # Nodo 1: carga el checkpoint. Salidas: [0]=MODEL, [1]=CLIP, [2]=VAE.
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": modelo},
        },
    }

    if usar_lora:
        # Nodo 8: aplica el LoRA sobre el modelo y el CLIP del checkpoint.
        # Salidas: [0]=MODEL con LoRA, [1]=CLIP con LoRA.
        workflow["8"] = {
            "class_type": "LoraLoader",
            "inputs": {
                "lora_name": str(lora).strip(),
                "strength_model": float(fuerza_lora),
                "strength_clip": float(fuerza_lora),
                "model": ["1", 0],
                "clip": ["1", 1],
            },
        }
        origen_modelo = ["8", 0]
        origen_clip = ["8", 1]

    workflow.update(
        {
            # Nodo 2: prompt positivo.
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": texto_positivo, "clip": origen_clip},
            },
            # Nodo 3: prompt negativo.
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": str(negative or ""), "clip": origen_clip},
            },
            # Nodo 4: lienzo vacío del tamaño pedido (una sola imagen por trabajo).
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": _dimension(width, "width"),
                    "height": _dimension(height, "height"),
                    "batch_size": 1,
                },
            },
            # Nodo 5: muestreador. model viene del checkpoint (o del LoRA), los
            # prompts de los nodos 2/3 y el lienzo vacío del nodo 4.
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": _semilla(seed),
                    "steps": _entero(steps, "steps", minimo=1, maximo=150),
                    "cfg": _cfg(cfg),
                    "sampler_name": str(sampler or "dpmpp_2m"),
                    "scheduler": str(scheduler or "karras"),
                    "denoise": 1.0,
                    "model": origen_modelo,
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            # Nodo 6: decodifica el latent a imagen usando el VAE del nodo 1 (salida 2).
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            # Nodo 7: guarda el resultado. La salida de VAEDecode es la 0.
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": str(prefijo or PREFIJO_POR_DEFECTO),
                    "images": ["6", 0],
                },
            },
        }
    )
    return workflow


# ===========================================================================
# 3) Cola y espera
# ===========================================================================
def encolar(
    workflow: dict[str, Any],
    url: str | None = None,
    client_id: str | None = None,
) -> str:
    """Envía el workflow a la cola de ComfyUI y devuelve su ``prompt_id``.

    Si ComfyUI rechaza el workflow (por ejemplo, un checkpoint que no existe),
    el error incluye el texto de ``node_errors`` para saber qué nodo falló.
    """
    if not isinstance(workflow, dict) or not workflow:
        raise ComfyUIError(
            "El workflow está vacío o no es un diccionario. "
            "Créalo con construir_workflow() antes de encolarlo."
        )

    # ComfyUI usa el client_id para agrupar trabajos de un mismo cliente; si no
    # nos dan uno, inventamos uno para que la cola y el historial sean coherentes.
    identificador = client_id or uuid.uuid4().hex
    carga = {"prompt": workflow, "client_id": identificador}

    respuesta = _peticion("POST", "/prompt", url=url, json=carga, timeout=TIMEOUT_ENVIO)
    if not respuesta.ok:
        raise _error_http(respuesta, "ComfyUI rechazó el workflow")

    datos = _json_de(respuesta, "POST /prompt")
    prompt_id = datos.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ComfyUIError(
            "ComfyUI aceptó el envío pero no devolvió 'prompt_id'. "
            f"Respuesta recibida: {str(datos)[:300]}"
        )
    return prompt_id


def _ids_cola(cola: Any) -> list[str]:
    """Extrae los prompt_id de las listas ``queue_running`` / ``queue_pending``."""
    if not isinstance(cola, list):
        return []
    ids: list[str] = []
    for elemento in cola:
        if isinstance(elemento, (list, tuple)) and len(elemento) > 1:
            ids.append(str(elemento[1]))
        elif isinstance(elemento, dict) and elemento.get("prompt_id"):
            ids.append(str(elemento["prompt_id"]))
    return ids


def _aviso_cola(prompt_id: str, base: str) -> str | None:
    """Texto de progreso basado en GET /queue ("cola: 2 delante", etc.)."""
    try:
        respuesta = _peticion("GET", "/queue", url=base, timeout=5.0)
        if not respuesta.ok:
            return None
        datos = _json_de(respuesta, "GET /queue")
    except ComfyUIError:
        # El aviso es solo informativo: si falla, no interrumpimos la espera.
        return None

    ejecutando = _ids_cola(datos.get("queue_running"))
    pendientes = _ids_cola(datos.get("queue_pending"))
    if prompt_id in ejecutando:
        return "generando la imagen..."
    if prompt_id in pendientes:
        delante = len(ejecutando) + pendientes.index(prompt_id)
        return f"cola: {delante} delante"
    return "esperando a ComfyUI..."


def _detalle_mensajes(mensajes: Any) -> str:
    """Resume los mensajes de estado del historial de ComfyUI."""
    if not isinstance(mensajes, list):
        return ""
    partes: list[str] = []
    for mensaje in mensajes:
        if not isinstance(mensaje, (list, tuple)) or not mensaje:
            continue
        tipo = str(mensaje[0])
        datos = mensaje[1] if len(mensaje) > 1 else None
        if tipo == "execution_error":
            if isinstance(datos, dict):
                nodo = datos.get("node_type") or datos.get("node_id") or "?"
                detalle = (
                    datos.get("exception_message")
                    or datos.get("exception_type")
                    or "error sin mensaje"
                )
                partes.append(f"{nodo}: {str(detalle).strip()}")
            else:
                partes.append("error de ejecución en ComfyUI")
        elif tipo == "execution_interrupted":
            partes.append("la ejecución se interrumpió (¿cancelaste en ComfyUI?)")
        # Los mensajes de inicio/éxito/caché no aportan nada al usuario.
    return " | ".join(partes)


def _comprobar_estado(entrada: dict[str, Any]) -> None:
    """Mira el bloque ``status`` del historial y lanza error si la ejecución falló."""
    estado = entrada.get("status")
    if not isinstance(estado, dict):
        return
    status_str = str(estado.get("status_str") or "")
    completado = estado.get("completed")
    mensajes = estado.get("messages")
    if status_str == "error" or (completado is False and mensajes):
        detalle = _detalle_mensajes(mensajes) or status_str or "error desconocido de ComfyUI"
        raise ComfyUIError(
            f"ComfyUI falló al generar la imagen: {detalle}. "
            "Revisa la consola/ventana de ComfyUI para ver el detalle completo."
        )


def _outputs_de_historial(entrada: dict[str, Any]) -> list[dict[str, str]]:
    """Saca de una entrada de /history la lista plana de imágenes generadas."""
    _comprobar_estado(entrada)

    salidas = entrada.get("outputs")
    imagenes: list[dict[str, str]] = []
    if isinstance(salidas, dict):
        for salida in salidas.values():
            if not isinstance(salida, dict):
                continue
            # SaveImage publica "images"; algunos nodos de vídeo publican "gifs".
            for clave in ("images", "gifs"):
                lista = salida.get(clave)
                if not isinstance(lista, list):
                    continue
                for imagen in lista:
                    if not isinstance(imagen, dict):
                        continue
                    nombre = str(imagen.get("filename") or "").strip()
                    if not nombre:
                        continue
                    imagenes.append(
                        {
                            "filename": nombre,
                            "subfolder": str(imagen.get("subfolder") or ""),
                            "type": str(imagen.get("type") or "output"),
                        }
                    )

    if not imagenes:
        raise ComfyUIError(
            "ComfyUI terminó el trabajo pero no devolvió ninguna imagen. "
            "Revisa que el workflow tenga un nodo SaveImage conectado a VAEDecode."
        )
    return imagenes


def esperar_resultado(
    prompt_id: str,
    url: str | None = None,
    timeout: float = 300.0,
    intervalo: float = 1.0,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    """Espera a que ComfyUI termine y devuelve las imágenes del historial.

    Va preguntando ``GET /history/{prompt_id}`` cada ``intervalo`` segundos.
    Mientras espera, consulta ``GET /queue`` y avisa por ``on_progress``
    (por ejemplo ``"cola: 2 delante"``). Devuelve una lista de diccionarios con
    ``filename``, ``subfolder`` y ``type``.

    Raises:
        ComfyUIError: si hay timeout, si se pierde la conexión varias veces
            seguidas o si ComfyUI terminó con error.
    """
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise ComfyUIError("Falta el prompt_id del trabajo de ComfyUI.")

    base = _url_base(url)
    try:
        limite = float(timeout)
    except (TypeError, ValueError) as exc:
        raise ComfyUIError(f"Timeout inválido: {timeout!r}. Debe ser un número de segundos.") from exc
    if limite <= 0:
        raise ComfyUIError("El timeout de espera debe ser mayor que 0 segundos.")

    try:
        pausa = max(0.05, float(intervalo))
    except (TypeError, ValueError):
        pausa = 1.0

    inicio = time.monotonic()
    fallos_seguidos = 0
    ultimo_aviso = ""

    while True:
        transcurrido = time.monotonic() - inicio
        if transcurrido > limite:
            raise ComfyUIError(
                f"Se agotó el tiempo de espera ({limite:.0f} s) para el trabajo {prompt_id}. "
                "ComfyUI puede seguir generando: revisa su ventana o baja steps/resolución."
            )

        try:
            respuesta = _peticion(
                "GET", f"/history/{prompt_id}", url=base, timeout=TIMEOUT_CORTO
            )
            if not respuesta.ok:
                raise _error_http(
                    respuesta,
                    f"No se pudo consultar el historial de ComfyUI para {prompt_id}",
                )
            datos = _json_de(respuesta, f"GET /history/{prompt_id}")
        except ComfyUIError:
            # Un fallo puntual no importa; tres seguidos sí (servidor caído).
            fallos_seguidos += 1
            if fallos_seguidos >= 3:
                raise
        else:
            fallos_seguidos = 0
            entrada = datos.get(prompt_id)
            if isinstance(entrada, dict):
                return _outputs_de_historial(entrada)

            # Todavía no está en el historial: informamos de la posición en la cola.
            aviso = _aviso_cola(prompt_id, base)
            if aviso and aviso != ultimo_aviso:
                ultimo_aviso = aviso
                _notificar(on_progress, aviso)

        restante = limite - (time.monotonic() - inicio)
        if restante <= 0:
            continue  # la comprobación del principio lanzará el timeout
        time.sleep(min(pausa, restante))


# ===========================================================================
# 4) Descarga
# ===========================================================================
def descargar_imagen(
    filename: str,
    subfolder: str = "",
    url: str | None = None,
) -> bytes:
    """Descarga un archivo generado con ``GET {url}/view`` y devuelve sus bytes."""
    if not str(filename or "").strip():
        raise ComfyUIError("Falta el nombre de archivo de la imagen a descargar.")

    params = {
        "filename": str(filename),
        "subfolder": str(subfolder or ""),
        "type": "output",
    }
    respuesta = _peticion(
        "GET", "/view", url=url, params=params, timeout=TIMEOUT_DESCARGA
    )
    if not respuesta.ok:
        raise _error_http(respuesta, f"No se pudo descargar la imagen {filename}")

    contenido = respuesta.content
    if not contenido:
        raise ComfyUIError(
            f"ComfyUI devolvió la imagen {filename} vacía. Revisa la carpeta de salida de ComfyUI."
        )
    # ComfyUI a veces responde con una página/JSON de error y código 200.
    if not (
        contenido.startswith(b"\x89PNG")
        or contenido.startswith(b"\xff\xd8")
        or contenido.startswith(b"RIFF")
    ):
        raise ComfyUIError(
            f"El archivo {filename} no parece una imagen válida "
            "(¿ComfyUI devolvió una página de error?)."
        )
    return contenido


# ===========================================================================
# 5) Flujo completo
# ===========================================================================
def generar_imagen(
    prompt: str,
    negative: str = "",
    seed: int | None = None,
    checkpoint: str | None = None,
    width: int = 1024,
    height: int = 576,
    destino: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
    steps: int = 20,
    cfg: float = 6.5,
    sampler: str = "dpmpp_2m",
    scheduler: str = "karras",
    lora: str | None = None,
    fuerza_lora: float = 1.0,
) -> Path:
    """Genera UNA imagen de principio a fin y devuelve la ruta del PNG guardado.

    Flujo: workflow -> encolar -> esperar -> descargar -> guardar.

    Args:
        prompt: descripción de la imagen (en inglés funciona mejor).
        negative: lo que no queremos que salga.
        seed: semilla fija para reproducir; ``None`` genera una al azar.
        checkpoint: modelo a usar; ``None``/vacío usa el configurado o el primero.
        width, height: tamaño del lienzo (1024x576 = 16:9).
        destino: ruta del archivo, o una carpeta donde guardarlo. Si es ``None``,
            se guarda en ``IMAGES_DIR`` con un nombre ``ytagent_seed_archivo.png``.
        on_progress: callback de texto para que la UI muestre el avance.
        steps, cfg, sampler, scheduler: ajustes del muestreador. Con el LoRA
            Lightning usa ``steps=4, cfg=1.5, sampler="euler"``.
        lora: archivo LoRA opcional (acelerador o estilo).
        fuerza_lora: intensidad del LoRA.

    Returns:
        La ruta del PNG guardado.
    """
    semilla = random.randint(0, 2**32 - 1) if seed is None else _semilla(seed)
    _notificar(on_progress, f"preparando workflow (seed {semilla})...")

    workflow = construir_workflow(
        prompt=prompt,
        negative=negative,
        seed=semilla,
        checkpoint=checkpoint,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        sampler=sampler,
        scheduler=scheduler,
        lora=lora,
        fuerza_lora=fuerza_lora,
    )

    _notificar(on_progress, "enviando el trabajo a la cola de ComfyUI...")
    prompt_id = encolar(workflow)
    _notificar(on_progress, f"trabajo aceptado (id {prompt_id[:8]}), esperando...")

    salidas = esperar_resultado(prompt_id, on_progress=on_progress)
    primera = salidas[0]
    _notificar(on_progress, f"descargando {primera['filename']}...")
    contenido = descargar_imagen(primera["filename"], primera["subfolder"])

    # Resolver el destino: ruta exacta o carpeta (o la carpeta por defecto).
    destino_path = Path(destino) if destino is not None else None
    if destino_path is None:
        carpeta = IMAGES_DIR
        nombre = f"{PREFIJO_POR_DEFECTO}_{semilla}_{primera['filename']}"
        ruta = carpeta / _nombre_seguro(nombre)
    elif (destino_path.exists() and destino_path.is_dir()) or destino_path.suffix == "":
        ruta = destino_path / _nombre_seguro(
            f"{PREFIJO_POR_DEFECTO}_{semilla}_{primera['filename']}"
        )
    else:
        ruta = destino_path

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    _notificar(on_progress, f"imagen guardada en {ruta}")
    return ruta


# ===========================================================================
# 6) Lotes
# ===========================================================================
def _datos_item(item: Any, indice: int) -> dict[str, Any]:
    """Normaliza un dict de BD o un ``ImagePrompt`` a un diccionario simple."""
    if isinstance(item, ImagePrompt):
        numero = item.numero or indice
        return {
            "id": numero,
            "numero": numero,
            "prompt": item.prompt,
            "negative": item.negative,
            "seed": item.seed,
            "width": item.width,
            "height": item.height,
        }

    if isinstance(item, dict):
        numero = item.get("numero", item.get("scene_numero", indice))
        try:
            numero = int(numero)
        except (TypeError, ValueError):
            numero = indice
        if numero <= 0:
            numero = indice
        return {
            "id": item.get("id", numero),
            "numero": numero,
            "prompt": item.get("prompt", ""),
            "negative": item.get("negative", "") or "",
            "seed": item.get("seed"),
            "width": item.get("width") or 1024,
            "height": item.get("height") or 576,
        }

    raise ComfyUIError(
        f"El elemento {indice} del lote no es un diccionario ni un ImagePrompt "
        f"(es {type(item).__name__})."
    )


def procesar_lote(
    prompts: list[Any],
    salida: Path | None = None,
    on_item: Callable[[int, Path | str], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    cancelar: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """Genera una imagen por elemento, una detrás de otra, sin abortar por fallos.

    Acepta filas de la base de datos (dicts con ``id``, ``numero``, ``prompt``,
    ``negative``, ``seed``) o modelos :class:`ImagePrompt`.

    Args:
        prompts: lista de elementos a generar.
        salida: carpeta donde guardar los PNG. Si es ``None``, ``IMAGES_DIR``.
        on_item: callback ``(numero, ruta_o_error)`` tras cada imagen; si falló,
            recibe el mensaje de error como texto.
        on_progress: callback de texto para la UI.
        cancelar: función que devuelve ``True`` para parar el lote limpiamente.

    Returns:
        Lista de resultados::

            [{"id": 1, "numero": 1, "ok": True, "imagen": "...", "error": ""}]
    """
    elementos = list(prompts or [])
    total = len(elementos)
    carpeta = Path(salida) if salida is not None else None
    if carpeta is not None:
        carpeta.mkdir(parents=True, exist_ok=True)

    resultados: list[dict[str, Any]] = []

    for indice, elemento in enumerate(elementos, start=1):
        # 1) ¿El usuario pidió cancelar? Paramos sin romper nada.
        if cancelar is not None and cancelar():
            break

        # 2) Normalizar la fila a un formato único.
        try:
            datos = _datos_item(elemento, indice)
        except ComfyUIError as exc:
            resultados.append(
                {
                    "id": indice,
                    "numero": indice,
                    "ok": False,
                    "imagen": "",
                    "error": str(exc),
                }
            )
            _notificar_item(on_item, indice, str(exc))
            continue

        numero = datos["numero"]
        _notificar(on_progress, f"imagen {indice}/{total} (numero {numero})...")

        # 3) Nombre de archivo seguro si nos dieron una carpeta de salida.
        destino: Path | None = None
        if carpeta is not None:
            nombre = f"{numero:03d}_{_slug(datos['prompt'])}.png"
            destino = carpeta / _nombre_seguro(nombre)

        # Callback de progreso con el índice del lote delante (se fija con
        # valores por defecto para no capturar variables del bucle).
        def avisar(mensaje: str, _i: int = indice, _n: int = total) -> None:
            _notificar(on_progress, f"imagen {_i}/{_n}: {mensaje}")

        # 4) Generar. Cualquier fallo se anota y se sigue con la siguiente.
        try:
            ruta = generar_imagen(
                prompt=datos["prompt"],
                negative=datos["negative"],
                seed=datos["seed"],
                width=datos["width"],
                height=datos["height"],
                destino=destino,
                on_progress=avisar,
            )
        except Exception as exc:  # una imagen rota no debe tumbar todo el lote
            error = f"{type(exc).__name__}: {exc}"
            resultados.append(
                {
                    "id": datos["id"],
                    "numero": numero,
                    "ok": False,
                    "imagen": "",
                    "error": error,
                }
            )
            _notificar_item(on_item, numero, error)
            continue

        resultados.append(
            {
                "id": datos["id"],
                "numero": numero,
                "ok": True,
                "imagen": str(ruta),
                "error": "",
            }
        )
        _notificar_item(on_item, numero, ruta)

    return resultados


# ===========================================================================
# 7) Diagnóstico para la interfaz
# ===========================================================================
def diagnostico() -> dict[str, Any]:
    """Foto del estado de ComfyUI para que la UI lo muestre. Nunca lanza excepción.

    Returns:
        ``{"disponible": bool, "url": str, "checkpoints": [...],
        "checkpoint_actual": str, "error": str}``
    """
    estado: dict[str, Any] = {
        "disponible": False,
        "url": settings.comfyui_url,
        "checkpoints": [],
        "checkpoint_actual": settings.comfyui_checkpoint,
        "error": "",
    }
    try:
        base = _url_base()
        estado["url"] = base

        if not disponible(base):
            estado["error"] = (
                f"No se pudo conectar con ComfyUI en {base}. "
                "Abre ComfyUI (o revisa COMFYUI_URL en el archivo .env)."
            )
            return estado

        estado["disponible"] = True
        try:
            modelos = listar_checkpoints()
        except ComfyUIError as exc:
            estado["error"] = str(exc)
            return estado

        estado["checkpoints"] = modelos
        configurado = settings.comfyui_checkpoint.strip()
        if configurado:
            estado["checkpoint_actual"] = configurado
            if modelos and configurado not in modelos:
                estado["error"] = (
                    f"El checkpoint configurado '{configurado}' no está instalado en ComfyUI. "
                    f"Disponibles: {', '.join(modelos)}."
                )
        elif modelos:
            estado["checkpoint_actual"] = modelos[0]
        else:
            estado["error"] = (
                "ComfyUI responde, pero no hay checkpoints instalados. "
                "Copia un modelo en ComfyUI/models/checkpoints."
            )
        return estado
    except Exception as exc:  # el diagnóstico jamás debe tumbar la interfaz
        estado["error"] = f"Error inesperado al diagnosticar ComfyUI: {exc}"
        return estado
