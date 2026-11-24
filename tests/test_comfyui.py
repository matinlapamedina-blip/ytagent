"""Tests de `ytagent.comfyui` sin necesitar un ComfyUI real.

Estrategia:
- Lo que se puede probar sin red (workflow y validaciones) se prueba directo.
- Para lo que sí habla HTTP se levanta un servidor falso local
  (`http.server`) que imita las rutas de ComfyUI: /system_stats,
  /object_info, /prompt, /history, /queue y /view.
- `diagnostico()` contra un puerto cerrado comprueba que no lanza excepciones.

Ejecutar:
    $env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe -m pytest tests/test_comfyui.py -q
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

# Permite `pytest` sin tener que exportar PYTHONPATH a mano.
RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROYECTO / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO / "src"))

from ytagent import comfyui  # noqa: E402
from ytagent.schemas import ImagePrompt  # noqa: E402

PNG_FALSO = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
CKPT_FALSO = "modelo_falso.safetensors"


# ===========================================================================
# Servidor falso de ComfyUI
# ===========================================================================
class _ManejadorComfy(BaseHTTPRequestHandler):
    """Imita las rutas HTTP de ComfyUI que usa el módulo."""

    # Cada fixture de test inyecta su propio dict de estado en esta clase hija.
    estado: dict[str, Any] = {}

    def log_message(self, *args: Any) -> None:  # silencia el log del servidor
        pass

    # --- utilidades de respuesta -------------------------------------------------
    def _json(self, datos: Any, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _bytes(self, datos: bytes, tipo: str = "image/png") -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _texto(self, texto: str, codigo: int = 200) -> None:
        cuerpo = texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    # --- GET ---------------------------------------------------------------------
    def do_GET(self) -> None:
        estado = type(self).estado
        ruta = urlparse(self.path)

        if ruta.path == "/system_stats":
            self._json({"system": {"os": "nt"}, "devices": []})
            return

        if ruta.path == "/object_info/CheckpointLoaderSimple":
            modo = estado.get("object_info_modo")
            if modo == "html":
                self._texto("<html>esto no es json</html>")
                return
            if modo == "raro":
                self._json({})
                return
            self._json(
                {
                    "CheckpointLoaderSimple": {
                        "input": {
                            "required": {
                                "ckpt_name": [
                                    list(estado["checkpoints"]),
                                    {"tooltip": "modelos instalados"},
                                ]
                            }
                        }
                    }
                }
            )
            return

        if ruta.path == "/queue":
            self._json({"queue_running": [], "queue_pending": []})
            return

        if ruta.path.startswith("/history/"):
            if estado.get("history_vacias", 0) > 0:
                estado["history_vacias"] -= 1
                self._json({})
                return
            modo = estado.get("history_modo", "success")
            prompt_id = estado["prompt_id"]
            if modo == "vacio":
                self._json({})
            elif modo == "error":
                self._json(
                    {
                        prompt_id: {
                            "outputs": {},
                            "status": {
                                "status_str": "error",
                                "completed": False,
                                "messages": [
                                    [
                                        "execution_error",
                                        {
                                            "node_id": "5",
                                            "node_type": "KSampler",
                                            "exception_message": "CUDA out of memory",
                                        },
                                    ]
                                ],
                            },
                        }
                    }
                )
            elif modo == "sin_imagenes":
                self._json(
                    {
                        prompt_id: {
                            "outputs": {},
                            "status": {
                                "status_str": "success",
                                "completed": True,
                                "messages": [],
                            },
                        }
                    }
                )
            else:
                self._json(
                    {
                        prompt_id: {
                            "outputs": {
                                "7": {
                                    "images": [
                                        {
                                            "filename": "ytagent_00001_.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            },
                            "status": {
                                "status_str": "success",
                                "completed": True,
                                "messages": [],
                            },
                        }
                    }
                )
            return

        if ruta.path == "/view":
            # keep_blank_values: el parámetro `subfolder` puede venir vacío.
            estado["view_params"] = {
                clave: valores[0]
                for clave, valores in parse_qs(ruta.query, keep_blank_values=True).items()
            }
            self._bytes(estado["imagen"])
            return

        self._json({"error": "ruta no simulada"}, 404)

    # --- POST --------------------------------------------------------------------
    def do_POST(self) -> None:
        estado = type(self).estado
        if urlparse(self.path).path != "/prompt":
            self._json({"error": "ruta no simulada"}, 404)
            return

        # Importante: un servidor real LEE el cuerpo antes de responder.
        # Si respondemos sin consumirlo, el cliente recibe un corte de conexión
        # (WinError 10053) en vez del error 400, y el test no prueba lo que cree.
        largo = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(largo) if largo else b"{}"

        if estado.get("http_error"):
            codigo, cuerpo = estado["http_error"]
            self._json(cuerpo, codigo)
            return

        estado["payload"] = json.loads(crudo or b"{}")
        self._json({"prompt_id": estado["prompt_id"], "number": 1, "node_errors": {}})


def _url_sin_servidor() -> str:
    """URL de 127.0.0.1 en un puerto que acabamos de liberar (nadie escucha)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        puerto = sock.getsockname()[1]
    return f"http://127.0.0.1:{puerto}"


