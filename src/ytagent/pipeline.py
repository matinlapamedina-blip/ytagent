"""Pipeline: el flujo de trabajo completo del agente.

Une todas las piezas en una sola secuencia:

    generar ideas -> escribir guion -> generar escenas -> prompts masivos
        -> títulos y descripción -> (ComfyUI genera las imágenes) -> exportar

La interfaz y la terminal solo llaman a estas funciones; así el "cómo" vive
en un solo lugar.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import store
from .config import OUTPUT_DIR, settings
from .image_prompts import desde_guion, exportar_todo
from .llm import LLMBase, LLMError, get_llm
from .schemas import Idea, ImagePrompt, Script, Usage, VideoMetadata

# Tipo de callback para informar progreso a la UI
Progreso = Callable[[str], None]

CONTEXTO_CANAL = (
    "Canal de YouTube de historias narradas con estética cinematográfica, "
    "en español, videos de 6 a 12 minutos. Público hispanohablante de 18 a 40 años."
)

# Preferencias de la sesión (las pone la interfaz al cambiar Ajustes).
# Si quedan vacías, se usan las del archivo .env.
_preferencias_sesion: dict[str, str | None] = {"estilo": None, "aspecto": None}


def configurar_sesion(estilo: str | None = None, aspecto: str | None = None) -> None:
    """Guarda el estilo visual y la relación de aspecto elegidos en la interfaz."""
    if estilo:
        _preferencias_sesion["estilo"] = estilo
    if aspecto:
        _preferencias_sesion["aspecto"] = aspecto


def estilo_actual() -> str:
    """Estilo visual efectivo: el de la sesión o el del .env."""
    return _preferencias_sesion["estilo"] or settings.visual_style


def aspecto_actual() -> str:
    """Relación de aspecto efectiva: la de la sesión o la del .env."""
    return _preferencias_sesion["aspecto"] or settings.image_aspect


def _avisar(cb: Progreso | None, mensaje: str) -> None:
    if cb:
        cb(mensaje)


# ---------------------------------------------------------------------------
# Pasos individuales
# ---------------------------------------------------------------------------


def generar_ideas(
    video_id: int,
    tema: str,
    n: int = 8,
    contexto: str = CONTEXTO_CANAL,
    llm: LLMBase | None = None,
    progreso: Progreso | None = None,
) -> list[Idea]:
    """Genera varias ideas para un video y las guarda en la base de datos."""
    llm = llm or get_llm()
    _avisar(progreso, f"Pidiendo {n} ideas a {llm.modo}...")
    ideas = llm.generar_ideas(tema, n, contexto)
    store.guardar_ideas(video_id, ideas)
    store.actualizar_estado(video_id, "ideas")
    _avisar(progreso, f"{len(ideas)} ideas guardadas.")
    return ideas


def escribir_guion(
    video_id: int,
    duracion_min: int = 8,
    n_escenas: int = 20,
    estilo: str | None = None,
    llm: LLMBase | None = None,
    progreso: Progreso | None = None,
) -> Script:
    """Escribe el guion (2 pasos) y añade las escenas con prompts de imagen."""
    llm = llm or get_llm()
    idea = store.idea_elegida(video_id)
    if idea is None:
        raise LLMError("Primero marca una idea como elegida.")

    _avisar(progreso, "Paso 1/2: escribiendo el guion...")
    guion = llm.generar_guion(idea, duracion_min=duracion_min, contexto=CONTEXTO_CANAL)
    store.guardar_guion(video_id, guion)
    store.actualizar_estado(video_id, "guion")

    _avisar(progreso, f"Paso 2/2: dividiendo en {n_escenas} escenas con prompts...")
    escenas = llm.generar_escenas(guion, n_escenas, estilo=estilo or estilo_actual())
    guion.escenas = escenas
    guion.duracion_total_seg = sum(e.duracion_seg for e in escenas)
    store.guardar_guion(video_id, guion)
    store.actualizar_estado(video_id, "guion")
    _avisar(progreso, f"Guion listo: {len(escenas)} escenas, {guion.palabras} palabras.")
    return guion


def generar_prompts(
    video_id: int,
    solo_escenas: list[int] | None = None,
    estilo: str | None = None,
    aspecto: str | None = None,
    llm: LLMBase | None = None,
    progreso: Progreso | None = None,
) -> list[ImagePrompt]:
    """Crea los prompts masivos de imagen y los guarda (estado: pendiente).

    Usa el estilo visual y la relación de aspecto activos (los de Ajustes en la
    interfaz, o los del .env si no se ha elegido nada).
    """
    guion = store.obtener_guion(video_id)
    if guion is None:
        raise ValueError("Este video todavía no tiene guion.")
    if not guion.escenas:
        raise ValueError("El guion no tiene escenas. Vuelve a escribir el guion.")

    prompts = desde_guion(
        guion,
        estilo=estilo or estilo_actual(),
        aspecto=aspecto or aspecto_actual(),
        solo_escenas=solo_escenas,
    )
    store.guardar_prompts(video_id, prompts)
    store.actualizar_estado(video_id, "prompts")
    _avisar(progreso, f"{len(prompts)} prompts listos para generar.")
    return prompts


def generar_metadata(
    video_id: int,
    llm: LLMBase | None = None,
    progreso: Progreso | None = None,
) -> VideoMetadata:
    """Genera títulos, descripción, tags, miniatura y comentario fijado."""
    guion = store.obtener_guion(video_id)
    if guion is None:
        raise ValueError("Este video todavía no tiene guion.")
    llm = llm or get_llm()
    _avisar(progreso, "Escribiendo títulos, descripción y miniatura...")
    meta = llm.generar_metadata(guion, contexto=CONTEXTO_CANAL)
    store.guardar_metadata(video_id, meta)
    store.actualizar_estado(video_id, "metadata")
    return meta


# ---------------------------------------------------------------------------
# Flujo completo de una vez
# ---------------------------------------------------------------------------


def crear_proyecto(titulo: str, tema: str) -> int:
    """Crea el registro del video y devuelve su id."""
    return store.crear_video(titulo=titulo, tema=tema)


def flujo_completo(
    video_id: int,
    *,
    n_ideas: int = 8,
    duracion_min: int = 8,
    n_escenas: int = 20,
    llm: LLMBase | None = None,
    progreso: Progreso | None = None,
) -> dict[str, Any]:
    """Hace ideas + guion + prompts + metadata de golpe, sin intervención.

    Ojo: elige automáticamente la idea con mejor nota promedio.
    """
    llm = llm or get_llm()
    video = store.obtener_video(video_id)
    if video is None:
        raise ValueError("Ese video no existe.")

    tema = video.get("tema") or video["titulo"]

    _avisar(progreso, "1/4 Generando ideas...")
    ideas = generar_ideas(video_id, tema, n=n_ideas, llm=llm, progreso=progreso)

    _avisar(progreso, "2/4 Eligiendo la mejor idea...")
    mejor = max(ideas, key=lambda i: i.nota)
    # La guardamos como elegida (buscando su fila en la BD)
    for fila in store.listar_ideas(video_id):
        if fila["titulo"] == mejor.titulo:
            store.marcar_idea(video_id, fila["id"])
            break

    _avisar(progreso, f"3/4 Escribiendo guion de «{mejor.titulo}»...")
    guion = escribir_guion(
        video_id, duracion_min=duracion_min, n_escenas=n_escenas, llm=llm, progreso=progreso
    )

    _avisar(progreso, "4/4 Prompts de imagen y metadata...")
    prompts = generar_prompts(video_id, llm=llm, progreso=progreso)
    meta = generar_metadata(video_id, llm=llm, progreso=progreso)

    return {
        "video_id": video_id,
        "idea": mejor,
        "guion": guion,
        "prompts": prompts,
        "metadata": meta,
        "usage": llm.usage,
    }


# ---------------------------------------------------------------------------
# Utilidades de resumen
# ---------------------------------------------------------------------------


def resumen_video(video_id: int) -> dict[str, Any]:
    """Todo lo que se sabe del video, para pantallas y exportaciones."""
    return {
        "video": store.obtener_video(video_id),
        "ideas": store.listar_ideas(video_id),
        "guion": store.obtener_guion(video_id),
        "prompts": store.listar_prompts(video_id),
        "metadata": store.obtener_metadata(video_id),
        "jobs": store.contar_jobs(video_id),
    }


def carpeta_video(video_id: int) -> Path:
    """Carpeta de salida de un video: output/<slug>/"""
    video = store.obtener_video(video_id)
    slug = video["slug"] if video else f"video-{video_id}"
    destino = OUTPUT_DIR / slug
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def exportar_todo_el_paquete(video_id: int) -> dict[str, Path]:
    """Exporta guion, prompts (txt/csv/json) y metadata a la carpeta del video."""
    from . import exporters

    return exporters.exportar_paquete(video_id)


def exportar_prompts(video_id: int) -> dict[str, Path]:
    """Exporta solo los prompts masivos en los 3 formatos."""
    video = store.obtener_video(video_id)
    prompts = store.listar_prompts(video_id)
    if not video or not prompts:
        raise ValueError("No hay prompts que exportar.")
    return exportar_todo(prompts, video["slug"])


def uso_estimado(usage: Usage) -> dict[str, float]:
    """Estimación aproximada del costo en dólares.

    Precios de referencia de DeepSeek (pueden cambiar; ajústalos en un solo sitio).
    """
    # USD por millón de tokens (referencia 2026: flash es muy barato)
    precio_entrada = 0.14 / 1_000_000
    precio_salida = 0.28 / 1_000_000
    costo = usage.prompt_tokens * precio_entrada + usage.completion_tokens * precio_salida
    return {
        "tokens_entrada": usage.prompt_tokens,
        "tokens_salida": usage.completion_tokens,
        "tokens_total": usage.total_tokens,
        "llamadas": usage.llamadas,
        "costo_estimado_usd": round(costo, 4),
    }
