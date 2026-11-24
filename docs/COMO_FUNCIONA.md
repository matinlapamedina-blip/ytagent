# 🛠️ Cómo funciona ytagent por dentro

Este documento explica la arquitectura real del proyecto, módulo por módulo, para
que puedas mantenerlo, ampliarlo y entender **por qué** está hecho así. Está pensado
para el dueño del repo y para cualquiera que lo vea en GitHub.

Si lo que buscas es usarlo paso a paso, abre
[`PASO_A_PASO.md`](PASO_A_PASO.md). Si buscas la presentación del proyecto,
[`../README.md`](../README.md).

---

## 1. Vista general

`ytagent` es un **pipeline** (una cadena de pasos) donde cada módulo hace una sola
cosa y se comunica con los demás a través de datos ya validados. La interfaz
(Streamlit o CLI) no sabe *cómo* se genera nada: solo llama a `pipeline.py`.

```text
                        ┌──────────────────────────┐
        Usuario ───────>│  dashboard.py (Streamlit)│
                        │  cli.py (terminal)       │
                        └────────────┬─────────────┘
                                     │ llama funciones
                                     ▼
                        ┌──────────────────────────┐
                        │  pipeline.py             │  orquesta el flujo
                        └──┬─────┬─────┬─────┬─────┘
                           │     │     │     │
             ┌─────────────┘     │     │     └──────────────┐
             ▼                   ▼     ▼                    ▼
      ┌────────────┐     ┌──────────────┐  ┌──────────┐  ┌──────────────┐
      │ llm.py     │     │image_prompts │  │ store.py │  │ exporters.py │
      │ DeepSeek o │     │ .py          │  │ SQLite   │  │ .md/.txt/.json│
      │ DemoLLM    │     │ prompts 16:9 │  │data/     │  │ output/       │
      └─────┬──────┘     └──────┬───────┘  │ytagent.db│  └──────────────┘
            │                   │          └──────────┘
            ▼                   ▼
      ┌────────────┐     ┌──────────────┐   HTTP   ┌────────────────────┐
      │ prompts.py │     │ comfyui.py   │ ───────> │ ComfyUI 127.0.0.1  │
      │ plantillas │     │ workflow+cola│ <─────── │ :8188 (GPU local)  │
      └────────────┘     └──────┬───────┘  PNG     └────────────────────┘
                                ▼
                       output/_imagenes/*.png
```

### El flujo de datos, en orden

```text
1. Se crea un video            -> store.crear_video()            -> tabla videos
2. Se generan ideas            -> llm.generar_ideas()            -> tabla ideas
3. Se elige una idea           -> store.marcar_idea()            -> ideas.elegida = 1
4. Guion paso A (texto)        -> llm.generar_guion()            -> tabla scripts
5. Guion paso B (escenas)      -> llm.generar_escenas()          -> tabla scripts
6. Prompts masivos             -> image_prompts.desde_guion()    -> tabla image_prompts
7. Imágenes                    -> comfyui.generar_imagen()       -> output/_imagenes/
8. Ficha del video             -> llm.generar_metadata()         -> tabla metadata
9. Exportación                 -> exporters.exportar_paquete()   -> output/<slug>/
```

Estados del video (`videos.estado`): `borrador` → `ideas` → `guion` → `prompts`
→ `imagenes` → `metadata`. No existe una transición automática al estado `listo`:
tú decides cuándo está listo (la interfaz muestra iconos para todos los estados).

---

## 2. Cada archivo de `src/ytagent/`, en una tabla