@pytest.fixture
def comfy_falso() -> Any:
    """Levanta el servidor falso en un hilo y entrega su URL + estado mutable."""
    estado: dict[str, Any] = {
        "prompt_id": "pid-123",
        "checkpoints": [CKPT_FALSO],
        "imagen": PNG_FALSO,
        "payload": None,
        "view_params": None,
        "history_vacias": 0,
        "history_modo": "success",
        "http_error": None,
        "object_info_modo": None,
    }
    clase = type("ManejadorDePrueba", (_ManejadorComfy,), {"estado": estado})
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), clase)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}"
    try:
        yield SimpleNamespace(url=url, estado=estado)
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=2)


@pytest.fixture
def carpeta_temporal(request: pytest.FixtureRequest) -> Path:
    """Carpeta de trabajo dentro del proyecto, propia de cada test.

    No usamos `tmp_path` de pytest porque en este equipo el sandbox de Windows
    crea sus directorios con unos permisos que luego impiden leerlos
    (WinError 5: acceso denegado). Aquí creamos la carpeta con permisos normales
    y limpiamos los archivos de ejecuciones anteriores. La carpeta en sí no se
    borra al final porque el sandbox del workspace tampoco permite eliminar
    directorios; reutilizarla es inofensivo.
    """
    carpeta = RAIZ_PROYECTO / ".tmp-tests-comfyui" / request.node.name
    if carpeta.exists():
        for archivo in carpeta.rglob("*"):
            if archivo.is_file():
                archivo.unlink()
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


# ===========================================================================
# a) Workflow en formato API (sin servidor)
# ===========================================================================
def test_construir_workflow_tiene_7_nodos_y_enlaces_correctos() -> None:
    wf = comfyui.construir_workflow(
        prompt="un faro en un acantilado al atardecer",
        negative="texto, marca de agua",
        seed=42,
        checkpoint=CKPT_FALSO,
    )

    # Debe haber exactamente 7 nodos, con claves de texto "1".."7".
    assert set(wf) == {str(numero) for numero in range(1, 8)}

    # Nodo 1: carga del checkpoint.
    assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
    assert wf["1"]["inputs"]["ckpt_name"] == CKPT_FALSO

    # Nodos 2 y 3: CLIP positivo/negativo alimentados por la salida 1 del nodo 1.
    assert wf["2"]["class_type"] == "CLIPTextEncode"
    assert wf["2"]["inputs"]["text"] == "un faro en un acantilado al atardecer"
    assert wf["2"]["inputs"]["clip"] == ["1", 1]
    assert wf["3"]["class_type"] == "CLIPTextEncode"
    assert wf["3"]["inputs"]["text"] == "texto, marca de agua"
    assert wf["3"]["inputs"]["clip"] == ["1", 1]

    # Nodo 4: lienzo 16:9.
    assert wf["4"]["class_type"] == "EmptyLatentImage"
    assert wf["4"]["inputs"] == {"width": 1024, "height": 576, "batch_size": 1}

    # Nodo 5: el KSampler con TODOS sus enlaces bien formados.
    entradas_ksampler = wf["5"]["inputs"]
    assert wf["5"]["class_type"] == "KSampler"
    assert entradas_ksampler["model"] == ["1", 0]
    assert entradas_ksampler["positive"] == ["2", 0]
    assert entradas_ksampler["negative"] == ["3", 0]
    assert entradas_ksampler["latent_image"] == ["4", 0]
    assert entradas_ksampler["seed"] == 42
    assert entradas_ksampler["steps"] == 20
    assert entradas_ksampler["cfg"] == 6.5
    assert entradas_ksampler["sampler_name"] == "dpmpp_2m"
    assert entradas_ksampler["scheduler"] == "karras"
    assert entradas_ksampler["denoise"] == 1.0

    # Nodo 6: VAEDecode toma el latent del KSampler y el VAE del nodo 1.
    assert wf["6"]["class_type"] == "VAEDecode"
    assert wf["6"]["inputs"]["samples"] == ["5", 0]
    assert wf["6"]["inputs"]["vae"] == ["1", 2]

    # Nodo 7: SaveImage toma la imagen del VAEDecode.
    assert wf["7"]["class_type"] == "SaveImage"
    assert wf["7"]["inputs"]["images"] == ["6", 0]
    assert wf["7"]["inputs"]["filename_prefix"] == "ytagent"


