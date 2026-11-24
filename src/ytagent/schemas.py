"""Moldes de datos (schemas) del agente.

Cada clase aquí es un **contrato**: define qué campos esperamos de la IA.
Pydantic valida esos campos automáticamente. Si la IA devuelve basura,
Pydantic lanza un error claro en lugar de dejar pasar datos rotos.

Piensa en esto como el "formulario" que la IA debe rellenar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ===========================================================================
# 1) IDEAS
# ===========================================================================


class IdeaScore(BaseModel):
    """Notas de 0 a 10 para decidir qué idea merece producirse."""

    hook: int = Field(0, ge=0, le=10, description="Fuerza del gancho inicial")
    retencion: int = Field(0, ge=0, le=10, description="Capacidad de retener al espectador")
    originalidad: int = Field(0, ge=0, le=10, description="Qué tan distinta es la idea")
    visual: int = Field(0, ge=0, le=10, description="Cuánto potencial visual tiene")


class Idea(BaseModel):
    """Una idea de video lista para evaluar."""

    titulo: str = Field(..., min_length=3, description="Título de trabajo del video")
    hook: str = Field(..., min_length=5, description="Primera frase que atrapa al espectador")
    premisa: str = Field(..., min_length=10, description="De qué trata en 1-2 frases")
    angulo: str = Field("", description="El giro único / punto de vista")
    final: str = Field("", description="Cómo cierra el video")
    puntos: IdeaScore = Field(default_factory=IdeaScore)
    etiquetas: list[str] = Field(default_factory=list)

    @property
    def nota(self) -> float:
        """Promedio simple de las 4 notas (0-10)."""
        s = self.puntos
        return round((s.hook + s.retencion + s.originalidad + s.visual) / 4, 1)


# ===========================================================================
# 2) GUION Y ESCENAS
# ===========================================================================


class Scene(BaseModel):
    """Un "plano" del video: un trozo de narración + la imagen que lo acompaña."""

    numero: int = Field(..., ge=1, description="Orden del plano, empieza en 1")
    duracion_seg: int = Field(6, ge=2, le=60, description="Segundos aproximados en pantalla")
    narracion: str = Field(..., min_length=3, description="Lo que dice el narrador")
    visual: str = Field("", description="Descripción visual en español (qué se ve)")
    prompt_imagen: str = Field("", description="Prompt en INGLÉS para el generador de imagen")
    nota_edicion: str = Field("", description="Transición, corte o efecto sugerido")

    @field_validator("numero", mode="before")
    @classmethod
    def _int_numero(cls, v: object) -> int:
        # A veces la IA devuelve "1" o 1.0; lo normalizamos
        try:
            return int(float(str(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 1


class Script(BaseModel):
    """El guion completo del video."""

    titulo: str = Field(..., min_length=3)
    hook: str = Field(..., description="Gancho de los primeros 3-5 segundos")
    intro: str = Field("", description="Contexto inicial")
    desarrollo: list[str] = Field(default_factory=list, description="Bloques del cuerpo")
    clímax: str = Field("", description="Punto de máxima tensión")
    cierre: str = Field("", description="Final o llamada a la acción")
    escenas: list[Scene] = Field(default_factory=list, description="Lista de planos")
    duracion_total_seg: int = Field(0, ge=0)
    cta: str = Field("", description="Llamada a la acción final")

    @property
    def texto_completo(self) -> str:
        """Todo el guion como texto corrido (útil para exportar)."""
        partes = [self.hook, self.intro, *self.desarrollo, self.clímax, self.cierre, self.cta]
        return "\n\n".join(p.strip() for p in partes if p and p.strip())

    @property
    def palabras(self) -> int:
        return len(self.texto_completo.split())


# ===========================================================================
# 3) PROMPTS MASIVOS DE IMAGEN
# ===========================================================================


class ImagePrompt(BaseModel):
    """Un prompt de imagen listo para enviar a ComfyUI / Midjourney / Flux."""

    numero: int = Field(..., ge=1)
    scene_numero: int = Field(0, ge=0, description="Escena del guion a la que pertenece")
    prompt: str = Field(..., min_length=10, description="Prompt principal en inglés")
    negative: str = Field("", description="Negative prompt (lo que NO debe salir)")
    seed: int | None = Field(None, description="Semilla fija para reproducir la imagen")
    width: int = Field(1024)
    height: int = Field(576)
    estado: Literal["pendiente", "generando", "listo", "error"] = "pendiente"
    imagen: str = Field("", description="Ruta del archivo generado")

    def prompt_con_estilo(self, estilo: str) -> str:
        """Une el prompt con el estilo fijo del canal."""
        if not estilo:
            return self.prompt
        return f"{self.prompt}, {estilo}"


# ===========================================================================
# 4) METADATA DE YOUTUBE
# ===========================================================================


class VideoMetadata(BaseModel):
    """Todo lo que va en la ficha del video al publicarlo."""

    titulos: list[str] = Field(default_factory=list, description="5 opciones de título (150 caracteres máx.)")
    descripcion: str = Field("", description="Descripción completa con capítulos")
    tags: list[str] = Field(default_factory=list, description="Etiquetas para el buscador")
    hashtags: list[str] = Field(default_factory=list)
    texto_miniatura: str = Field("", description="3-5 palabras que van sobre la miniatura")
    prompt_miniatura: str = Field("", description="Prompt para generar la miniatura")
    comentario_fijado: str = Field("", description="Comentario para fijar y mover interacción")
    horas_publicacion: list[str] = Field(default_factory=list, description="Mejores horas para subir")


# ===========================================================================
# 5) REGISTRO DE TRABAJOS (queues) Y USO DE TOKENS
# ===========================================================================


class Usage(BaseModel):
    """Gasto de una llamada a la IA (para controlar costos)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llamadas: int = 0

    def add(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            llamadas=self.llamadas + other.llamadas,
        )


class VideoRecord(BaseModel):
    """Una fila de la tabla `videos` (un video en producción)."""

    id: int = 0
    slug: str = ""
    titulo: str = ""
    estado: str = "borrador"  # borrador -> guion -> prompts -> imagenes -> listo
    creado: datetime | None = None


class QueueJob(BaseModel):
    """Un trabajo de la cola de imágenes."""

    id: int = 0
    video_id: int = 0
    prompt: str = ""
    estado: str = "pendiente"  # pendiente -> generando -> listo -> error
    imagen: str = ""
    error: str = ""