| Archivo | Qué hace | Lo que expone (API pública) | Lee | Escribe |
|---|---|---|---|---|
| `config.py` | Carga el `.env` y concentra rutas, clave y preferencias en un objeto `Settings`. | `PROJECT_ROOT`, `DATA_DIR`, `OUTPUT_DIR`, `PROMPTS_DIR`, `DB_PATH`, `IMAGES_DIR`, `ENV_PATH`; clase `Settings` (campos y propiedades `has_api_key`, `demo_mode`, `ensure_dirs()`); instancia global `settings`. | Variables de entorno y `.env`. | Crea carpetas `data/`, `data/images/`, `output/`, `prompts/` cuando se llama `ensure_dirs()` (lo hacen `store.conectar()` y el arranque). No escribe configuración. |
| `schemas.py` | "Moldes" de datos validados con Pydantic. Es el contrato con la IA y con la base de datos. | `IdeaScore`, `Idea` (propiedad `nota`), `Scene`, `Script` (`texto_completo`, `palabras`), `ImagePrompt` (`prompt_con_estilo()`), `VideoMetadata`, `Usage` (`add()`), `VideoRecord`, `QueueJob`. | Nada (no hace E/S). | Nada. |
| `llm.py` | Habla con la API de DeepSeek y, si no hay clave, genera contenido de ejemplo. Convierte texto de la IA a objetos Pydantic. | `LLMError`; `extraer_json()`; `LLMBase` (interfaz abstracta); `DeepSeekLLM` (`probar_conexion()`); `DemoLLM`; `get_llm()`. | `.env`/`settings` (a través de `config`), las plantillas de `prompts.py`. | En memoria acumula `usage` (tokens); imprime avisos/reintentos en consola. No escribe archivos. |
| `prompts.py` | Las instrucciones maestras en español que recibe la IA. Aquí vive el "talento" del agente. | `ESTILO_NARRATIVO`, `IDEAS`, `GUION_TEXTO`, `ESCENAS`, `PROMPTS_IMAGEN`, `METADATA`, y `render(template, **kwargs)`. | Nada. | Nada. |
| `store.py` | Base de datos SQLite en un archivo. Crea el esquema, migra columnas nuevas y expone funciones de lectura/escritura. | `conectar()`, `ahora()`, `slugify()`; videos (`crear_video`, `listar_videos`, `obtener_video`, `actualizar_estado`, `borrar_video`); ideas (`guardar_ideas`, `listar_ideas`, `marcar_idea`, `idea_elegida`); guion (`guardar_guion`, `obtener_guion`); prompts (`guardar_prompts`, `listar_prompts`, `actualizar_prompt`, `cambiar_estado_prompts`); metadata (`guardar_metadata`, `obtener_metadata`); cola (`encolar_pendientes`, `siguiente_job`, `marcar_job`, `contar_jobs`); referencias (`agregar_referencia`, `listar_referencias`, `borrar_referencia`). | Esquema SQL y datos de `data/ytagent.db`. | `data/ytagent.db` (crea tablas, índices y migra columnas). |
| `image_prompts.py` | Convierte las escenas del guion en prompts listos para generar, y los exporta a txt/csv/json. | `ASPECTOS` (mapa de proporciones a píxeles), `NEGATIVE_BASE`, `tamano_para()`, `limpiar_prompt()`, `quitar_estilo()`, `componer()`, `desde_guion()`, `carpeta_prompts()`, `exportar_txt()`, `exportar_csv()`, `exportar_json()`, `exportar_todo()`. | El `Script` en memoria y `settings.visual_style` / `settings.image_aspect`. | `output/<slug>/prompts.txt`, `prompts.csv` y `prompts.json` (este último incluye el workflow de ComfyUI). |
| `comfyui.py` | Cliente HTTP de ComfyUI: arma el workflow, lo encola, espera el resultado y descarga el PNG. No usa WebSockets: consulta por HTTP. | `ComfyUIError`; `disponible()`, `listar_checkpoints()`, `construir_workflow()`, `encolar()`, `esperar_resultado()`, `descargar_imagen()`, `generar_imagen()`, `procesar_lote()`, `diagnostico()`. | ComfyUI en `settings.comfyui_url` (endpoints `/system_stats`, `/object_info`, `/prompt`, `/history`, `/queue`, `/view`). | Archivos PNG en la ruta `destino` que le pases; por defecto en `data/images/`. |
| `pipeline.py` | El flujo de trabajo completo: une `llm`, `store`, `image_prompts` y `exporters`. Es lo único que llaman la interfaz y la CLI. | `CONTEXTO_CANAL`; `generar_ideas()`, `escribir_guion()`, `generar_prompts()`, `generar_metadata()`, `crear_proyecto()`, `flujo_completo()`, `resumen_video()`, `carpeta_video()`, `exportar_prompts()`, `exportar_todo_el_paquete()`, `uso_estimado()`. | La base de datos (a través de `store`) y la IA (a través de `llm`). | La base de datos (ideas, guion, prompts, metadata, estado) y `output/` al exportar. |
| `cli.py` | Interfaz de terminal con `argparse`: permite usar el agente sin navegador. | `main()` y los comandos `estado`, `nuevo`, `ideas`, `guion`, `prompts`, `metadata`, `automatico`, `exportar`, `probar`. | Argumentos de la terminal, base de datos, IA, ComfyUI. | La base de datos y `output/` (a través de `pipeline`/`exporters`); mensajes por consola. |
| `dashboard.py` | Interfaz visual de una sola página con pestañas. También es el punto de entrada de `start.bat`. | `main()`; internamente `sidebar()`, `tab_ideas()`, `tab_guion()`, `tab_prompts()`, `tab_publicar()`, `_ejecutar_cola()`; añade `src/` al `sys.path` para poder ejecutarse como archivo. | Base de datos, `settings`, IA, ComfyUI, imágenes de referencia subidas. | La base de datos, `output/`, `data/refs/` (referencias subidas) e imágenes en `output/_imagenes/`. |
| `exporters.py` | Convierte lo guardado en la base de datos a archivos legibles/útiles. | `guion_a_markdown()`, `exportar_guion()`, `metadata_a_texto()`, `exportar_metadata()`, `exportar_guion_json()`, `exportar_paquete()`, `listar_archivos_exportados()`, `carpeta_de_prompts()`. | La base de datos (`store`). | `output/<slug>/guion.md`, `guion.txt`, `guion.json`, `metadata.md`, `metadata.json` y los prompts. |

