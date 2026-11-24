"""Tests de integración del agente (sin internet y sin gastar API).

Cubre el flujo completo en modo demo:
    idea -> guion -> escenas -> prompts -> metadata -> export -> base de datos.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

import pytest  # noqa: E402

from ytagent import store  # noqa: E402
from ytagent.image_prompts import componer, desde_guion, quitar_estilo, tamano_para  # noqa: E402
from ytagent.llm import DemoLLM, extraer_json  # noqa: E402


@pytest.fixture()
def video_id() -> int:
    """Crea un video de prueba y lo borra al terminar."""
    nuevo = store.crear_video("Video de prueba", "camioneros de prueba")
    yield nuevo
    store.borrar_video(nuevo)


# ---------------------------------------------------------------------------
# Utilidades de JSON
# ---------------------------------------------------------------------------


def test_extraer_json_limpio() -> None:
    assert extraer_json('{"a": 1}') == {"a": 1}


def test_extraer_json_con_markdown() -> None:
    assert extraer_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extraer_json_con_texto_alrededor() -> None:
    assert extraer_json('Aquí va: {"a": 1} y ya está') == {"a": 1}


def test_extraer_json_truncado_se_repara() -> None:
    """El caso real: la IA corta la respuesta a mitad del último objeto."""
    roto = '{"ideas": [{"titulo": "Uno", "hook": "Hola"}, {"titulo": "Dos", "ho'
    data = extraer_json(roto)
    assert isinstance(data, dict)
    assert "ideas" in data
    # El último objeto queda incompleto: se descarta o se recorta, pero el JSON
    # debe poder leerse y contener al menos la primera idea completa.
    assert len(data["ideas"]) >= 1
    assert data["ideas"][0]["titulo"] == "Uno"


def test_extraer_json_lista_suelta() -> None:
    data = extraer_json('[{"titulo": "Uno"}, {"titulo": "Dos"}]')
    assert "ideas" in data
    assert len(data["ideas"]) == 2


# ---------------------------------------------------------------------------
# Estilo visual
# ---------------------------------------------------------------------------


def test_quitar_estilo_evita_duplicados() -> None:
    estilo = "cinematic photorealistic, teal and orange color grading, film grain"
    prompt = f"a truck at night, {estilo}"
    limpio = quitar_estilo(prompt, estilo)
    assert "teal and orange" not in limpio
    assert limpio == "a truck at night"


def test_componer_solo_un_estilo() -> None:
    resultado = componer("a lonely road")
    assert resultado["prompt"].count("film grain") == 1
    assert resultado["width"] == 1024
    assert resultado["height"] == 576
    assert resultado["negative"]


def test_tamano_16_9() -> None:
    assert tamano_para("16:9") == (1024, 576)
    assert tamano_para("9:16") == (576, 1024)


# ---------------------------------------------------------------------------
# Flujo completo con el motor demo
# ---------------------------------------------------------------------------


def test_flujo_completo_demo(video_id: int) -> None:
    from ytagent import pipeline

    llm = DemoLLM()

    # 1) Ideas
    ideas = pipeline.generar_ideas(video_id, "camioneros de prueba", n=4, llm=llm)
    assert len(ideas) == 4
    assert store.listar_ideas(video_id)
    assert all(0 <= idea.nota <= 10 for idea in ideas)

    # 2) Elegir una
    fila = store.listar_ideas(video_id)[0]
    assert store.marcar_idea(video_id, fila["id"]) is not None
    assert store.idea_elegida(video_id) is not None

    # 3) Guion + escenas
    guion = pipeline.escribir_guion(video_id, duracion_min=6, n_escenas=12, llm=llm)
    assert len(guion.escenas) == 12
    assert [e.numero for e in guion.escenas] == list(range(1, 13))
    assert all(e.prompt_imagen for e in guion.escenas)
    assert store.obtener_guion(video_id) is not None

    # 4) Prompts masivos
    prompts = pipeline.generar_prompts(video_id)
    assert len(prompts) == 12
    assert store.listar_prompts(video_id)[0]["estado"] == "pendiente"

    # 5) Metadata
    meta = pipeline.generar_metadata(video_id, llm=llm)
    assert len(meta.titulos) >= 3
    assert meta.descripcion
    assert meta.tags

    # 6) Exportar
    from ytagent import exporters

    exportado = exporters.exportar_paquete(video_id)
    assert not exportado["errores"], exportado["errores"]
    carpeta = Path(exportado["carpeta"])
    for nombre in ("guion.md", "guion.txt", "prompts.txt", "prompts.csv", "metadata.md"):
        assert (carpeta / nombre).exists(), f"falta {nombre}"

    # El guion exportado contiene el título
    assert guion.titulo in (carpeta / "guion.md").read_text(encoding="utf-8")

    # prompts.json es válido y tiene un elemento por prompt
    datos = json.loads((carpeta / "prompts.json").read_text(encoding="utf-8"))
    assert len(datos) == 12


def test_prompts_desde_guion_sin_ia(video_id: int) -> None:
    """Se pueden crear prompts solo con el guion (ruta sin gastar tokens)."""
    from ytagent import pipeline

    llm = DemoLLM()
    pipeline.generar_ideas(video_id, "tema", n=2, llm=llm)
    store.marcar_idea(video_id, store.listar_ideas(video_id)[0]["id"])
    guion = pipeline.escribir_guion(video_id, duracion_min=4, n_escenas=8, llm=llm)

    prompts = desde_guion(guion, aspecto="16:9")
    assert len(prompts) == len(guion.escenas)
    assert prompts[0].width == 1024
    assert prompts[0].height == 576


def test_borrar_video_borra_todo(video_id: int) -> None:
    from ytagent import pipeline

    llm = DemoLLM()
    pipeline.generar_ideas(video_id, "tema", n=2, llm=llm)
    store.marcar_idea(video_id, store.listar_ideas(video_id)[0]["id"])
    pipeline.escribir_guion(video_id, duracion_min=4, n_escenas=6, llm=llm)
    pipeline.generar_prompts(video_id)

    assert store.listar_ideas(video_id)
    store.borrar_video(video_id)

    assert store.obtener_video(video_id) is None
    assert store.listar_ideas(video_id) == []
    assert store.obtener_guion(video_id) is None
    assert store.listar_prompts(video_id) == []


def test_elegir_idea_inexistente_devuelve_none(video_id: int) -> None:
    assert store.marcar_idea(video_id, 999999) is None


def test_exportar_sin_datos_da_error_claro(video_id: int) -> None:
    from ytagent import exporters

    with pytest.raises(ValueError):
        exporters.exportar_guion(video_id)


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------


def test_slug_unico(video_id: int) -> None:
    otro = store.crear_video("Video de prueba", "otro tema")
    try:
        assert otro != video_id
        videos = {v["id"]: v["slug"] for v in store.listar_videos()}
        assert videos[otro] != videos[video_id]
    finally:
        store.borrar_video(otro)


def test_cola_de_trabajos(video_id: int) -> None:
    from ytagent import pipeline

    llm = DemoLLM()
    pipeline.generar_ideas(video_id, "tema", n=2, llm=llm)
    store.marcar_idea(video_id, store.listar_ideas(video_id)[0]["id"])
    pipeline.escribir_guion(video_id, duracion_min=4, n_escenas=5, llm=llm)
    pipeline.generar_prompts(video_id)

    assert store.encolar_pendientes(video_id) == 5
    job = store.siguiente_job()
    assert job is not None
    assert job["prompt"]

    store.marcar_job(job["job_id"], "listo")
    assert store.contar_jobs(video_id).get("listo") == 1


def test_uso_estimado() -> None:
    from ytagent.pipeline import uso_estimado
    from ytagent.schemas import Usage

    datos = uso_estimado(Usage(prompt_tokens=1000, completion_tokens=2000, total_tokens=3000))
    assert datos["tokens_total"] == 3000
    assert datos["costo_estimado_usd"] >= 0
