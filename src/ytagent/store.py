"""Base de datos local (SQLite) del agente.

SQLite es una base de datos que vive en UN SOLO archivo (`data/ytagent.db`).
No necesitas instalar ningún servidor: viene incluida en Python.

Tablas:
    videos       -> cada video en producción (una "carpeta" lógica)
    ideas        -> las ideas generadas para un video
    scripts      -> el guion (JSON completo) de un video
    image_prompts-> los prompts masivos y su estado / imagen generada
    metadata     -> títulos, descripción, tags, miniatura
    jobs         -> cola de trabajos de imagen (para procesar por lotes)
    ref_images   -> imágenes de referencia para guiar el estilo
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from typing import Any

from .config import DB_PATH, settings
from .schemas import Idea, ImagePrompt, Script, VideoMetadata

# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

ESQUEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    titulo      TEXT NOT NULL,
    tema        TEXT DEFAULT '',
    estado      TEXT DEFAULT 'borrador',
    creado      TEXT NOT NULL,
    actualizado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ideas (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id  INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    titulo    TEXT NOT NULL,
    elegida   INTEGER DEFAULT 0,
    nota      REAL DEFAULT 0,
    datos     TEXT NOT NULL,
    creado    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scripts (
    video_id  INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    datos     TEXT NOT NULL,
    creado    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS image_prompts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    numero       INTEGER NOT NULL,
    scene_numero INTEGER DEFAULT 0,
    prompt       TEXT NOT NULL,
    negative     TEXT DEFAULT '',
    seed         INTEGER,
    width        INTEGER DEFAULT 1024,
    height       INTEGER DEFAULT 576,
    estado       TEXT DEFAULT 'pendiente',
    imagen       TEXT DEFAULT '',
    error        TEXT DEFAULT '',
    creado       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    video_id INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
    datos    TEXT NOT NULL,
    creado   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id  INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    prompt_id INTEGER NOT NULL REFERENCES image_prompts(id) ON DELETE CASCADE,
    estado    TEXT DEFAULT 'pendiente',
    error     TEXT DEFAULT '',
    creado    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ref_images (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT NOT NULL,
    ruta     TEXT NOT NULL,
    peso     INTEGER DEFAULT 0,
    creado   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ideas_video ON ideas(video_id);
CREATE INDEX IF NOT EXISTS idx_prompts_video ON image_prompts(video_id);
CREATE INDEX IF NOT EXISTS idx_jobs_estado ON jobs(estado);
"""


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    """Abre la base de datos, crea las tablas si no existen y activa claves foráneas."""
    settings.ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    _migrar(conn)
    conn.commit()
    return conn


def _migrar(conn: sqlite3.Connection) -> None:
    """Añade columnas nuevas a bases de datos antiguas (sin perder datos).

    Cada migración es segura de ejecutar varias veces: solo añade si falta.
    """
    columnas = {fila[1] for fila in conn.execute("PRAGMA table_info(image_prompts)")}
    nuevas = {
        "width": "INTEGER DEFAULT 1024",
        "height": "INTEGER DEFAULT 576",
        "error": "TEXT DEFAULT ''",
    }
    for nombre, tipo in nuevas.items():
        if nombre not in columnas:
            conn.execute(f"ALTER TABLE image_prompts ADD COLUMN {nombre} {tipo}")


def slugify(texto: str, maxlargo: int = 60) -> str:
    """Convierte 'El turno de noche' en 'el-turno-de-noche' (para nombres de carpeta)."""
    limpio = re.sub(r"[^\w\s-]", "", texto.lower(), flags=re.UNICODE)
    limpio = re.sub(r"[\s_-]+", "-", limpio).strip("-")
    return (limpio or "video")[:maxlargo]


# ---------------------------------------------------------------------------
# VIDEOS
# ---------------------------------------------------------------------------


def crear_video(titulo: str, tema: str = "") -> int:
    """Crea un video nuevo y devuelve su id. Si el slug existe, le añade un número."""
    conn = conectar()
    slug_base = slugify(titulo)
    slug = slug_base
    n = 2
    while conn.execute("SELECT 1 FROM videos WHERE slug = ?", (slug,)).fetchone():
        slug = f"{slug_base}-{n}"
        n += 1
    cur = conn.execute(
        "INSERT INTO videos (slug, titulo, tema, estado, creado, actualizado) VALUES (?,?,?,?,?,?)",
        (slug, titulo, tema, "borrador", ahora(), ahora()),
    )
    conn.commit()
    nuevo_id = int(cur.lastrowid)
    conn.close()
    return nuevo_id