> **Nota sobre `tests/`:** hay tests de ComfyUI (`test_comfyui.py`, que levanta un
> servidor HTTP falso) y del flujo completo en modo demo (`test_pipeline.py`).

---

## 3. La base de datos (`data/ytagent.db`)

SQLite guarda todo en **un solo archivo**: `data/ytagent.db`. No hay servidor que
instalar. `store.conectar()` crea las tablas si no existen, activa
`PRAGMA foreign_keys = ON` y ejecuta una migración segura (`_migrar`) que añade
columnas nuevas a bases antiguas sin perder datos.

| Tabla | Para qué sirve | Columnas principales | Relaciones |
|---|---|---|---|
| `videos` | Un video en producción. Es la "carpeta lógica" de todo lo demás. | `id`, `slug` (único), `titulo`, `tema`, `estado`, `creado`, `actualizado` | raíz del resto |
| `ideas` | Las ideas generadas para un video, con su nota y los datos completos en JSON. | `id`, `video_id`, `titulo`, `elegida` (0/1), `nota` (0-10), `datos` (JSON de `Idea`), `creado` | `video_id → videos.id` (borrado en cascada) |
| `scripts` | El guion completo (incluidas las escenas) de un video. | `video_id` (PK), `datos` (JSON de `Script`), `creado` | `video_id → videos.id` |
| `image_prompts` | Un prompt por imagen, con su estado y la ruta del PNG generado. | `id`, `video_id`, `numero`, `scene_numero`, `prompt`, `negative`, `seed`, `width` (1024), `height` (576), `estado`, `imagen`, `error`, `creado` | `video_id → videos.id` |
| `metadata` | La ficha de YouTube: títulos, descripción, tags, miniatura... | `video_id` (PK), `datos` (JSON de `VideoMetadata`), `creado` | `video_id → videos.id` |
| `jobs` | Cola de trabajos de imagen para procesar por lotes desde código. | `id`, `video_id`, `prompt_id`, `estado`, `error`, `creado` | `video_id → videos.id`, `prompt_id → image_prompts.id` |
| `ref_images` | Imágenes de referencia subidas desde la pestaña de prompts. | `id`, `nombre`, `ruta`, `peso`, `creado` | ninguna |

Estados posibles de un prompt (`image_prompts.estado` y `schemas.ImagePrompt`):
`pendiente` → `generando` → `listo` (o `error`, con el mensaje en `error`).

La interfaz ejecuta la cola recorriendo `image_prompts` directamente
(`dashboard._ejecutar_cola`). La tabla `jobs` y sus funciones (`encolar_pendientes`,
`siguiente_job`, `marcar_job`, `contar_jobs`) quedan disponibles para automatizar
lotes desde código o para un futuro "worker" separado.

Los JSON guardados (`ideas.datos`, `scripts.datos`, `metadata.datos`) son el
`model_dump_json()` del modelo Pydantic correspondiente. Al leerlos se reconstruyen
con `model_validate_json()`, así que la base de datos nunca devuelve datos "a medias".

---

## 4. Cómo se construye un prompt de imagen

