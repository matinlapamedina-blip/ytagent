"""Configuración central del proyecto.

Aquí vive TODO lo que se puede tocar sin meter mano al código:
claves de API, rutas de carpetas, modelo de IA, estilo visual...

Se lee en este orden:
  1. Las variables de entorno reales del sistema.
  2. El archivo `.env` de la raíz del proyecto.
  3. Valores por defecto seguros.

Regla de oro: si una clave no existe, el proyecto NO explota:
simplemente entra en "modo demo" (respuestas simuladas).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
# config.py está en <raíz>/src/ytagent/config.py
# .parents[0] = ytagent, .parents[1] = src, .parents[2] = raíz del proyecto
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = PROJECT_ROOT / "data"
OUTPUT_DIR: Path = PROJECT_ROOT / "output"
PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"  # prompts maestros (.md) editables
DB_PATH: Path = DATA_DIR / "ytagent.db"
IMAGES_DIR: Path = DATA_DIR / "images"
ENV_PATH: Path = PROJECT_ROOT / ".env"

# Carga el .env (no falla si no existe)
load_dotenv(ENV_PATH)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Configuración tipada
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    """Todas las preferencias del agente en un solo objeto."""

    # --- IA de texto (DeepSeek) ---
    deepseek_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY"))
    deepseek_base_url: str = field(
        default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    )
    deepseek_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-flash"))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 1.1))
    max_tokens: int = field(default_factory=lambda: int(_env_float("LLM_MAX_TOKENS", 8000)))
    request_timeout: int = 180  # segundos

    # --- Imágenes (ComfyUI local) ---
    comfyui_url: str = field(
        default_factory=lambda: _env("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
    )
    comfyui_checkpoint: str = field(default_factory=lambda: _env("COMFYUI_CHECKPOINT"))
    # LoRA opcional (por ejemplo el acelerador SDXL Lightning de 4 pasos)
    comfyui_lora: str = field(default_factory=lambda: _env("COMFYUI_LORA"))
    image_aspect: str = field(default_factory=lambda: _env("IMAGE_ASPECT", "16:9"))
    # Ajustes del muestreador. Con Lightning: steps=4, cfg=1.5, sampler=euler
    image_steps: int = field(default_factory=lambda: int(_env_float("IMAGE_STEPS", 20)))
    image_cfg: float = field(default_factory=lambda: _env_float("IMAGE_CFG", 6.5))
    image_sampler: str = field(default_factory=lambda: _env("IMAGE_SAMPLER", "dpmpp_2m"))
    image_scheduler: str = field(default_factory=lambda: _env("IMAGE_SCHEDULER", "karras"))

    # --- Preferencias de contenido ---
    visual_style: str = field(
        default_factory=lambda: _env(
            "VISUAL_STYLE",
            "cinematic photorealistic, teal and orange color grading, dramatic rim lighting, "
            "film grain, 35mm lens, shallow depth of field, ultra detailed",
        )
    )
    language: str = field(default_factory=lambda: _env("LANGUAGE", "es"))

    # --- Modo demo ---
    force_demo: bool = field(default_factory=lambda: _env("DEMO_MODE").lower() in {"1", "true", "si"})

    # --- Propiedades calculadas ---
    @property
    def has_api_key(self) -> bool:
        """¿Tenemos clave para llamar a DeepSeek?"""
        return bool(self.deepseek_api_key) and not self.force_demo

    @property
    def demo_mode(self) -> bool:
        """Si no hay clave (o se forzó), el agente simula las respuestas."""
        return not self.has_api_key

    def ensure_dirs(self) -> None:
        """Crea las carpetas de trabajo si no existen."""
        for folder in (DATA_DIR, OUTPUT_DIR, IMAGES_DIR, PROMPTS_DIR):
            folder.mkdir(parents=True, exist_ok=True)


# Instancia global que importa el resto del proyecto
settings = Settings()