def test_workflow_no_tiene_enlaces_rotos() -> None:
    wf = comfyui.construir_workflow("una ciudad futurista", checkpoint=CKPT_FALSO)
    for nodo, datos in wf.items():
        assert "class_type" in datos and "inputs" in datos
        for nombre, valor in datos["inputs"].items():
            if isinstance(valor, list) and len(valor) == 2 and isinstance(valor[0], str):
                assert valor[0] in wf, f"{nodo}.{nombre} apunta a un nodo inexistente"
                assert isinstance(valor[1], int) and valor[1] >= 0


def test_workflow_ajusta_tamano_a_multiplos_de_8() -> None:
    wf = comfyui.construir_workflow("x", checkpoint=CKPT_FALSO, width=1001, height=571)
    assert wf["4"]["inputs"]["width"] == 1000
    assert wf["4"]["inputs"]["height"] == 568


def test_workflow_usa_checkpoint_de_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "desde_env.safetensors")
    wf = comfyui.construir_workflow("x", checkpoint="")
    assert wf["1"]["inputs"]["ckpt_name"] == "desde_env.safetensors"


def test_workflow_usa_primer_checkpoint_instalado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "")
    monkeypatch.setattr(
        comfyui, "listar_checkpoints", lambda: ["primero.safetensors", "segundo.safetensors"]
    )
    wf = comfyui.construir_workflow("x")
    assert wf["1"]["inputs"]["ckpt_name"] == "primero.safetensors"


def test_workflow_sin_checkpoints_lanza_error_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "")
    monkeypatch.setattr(comfyui, "listar_checkpoints", lambda: [])
    with pytest.raises(comfyui.ComfyUIError, match="No hay checkpoints"):
        comfyui.construir_workflow("x")


def test_workflow_prompt_vacio_lanza_error() -> None:
    with pytest.raises(comfyui.ComfyUIError, match="prompt"):
        comfyui.construir_workflow("   ", checkpoint=CKPT_FALSO)


def test_workflow_seed_invalida_lanza_error() -> None:
    with pytest.raises(comfyui.ComfyUIError, match="Seed"):
        comfyui.construir_workflow("x", checkpoint=CKPT_FALSO, seed="no-es-numero")  # type: ignore[arg-type]


# ===========================================================================
# Disponibilidad, checkpoints y cola (servidor falso)
# ===========================================================================
def test_disponible_con_servidor(comfy_falso: Any) -> None:
    assert comfyui.disponible(comfy_falso.url, timeout=2.0) is True


def test_disponible_sin_servidor() -> None:
    assert comfyui.disponible(_url_sin_servidor(), timeout=0.5) is False