Un prompt útil para SDXL/Flux no es una frase bonita: es una **ficha técnica**.
El proyecto pide a la IA (`PROMPTS_IMAGEN` en `prompts.py`) y arma (`image_prompts.py`)
esta estructura:

```text
sujeto + acción/detalle + escenario + hora del día + lente + iluminación + paleta + estilo del canal
```

Ejemplo real generado por el agente:

```text
wide establishing shot of a lone semi truck on a desert highway at night,
headlights cutting fog, 35mm lens, teal and orange color grading,
dramatic rim lighting, ultra detailed
```

### Las piezas

| Pieza | Dónde vive | Para qué |
|---|---|---|
| **Prompt positivo** | `ImagePrompt.prompt` → `image_prompts.componer()` | lo que quieres ver. En inglés funciona mejor en los modelos. |
| **Negative prompt** | `ImagePrompt.negative` / `NEGATIVE_BASE` | lo que **no** quieres: `text, letters, words, watermark, logo, blurry, deformed hands, extra fingers, cartoon...` |
| **Estilo del canal** | `settings.visual_style` (`.env`) | se añade al final de todos los prompts para que el canal se vea igual. `quitar_estilo()` evita duplicarlo si la IA ya lo escribió. |
| **Seed** | `ImagePrompt.seed` | número entero. Con la **misma seed**, los mismos ajustes y la misma versión del modelo sale la misma imagen. Sirve para repetir una toma buena o variar una mala cambiando la seed. |
| **Relación de aspecto** | `IMAGE_ASPECT` (`.env`) → `ASPECTOS` | `16:9` es lo normal en YouTube. `16:9` = **1024×576**. Otros valores: `9:16` (576×1024), `1:1` (768×768), `4:5` (768×960), `3:4` (768×1024), `21:9` (1152×512). Son múltiplos de 64 porque los modelos SDXL están entrenados con tamaños divisibles por 8/64. |

### Del guion al prompt

1. La IA devuelve, por escena, un `prompt_imagen` en inglés
   (si falta, se usa `visual` y, en último caso, la narración).
2. `desde_guion()` toma cada escena y llama a `componer()`, que:
   - limpia el texto (`limpiar_prompt`: sin saltos de línea ni comas dobles),
   - quita el estilo si ya estaba (`quitar_estilo`),
   - añade `settings.visual_style`,
   - fija el tamaño (`tamano_para`),
   - elige negative (`NEGATIVE_BASE`) y una seed aleatoria si no hay una fija.
3. El resultado se guarda en `image_prompts` con `estado = "pendiente"`.

### Del prompt a la imagen (`comfyui.py`)

`construir_workflow()` crea un workflow en formato **API** de ComfyUI con 7 nodos:

| Nodo | Clase | Función |
|---|---|---|
| `1` | `CheckpointLoaderSimple` | carga el modelo (`.safetensors`) + CLIP + VAE |
| `2` | `CLIPTextEncode` | prompt **positivo** |
| `3` | `CLIPTextEncode` | prompt **negativo** |
| `4` | `EmptyLatentImage` | lienzo vacío 1024×576 |
| `5` | `KSampler` | genera la imagen (por defecto `steps=20`, `cfg=6.5`, `dpmpp_2m` + `karras`) |
| `6` | `VAEDecode` | pasa el resultado a píxeles |
| `7` | `SaveImage` | guarda el PNG con prefijo `ytagent` |

Después: `/prompt` (encolar) → `/history/{id}` en bucle (esperar) → `/view`
(descargar) → guardar el PNG. El cliente tolera un fallo puntual de red y solo
aborta tras 3 fallos seguidos.

---

## 5. El diseño del JSON: por qué pedimos JSON y cómo lo validamos

### Por qué JSON

La IA de texto devuelve lenguaje natural. Para que un programa pueda usarla hay que
pedirle una **estructura fija**. Por eso:

- cada plantilla de `prompts.py` termina con `Devuelve SOLO un JSON válido con este formato exacto`,
- `DeepSeekLLM._llamar()` envía `response_format: {"type": "json_object"}`,
- cada respuesta se convierte en un modelo Pydantic (`Idea`, `Scene`, `ImagePrompt`,
  `VideoMetadata`).

Si la IA devuelve un dato inválido, Pydantic lanza un error **claro** (por ejemplo,
"la nota debe estar entre 0 y 10") en vez de dejar pasar basura a la base de datos.

### Qué pasa si la IA se equivoca

`llm.py` tiene tres capas de defensa:

