"""Prompts masivos de imagen: composición, lotes y exportación.

La idea copiada de la app de tu foto siempre es la misma:
    guion -> lista larga de prompts -> cola -> imágenes 16:9

`Negative prompt` es lo que NO quieres que salga (texto, logos, manos deformadas).
`Seed` es el número que hace que una imagen se pueda repetir exacta.
"""

from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any

from .config import OUTPUT_DIR, settings
from .schemas import ImagePrompt, Script

# ---------------------------------------------------------------------------
# Relaciones de aspecto -> píxeles (múltiplos de 64 para los modelos SDXL)
# ---------------------------------------------------------------------------
ASPECTOS: dict[str, tuple[int, int]] = {
    "16:9": (1024, 576),
    "9:16": (576, 1024),
    "1:1": (768, 768),
    "4:5": (768, 960),
    "3:4": (768, 1024),
    "21:9": (1152, 512),
}

NEGATIVE_BASE = (
    "text, letters, words, watermark, signature, logo, brand marks, blurry, out of focus, "
    "low quality, jpeg artifacts, deformed hands, extra fingers, extra limbs, bad anatomy, "
    "cartoon, anime, illustration, oversaturated, distorted faces, duplicate, cropped"
)


def tamano_para(aspecto: str | None = None) -> tuple[int, int]:
    """Devuelve (ancho, alto) según la relación de aspecto configurada."""
    return ASPECTOS.get(aspecto or settings.image_aspect, ASPECTOS["16:9"])


def limpiar_prompt(prompt: str) -> str:
    """Normaliza el prompt: espacios, comas repetidas y caracteres que rompen ComfyUI."""
    texto = re.sub(r"\s+", " ", prompt).strip()
    texto = re.sub(r",\s*,+", ", ", texto)
    texto = texto.strip(", ")
    # los saltos de línea rompen algunos nodos de ComfyUI
    return texto.replace("\n", " ")


def _normalizar(texto: str) -> str:
    """Minúsculas y solo letras/números/espacios (para comparar dos textos)."""
    return re.sub(r"[^a-z0-9\s]", " ", texto.lower())


def quitar_estilo(prompt: str, estilo: str | None = None) -> str:
    """Quita el estilo del canal si la IA ya lo incluyó al final del prompt.

    Compara trozo a trozo (separados por comas), de atrás hacia adelante, y va
    eliminando los que ya pertenecen al estilo. Así evitamos prompts del tipo
    "...film grain, teal and orange, film grain, teal and orange...".
    """
    texto = limpiar_prompt(prompt)
    estilo = (estilo or settings.visual_style).strip().rstrip(",")
    if not estilo:
        return texto

    def normalizar(frase: str) -> str:
        return " ".join(_normalizar(frase).split())

    # Fragmentos del estilo (normalizados) y palabras sueltas significativas
    trozos_estilo = [normalizar(t) for t in estilo.split(",") if t.strip()]
    palabras_estilo = {p for t in trozos_estilo for p in t.split() if len(p) > 3}

    partes = [p.strip() for p in texto.split(",") if p.strip()]
    while partes:
        ultimo = normalizar(partes[-1])
        if not ultimo:
            partes.pop()
            continue
        # ¿Este trozo final es del estilo? (similar a algún fragmento o
        # compuesto solo de sus palabras clave)
        es_del_estilo = any(
            ultimo == trozo or (len(ultimo) > 8 and ultimo in trozo) or (len(trozo) > 8 and trozo in ultimo)
            for trozo in trozos_estilo
        )
        if not es_del_estilo:
            palabras_trozo = [p for p in ultimo.split() if len(p) > 3]
            if palabras_trozo and len(palabras_trozo) <= 6:
                coincidencias = sum(1 for p in palabras_trozo if p in palabras_estilo)
                if coincidencias / len(palabras_trozo) >= 0.75:
                    es_del_estilo = True
        if not es_del_estilo:
            break
        partes.pop()

    return ", ".join(partes).strip(", ")