def test_listar_checkpoints(comfy_falso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    assert comfyui.listar_checkpoints() == [CKPT_FALSO]


def test_listar_checkpoints_sin_servidor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_url", _url_sin_servidor())
    with pytest.raises(comfyui.ComfyUIError, match="conectar"):
        comfyui.listar_checkpoints()


def test_listar_checkpoints_formato_raro(comfy_falso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    comfy_falso.estado["object_info_modo"] = "raro"
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    with pytest.raises(comfyui.ComfyUIError, match="checkpoints"):
        comfyui.listar_checkpoints()


def test_listar_checkpoints_json_invalido(comfy_falso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    comfy_falso.estado["object_info_modo"] = "html"
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    with pytest.raises(comfyui.ComfyUIError, match="JSON"):
        comfyui.listar_checkpoints()


def test_encolar_envia_workflow_y_devuelve_prompt_id(comfy_falso: Any) -> None:
    wf = comfyui.construir_workflow("x", checkpoint=CKPT_FALSO)
    prompt_id = comfyui.encolar(wf, url=comfy_falso.url, client_id="cliente-prueba")
    assert prompt_id == "pid-123"
    assert comfy_falso.estado["payload"]["prompt"] == wf
    assert comfy_falso.estado["payload"]["client_id"] == "cliente-prueba"


def test_encolar_sin_client_id_genera_uno(comfy_falso: Any) -> None:
    wf = comfyui.construir_workflow("x", checkpoint=CKPT_FALSO)
    comfyui.encolar(wf, url=comfy_falso.url)
    assert isinstance(comfy_falso.estado["payload"]["client_id"], str)
    assert comfy_falso.estado["payload"]["client_id"]


def test_encolar_error_http_incluye_node_errors(comfy_falso: Any) -> None:
    comfy_falso.estado["http_error"] = (
        400,
        {
            "error": {
                "type": "prompt_outputs_failed_validation",
                "message": "Prompt outputs failed validation",
            },
            "node_errors": {
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "errors": [
                        {
                            "type": "value_not_in_list",
                            "message": "Value not in list",
                            "details": "ckpt_name: 'no_existe.safetensors' not in []",
                        }
                    ],
                }
            },
        },
    )
    wf = comfyui.construir_workflow("x", checkpoint=CKPT_FALSO)
    with pytest.raises(comfyui.ComfyUIError) as excinfo:
        comfyui.encolar(wf, url=comfy_falso.url)

    mensaje = str(excinfo.value)
    # El detalle útil de ComfyUI debe llegar al usuario (para eso existe).
    assert "no_existe.safetensors" in mensaje
    assert "nodo 1" in mensaje
    assert "CheckpointLoaderSimple" in mensaje
    assert "HTTP 400" in mensaje


def test_encolar_workflow_vacio_lanza_error() -> None:
    with pytest.raises(comfyui.ComfyUIError, match="vacío"):
        comfyui.encolar({}, url=_url_sin_servidor())


def test_esperar_resultado_ok(comfy_falso: Any) -> None:
    salidas = comfyui.esperar_resultado(
        "pid-123", url=comfy_falso.url, timeout=5.0, intervalo=0.05
    )
    assert salidas == [
        {"filename": "ytagent_00001_.png", "subfolder": "", "type": "output"}
    ]


def test_esperar_resultado_avisa_progreso(comfy_falso: Any) -> None:
    comfy_falso.estado["history_vacias"] = 2  # las dos primeras consultas: aún no está
    avisos: list[str] = []
    salidas = comfyui.esperar_resultado(
        "pid-123",
        url=comfy_falso.url,
        timeout=5.0,
        intervalo=0.05,
        on_progress=avisos.append,
    )
    assert len(salidas) == 1
    assert any("esperando" in aviso for aviso in avisos)


def test_esperar_resultado_error_de_ejecucion(comfy_falso: Any) -> None:
    comfy_falso.estado["history_modo"] = "error"
    with pytest.raises(comfyui.ComfyUIError, match="CUDA out of memory"):
        comfyui.esperar_resultado("pid-123", url=comfy_falso.url, timeout=5.0, intervalo=0.05)


def test_esperar_resultado_sin_imagenes(comfy_falso: Any) -> None:
    comfy_falso.estado["history_modo"] = "sin_imagenes"
    with pytest.raises(comfyui.ComfyUIError, match="ninguna imagen"):
        comfyui.esperar_resultado("pid-123", url=comfy_falso.url, timeout=5.0, intervalo=0.05)


def test_esperar_resultado_timeout(comfy_falso: Any) -> None:
    comfy_falso.estado["history_modo"] = "vacio"  # nunca aparece en el historial
    with pytest.raises(comfyui.ComfyUIError, match="tiempo"):
        comfyui.esperar_resultado("pid-123", url=comfy_falso.url, timeout=0.4, intervalo=0.05)


# ===========================================================================
# Descarga y flujo completo
# ===========================================================================
def test_descargar_imagen(comfy_falso: Any) -> None:
    contenido = comfyui.descargar_imagen("ytagent_00001_.png", url=comfy_falso.url)
    assert contenido == PNG_FALSO
    assert comfy_falso.estado["view_params"] == {
        "filename": "ytagent_00001_.png",
        "subfolder": "",
        "type": "output",
    }


def test_descargar_imagen_no_es_imagen(comfy_falso: Any) -> None:
    comfy_falso.estado["imagen"] = b"<html>error</html>"
    with pytest.raises(comfyui.ComfyUIError, match="imagen válida"):
        comfyui.descargar_imagen("x.png", url=comfy_falso.url)


def _simular_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sustituye red/paso HTTP de generar_imagen por versiones de mentira."""
    monkeypatch.setattr(
        comfyui, "encolar", lambda workflow, url=None, client_id=None: "pid-1"
    )
    monkeypatch.setattr(
        comfyui,
        "esperar_resultado",
        lambda prompt_id, url=None, timeout=300.0, intervalo=1.0, on_progress=None: [
            {"filename": "ytagent_00001_.png", "subfolder": "", "type": "output"}
        ],
    )
    monkeypatch.setattr(
        comfyui,
        "descargar_imagen",
        lambda filename, subfolder="", url=None: PNG_FALSO,
    )


def test_generar_imagen_guarda_en_archivo(
    monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path
) -> None:
    _simular_pipeline(monkeypatch)
    avisos: list[str] = []
    destino = carpeta_temporal / "sub" / "imagen.png"
    ruta = comfyui.generar_imagen(
        "un faro",
        checkpoint=CKPT_FALSO,
        seed=7,
        destino=destino,
        on_progress=avisos.append,
    )
    assert ruta == destino
    assert ruta.read_bytes() == PNG_FALSO
    assert avisos and "guardada" in avisos[-1]


def test_generar_imagen_guarda_en_carpeta(
    monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path
) -> None:
    _simular_pipeline(monkeypatch)
    carpeta = carpeta_temporal / "carpeta_nueva"
    ruta = comfyui.generar_imagen(
        "un faro", checkpoint=CKPT_FALSO, seed=7, destino=carpeta
    )
    assert ruta.parent == carpeta
    assert ruta.name.startswith("ytagent_7_")
    assert ruta.read_bytes() == PNG_FALSO


def test_generar_imagen_seed_aleatoria(monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path) -> None:
    _simular_pipeline(monkeypatch)
    monkeypatch.setattr(comfyui.random, "randint", lambda inicio, fin: 123456)
    ruta = comfyui.generar_imagen("un faro", checkpoint=CKPT_FALSO, destino=carpeta_temporal)
    assert "ytagent_123456_" in ruta.name


# ===========================================================================
# Lotes
# ===========================================================================
def _falso_generar_imagen(**kwargs: Any) -> Path:
    """Genera un archivo local sin red; falla si el prompt contiene 'falla'."""
    if "falla" in kwargs["prompt"]:
        raise comfyui.ComfyUIError("servidor caído de prueba")
    ruta: Path = kwargs["destino"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(PNG_FALSO)
    if kwargs.get("on_progress") is not None:
        kwargs["on_progress"]("listo")
    return ruta


def test_procesar_lote_sigue_tras_un_fallo(
    monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path
) -> None:
    monkeypatch.setattr(comfyui, "generar_imagen", _falso_generar_imagen)
    prompts = [
        {"id": 10, "numero": 1, "prompt": "un faro al atardecer", "seed": 5},
        {"id": 11, "numero": 2, "prompt": "falla total", "seed": 6},
        {"id": 12, "numero": 3, "prompt": "bosque de niebla", "seed": 7},
    ]
    llamadas_on_item: list[tuple[int, Any]] = []
    avisos: list[str] = []
    resultados = comfyui.procesar_lote(
        prompts,
        salida=carpeta_temporal / "lote",
        on_item=lambda numero, valor: llamadas_on_item.append((numero, valor)),
        on_progress=avisos.append,
    )

    assert [resultado["ok"] for resultado in resultados] == [True, False, True]
    assert [resultado["id"] for resultado in resultados] == [10, 11, 12]

    assert resultados[0]["imagen"].endswith("001_un-faro-al-atardecer.png")
    assert resultados[1]["imagen"] == ""
    assert "servidor caído de prueba" in resultados[1]["error"]
    assert resultados[2]["imagen"].endswith("003_bosque-de-niebla.png")

    # on_item se llamó 3 veces: ruta (Path) en las buenas, texto en el error.
    assert len(llamadas_on_item) == 3
    assert isinstance(llamadas_on_item[0][1], Path)
    assert isinstance(llamadas_on_item[1][1], str)
    assert isinstance(llamadas_on_item[2][1], Path)
    assert avisos and any("imagen 1/3" in aviso for aviso in avisos)
    assert len(list((carpeta_temporal / "lote").glob("*.png"))) == 2


def test_procesar_lote_acepta_imageprompt(
    monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path
) -> None:
    monkeypatch.setattr(comfyui, "generar_imagen", _falso_generar_imagen)
    elementos = [
        ImagePrompt(numero=4, scene_numero=1, prompt="un faro de noche", seed=9),
    ]
    resultados = comfyui.procesar_lote(elementos, salida=carpeta_temporal)
    assert resultados[0]["ok"] is True
    assert resultados[0]["numero"] == 4
    assert resultados[0]["imagen"].endswith("004_un-faro-de-noche.png")


def test_procesar_lote_item_invalido(monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path) -> None:
    monkeypatch.setattr(comfyui, "generar_imagen", _falso_generar_imagen)
    resultados = comfyui.procesar_lote([42], salida=carpeta_temporal)  # type: ignore[list-item]
    assert resultados[0]["ok"] is False
    assert "no es un diccionario" in resultados[0]["error"]


def test_procesar_lote_cancelar(monkeypatch: pytest.MonkeyPatch, carpeta_temporal: Path) -> None:
    monkeypatch.setattr(comfyui, "generar_imagen", _falso_generar_imagen)
    prompts = [
        {"id": numero, "numero": numero, "prompt": f"escena {numero}", "seed": numero}
        for numero in range(1, 6)
    ]
    consultas = {"veces": 0}

    def cancelar() -> bool:
        consultas["veces"] += 1
        return consultas["veces"] > 1  # deja hacer la primera y luego para

    resultados = comfyui.procesar_lote(prompts, salida=carpeta_temporal, cancelar=cancelar)
    assert len(resultados) == 1
    assert resultados[0]["ok"] is True


# ===========================================================================
# b) Diagnóstico (nunca lanza)
# ===========================================================================
def test_diagnostico_sin_servidor(monkeypatch: pytest.MonkeyPatch) -> None:
    url_apagada = _url_sin_servidor()
    monkeypatch.setattr(comfyui.settings, "comfyui_url", url_apagada)
    estado = comfyui.diagnostico()

    assert estado["disponible"] is False
    assert estado["url"] == url_apagada
    assert estado["checkpoints"] == []
    assert isinstance(estado["error"], str) and estado["error"]
    assert "ComfyUI" in estado["error"]


def test_diagnostico_con_servidor(comfy_falso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "")
    estado = comfyui.diagnostico()

    assert estado["disponible"] is True
    assert estado["checkpoints"] == [CKPT_FALSO]
    assert estado["checkpoint_actual"] == CKPT_FALSO
    assert estado["error"] == ""


def test_diagnostico_checkpoint_configurado_inexistente(
    comfy_falso: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "otro.safetensors")
    estado = comfyui.diagnostico()

    assert estado["disponible"] is True
    assert "otro.safetensors" in estado["error"]


def test_diagnostico_sin_checkpoints(comfy_falso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    comfy_falso.estado["checkpoints"] = []
    monkeypatch.setattr(comfyui.settings, "comfyui_url", comfy_falso.url)
    monkeypatch.setattr(comfyui.settings, "comfyui_checkpoint", "")
    estado = comfyui.diagnostico()

    assert estado["disponible"] is True
    assert estado["checkpoints"] == []
    assert "checkpoints" in estado["error"]
