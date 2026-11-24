# 🎬 ytagent — Agente de IA para YouTube

**ytagent** convierte una idea suelta en un video completo de YouTube: propone ideas,
escribe el guion, lo divide en escenas, crea **prompts masivos de imagen** para
ComfyUI (o Midjourney/Flux) y prepara títulos, descripción, tags y miniatura.
Todo funciona en tu PC, sin depender de servicios de pago para las imágenes.

> Hecho para aprender Python desde cero y publicar el proyecto en GitHub.
> Interfaz visual en Streamlit + base de datos SQLite + IA de texto DeepSeek.

---

## ✨ Características

- 💡 **Ideas con nota**: propone varias ideas y les pone puntaje (gancho, retención, originalidad, visual) para que elijas la mejor.
- 📖 **Guion en dos pasos**: primero el texto que se locuta; después las escenas. Así la IA no corta la respuesta a la mitad.
- 🎬 **Escenas listas para editar**: cada plano trae narración, descripción visual, prompt en inglés y nota de edición.
- 🖼️ **Prompts masivos 16:9**: uno por escena (1024×576), con *negative prompt* y *seed* para repetir la misma imagen.
- 🖨️ **Cola de ComfyUI local**: envía los prompts a ComfyUI, espera cada trabajo y descarga las imágenes. Pensado para una RTX 4060 de 8 GB.
- 🎨 **Estilo del canal fijo**: un estilo visual se añade a todos los prompts para que el canal se vea uniforme.
- 👤 **Referencias de estilo**: puedes subir imágenes de referencia para inspirarte.
- 📢 **Ficha del video**: 5 títulos, descripción con capítulos, tags, hashtags, texto y prompt de miniatura, y comentario fijado.
- 📦 **Exportación total**: `guion.md`, `guion.txt`, `prompts.txt/csv/json`, `metadata.md/json` en `output/<video>/`.
- 🧪 **Modo demo**: sin clave de API la app genera contenido de ejemplo y todo el flujo funciona igual.
- 🗄️ **Base de datos local**: SQLite en `data/ytagent.db`. No hay que instalar ningún servidor.
- ✅ **Tests**: suite con `pytest` que simula un ComfyUI falso (no necesitas GPU para probar).

---

## 🔄 El flujo, en texto

```text
    💡 Idea              📖 Guion             🎬 Escenas         🖼️ Prompts masivos
 ┌─────────────┐      ┌──────────────┐     ┌──────────────┐    ┌──────────────────┐
 │ DeepSeek    │ ───> │ texto que    │ ──> │ 20 planos    │ ─> │ 20 prompts 16:9  │
 │ sugiere 6   │      │ se locuta    │     │ con narración│    │ + negative + seed│
 └─────────────┘      └──────────────┘     └──────────────┘    └────────┬─────────┘
                                                                       │
         ┌─────────────────────────────────────────────────────────────┤
         │                              ┌──────────────────┐           │
         └──  exportar ───>  📦       │ ComfyUI local    │  <────────┘
                              output/  │ (RTX 4060 8 GB)  │
                                       └────────┬─────────┘
                                                │ PNG 16:9
                                                ▼
                     📢 Ficha de YouTube (títulos, descripción, tags, miniatura)
```

---

## ✅ Requisitos