1. **Tolerancia a adornos**: `extraer_json()` quita los bloques de código markdown
   que a veces envuelven al JSON, busca el `{...}` o `[...]` más externo y, si la
   respuesta está truncada a mitad,
   `_cerrar_json_incompleto()` intenta "curarla" cerrando comillas, llaves y
   corchetes abiertos.
2. **Reintentos**: `_llamar()` intenta hasta 3 veces bajando la temperatura
   (`settings.temperature`, `0.7`, `0.3`) y esperando 2, 4... segundos entre
   intentos. Un 401 (clave inválida) **no** se reintenta; un 429 o un 5xx sí.
3. **Validación por elemento**: si una idea, escena o prompt no valida, se descarta
   y se sigue con el resto (`print("[aviso] idea descartada...")`). Un elemento roto
   no tumba el lote entero. Si *ninguno* valida, se lanza `LLMError`.

Además, `_ruta()` busca nombres alternativos (`"escenas"`, `"scenes"`, `"items"`)
por si la IA cambia una clave. Y `Scene` normaliza `numero` cuando la IA devuelve
`"1"` o `1.0` en vez de `1`.

### Ejemplo de molde

```json
{
  "ideas": [
    {
      "titulo": "El turno que nadie quería",
      "hook": "A las 3 de la mañana no hay nadie en la carretera. Y eso es lo raro.",
      "premisa": "Un conductor acepta un turno nocturno por el doble de pago.",
      "puntos": {"hook": 9, "retencion": 8, "originalidad": 8, "visual": 9},
      "etiquetas": ["carretera", "noche"]
    }
  ]
}
```

`Idea` valida que `titulo` tenga al menos 3 caracteres, que `hook` tenga 5, que la
premisa tenga 10, y que cada nota esté entre 0 y 10. La propiedad `nota` calcula el
promedio de las 4 notas.

---

## 6. El "dos pasos" del guion (y por qué)

Escribir un guion + 20 escenas + 20 prompts en **una sola** respuesta de IA suele
fallar: la respuesta se corta al llegar al límite de tokens (`max_tokens`, por
defecto 8000) y el JSON queda incompleto. Por eso el guion se hace en dos llamadas:

```text
Paso A: generar_guion()     GUION_TEXTO  -> {titulo, hook, intro, desarrollo[], clímax, cierre, cta}
Paso B: generar_escenas()   ESCENAS      -> [{numero, duracion_seg, narracion, visual, prompt_imagen, nota_edicion}]
```

- **Paso A** pide ~130 palabras por minuto de narración (`duracion_min * 130`).
  Así un video de 8 minutos apunta a unas 1040 palabras.
- **Paso B** recibe el texto del guion. Si es muy largo, se recorta a 9000
  caracteres (`...`) para no reventar el contexto, y devuelve las escenas.
- `pipeline.escribir_guion()` guarda **dos veces** el guion: una sin escenas y otra
  con ellas; y recalcula `duracion_total_seg` sumando los segundos de las escenas.
- `generar_prompts()` es "de fábrica": **no gasta IA**, reutiliza los `prompt_imagen`
  de las escenas y compone los prompts masivos con el estilo del canal.

Ventaja extra: si el paso B falla, el guion ya está guardado y no hay que volver a
pagarlo. Podrías reintentar solo las escenas.

---

## 7. Cómo extender el proyecto

### 7.1 Otro proveedor de texto (OpenAI, Claude, Ollama...)

Todo está detrás de la interfaz `LLMBase` (`llm.py`). Crea una clase que implemente
los 6 métodos y listo:

```python
from .llm import LLMBase
from .schemas import Idea, ImagePrompt, Scene, Script, VideoMetadata

class MiProveedorLLM(LLMBase):
    @property
    def modo(self) -> str:
        return "mi-proveedor"

    def generar_ideas(self, tema: str, n: int, contexto: str = "") -> list[Idea]: ...
    def generar_guion(self, idea: Idea, duracion_min: int = 8, contexto: str = "") -> Script: ...
    def generar_escenas(self, guion: Script, n: int, estilo: str = "") -> list[Scene]: ...
    def generar_prompts(self, script: Script, n: int | None = None, estilo: str = "") -> list[ImagePrompt]: ...
    def generar_metadata(self, script: Script, contexto: str = "") -> VideoMetadata: ...
```

