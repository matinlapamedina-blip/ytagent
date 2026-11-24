"""Exportadores: convierten lo que hay en la base de datos en archivos útiles.

Formatos:
    guion.md          -> el guion legible (para leerlo o locutarlo)
    guion.txt         -> solo el texto de narración (para el TTS / teleprompter)
    prompts.txt/csv/json -> los prompts masivos
    metadata.md       -> títulos, descripción, tags listos para copiar y pegar
    paquete.zip       -> todo junto
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import store
from .config import OUTPUT_DIR
from .image_prompts import carpeta_prompts, empaquetar_zip, exportar_todo
from .schemas import Script, VideoMetadata


def _slug_video(video_id: int) -> str:
    video = store.obtener_video(video_id)
    return video["slug"] if video else f"video-{video_id}"


# ---------------------------------------------------------------------------
# Guion
# ---------------------------------------------------------------------------


def guion_a_markdown(script: Script, meta: VideoMetadata | None = None) -> str:
    """Convierte el guion en un markdown bonito y completo."""
    lineas = [f"# {script.titulo}", ""]
    if meta and meta.titulos:
        lineas += ["## Títulos alternativos", "", *[f"- {t}" for t in meta.titulos], ""]

    lineas += [
        f"**Duración estimada:** {script.duracion_total_seg // 60} min "
        f"{script.duracion_total_seg % 60} s  ",
        f"**Palabras:** {script.palabras}  ",
        f"**Escenas:** {len(script.escenas)}",
        "",
        "---",
        "",
        "## 🎣 Hook",
        "",
        script.hook,
        "",
    ]
    if script.intro:
        lineas += ["## Intro", "", script.intro, ""]
    if script.desarrollo:
        lineas += ["## Desarrollo", ""]
        for i, bloque in enumerate(script.desarrollo, start=1):
            lineas += [f"### Bloque {i}", "", bloque, ""]
    if script.clímax:
        lineas += ["## Clímax", "", script.clímax, ""]
    if script.cierre:
        lineas += ["## Cierre", "", script.cierre, ""]
    if script.cta:
        lineas += ["## Llamada a la acción", "", script.cta, ""]

    if script.escenas:
        lineas += ["---", "", "## 🎥 Escenas y prompts de imagen", ""]
        lineas += ["| # | Seg | Narración | Prompt de imagen |", "|---|---|---|---|"]
        for e in script.escenas:
            narracion = e.narracion.replace("|", "\\|")
            prompt = e.prompt_imagen.replace("|", "\\|")
            lineas.append(f"| {e.numero} | {e.duracion_seg}s | {narracion} | {prompt} |")
        lineas.append("")

    return "\n".join(lineas)


def exportar_guion(video_id: int) -> dict[str, Path]:
    """Guarda guion.md + guion.txt (solo narración) en la carpeta del video."""
    script = store.obtener_guion(video_id)
    if script is None:
        raise ValueError("No hay guion para exportar.")
    meta = store.obtener_metadata(video_id)
    destino = OUTPUT_DIR / _slug_video(video_id)
    destino.mkdir(parents=True, exist_ok=True)

    md = destino / "guion.md"
    md.write_text(guion_a_markdown(script, meta), encoding="utf-8")

    txt = destino / "guion.txt"
    txt.write_text(script.texto_completo, encoding="utf-8")

    return {"guion_md": md, "guion_txt": txt}


# ---------------------------------------------------------------------------
# Metadata de YouTube
# ---------------------------------------------------------------------------


def metadata_a_texto(meta: VideoMetadata) -> str:
    """Formato para copiar y pegar directamente en YouTube Studio."""
    lineas = ["# FICHA DEL VIDEO", ""]
    lineas += ["## TÍTULOS (elige uno)", ""]
    lineas += [f"{i}. {t}" for i, t in enumerate(meta.titulos, start=1)] or ["(sin títulos)"]

    lineas += ["", "## DESCRIPCIÓN", "", meta.descripcion, ""]
    lineas += ["## TAGS", "", ", ".join(meta.tags), ""]
    lineas += ["## HASHTAGS", "", " ".join(meta.hashtags), ""]
    lineas += ["## MINIATURA", "", f"Texto: **{meta.texto_miniatura}**", ""]
    if meta.prompt_miniatura:
        lineas += ["Prompt de la miniatura:", "```", meta.prompt_miniatura, "```", ""]
    lineas += ["## COMENTARIO FIJADO", "", meta.comentario_fijado, ""]
    if meta.horas_publicacion:
        lineas += ["## MEJORES HORAS", "", ", ".join(meta.horas_publicacion), ""]
    return "\n".join(lineas)


def exportar_metadata(video_id: int) -> dict[str, Path]:
    """Guarda metadata.md (para copiar y pegar) y metadata.json (para automatizar)."""
    meta = store.obtener_metadata(video_id)
    if meta is None:
        raise ValueError("No hay metadata para exportar.")
    destino = OUTPUT_DIR / _slug_video(video_id)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "metadata.md"
    ruta.write_text(metadata_a_texto(meta), encoding="utf-8")

    # JSON para automatizaciones (por ejemplo, subida con la API de YouTube)
    ruta_json = destino / "metadata.json"
    ruta_json.write_text(
        json.dumps(meta.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"metadata_md": ruta, "metadata_json": ruta_json}


# ---------------------------------------------------------------------------
# Paquete completo
# ---------------------------------------------------------------------------


def exportar_guion_json(video_id: int) -> Path | None:
    """Guion crudo en JSON (útil para programar)."""
    script = store.obtener_guion(video_id)
    if script is None:
        return None
    destino = OUTPUT_DIR / _slug_video(video_id)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "guion.json"
    ruta.write_text(
        json.dumps(script.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ruta


def exportar_paquete(video_id: int) -> dict[str, Any]:
    """Exporta TODO lo que exista del video. Tolera que falten partes."""
    resultado: dict[str, Any] = {"errores": []}
    slug = _slug_video(video_id)

    try:
        resultado.update(exportar_guion(video_id))
    except ValueError as exc:
        resultado["errores"].append(str(exc))

    try:
        resultado.update(exportar_metadata(video_id))
    except ValueError as exc:
        resultado["errores"].append(str(exc))

    prompts = store.listar_prompts(video_id)
    if prompts:
        resultado.update(exportar_todo(prompts, slug))
        try:
            resultado["zip"] = empaquetar_zip(prompts, slug)
        except OSError as exc:
            resultado["errores"].append(f"No se pudo crear el ZIP: {exc}")

    ruta_json = exportar_guion_json(video_id)
    if ruta_json:
        resultado["guion_json"] = ruta_json

    resultado["carpeta"] = str(OUTPUT_DIR / slug)
    return resultado


def listar_archivos_exportados(video_id: int) -> list[Path]:
    """Lista los archivos que ya existen en la carpeta de salida del video."""
    carpeta = OUTPUT_DIR / _slug_video(video_id)
    if not carpeta.exists():
        return []
    return sorted(p for p in carpeta.iterdir() if p.is_file())


def carpeta_de_prompts(video_id: int) -> Path:
    return carpeta_prompts(_slug_video(video_id))