| Necesitas | Para qué | ¿Obligatorio? |
|---|---|---|
| Windows 10/11 | sistema operativo del proyecto | sí |
| Python 3.10 o superior (probado con 3.12) | ejecutar la app | sí |
| Cuenta en [DeepSeek](https://platform.deepseek.com/api_keys) | generar textos con IA | no (hay modo demo) |
| [ComfyUI](https://www.comfy.org/) + un modelo `.safetensors` | generar las imágenes | no (puedes exportar prompts) |
| Git (o GitHub Desktop) | subir el proyecto a GitHub | solo para publicar |

---

## 🚀 Instalación rápida

Abre **PowerShell** en la carpeta del proyecto y copia y pega:

```powershell
cd "C:\Users\LENGION\Downloads\vide de teerros shors"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

> Si ya existe un `.env` con tu clave (por ejemplo, en este equipo), **sáltate** el
> último comando: sobrescribiría tu configuración. Y si el `.venv` ya existe,
> también puedes saltarte su creación.

Después abre el archivo `.env` y pon tu clave real:

```text
DEEPSEEK_API_KEY=sk-tu-clave-aqui
```

> 💡 Si no tienes clave, **no pasa nada**: deja el `.env` como está y el agente
> entra en modo demo. Puedes activarlo también desde la interfaz.

> 🔒 El `.env` es privado: está en `.gitignore` y **nunca se sube a GitHub**.

### Arrancar la app

La forma más fácil (Windows):

```powershell
.\start.bat
```

O manualmente, desde la raíz del proyecto:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run src\ytagent\dashboard.py
```

Se abre en tu navegador en `http://localhost:8501`. Para cerrar: `Ctrl + C` en PowerShell.

📘 **Guía completa, paso a paso y con todos los detalles:**
[`docs/PASO_A_PASO.md`](docs/PASO_A_PASO.md)

---

## ⚙️ Configuración (`.env`)

Toda la configuración vive en el archivo `.env` de la raíz. Estas son las variables:

| Variable | Por defecto | Qué hace |
|---|---|---|
| `DEEPSEEK_API_KEY` | *(vacío)* | tu clave de DeepSeek; sin ella se activa el modo demo |
| `DEEPSEEK_MODEL` | `deepseek-flash` | modelo de texto: `deepseek-flash` (barato/rápido) o `deepseek-v4-pro` (mejor para guiones) |
| `LLM_TEMPERATURE` | `1.1` | creatividad del texto (0 = predecible, 2 = muy creativo) |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | dónde escucha ComfyUI |
| `COMFYUI_CHECKPOINT` | *(vacío)* | nombre exacto del `.safetensors`; vacío = usa el primero instalado |
| `VISUAL_STYLE` | `cinematic photorealistic, ...` | estilo que se añade a **todos** los prompts |
| `IMAGE_ASPECT` | `16:9` | relación de aspecto (→ 1024×576) |
| `LANGUAGE` | `es` | reservado para el idioma de los textos |
| `DEMO_MODE` | *(vacío)* | pon `1` para forzar el modo demo sin borrar la clave |

Copia siempre [`.env.example`](.env.example) como plantilla. Su valor de clave es
solo un ejemplo: reemplázalo por el tuyo.

---

## 🗂️ Estructura del proyecto

```text
ytagent/
├── src/ytagent/          # el motor del agente (Python)
│   ├── config.py         # claves, rutas y preferencias (.env)
│   ├── schemas.py        # contratos de datos validados con Pydantic
│   ├── llm.py            # DeepSeek + modo demo (interfaz LLMBase)
│   ├── prompts.py        # instrucciones maestras que recibe la IA
│   ├── store.py          # base de datos SQLite
│   ├── image_prompts.py  # composición y exportación de prompts masivos
│   ├── comfyui.py        # cliente de ComfyUI (workflow, cola, descargas)
│   ├── pipeline.py       # el flujo completo, paso a paso
│   ├── cli.py            # comandos de terminal
│   ├── dashboard.py      # interfaz visual (Streamlit)
│   └── exporters.py      # guion, metadata y paquete de archivos exportados
├── tests/                # pytest (ComfyUI falso, sin GPU)
├── docs/                 # documentación en español
├── data/                 # base de datos e imágenes (NO se sube a GitHub)
├── output/               # exportaciones por video (NO se sube a GitHub)
├── prompts/              # espacio para prompts maestros editables
├── .env.example          # plantilla de configuración
├── requirements.txt      # dependencias de Python
├── pyproject.toml        # metadatos del paquete + pytest + ruff
├── start.bat             # arranca la app con doble clic
└── README.md
```

📘 **Cómo funciona por dentro (arquitectura, base de datos, JSON, extensiones):**
[`docs/COMO_FUNCIONA.md`](docs/COMO_FUNCIONA.md)

---

## 🧪 Tests

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest -q
```

Los tests viven en `tests/`: [`test_comfyui.py`](tests/test_comfyui.py) simula un
servidor de ComfyUI con `http.server` (workflow, cola, descarga, diagnóstico) y
[`test_pipeline.py`](tests/test_pipeline.py) recorre el flujo completo en modo demo.
No necesitas GPU ni conexión a internet para correrlos.

---

## 🧱 Stack

- **Python 3.12** · `requests` · `pydantic` · `python-dotenv`
- **Streamlit** para la interfaz visual
- **DeepSeek** (`deepseek-flash` / `deepseek-v4-pro`) para el texto
- **ComfyUI** local (SDXL) para las imágenes
- **SQLite** (incluido en Python) para la base de datos
- **pytest** para los tests

---

## 🔒 Seguridad: claves de API

- El archivo `.env` **nunca** debe subirse a GitHub. Ya está protegido por `.gitignore`.
- Antes de tu primer `git push` comprueba que no aparece:
  `git check-ignore -v .env` (debe mostrar la regla de `.gitignore`).
- Si alguna vez subes una clave por error: **revócala y crea otra** en
  [platform.deepseek.com](https://platform.deepseek.com/api_keys). Borrar el archivo
  del último commit no borra el historial.
- Si compartes capturas de la app, tapa la parte del panel donde se ven tokens.

---

## 🧪 Modo demo (sin clave, sin coste)

El agente detecta si no hay clave y usa `DemoLLM`, que responde con contenido de
ejemplo coherente (ideas, guion, escenas, prompts y ficha). Sirve para aprender y
probar todo el flujo sin gastar tokens. Puedes activarlo de tres maneras:

1. Desde la interfaz: **⚙️ Ajustes → Modo demo (sin API)**.
2. En la terminal: añade `--demo` a `ideas`, `guion`, `metadata` o `automatico`.
3. En el `.env`: `DEMO_MODE=1` (y quítalo para volver a la API).

---

## 📄 Licencia

MIT © 2026 **LENGION**. Consulta el archivo [LICENSE](LICENSE).