def listar_videos() -> list[dict[str, Any]]:
    conn = conectar()
    filas = conn.execute(
        """
        SELECT v.*,
               (SELECT COUNT(*) FROM image_prompts p WHERE p.video_id = v.id) AS n_prompts,
               (SELECT COUNT(*) FROM image_prompts p WHERE p.video_id = v.id AND p.estado = 'listo') AS n_listos
        FROM videos v ORDER BY v.id DESC
        """
    ).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def obtener_video(video_id: int) -> dict[str, Any] | None:
    conn = conectar()
    fila = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    conn.close()
    return dict(fila) if fila else None


def actualizar_estado(video_id: int, estado: str) -> None:
    conn = conectar()
    conn.execute(
        "UPDATE videos SET estado = ?, actualizado = ? WHERE id = ?", (estado, ahora(), video_id)
    )
    conn.commit()
    conn.close()


def borrar_video(video_id: int) -> None:
    """Borra el video y todo lo suyo (las claves foráneas en cascada hacen el resto)."""
    conn = conectar()
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# IDEAS
# ---------------------------------------------------------------------------


def guardar_ideas(video_id: int, ideas: list[Idea]) -> None:
    """Reemplaza las ideas anteriores del video por las nuevas."""
    conn = conectar()
    conn.execute("DELETE FROM ideas WHERE video_id = ?", (video_id,))
    for idea in ideas:
        conn.execute(
            "INSERT INTO ideas (video_id, titulo, elegida, nota, datos, creado) VALUES (?,?,?,?,?,?)",
            (video_id, idea.titulo, 0, idea.nota, idea.model_dump_json(), ahora()),
        )
    conn.commit()
    conn.close()


def listar_ideas(video_id: int) -> list[dict[str, Any]]:
    conn = conectar()
    filas = conn.execute(
        "SELECT * FROM ideas WHERE video_id = ? ORDER BY nota DESC", (video_id,)
    ).fetchall()
    conn.close()
    resultado = []
    for f in filas:
        d = dict(f)
        d["idea"] = Idea.model_validate_json(d["datos"])
        resultado.append(d)
    return resultado


def marcar_idea(video_id: int, idea_id: int) -> Idea | None:
    """Marca UNA idea como la elegida y devuelve sus datos."""
    conn = conectar()
    fila = conn.execute(
        "SELECT datos FROM ideas WHERE id = ? AND video_id = ?", (idea_id, video_id)
    ).fetchone()
    if not fila:
        conn.close()
        return None
    conn.execute("UPDATE ideas SET elegida = 0 WHERE video_id = ?", (video_id,))
    conn.execute("UPDATE ideas SET elegida = 1 WHERE id = ?", (idea_id,))
    conn.commit()
    conn.close()
    return Idea.model_validate_json(fila["datos"])


def idea_elegida(video_id: int) -> Idea | None:
    conn = conectar()
    fila = conn.execute(
        "SELECT datos FROM ideas WHERE video_id = ? AND elegida = 1", (video_id,)
    ).fetchone()
    conn.close()
    return Idea.model_validate_json(fila["datos"]) if fila else None


# ---------------------------------------------------------------------------
# GUION
# ---------------------------------------------------------------------------


def guardar_guion(video_id: int, script: Script) -> None:
    conn = conectar()
    conn.execute(
        "INSERT INTO scripts (video_id, datos, creado) VALUES (?,?,?) "
        "ON CONFLICT(video_id) DO UPDATE SET datos = excluded.datos, creado = excluded.creado",
        (video_id, script.model_dump_json(), ahora()),
    )
    conn.commit()
    conn.close()


def obtener_guion(video_id: int) -> Script | None:
    conn = conectar()
    fila = conn.execute("SELECT datos FROM scripts WHERE video_id = ?", (video_id,)).fetchone()
    conn.close()
    return Script.model_validate_json(fila["datos"]) if fila else None


# ---------------------------------------------------------------------------
# PROMPTS DE IMAGEN
# ---------------------------------------------------------------------------


