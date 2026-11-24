"""Conexión con la IA de texto (DeepSeek) y modo demo.

La idea central de este archivo es la **interfaz** `LLMBase`:
el resto del proyecto solo llama métodos como `generar_ideas(...)` y no le
importa si detrás está DeepSeek (internet) o el modo demo (sin internet).

Así, cuando el día de mañana quieras usar OpenAI, Claude u Ollama,
solo escribes otra clase que herede de `LLMBase` y **no tocas nada más**.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from . import prompts as P
from .config import settings
from .schemas import Idea, ImagePrompt, Scene, Script, Usage, VideoMetadata

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


class LLMError(RuntimeError):
    """Error de la IA (clave inválida, sin internet, respuesta rota...)."""


def extraer_json(texto: str) -> dict[str, Any]:
    """Saca el JSON de una respuesta que puede venir con ```json ... ``` o texto extra.

    Los modelos a veces "decoran" su respuesta. Esta función tolera eso.
    Siempre devuelve un dict (si la IA devuelve una lista, la envuelve).
    """
    limpio = texto.strip()

    # Quita bloques de markdown ```json
    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)

    if not limpio:
        raise LLMError("La IA devolvió una respuesta vacía (posiblemente el JSON se cortó).")

    try:
        objeto = json.loads(limpio)
        return _envolver(objeto)
    except json.JSONDecodeError:
        pass

    # Busca el objeto JSON más externo {...} o [...]
    inicio = min(
        (i for i in (limpio.find("{"), limpio.find("[")) if i != -1),
        default=-1,
    )
    if inicio != -1:
        # Primer intento: probar desde el final hacia atrás (el caso completo)
        for fin in range(len(limpio), inicio, -1):
            trozo = limpio[inicio:fin]
            try:
                return _envolver(json.loads(trozo))
            except json.JSONDecodeError:
                continue

        # Segundo intento: el JSON se cortó a mitad. Intentamos "curarlo"
        # cerrando la última estructura abierta (típico en respuestas largas).
        curado = _cerrar_json_incompleto(limpio[inicio:])
        if curado is not None:
            return curado

    raise LLMError(f"La IA no devolvió un JSON válido. Respuesta: {texto[:300]}...")


def _envolver(objeto: Any) -> dict[str, Any]:
    """Normaliza la respuesta: si es una lista suelta, la mete en un dict."""
    if isinstance(objeto, dict):
        return objeto
    if isinstance(objeto, list):
        return {"ideas": objeto, "prompts": objeto, "items": objeto}
    raise LLMError(f"La IA devolvió un JSON válido pero no es un objeto: {str(objeto)[:120]}")


def _cerrar(recortado: str) -> str | None:
    """Cierra las llaves/corchetes que falten en un trozo de JSON."""
    pila: list[str] = []
    dentro_string = False
    escape = False
    for ch in recortado:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            dentro_string = not dentro_string
            continue
        if dentro_string:
            continue
        if ch in "{[":
            pila.append(ch)
        elif ch in "}]" and pila:
            pila.pop()
    if not pila:
        return None
    return recortado + "".join("}" if c == "{" else "]" for c in reversed(pila))


def _cerrar_json_incompleto(trozo: str) -> dict[str, Any] | None:
    """Arregla un JSON truncado, por ejemplo cortado a mitad de una clave.

    Estrategia (de más conservadora a más agresiva):
      1. Cerrar la estructura general tal cual está.
      2. Si falla, quitar el último elemento incompleto (desde la última coma)
         y cerrar la estructura. Así se conserva todo lo que sí llegó completo.
    """
    recortado = trozo.rstrip()
    if recortado.endswith(","):
        recortado = recortado[:-1]

    candidatos: list[str] = []

    # Intento 1: tal cual
    base = recortado
    if base.count('"') % 2 == 1:
        base += '"'
    candidatos.append(base)

    # Intento 2: quitar el último elemento a medias (corte dentro de una clave/valor)
    ultima_coma = recortado.rfind(",")
    if ultima_coma > 0:
        recortado2 = recortado[:ultima_coma]
        if recortado2.count('"') % 2 == 1:
            recortado2 += '"'
        candidatos.append(recortado2)

    # Intento 3: quitar la clave sin valor del final
    sin_clave = re.sub(r',?\s*"[^"]*"\s*:\s*$', "", recortado)
    if sin_clave != recortado:
        if sin_clave.count('"') % 2 == 1:
            sin_clave += '"'
        candidatos.append(sin_clave)

    for candidato in candidatos:
        cerrado = _cerrar(candidato)
        if not cerrado:
            continue
        try:
            return _envolver(json.loads(cerrado))
        except json.JSONDecodeError:
            continue
    return None


def _ruta(diccionario: dict[str, Any], *candidatos: str, default: Any = None) -> Any:
    """Busca el primer alias que exista en el diccionario (por si la IA cambia un nombre)."""
    for c in candidatos:
        if c in diccionario:
            return diccionario[c]
    return default


# ---------------------------------------------------------------------------
# Interfaz común
# ---------------------------------------------------------------------------
class LLMBase(ABC):
    """Contrato que cumplen tanto DeepSeek como el modo demo."""

    def __init__(self) -> None:
        self.usage = Usage()

    @abstractmethod
    def generar_ideas(self, tema: str, n: int, contexto: str = "") -> list[Idea]: ...

    @abstractmethod
    def generar_guion(self, idea: Idea, duracion_min: int = 8, contexto: str = "") -> Script: ...

    @abstractmethod
    def generar_escenas(self, guion: Script, n: int, estilo: str = "") -> list[Scene]: ...

    @abstractmethod
    def generar_prompts(
        self, script: Script, n: int | None = None, estilo: str = ""
    ) -> list[ImagePrompt]: ...

    @abstractmethod
    def generar_metadata(
        self, script: Script, contexto: str = ""
    ) -> VideoMetadata: ...

    @property
    @abstractmethod
    def modo(self) -> str:
        """'deepseek' o 'demo' (se muestra en la interfaz)."""


# ---------------------------------------------------------------------------
# Implementación real: DeepSeek
# ---------------------------------------------------------------------------
class DeepSeekLLM(LLMBase):
    """Cliente de la API de DeepSeek (compatible con el formato de OpenAI)."""

    def __init__(self) -> None:
        super().__init__()
        if not settings.deepseek_api_key:
            raise LLMError("Falta DEEPSEEK_API_KEY en el archivo .env")
        self.url = f"{settings.deepseek_base_url}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    @property
    def modo(self) -> str:
        return f"deepseek/{settings.deepseek_model}"

    # -- método de bajo nivel ------------------------------------------------
    def _llamar(
        self,
        system: str,
        user: str,
        *,
        temperaturas: tuple[float, ...] = (),
        max_tokens: int | None = None,
        intentos: int = 3,
    ) -> dict[str, Any]:
        """Llama a la API y devuelve el JSON ya parseado, con reintentos."""
        if not temperaturas:
            temperaturas = (settings.temperature, 0.7, 0.3)

        ultimo_error: Exception | None = None
        for intento, temperatura in enumerate(temperaturas, start=1):
            payload = {
                "model": settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperatura,
                "max_tokens": max_tokens or settings.max_tokens,
                "response_format": {"type": "json_object"},
                "stream": False,
            }
            try:
                r = requests.post(
                    self.url, headers=self.headers, json=payload, timeout=settings.request_timeout
                )

                if r.status_code == 401:
                    raise LLMError("La clave de DeepSeek no es válida o caducó (revisa .env)")
                if r.status_code == 429:
                    raise requests.HTTPError("429 límite de peticiones")
                if r.status_code >= 500:
                    raise requests.HTTPError(f"{r.status_code} error del servidor")
                if r.status_code != 200:
                    raise LLMError(f"DeepSeek respondió {r.status_code}: {r.text[:300]}")

                data = r.json()

                # Acumula uso de tokens
                uso = data.get("usage", {})
                self.usage = self.usage.add(
                    Usage(
                        prompt_tokens=uso.get("prompt_tokens", 0),
                        completion_tokens=uso.get("completion_tokens", 0),
                        total_tokens=uso.get("total_tokens", 0),
                        llamadas=1,
                    )
                )

                contenido = data["choices"][0]["message"]["content"]
                return extraer_json(contenido)

            except LLMError:
                # Error de negocio (clave inválida, JSON vacío...) -> no reintentar
                raise
            except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
                ultimo_error = exc
                if intento < len(temperaturas):
                    espera = 2 ** intento  # 2s, 4s...
                    print(f"  [reintento {intento}/{len(temperaturas)}] {exc} (espero {espera}s)")
                    time.sleep(espera)

        raise LLMError(f"No pude obtener respuesta de DeepSeek: {ultimo_error}")

    # -- métodos de alto nivel ----------------------------------------------
    def generar_ideas(self, tema: str, n: int, contexto: str = "") -> list[Idea]:
        user = P.render(
            P.IDEAS,
            n=n,
            tema=tema,
            contexto=contexto or "canal de historias narradas cinematográficas",
            estilo=P.ESTILO_NARRATIVO,
        )
        data = self._llamar("Eres un guionista de YouTube experto.", user)
        crudos = _ruta(data, "ideas", "items", default=[]) or []
        ideas = []
        for c in crudos[:n]:
            try:
                ideas.append(Idea.model_validate(c))
            except Exception as exc:  # una idea rota no debe tumbar el lote
                print(f"  [aviso] idea descartada: {exc}")
        if not ideas:
            raise LLMError("La IA no devolvió ideas válidas.")
        return ideas

    def generar_guion(self, idea: Idea, duracion_min: int = 8, contexto: str = "") -> Script:
        """Paso A: escribe el texto que se locuta. (Paso B: `generar_escenas`)."""
        # ~130 palabras por minuto de narración
        palabras = int(duracion_min * 130)
        user = P.render(
            P.GUION_TEXTO,
            titulo=idea.titulo,
            premisa=idea.premisa,
            hook=idea.hook,
            angulo=idea.angulo or "sin ángulo definido",
            final=idea.final or "sorprendente y coherente",
            duracion=duracion_min,
            palabras=palabras,
            contexto=contexto or "canal de historias narradas cinematográficas",
            estilo=P.ESTILO_NARRATIVO,
        )
        data = self._llamar("Eres un guionista de YouTube experto en retención.", user)
        # "clímax" puede venir sin tilde
        data.setdefault("clímax", data.get("climax", ""))
        # Rellenamos campos del molde que este paso no pide (escenas se añaden después)
        data.setdefault("escenas", [])
        script = Script.model_validate(data)
        if not script.desarrollo:
            raise LLMError("El guion llegó sin bloques de desarrollo.")
        return script

    def generar_escenas(self, guion: Script, n: int, estilo: str = "") -> list[Scene]:
        """Paso B: divide el guion en escenas con prompt de imagen en inglés."""
        estilo = estilo or settings.visual_style
        texto = guion.texto_completo
        # Si el guion es muy largo, recortamos para no reventar el contexto
        if len(texto) > 9000:
            texto = texto[:9000] + " ..."
        user = P.render(P.ESCENAS, n=n, guion=texto, estilo=estilo)
        data = self._llamar("Eres director de fotografía cinematográfica.", user)
        crudos = _ruta(data, "escenas", "scenes", "items", default=[]) or []

        escenas: list[Scene] = []
        for i, c in enumerate(crudos, start=1):
            try:
                escenas.append(
                    Scene.model_validate(
                        {
                            "numero": c.get("numero", i),
                            "duracion_seg": c.get("duracion_seg", 7),
                            "narracion": c.get("narracion", ""),
                            "visual": c.get("visual", ""),
                            "prompt_imagen": c.get("prompt_imagen", c.get("prompt", "")),
                            "nota_edicion": c.get("nota_edicion", ""),
                        }
                    )
                )
            except Exception as exc:
                print(f"  [aviso] escena descartada: {exc}")

        if not escenas:
            raise LLMError("La IA no devolvió escenas válidas.")
        # Renumeramos por si la IA se saltó números
        for i, e in enumerate(escenas, start=1):
            e.numero = i
        return escenas

    def generar_prompts(
        self, script: Script, n: int | None = None, estilo: str = ""
    ) -> list[ImagePrompt]:
        estilo = estilo or settings.visual_style
        guion = "\n".join(
            f"Escena {e.numero} ({e.duracion_seg}s): {e.narracion} | visual: {e.visual}"
            for e in script.escenas
        )
        cantidad = n or len(script.escenas) or 20
        user = P.render(P.PROMPTS_IMAGEN, n=cantidad, estilo=estilo, guion=guion)
        data = self._llamar("Eres director de fotografía cinematográfica.", user)
        crudos = _ruta(data, "prompts", "items", default=[]) or []

        # El estilo lo añadimos nosotros al componer el prompt; nos aseguramos
        # de que la IA no lo haya metido ya (evita duplicados).
        from .image_prompts import quitar_estilo

        resultado: list[ImagePrompt] = []
        for i, c in enumerate(crudos[:cantidad], start=1):
            try:
                item = ImagePrompt.model_validate(
                    {
                        "numero": c.get("numero", i),
                        "scene_numero": c.get("scene_numero", c.get("scene", i)),
                        "prompt": quitar_estilo(c.get("prompt", ""), estilo),
                        "negative": c.get("negative", ""),
                        "seed": c.get("seed"),
                        "width": c.get("width", 1024),
                        "height": c.get("height", 576),
                    }
                )
                if item.prompt.strip():
                    resultado.append(item)
            except Exception as exc:
                print(f"  [aviso] prompt descartado: {exc}")

        if not resultado:
            raise LLMError("La IA no devolvió prompts válidos.")
        return resultado

    def generar_metadata(self, script: Script, contexto: str = "") -> VideoMetadata:
        resumen = script.texto_completo[:2000]
        user = P.render(
            P.METADATA,
            titulo=script.titulo,
            hook=script.hook,
            resumen=resumen,
            contexto=contexto or "canal de historias narradas cinematográficas",
        )
        data = self._llamar("Eres estratega de YouTube experto en CTR y SEO.", user)
        return VideoMetadata.model_validate(data)

    # -- diagnóstico ---------------------------------------------------------
    def probar_conexion(self) -> tuple[bool, str]:
        """Comprueba que la clave funciona. Devuelve (ok, mensaje)."""
        try:
            r = requests.get(
                f"{settings.deepseek_base_url}/models",
                headers=self.headers,
                timeout=20,
            )
            if r.status_code == 200:
                modelos = [m.get("id") for m in r.json().get("data", [])]
                return True, f"Conectado. Modelos disponibles: {', '.join(modelos)}"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as exc:
            return False, f"Sin conexión: {exc}"


# ---------------------------------------------------------------------------
# Implementación demo: sin internet, sin costo
# ---------------------------------------------------------------------------
class DemoLLM(LLMBase):
    """Genera contenido de ejemplo coherente para aprender sin gastar API.

    No es una IA: son plantillas rellenas con datos del tema que pidas.
    Sirve para probar la app completa de punta a punta.
    """

    @property
    def modo(self) -> str:
        return "demo (sin API)"

    def _resumen_tema(self, tema: str) -> str:
        return tema.strip()[:80] or "una historia de camioneros"

    def generar_ideas(self, tema: str, n: int, contexto: str = "") -> list[Idea]:
        base = self._resumen_tema(tema)
        plantillas = [
            (
                "El turno que nadie quería",
                f"A las 3 de la mañana, {base} no encuentra a nadie en la carretera. Y eso es lo raro.",
                f"Un conductor acepta un turno nocturno sobre {base} por el doble de pago. "
                "Lo que descubre en el camino cambia su forma de trabajar para siempre.",
                "Contar la historia solo con lo que el narrador ve por los espejos.",
                "El narrador vuelve a casa y deja la puerta abierta.",
            ),
            (
                "El último viaje del año",
                f"Todo el mundo celebra. {base} sigue en la carretera, solo.",
                "La noche del 31 de diciembre, un conductor acepta el último viaje del año. "
                "El destino es la casa donde creció.",
                "Narrar en presente, con el reloj del tablero marcando la cuenta atrás.",
                "Llega a las 23:59 y no llama a la puerta.",
            ),
            (
                "La regla número uno",
                f"Hay una regla que ningún conductor de {base} rompe. Hoy alguien la rompió.",
                "Un conductor novato ignora la regla más vieja del oficio y provoca una cadena "
                "de consecuencias que llega hasta la oficina central.",
                "Mostrar la regla sin decirla hasta el final.",
                "El novato la entiende solo cuando ya es tarde para él.",
            ),
            (
                "La gasolinera que no aparece",
                f"{base} conoce cada gasolinera de la ruta. Hoy hay una que no está en el mapa.",
                "Un conductor se queda sin combustible y encuentra una estación que no figura "
                "en ninguna aplicación. Al volver, ya no está.",
                "Lo paranormal tratado como algo cotidiano, sin sustos fáciles.",
                "El narrador guarda el recibo y revisa la fecha: es de hace veinte años.",
            ),
            (
                "El pasajero de los 400 kilómetros",
                "Una caja en la cabina. Cuatrocientos kilómetros sin abrirla. Ese es el trabajo.",
                f"Un transportista de {base} acepta llevar un objeto sellado. Lo que transporta "
                "cambia la vida de todos los que se cruzan con su camión.",
                "No revelar nunca el contenido de la caja.",
                "Al entregar la caja, el receptor dice su nombre: es el propio narrador.",
            ),
            (
                "La carretera que se repite",
                f"El mismo camión. El mismo peaje. La misma hora. {base} ya perdió la cuenta.",
                "Un conductor se da cuenta de que lleva horas recorriendo el mismo tramo de "
                "carretera, con los mismos árboles y el mismo coche.",
                "La repetición como forma de contar: misma frase, algo distinto cada vez.",
                "El bucle se rompe cuando el narrador se atreve a parar el camión.",
            ),
            (
                "Lo que dejé en el asiento",
                f"{base} lleva tres meses sin hablar de la caja que dejó en el asiento de atrás.",
                "Un conductor narra lo que encontró en un camión abandonado y por qué decidió "
                "guardarlo en lugar de entregarlo.",
                "El objeto como personaje: la historia gira alrededor de la caja.",
                "El narrador la devuelve, pero nunca dice a quién.",
            ),
            (
                "El CB que no debería sonar",
                f"En el canal 19 alguien lleva toda la noche llamando a {base} por su nombre.",
                "Un conductor conecta su radio vieja y escucha una conversación entre dos "
                "camioneros que dicen estar en el mismo punto de la carretera que él.",
                "Crear tensión con voces y sonido, no con imágenes.",
                "La radio se apaga sola y el nombre que sonaba es el de su padre.",
            ),
        ]
        ideas: list[Idea] = []
        for i in range(min(n, len(plantillas))):
            titulo, hook, premisa, angulo, final = plantillas[i]
            ideas.append(
                Idea(
                    titulo=titulo,
                    hook=hook,
                    premisa=premisa,
                    angulo=angulo,
                    final=final,
                    puntos={"hook": 9 - i % 2, "retencion": 8, "originalidad": 8, "visual": 9},
                    etiquetas=[base, "historia narrada", "carretera", "noche"],
                )
            )
        return ideas

    # Planos de ejemplo (en inglés, como los pediría la IA de verdad)
    VISUALES = [
        "wide establishing shot of a lone semi truck on a desert highway at night, headlights cutting fog",
        "medium shot of a driver's hands gripping the wheel, dashboard glow on his face",
        "close-up of a vintage CB radio crackling with static, red LED display",
        "over-the-shoulder shot through the windshield, empty road stretching to the horizon",
        "drone shot from above, truck headlights carving a line through dark cornfields",
        "interior close-up, coffee cup shaking on the dashboard as the engine idles",
        "wide shot of a lonely gas station under flickering sodium lights, rain falling",
        "side profile of the truck parked at a weigh station, steam rising from the asphalt",
        "macro shot of raindrops on the side mirror reflecting distant red taillights",
        "low angle shot of boots stepping down from the cab onto wet gravel",
    ]

    def generar_escenas(self, guion: Script, n: int, estilo: str = "") -> list[Scene]:
        escenas: list[Scene] = []
        for i in range(1, n + 1):
            base = self.VISUALES[(i - 1) % len(self.VISUALES)]
            escenas.append(
                Scene(
                    numero=i,
                    duracion_seg=8,
                    narracion=(
                        f"Escena {i}: el narrador avanza la historia de «{guion.titulo}». "
                        "Un detalle nuevo aparece y obliga a mirar dos veces."
                    ),
                    visual=base,
                    prompt_imagen=base + ", cinematic photorealistic, teal and orange, film grain",
                    nota_edicion="corte a negro de 0.3s" if i % 4 == 0 else "corte directo",
                )
            )
        return escenas

    def generar_guion(self, idea: Idea, duracion_min: int = 8, contexto: str = "") -> Script:
        return Script(
            titulo=idea.titulo,
            hook=idea.hook,
            intro=f"Esto es lo que nadie te cuenta sobre {idea.premisa}",
            desarrollo=[f"Bloque {i}: un giro más de la historia." for i in range(1, 8)],
            clímax="Y entonces todo encaja: el detalle que parecía casual era la clave.",
            cierre=idea.final or "El narrador apaga el motor y se queda mirando la carretera.",
            cta="¿Te subirías a ese camión? Te leo en los comentarios.",
            escenas=[],
            duracion_total_seg=duracion_min * 60,
        )

    def generar_prompts(
        self, script: Script, n: int | None = None, estilo: str = ""
    ) -> list[ImagePrompt]:
        estilo = estilo or settings.visual_style
        cantidad = n or len(script.escenas)
        from .image_prompts import quitar_estilo

        resultado: list[ImagePrompt] = []
        for i, escena in enumerate(script.escenas[:cantidad], start=1):
            base = escena.prompt_imagen or escena.visual or escena.narracion
            resultado.append(
                ImagePrompt(
                    numero=i,
                    scene_numero=escena.numero,
                    # El estilo del canal se añade al componer el prompt final
                    prompt=quitar_estilo(base, estilo),
                    negative=(
                        "text, watermark, logo, blurry, low quality, deformed hands, "
                        "extra fingers, cartoon, oversaturated, distorted faces"
                    ),
                    seed=100000 + i,
                )
            )
        return resultado

    def generar_metadata(self, script: Script, contexto: str = "") -> VideoMetadata:
        return VideoMetadata(
            titulos=[
                f"{script.titulo} | La historia que nadie se atreve a contar",
                "El turno de noche que cambió su vida",
                "Nadie quería este viaje. Él aceptó.",
                "Lo que encontró en la carretera a las 3 AM",
                "La regla que todo camionero conoce",
            ],
            descripcion=(
                f"{script.hook}\n\n"
                f"{script.intro}\n\n"
                "En este video te cuento la historia completa, paso a paso.\n\n"
                "00:00 Intro\n01:20 El primer viaje\n03:45 Lo que nadie esperaba\n"
                "06:10 El giro final\n\n"
                "Si te gustó, suscríbete y activa la campanita.\n\n"
                "#historias #carretera #noche"
            ),
            tags=["historias narradas", "camioneros", "carretera", "misterio", "noche", "audio español"],
            hashtags=["#historias", "#carretera", "#narracion"],
            texto_miniatura="A LAS 3 AM 🚛",
            prompt_miniatura=(
                "cinematic thumbnail, semi truck headlights on a dark empty highway, "
                "silhouette of a driver, dramatic teal and orange lighting, high contrast"
            ),
            comentario_fijado="¿Tú también escuchaste el CB esa noche? Cuéntame 👇",
            horas_publicacion=["18:00", "21:00"],
        )


# ---------------------------------------------------------------------------
# Fábrica: decide qué implementación usar
# ---------------------------------------------------------------------------
def get_llm(forzar_demo: bool | None = None) -> LLMBase:
    """Devuelve el motor de IA adecuado según la configuración.

    - Si hay clave y no está forzado el demo -> DeepSeekLLM
    - Si no -> DemoLLM
    """
    usar_demo = settings.force_demo if forzar_demo is None else forzar_demo
    if not usar_demo and settings.deepseek_api_key:
        try:
            return DeepSeekLLM()
        except LLMError as exc:
            print(f"[aviso] {exc}. Uso modo demo.")
    return DemoLLM()