Y después dile a `get_llm()` cuándo usarlo (o instáncialo directamente donde lo
necesites). **No hay que tocar `pipeline.py`, `dashboard.py` ni `store.py`**: todos
trabajan con `LLMBase`.

### 7.2 Otro generador de imágenes (Automatic1111, DALL·E, API...)

`dashboard.py` usa tres cosas del módulo `comfyui`: `diagnostico()`,
`generar_imagen(prompt, negative, seed, width, height, destino)` y
`construir_workflow()` (este último desde `exporters`/`image_prompts` para el
`prompts.json`). Lo más limpio es crear un módulo hermano con esas mismas firmas y
cambiar el import en `dashboard._mod_comfyui()` y en `image_prompts.exportar_json()`.
Mantén el formato de `ImagePrompt` y el resto del flujo seguirá funcionando.

### 7.3 Otro idioma

Hoy los prompts y la interfaz están en español. La variable `LANGUAGE` del `.env`
se carga en `Settings.language`, pero **todavía no cambia nada**: es un hueco
reservado. Para otro idioma:

1. Traduce los textos de `prompts.py` (las reglas de `ESTILO_NARRATIVO` y las
   plantillas) o duplica las plantillas y elige según `settings.language`.
2. Traduce las etiquetas de `dashboard.py` y los textos de `cli.py`.
3. Los prompts de imagen **conviene dejarlos en inglés**: los modelos suelen
   responder mejor. Lo que se traduce es la narración y la ficha.

### 7.4 Otras ideas pequeñas

- Añadir más estilos al diccionario `ESTILOS_PRESET` de `dashboard.py`.
- Hacer que la cola use la tabla `jobs` (ya existen sus funciones en `store.py`).
- Añadir un "worker" que procese la cola aunque cierres la app.
- Añadir tests de `llm.py`, `store.py` y `image_prompts.py` en `tests/`.

---

## 8. Arquitectura de carpetas del repo

```text
vide de teerros shors/          <- raíz del repo
├── .env                        # privado: clave de API (NO se sube a GitHub)
├── .env.example                # plantilla pública de configuración
├── .gitignore                  # protege .env, .venv/, data/, output/...
├── start.bat                   # arranca la app (streamlit, puerto 8501)
├── README.md                   # presentación del proyecto
├── LICENSE                     # licencia MIT
├── pyproject.toml              # metadatos, dependencias, pytest y ruff
├── requirements.txt             # dependencias para pip
├── docs/
│   ├── PASO_A_PASO.md          # guía para usarlo y subirlo a GitHub
│   └── COMO_FUNCIONA.md        # este documento
├── src/
│   ├── __init__.py
│   └── ytagent/
│       ├── __init__.py         # versión y mapa de módulos
│       ├── config.py           # configuración central
│       ├── schemas.py          # modelos Pydantic
│       ├── llm.py              # DeepSeek + DemoLLM
│       ├── prompts.py          # instrucciones maestras
│       ├── store.py            # SQLite
│       ├── image_prompts.py    # prompts masivos
│       ├── comfyui.py          # cliente de ComfyUI
│       ├── pipeline.py         # flujo completo
│       ├── cli.py              # interfaz de terminal
│       ├── dashboard.py        # interfaz Streamlit
│       └── exporters.py        # exportadores
├── tests/
│   ├── test_comfyui.py         # cliente ComfyUI con servidor falso
│   └── test_pipeline.py        # flujo completo en modo demo
├── data/                       # generado: ytagent.db, images/, refs/ (no se sube)
├── output/                     # generado: exportaciones por video (no se sube)
├── prompts/                    # carpeta para prompts maestros editables (vacía hoy)
└── .venv/                      # entorno virtual (no se sube)
```

---

## 9. Resumen para quien llega nuevo al repo

1. `config.py` carga el `.env`; sin clave, `get_llm()` devuelve `DemoLLM` y el flujo
   funciona igual.
2. La interfaz solo llama a `pipeline.py`.
3. `pipeline.py` pide a `llm.py` los textos, los valida con `schemas.py`, los guarda
   en `store.py` (SQLite) y arma los prompts con `image_prompts.py`.
4. Para las imágenes, `comfyui.py` convierte cada prompt en un workflow de ComfyUI,
   lo encola, espera el resultado y descarga el PNG.
5. `exporters.py` convierte todo lo anterior en archivos listos para leer, locutar
   o subir a YouTube.

Eso es todo: once archivos, cada uno con una responsabilidad clara.