def guardar_prompts(video_id: int, prompts: list[ImagePrompt]) -> None:
    conn = conectar()
    conn.execute("DELETE FROM image_prompts WHERE video_id = ?", (video_id,))
    for p in prompts:
        conn.execute(
            """INSERT INTO image_prompts
               (video_id, numero, scene_numero, prompt, negative, seed, width, height,
                estado, imagen, creado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                video_id,
                p.numero,
                p.scene_numero,
                p.prompt,
                p.negative,
                p.seed,
                p.width,
                p.height,
                p.estado,
                p.imagen,
                ahora(),
            ),
        )
    conn.commit()
    conn.close()


def listar_prompts(video_id: int) -> list[dict[str, Any]]:
    conn = conectar()
    filas = conn.execute(
        "SELECT * FROM image_prompts WHERE video_id = ? ORDER BY numero", (video_id,)
    ).fetchall()
    conn.close()
    return [dict(f) for f in filas]


def actualizar_prompt(prompt_id: int, **campos: Any) -> None:
    """Actualiza columnas sueltas: estado, imagen, error..."""
    permitidos = {"estado", "imagen", "error", "seed", "negative", "prompt"}
    campos = {k: v for k, v in campos.items() if k in permitidos}
    if not campos:
        return
    sets = ", ".join(f"{k} = ?" for k in campos)
    conn = conectar()
    conn.execute(f"UPDATE image_prompts SET {sets} WHERE id = ?", (*campos.values(), prompt_id))
    conn.commit()
    conn.close()


def cambiar_estado_prompts(video_id: int, estado: str) -> None:
    conn = conectar()
    conn.execute("UPDATE image_prompts SET estado = ? WHERE video_id = ?", (estado, video_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------


def guardar_metadata(video_id: int, meta: VideoMetadata) -> None:
    conn = conectar()
    conn.execute(
        "INSERT INTO metadata (video_id, datos, creado) VALUES (?,?,?) "
        "ON CONFLICT(video_id) DO UPDATE SET datos = excluded.datos, creado = excluded.creado",
        (video_id, meta.model_dump_json(), ahora()),
    )
    conn.commit()
    conn.close()


def obtener_metadata(video_id: int) -> VideoMetadata | None:
    conn = conectar()
    fila = conn.execute("SELECT datos FROM metadata WHERE video_id = ?", (video_id,)).fetchone()
    conn.close()
    return VideoMetadata.model_validate_json(fila["datos"]) if fila else None


# ---------------------------------------------------------------------------
# COLA DE TRABAJOS
# ---------------------------------------------------------------------------


def encolar_pendientes(video_id: int) -> int:
    """Mete en la cola todos los prompts del video que aún no tienen imagen."""
    conn = conectar()
    prompts = conn.execute(
        "SELECT id FROM image_prompts WHERE video_id = ? AND estado IN ('pendiente','error')",
        (video_id,),
    ).fetchall()
    creados = 0
    for p in prompts:
        conn.execute(
            "INSERT INTO jobs (video_id, prompt_id, estado, creado) VALUES (?,?,?,?)",
            (video_id, p["id"], "pendiente", ahora()),
        )
        creados += 1
    conn.commit()
    conn.close()
    return creados


def siguiente_job() -> dict[str, Any] | None:
    """Saca el siguiente trabajo pendiente (con los datos del prompt)."""
    conn = conectar()
    fila = conn.execute(
        """
        SELECT j.id AS job_id, j.video_id, j.prompt_id, p.numero, p.prompt, p.negative, p.seed
        FROM jobs j JOIN image_prompts p ON p.id = j.prompt_id
        WHERE j.estado = 'pendiente' ORDER BY j.id LIMIT 1
        """
    ).fetchone()
    conn.close()
    return dict(fila) if fila else None


def marcar_job(job_id: int, estado: str, error: str = "") -> None:
    conn = conectar()
    conn.execute("UPDATE jobs SET estado = ?, error = ? WHERE id = ?", (estado, error, job_id))
    conn.commit()
    conn.close()


def contar_jobs(video_id: int | None = None) -> dict[str, int]:
    """Cuenta trabajos por estado: {"pendiente": 3, "listo": 10, ...}"""
    conn = conectar()
    if video_id is None:
        filas = conn.execute("SELECT estado, COUNT(*) c FROM jobs GROUP BY estado").fetchall()
    else:
        filas = conn.execute(
            "SELECT estado, COUNT(*) c FROM jobs WHERE video_id = ? GROUP BY estado", (video_id,)
        ).fetchall()
    conn.close()
    return {f["estado"]: f["c"] for f in filas}


# ---------------------------------------------------------------------------
# IMÁGENES DE REFERENCIA
# ---------------------------------------------------------------------------


def agregar_referencia(nombre: str, ruta: str, peso: int = 1) -> int:
    conn = conectar()
    cur = conn.execute(
        "INSERT INTO ref_images (nombre, ruta, peso, creado) VALUES (?,?,?,?)",
        (nombre, ruta, peso, ahora()),
    )
    conn.commit()
    conn.close()
    return int(cur.lastrowid)


def listar_referencias() -> list[dict[str, Any]]:
    conn = conectar()
    filas = conn.execute("SELECT * FROM ref_images ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(f) for f in filas]


def borrar_referencia(ref_id: int) -> None:
    conn = conectar()
    conn.execute("DELETE FROM ref_images WHERE id = ?", (ref_id,))
    conn.commit()
    conn.close()