def componer(
    prompt: str,
    estilo: str | None = None,
    negativo: str | None = None,
    *,
    aspecto: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Une prompt + estilo del canal + tamaño + negative. Devuelve un dict listo para ComfyUI."""
    ancho, alto = tamano_para(aspecto)
    base = quitar_estilo(prompt, estilo)
    return {
        "prompt": limpiar_prompt(f"{base}, {estilo or settings.visual_style}"),
        "negative": limpiar_prompt(negativo or NEGATIVE_BASE),
        "width": ancho,
        "height": alto,
        "seed": seed if seed is not None else random.randint(1, 2**32 - 1),
    }


def desde_guion(
    script: Script,
    *,
    estilo: str | None = None,
    aspecto: str | None = None,
    semilla_fija: int | None = None,
    solo_escenas: list[int] | None = None,
) -> list[ImagePrompt]:
    """Crea prompts masivos a partir de las escenas del guion (sin gastar IA).

    Útil cuando ya tienes el guion y quieres los prompts "de fábrica".
    """
    ancho, alto = tamano_para(aspecto)
    resultado: list[ImagePrompt] = []

    for i, escena in enumerate(script.escenas, start=1):
        if solo_escenas and escena.numero not in solo_escenas:
            continue
        base = escena.prompt_imagen or escena.visual or escena.narracion
        compuesto = componer(
            base,
            estilo=estilo,
            aspecto=aspecto,
            seed=(semilla_fija + i) if semilla_fija is not None else None,
        )
        resultado.append(
            ImagePrompt(
                numero=len(resultado) + 1,
                scene_numero=escena.numero,
                prompt=compuesto["prompt"],
                negative=compuesto["negative"],
                seed=compuesto["seed"],
                width=ancho,
                height=alto,
            )
        )
    return resultado


# ---------------------------------------------------------------------------
# Exportación: de la app al generador que uses
# ---------------------------------------------------------------------------


def carpeta_prompts(video_slug: str) -> Path:
    destino = OUTPUT_DIR / video_slug
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def exportar_txt(prompts: list[dict[str, Any]], video_slug: str) -> Path:
    """Formato universal: un prompt por línea, numerado. Sirve para Midjourney,
    Flux, Leonardo o para pegarlos en la app de la foto."""
    ruta = carpeta_prompts(video_slug) / "prompts.txt"
    lineas = []
    for p in prompts:
        lineas.append(f"{p['numero']:03d}. {p['prompt']}")
        if p.get("negative"):
            lineas.append(f"     NEGATIVE: {p['negative']}")
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


def exportar_csv(prompts: list[dict[str, Any]], video_slug: str) -> Path:
    """Formato tabla para Excel / Google Sheets (una fila por imagen)."""
    import csv

    ruta = carpeta_prompts(video_slug) / "prompts.csv"
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["numero", "escena", "prompt", "negative", "seed", "estado", "imagen"])
        for p in prompts:
            writer.writerow(
                [
                    p.get("numero", ""),
                    p.get("scene_numero", ""),
                    p.get("prompt", ""),
                    p.get("negative", ""),
                    p.get("seed", ""),
                    p.get("estado", ""),
                    p.get("imagen", ""),
                ]
            )
    return ruta


def exportar_json(prompts: list[dict[str, Any]], video_slug: str) -> Path:
    """Formato para programar: incluye el workflow de ComfyUI listo para enviar."""
    import json

    # El módulo de ComfyUI es opcional para exportar: si no está, exportamos
    # los prompts igual y dejamos el workflow vacío.
    try:
        from .comfyui import construir_workflow
    except ImportError:  # pragma: no cover
        construir_workflow = None  # type: ignore[assignment]

    datos = []
    for p in prompts:
        workflow = None
        if construir_workflow is not None:
            try:
                workflow = construir_workflow(
                    prompt=p.get("prompt", ""),
                    negative=p.get("negative", ""),
                    seed=p.get("seed") or 1,
                )
            except Exception:  # noqa: BLE001 - exportar nunca debe fallar por el workflow
                workflow = None
        datos.append(
            {
                "numero": p.get("numero"),
                "escena": p.get("scene_numero"),
                "prompt": p.get("prompt"),
                "negative": p.get("negative"),
                "seed": p.get("seed"),
                "estado": p.get("estado"),
                "imagen": p.get("imagen"),
                "workflow": workflow,
            }
        )
    ruta = carpeta_prompts(video_slug) / "prompts.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def exportar_todo(prompts: list[dict[str, Any]], video_slug: str) -> dict[str, Path]:
    """Exporta la lista de prompts en los 3 formatos de una vez."""
    return {
        "txt": exportar_txt(prompts, video_slug),
        "csv": exportar_csv(prompts, video_slug),
        "json": exportar_json(prompts, video_slug),
    }


def empaquetar_zip(prompts: list[dict[str, Any]], video_slug: str) -> Path:
    """Crea un ZIP con todo lo exportado para descargarlo de una vez."""
    import zipfile

    carpeta = carpeta_prompts(video_slug)
    rutas = exportar_todo(prompts, video_slug)
    # Añade también guion/metadata si existen en la misma carpeta
    extras = [
        p for p in carpeta.glob("*") if p.suffix in {".md", ".txt", ".json", ".csv"} and p.is_file()
    ]
    destino = carpeta / "paquete.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta in {*rutas.values(), *extras}:
            zf.write(ruta, arcname=ruta.name)
    return destino
