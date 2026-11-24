# 🚀 PASO A PASO: de cero a tu primer video (y a GitHub)

Esta guía está pensada para alguien que **nunca ha usado Python en serio**. Vamos
despacio, con comandos de PowerShell listos para copiar y pegar. Al terminar vas a
tener la app funcionando, un video completo con sus imágenes y el proyecto publicado
en GitHub.

> 📌 Atajo: todo lo técnico está explicado a fondo en
> [`COMO_FUNCIONA.md`](COMO_FUNCIONA.md). Si algo no encaja, mira primero la
> sección **[Solución de problemas](#-solución-de-problemas)**.

---

## 🎯 1. Qué es este proyecto y qué vas a poder hacer

`ytagent` es un **agente de IA** que automatiza la parte pesada de un canal de
YouTube: organizar ideas, escribir guiones, crear **prompts masivos de imagen**
(decenas de imágenes 16:9, listas para una cola) y preparar la ficha del video (títulos,
descripción, tags y miniatura). La idea es la misma que la de una app de prompts en
cola: guion → lista larga de prompts → cola → imágenes.

Al terminar esta guía vas a poder:

- Abrir una **interfaz web local** (Streamlit) y crear un "video" con un título y un tema.
- Pedir **6 ideas** con nota, elegir una y **escribir el guion** completo.
- Generar **20 escenas** con su prompt de imagen en inglés.
- Generar **20 prompts masivos 16:9 (1024×576)** con *negative prompt* y *seed*.
- Enviarlos a **ComfyUI** en tu PC (RTX 4060 de 8 GB) y ver las imágenes aparecer.
- Generar **5 títulos, descripción, tags, miniatura y comentario fijado**.
- **Exportar** todo a `output/<nombre-del-video>/` y descargarlo.
- **Subir el proyecto a GitHub** sin subir nunca tu `.env`.

Y si un día no tienes clave de API, no pasa nada: hay un **modo demo** que genera
contenido de ejemplo y permite usar todo el flujo sin gastar ni un token.

---

## 🧰 2. Antes de empezar: qué necesitas

| Necesitas | Cómo lo compruebas | ¿Obligatorio? |
|---|---|---|
| Windows 10/11 con PowerShell | ya lo tienes | sí |
| Python 3.10 o superior (el proyecto probado con 3.12) | `python --version` | sí |
| El proyecto descargado en `C:\Users\LENGION\Downloads\vide de teerros shors` | — | sí |
| Cuenta de DeepSeek + clave | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) | no (modo demo) |
| ComfyUI + un modelo `.safetensors` | [comfy.org](https://www.comfy.org/) | no (puedes exportar prompts) |
| Git o GitHub Desktop | `git --version` | solo para el paso de GitHub |

### La clave de DeepSeek: de dónde salió y cómo cambiarla

La configuración vive en el archivo **`.env`** de la raíz del proyecto. Se creó
copiando `.env.example` y ahí se guarda la clave:

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-flash
LLM_TEMPERATURE=1.1
COMFYUI_URL=http://127.0.0.1:8188
VISUAL_STYLE=cinematic photorealistic, teal and orange color grading, ...
IMAGE_ASPECT=16:9
```

- **De dónde salió la clave:** este proyecto se montó en un equipo que ya tenía
  DeepSeek Harness instalado, y la clave se tomó de su configuración
  (`C:\Users\LENGION\.dsh\.credentials.yaml`) para poder probarlo de verdad. En un
  equipo nuevo: entra a `platform.deepseek.com`, crea una *API key* en la sección
  **API keys** y pégala en `.env`. Es una contraseña: no se comparte, no se pega en
  chats y **nunca** se sube a GitHub.
- **Cómo cambiarla:** abre el archivo con el Bloc de notas y edita esa línea:

  ```powershell
  notepad .env
  ```

  Guarda con `Ctrl + S`, cierra, y **reinicia la app** (`Ctrl + C` y vuelve a
  `.\start.bat`) para que la lea de nuevo.
- **Si no quieres usarla:** deja el campo vacío o activa el modo demo (lo verás en
  el paso 5). La app detecta que no hay clave y usa contenido de ejemplo.
- **Si el `.env` no existe** (por ejemplo, en otro PC): `Copy-Item .env.example .env`.

> 🔒 El `.env` está en `.gitignore`. Eso significa que Git lo ignora y **no se sube
> a GitHub**. Lo comprobaremos al final.

---

## 🪟 3. Abre PowerShell en la carpeta del proyecto

Hay tres formas; elige la que te resulte cómoda:

1. **Menú de inicio:** pulsa `Win + X` → *Terminal* o *Windows PowerShell*.
2. **Desde el Explorador:** entra a la carpeta, haz clic en la barra de direcciones,
   escribe `powershell` y pulsa `Enter`.
3. **Clic derecho:** dentro de la carpeta, `Shift + clic derecho` → *Abrir ventana de
   PowerShell aquí* (en Windows 11 puede llamarse *Abrir en Terminal*).

Ya en PowerShell, entra a la carpeta (las comillas son obligatorias por los espacios):

```powershell
cd "C:\Users\LENGION\Downloads\vide de teerros shors"
```

Comprueba que estás en el sitio correcto:

```powershell
Get-Location
Get-ChildItem
```

Debes ver `src`, `tests`, `docs`, `.env`, `requirements.txt`, `start.bat`, etc.

---

## 🐍 4. Activa el entorno virtual

El proyecto usa un **entorno virtual** (`.venv`): una carpeta con su propio Python y
sus propias librerías, para no ensuciar el Windows. Ya está creado en este equipo.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

- La primera línea **solo** desbloquea los scripts en esta ventana de PowerShell.
  Es segura y no cambia la configuración permanente del equipo.
- Si todo va bien, el *prompt* cambia y aparece `(.venv)` delante:

  ```text
  (.venv) PS C:\Users\LENGION\Downloads\vide de teerros shors>
  ```

> ⚠️ **Si PowerShell bloquea el script** con un mensaje como
> *"no se puede cargar el archivo ... Activate.ps1 porque la ejecución de scripts
> está deshabilitada en este sistema"*, ejecuta primero la línea de
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y vuelve a intentar.
> Si aun así falla, no pasa nada: **no hace falta activar nada**, usa siempre
> `.\.venv\Scripts\python.exe` en lugar de `python` (esta guía lo hace así en varios
> comandos para que no tengas problemas).

### Si el entorno virtual no existiera (otro PC o carpeta borrada)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> `python --version` debe ser 3.10 o superior. Si no tienes Python, instálalo desde
> [python.org](https://www.python.org/downloads/windows/) marcando *"Add python.exe
> to PATH"*.

---

## ✅ 5. Verifica que todo está instalado

Con el entorno activado (o usando el Python del `.venv` explícitamente), comprueba
las dependencias una por una:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -c "import streamlit; print('streamlit', streamlit.__version__)"
.\.venv\Scripts\python.exe -c "import pydantic, dotenv, requests, websocket; print('dependencias ok')"
```

Comprueba que el paquete del proyecto se puede importar (ojo con `PYTHONPATH`):

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -c "import ytagent; print('ytagent', ytagent.__version__)"
```

Y que la app "ve" tu configuración, la IA y ComfyUI:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m ytagent.cli estado
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m ytagent.cli probar
```

- `estado` muestra la carpeta, el modo de IA (`API deepseek-flash` o `DEMO`), la URL
  de ComfyUI, el estilo y los videos que ya existen.
- `probar` intenta hablar con DeepSeek (endpoint `/models`, no gasta tokens de
  generación) y con ComfyUI. Si ComfyUI no está abierto, avisará: es normal en este
  punto.

Opcionalmente, corre los tests (no necesitan GPU ni internet):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

> Si algo falla aquí, salta a **[Solución de problemas](#-solución-de-problemas)**.
> El error más típico es `No module named ytagent`, que se arregla ejecutando desde
> la raíz y definiendo `$env:PYTHONPATH="src"`.

---

## ▶️ 6. Arranca la app

### Opción A: el atajo de Windows (recomendado)

```powershell
.\start.bat
```

`start.bat` comprueba que existe `.venv`, define `PYTHONPATH`, abre el navegador y
lanza Streamlit en el puerto **8501**. Para cerrar: `Ctrl + C` en esa ventana.

### Opción B: el comando manual

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run src\ytagent\dashboard.py
```

Si ya activaste el entorno (paso 4), también puedes usar:

```powershell
$env:PYTHONPATH="src"; streamlit run src\ytagent\dashboard.py
```

Si el puerto 8501 está ocupado, cambia de puerto:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run src\ytagent\dashboard.py --server.port 8502
```

Abre el navegador en `http://localhost:8501` (o el puerto que hayas elegido). La
primera pantalla es la **"Fábrica de videos"** con una barra lateral y cinco
pestañas: **💡 Ideas**, **📖 Guion**, **🖼️ Prompts**, **📢 Publicar** y **❓ Ayuda**.

---

## 🎬 7. Usa la app paso a paso

### 7.1 Crea un video

1. En la barra lateral izquierda, abre **➕ Nuevo video**.
2. Escribe un **Título de trabajo** (ej. `El turno de las 3 AM`) y un
   **Tema / mundo** (ej. `camioneros misteriosos de noche`). El tema es el que
   alimenta las ideas; si lo dejas vacío, se usa el título.
3. Pulsa **Crear video**. La barra lateral mostrará `#1 · El turno de las 3 AM` y
   el estado `borrador`.

En la cabecera verás cuatro tarjetas de progreso: **💡 Ideas**, **📖 Guion**,
**🖼️ Imágenes** y **📢 Ficha**. Se van llenando solas.

### 7.2 Genera ideas

1. Ve a la pestaña **💡 Ideas**.
2. Ajusta el **Tema** (puedes cambiarlo aquí) y la **Cantidad** (de 1 a 12).
3. Pulsa **✨ Generar ideas**.
4. La IA devuelve ideas con **nota /10** (gancho, retención, originalidad y
   potencial visual). Lee el hook y la premisa y elige la mejor con
   **Usar esta idea**. La elegida queda marcada con ✅.

> 🔒 En modo demo verás ideas de ejemplo sobre camioneros: sirven para aprender el
> flujo; el contenido real es genérico a propósito.

### 7.3 Escribe el guion

1. Ve a la pestaña **📖 Guion**. Arriba verás la idea elegida.
2. Ajusta los **Minutos** (2 a 30) y las **Escenas** (6 a 40; 20 es un buen número).
3. Pulsa **✍️ Escribir guion**. Se hacen **dos llamadas a la IA**: primero el texto
   que se locuta y después la división en escenas con sus prompts.
4. Mira el resultado en **📝 Texto completo** y **🎥 Escenas**. Cada escena muestra
   narración, descripción visual, prompt de imagen (en inglés) y nota de edición.

> 💡 El guion de 8 minutos apunta a ~1040 palabras (130 por minuto), pensado para
> locutar en voz en off.

### 7.4 Genera los prompts masivos

1. Ve a la pestaña **🖼️ Prompts**.
2. Pulsa **🔁 Regenerar prompts**. Se crea **un prompt por escena** (20 escenas →
   20 prompts), con estilo del canal, *negative prompt* y *seed*.
3. Mira la galería (**🖼️ Vista de galería**) o la lista con el prompt completo,
   el negative y la seed.
4. Pulsa **💾 Exportar (txt/csv/json)** o descarga `prompts.txt` con el botón de la
   parte de abajo (`⬇️ Descargar prompts.txt`). Los archivos quedan además en
   `output/<slug>/` (por ejemplo `output/el-turno-de-las-3-am/`).

Este paso **no gasta tokens**: reutiliza los prompts que la IA ya escribió en las
escenas.

### 7.5 Envía la cola a ComfyUI

Primero instala y abre ComfyUI (paso 8). Después, en la pestaña **🖼️ Prompts**:

1. Pulsa **🔌 Probar conexión**. Si responde, verás la lista de checkpoints
   instalados; si no, el mensaje `No se pudo conectar con ComfyUI en ...`.
2. Pulsa **🚀 Iniciar cola (N)**, donde N son las imágenes pendientes.
3. La app envía cada prompt, espera a que ComfyUI lo genere y descarga el PNG. La
   barra de progreso muestra `N/M imágenes`. Si una imagen falla, la cola sigue con
   la siguiente y la marca en estado `error`.
4. Al terminar, las imágenes quedan en `output/_imagenes/img_001.png`,
   `img_002.png`, etc., y se ven en la galería.

### 7.6 Genera la ficha del video

1. Ve a la pestaña **📢 Publicar**.
2. Pulsa **✨ Generar títulos, descripción y tags**.
3. Tendrás **5 títulos**, una **descripción con capítulos** (`00:00 Intro...`),
   **tags**, **hashtags**, **texto de miniatura** (`3-5 palabras`), el
   **prompt de miniatura**, el **comentario fijado** y las **mejores horas**.

### 7.7 Exporta todo

En **📢 Publicar**, pulsa **💾 Exportar paquete completo**. La app escribe en
`output/<slug>/` (tolerando que falte alguna parte):

```text
output/el-turno-de-las-3-am/
├── guion.md          # guion legible (con tablas de escenas)
├── guion.txt         # solo narración, para TTS o teleprompter
├── guion.json        # guion crudo para programar
├── metadata.md       # ficha lista para copiar y pegar en YouTube Studio
├── metadata.json     # la misma ficha en JSON
├── prompts.txt       # 001. prompt + NEGATIVE: ...
├── prompts.csv       # tabla (Excel/Sheets) separada por ";"
└── prompts.json      # prompts + workflow de ComfyUI por si automatizas
```

Debajo aparecen botones **⬇️** para descargar cada archivo.

---

## 🖨️ 8. ComfyUI: instalar desde cero (y lo que ya está instalado aquí)

ComfyUI es el programa que convierte cada prompt en una imagen. Es local y gratuito;
con tu RTX 4060 de 8 GB funciona bien con modelos SDXL.

> ✅ **En ESTE equipo ya quedó instalado y verificado** (1.99 GB de programa + 6.46 GB
> de modelo + 376 MB de acelerador, en el disco `D:`):
> - Programa: `D:\ComfyUI\ComfyUI_windows_portable\` (versión 0.46.0, portable NVIDIA)
> - Arranque: `D:\ComfyUI\ComfyUI_windows_portable\run_nvidia_gpu.bat`
> - Modelo: `ComfyUI\models\checkpoints\sd_xl_base_1.0.safetensors`
> - Acelerador: `ComfyUI\models\loras\sdxl_lightning_4step_lora.safetensors`
> - Velocidad medida: **~27 segundos por imagen** a 1024×576.
> Si algún día lo reinstalas en otro PC, sigue los pasos de abajo.

### 8.1 Elige cómo instalarlo

- **ComfyUI Desktop** (más fácil): descarga el instalador para Windows desde
  [comfy.org](https://www.comfy.org/) y ejecútalo. Elige una carpeta para los
  modelos (por ejemplo `C:\Users\LENGION\Documents\ComfyUI\models`).
- **ComfyUI Portable** (lo que se usó aquí): descarga el 7z portátil para NVIDIA
  (`ComfyUI_windows_portable_nvidia.7z`) desde la sección *Releases* del repositorio
  de ComfyUI, descomprímelo y ejecuta `run_nvidia_gpu.bat`.
  Windows 11 descomprime `.7z` sin programas extra; también sirve 7-Zip.
  Si usas PowerShell, esto funciona tal cual:

  ```powershell
  # Descargar (ajusta la version a la ultima que veas en github.com/comfyanonymous/ComfyUI/releases)
  $url = "https://github.com/Comfy-Org/ComfyUI/releases/download/v0.46.0/ComfyUI_windows_portable_nvidia.7z"
  New-Item -ItemType Directory -Force -Path "D:\_descargas","D:\ComfyUI" | Out-Null
  curl.exe -L -o "D:\_descargas\ComfyUI.7z" $url
  # Descomprimir con el tar de Windows (lee .7z)
  tar -xf "D:\_descargas\ComfyUI.7z" -C "D:\ComfyUI"
  ```

En los dos casos, al abrir ComfyUI se levanta un servidor local en
`http://127.0.0.1:8188` y se abre su interfaz en el navegador. Deja esa ventana
abierta mientras uses ytagent.

### 8.2 Pon los modelos en su sitio

Los modelos `.safetensors` van en la carpeta **`models\checkpoints`**:

- **Portable:** `ComfyUI_windows_portable\ComfyUI\models\checkpoints\`
- **Desktop:** la carpeta de modelos que elegiste al instalar, seguida de
  `checkpoints\` (por ejemplo `C:\Users\LENGION\Documents\ComfyUI\models\checkpoints\`)

Copia el archivo `.safetensors` ahí y reinicia ComfyUI. Para comprobar que lo ve,
pulsa **🔌 Probar conexión** en ytagent: la app lista los modelos que ComfyUI ve.

Después, en el `.env`, pon el **nombre exacto** del archivo:

```text
COMFYUI_CHECKPOINT=sd_xl_base_1.0.safetensors
```

Si lo dejas vacío, ytagent usa el **primer** checkpoint instalado.

### 8.3 El acelerador LoRA (opcional pero recomendado)

El archivo `sdxl_lightning_4step_lora.safetensors` (376 MB) hace que una imagen
tarde **4 pasos en vez de 20**: pasa de ~2 minutos a ~27 segundos con casi la misma
calidad. Va en `ComfyUI\models\loras\` y se activa en el `.env`:

```text
COMFYUI_LORA=sdxl_lightning_4step_lora.safetensors
IMAGE_STEPS=4
IMAGE_CFG=1.5
IMAGE_SAMPLER=euler
IMAGE_SCHEDULER=sgm_uniform
```

Si borras el LoRA o dejas esas líneas vacías, ytagent vuelve solo a los valores
normales (20 pasos, cfg 6.5, dpmpp_2m/karras). Descarga del LoRA:

```powershell
$url = "https://huggingface.co/ByteDance/SDXL-Lightning/resolve/main/sdxl_lightning_4step_lora.safetensors"
curl.exe -L -o "D:\ComfyUI\ComfyUI_windows_portable\ComfyUI\models\loras\sdxl_lightning_4step_lora.safetensors" $url
```

### 8.4 El puerto 8188

ComfyUI escucha en el puerto **8188** por defecto. ytagent apunta ahí
(`COMFYUI_URL=http://127.0.0.1:8188`). No hace falta abrir el puerto en el router:
todo es local. Si usas firewall de terceros y te bloquea, permite la aplicación en
redes privadas. Si cambiaste el puerto de ComfyUI, actualiza `COMFYUI_URL`.

### 8.5 Modelos recomendados para 8 GB de VRAM

| Modelo | Tamaño aprox. | Nota |
|---|---|---|
| **SDXL Base 1.0** (`sd_xl_base_1.0.safetensors`) | ~6.46 GB | el instalado aquí; a 1024×576 va bien |
| **Juggernaut XL** (v9/v10) | ~7 GB | fotografía realista; muy popular para YouTube |
| **RealVisXL** (V4/V5) | ~7 GB | retratos y escenas realistas, buen detalle |

Consejos para 8 GB: genera de **una imagen a la vez** (ytagent ya lo hace),
mantén 1024×576 (16:9), usa el LoRA de 4 pasos, y cierra juegos u otros programas
que usen la GPU.

> **Flux:** es otro modelo más grande (12B parámetros). En 8 GB solo entra con
> **cuantización** (GGUF/FP8) y va justo y lento; además necesita nodos distintos
> (`UNETLoader`/GGUF) y el workflow de ytagent está hecho para un checkpoint SDXL
> normal (`CheckpointLoaderSimple`). Es decir: **Flux no funciona con este proyecto
> tal cual**. Para Flux usa la exportación a `prompts.txt`/`prompts.json`.

### 8.6 Si la app dice "ComfyUI no disponible"

Ese es el mensaje de `comfyui.diagnostico()`:
*"No se pudo conectar con ComfyUI en http://127.0.0.1:8188. Abre ComfyUI (o revisa
COMFYUI_URL en el archivo .env)."* Revisa, en este orden:

1. ¿ComfyUI está **abierto y terminó de cargar**? Debe responder en el navegador:
   `http://127.0.0.1:8188`. La primera vez tarda 1-2 minutos en levantar.
2. ¿La URL de `COMFYUI_URL` coincide? (Si cambiaste el puerto, cámbiala.)
3. ¿Otro programa ocupa el 8188?
   `netstat -ano | Select-String "8188"`
4. ¿Antivirus/firewall bloqueando la conexión local? Permite ComfyUI en redes privadas.
5. Vuelve a pulsar **🔌 Probar conexión** (a veces ComfyUI tarda en arrancar la cola).

Si conecta pero no hay modelos, el aviso será *"No hay checkpoints instalados..."*:
copia un `.safetensors` en `models\checkpoints` y reinicia ComfyUI.

Comando rápido para abrir ComfyUI desde PowerShell:

```powershell
& "D:\ComfyUI\ComfyUI_windows_portable\run_nvidia_gpu.bat"
```

---

## 🎨 9. Estilo visual y referencias

### El estilo del canal

El estilo es un texto en inglés que se añade a **todos** los prompts para que el
canal se vea uniforme. Vive en `VISUAL_STYLE` del `.env`:

```text
VISUAL_STYLE=cinematic photorealistic, teal and orange color grading, dramatic rim lighting, film grain, 35mm lens, shallow depth of field, ultra detailed
```

- **Para cambiarlo de forma permanente:** edita `VISUAL_STYLE` en el `.env`, guarda
  y reinicia la app. Después **regenera los prompts** (pestaña 🖼️ Prompts).
- **En la app:** en **⚙️ Ajustes** (barra lateral) hay estilos predefinidos
  (🎥 Cinematográfico, 🌑 Misterio, 🌅 Documental, 🌆 Neón, ☀️ Cálido) y una opción
  *✏️ Personalizado*. Ese estilo se usa al escribir las escenas **y** al generar los
  prompts masivos y las imágenes.
- **Relación de aspecto:** `IMAGE_ASPECT` (por defecto `16:9` = 1024×576). El
  selector de **⚙️ Ajustes** cambia el tamaño de los prompts que generes a partir de
  ese momento (el `.env` es el valor inicial).

### Las referencias de estilo

En la pestaña **🖼️ Prompts**, dentro de **03 · Referencias de estilo (opcional)**,
puedes subir imágenes PNG/JPG/WEBP que te gusten como inspiración. Se guardan en
`data/refs/` y quedan registradas en la base de datos. Hoy sirven como **guía
visual** para ti (no se envían automáticamente al modelo); el estilo se aplica por
texto con `VISUAL_STYLE` o con el selector de Ajustes.

---

## 🧭 10. Usa los prompts sin ComfyUI (Midjourney, Flux, Leonardo)

No necesitas GPU ni ComfyUI para aprovechar el agente. Los prompts son texto puro
en inglés y funcionan en cualquier generador.

1. Genera los prompts como siempre.
2. Expórtalos (**💾 Exportar (txt/csv/json)** o **💾 Exportar paquete completo**).
3. Usa `output/<slug>/prompts.txt`, que tiene este formato:

   ```text
   001. wide establishing shot of a lone semi truck on a desert highway at night, headlights cutting fog, cinematic photorealistic, teal and orange color grading
        NEGATIVE: text, letters, words, watermark, signature, logo, brand marks, blurry, ...
   002. ...
   ```

4. Según la herramienta:
   - **Midjourney (Discord/web):** pega el prompt en `/imagine` y añade
     `--ar 16:9`; el negative va con `--no text, watermark, logo, blurry`.
   - **Flux (web, fal, Replicate, etc.):** pega el prompt positivo; si la herramienta
     acepta campo negativo, copia la línea `NEGATIVE:`.
   - **Leonardo.ai:** pega el prompt, pon *aspect ratio 16:9* y usa el campo
     *negative prompt*.
   - **Excel/Sheets o herramientas por lotes:** usa `prompts.csv` (separado por `;`,
     con BOM para que Excel respete los acentos).
   - **Automatización:** `prompts.json` trae además el workflow de ComfyUI de cada
     prompt.

5. La **miniatura** tiene su propio prompt en `metadata.md` / `metadata.json`
   (campo `prompt_miniatura`): puedes generarla igual y luego ponerle el texto
   (`texto_miniatura`) en Canva o en cualquier editor.

---

## 💸 11. Controla el gasto de API

DeepSeek cobra **por tokens** (entrada y salida). El proyecto te da varias palancas:

- **Panel de uso:** en **⚙️ Ajustes** verás *"Tokens usados en esta sesión"*. Cada
  llamada a la IA suma tokens. La función `pipeline.uso_estimado()` calcula una
  estimación en dólares con precios de referencia (mira siempre la tarifa oficial
  de DeepSeek, pueden cambiar).
- **Elige el modelo:** en `.env`, `DEEPSEEK_MODEL=deepseek-flash` es el más barato y
  rápido (ideal para ideas y lotes); `deepseek-v4-pro` es más "inteligente" (mejor
  para guiones largos) y más caro. Empieza con `deepseek-flash`.
- **Baja la temperatura o los tokens máximos:** `LLM_TEMPERATURE` (1.1 por defecto) y
  `LLM_MAX_TOKENS` (8000 por defecto).
- **Pide menos:** menos ideas (`Cantidad`), menos escenas, videos más cortos. El
  guion pide ~130 palabras por minuto.
- **No repitas sin necesidad:** cada vez que pulsas *Generar ideas*, *Escribir
  guion* o *Generar ficha* se paga otra vez. Los prompts de imagen son gratis (se
  derivan del guion ya pagado).
- **Modo demo:** activa **⚙️ Ajustes → Modo demo (sin API)**, o añade `--demo` en la
  terminal, o pon `DEMO_MODE=1` en el `.env`. Todo el flujo funciona y no gasta nada.
- **`probar` no gasta:** consulta `/models`, no genera texto.

Si un error hace que la IA reintente (verás `[reintento ...]`), puede repetir la
llamada: revisa la clave y la conexión antes de insistir.

---

## 🐙 12. GitHub desde cero

Git guarda **instantáneas** de tu proyecto. GitHub es el sitio donde las publicas.
Aunque nunca hayas usado Git, solo necesitas entender cuatro palabras:

| Palabra | Qué es |
|---|---|
| **Repositorio (repo)** | la carpeta del proyecto con su historia de cambios |
| **Commit** | una *foto* de cómo está el proyecto en un momento, con un mensaje. Se puede volver a cualquier commit |
| **Rama (branch)** | una línea de commits. `main` es la principal (antes se llamaba `master`) |
| **Push** | subir tus commits locales al repositorio remoto (GitHub) |

### 12.1 Instala Git (todavía no lo tienes)

Comprueba si ya está:

```powershell
git --version
```

Si responde *"no se reconoce..."*, instálalo con `winget`:

```powershell
winget install --id Git.Git -e --source winget
```

Cierra y vuelve a abrir PowerShell para que coja el comando nuevo y comprueba:

```powershell
git --version
```

> ⚠️ Si `winget` no está disponible o falla (en algunos Windows 11 da error
> `0x8A150001`), tienes dos alternativas:
> 1. **GitHub Desktop** (lo más fácil, incluye Git): descárgalo de
>    [desktop.github.com](https://desktop.github.com/), instálalo e inicia sesión con
>    tu cuenta de GitHub. Con él puedes publicar el repo sin escribir comandos
>    (paso 12.6).
> 2. Instalador clásico de Git para Windows desde [git-scm.com](https://git-scm.com/download/win).

### 12.2 Configura tu identidad (una sola vez)

```powershell
git config --global user.name "LENGION"
git config --global user.email "tu-correo-de-github@ejemplo.com"
```

Usa el mismo correo con el que te registrarás en GitHub. Estas dos líneas solo se
ejecutan una vez en el equipo.

### 12.3 Inicia el repositorio local

```powershell
cd "C:\Users\LENGION\Downloads\vide de teerros shors"
git init
```

`git init` crea la carpeta oculta `.git`. Comprueba qué va a entrar en el primer commit:

```powershell
git status
```

> 👀 Antes de seguir, mira la lista con calma. Si aparece algún archivo personal
> (notas, capturas, pruebas) que **no** quieras publicar, bórralo o añádelo al
> `.gitignore`. `.env`, `.venv/`, `data/` y `output/` no aparecen: ya están
> ignorados. `README.md`, `docs/` y `LICENSE` sí aparecen, y está bien.

### 12.4 Primer commit

"Guardar el proyecto" en Git se hace en dos pasos: preparar y fotografiar.

```powershell
git add .
git commit -m "Primera versión de ytagent: agente de contenido para YouTube"
```

- `git add .` pone todos los cambios en la *zona de preparación* (staging).
- `git commit -m "..."` crea la foto con ese mensaje. Es tu primer commit.

Comprueba que quedó:

```powershell
git log --oneline
```

### 12.5 Crea el repositorio vacío en GitHub

1. Entra a [github.com](https://github.com) e inicia sesión (crea cuenta si no tienes).
2. Arriba a la derecha: **+** → **New repository**.
3. Nombre: `ytagent` (o el que quieras). Visibilidad: **Public** si quieres que
   cualquiera lo vea (recomendado para un portafolio), **Private** si no.
4. **No** marques *Add a README file*, ni .gitignore, ni licencia: ya tienes esos
   archivos en tu proyecto y chocarían.
5. Pulsa **Create repository**. GitHub te muestra la URL del repo, algo como
   `https://github.com/TU_USUARIO/ytagent.git`.

### 12.6 Conecta y sube

De vuelta en PowerShell, dentro del proyecto:

```powershell
git branch -M main
git remote add origin https://github.com/TU_USUARIO/ytagent.git
git push -u origin main
```

- `git branch -M main` renombra tu rama actual a `main` (el nombre que usa GitHub).
- `git remote add origin ...` le dice a Git dónde está el repo remoto; `origin` es
  solo un alias cómodo para esa URL.
- `git push -u origin main` sube tu rama `main` a `origin` y la deja enlazada
  (`-u`), así en el futuro basta con `git push`.

La primera vez puede abrirse una ventana del navegador para iniciar sesión en
GitHub. Si te pide usuario y contraseña, **GitHub ya no acepta contraseñas normales**:
crea un *token* en GitHub → *Settings* → *Developer settings* → *Personal access
tokens (classic)* → *Generate new token*, marca el permiso `repo` y úsalo como
contraseña (tu usuario es el nombre de usuario de GitHub).

Si prefieres GitHub Desktop: instálalo, inicia sesión, **File → Add local
repository** (elige la carpeta del proyecto) y pulsa **Publish repository**
(desmarca *Keep this code private* si quieres que sea público). GitHub Desktop hace
el `push` por ti.

### 12.7 Comprueba que el `.env` NO se subió (¡importante!)

En PowerShell, dentro del proyecto:

```powershell
git check-ignore -v .env
git ls-files | Select-String -Pattern "^\.env$"
```

- El primer comando debe responder algo así (significa que `.gitignore` lo protege):

  ```text
  .gitignore:2:.env	.env
  ```

- El segundo **no debe devolver nada** (`.env` no está en la lista de archivos
  rastreados). Si devuelve `.env`, **para todo** y revisa el paso 12.4: no hagas
  push con el archivo dentro.

También puedes abrir tu repo en el navegador y comprobar que solo están `.env.example`,
`README.md`, `LICENSE`, `docs/`, `src/`, `tests/`, `requirements.txt`,
`pyproject.toml`, `start.bat` y `.gitignore`.

> 🚨 **Si subiste el `.env` por error:** entra a
> [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys),
> **revoca esa clave y crea una nueva**, actualízala en tu `.env`, y después quita el
> archivo del repo:
>
> ```powershell
> git rm --cached .env
> git commit -m "Quitar .env del repositorio"
> git push
> ```
>
> Ojo: eso lo quita del último commit, pero **sigue en el historial**. Lo correcto es
> rotar la clave (que la vieja deje de funcionar) y, si el repo es público,
> plantearte borrarlo y volver a subirlo. Por eso se comprueba **antes** del primer
> push.

### 12.8 Tus siguientes cambios

Cada vez que cambies algo:

```powershell
git status
git add .
git commit -m "Describe lo que cambiaste"
git push
```

---

## 🧯 Solución de problemas

| Síntoma / error | Causa probable | Solución |
|---|---|---|
| `Falta DEEPSEEK_API_KEY en el archivo .env` | no hay clave y se intentó usar la API | pon la clave en `.env`, usa el modo demo o deja que `get_llm()` caiga en demo |
| `La clave de DeepSeek no es válida o caducó (revisa .env)` (HTTP 401) | clave mal copiada, revocada o de otra cuenta | copia de nuevo la clave desde `platform.deepseek.com`, guarda `.env` y reinicia la app; comprueba con `probar` |
| `No module named ytagent` | se ejecutó desde otra carpeta o sin `PYTHONPATH` | `cd` a la raíz y usa `$env:PYTHONPATH="src"`; o arranca con `.\start.bat` |
| `App did not start` / `Port 8501 is already in use` | otra app usa el puerto (a veces otra pestaña de Streamlit) | cierra la otra app o usa `--server.port 8502` |
| *"no se puede cargar el archivo ... porque la ejecución de scripts está deshabilitada"* | política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y vuelve a activar; o usa `.\.venv\Scripts\python.exe` sin activar |
| `pip` tarda mucho o da `ReadTimeoutError` | red lenta o proxy | `python -m pip install -r requirements.txt --timeout 120 --retries 5`; prueba otra red; actualiza pip con `-m pip install --upgrade pip` |
| La app dice *"No se pudo conectar con ComfyUI en http://127.0.0.1:8188"* | ComfyUI cerrado, otro puerto o firewall | abre ComfyUI, revisa `COMFYUI_URL`, comprueba `netstat -ano | Select-String "8188"` |
| *"El checkpoint configurado '...' no está instalado en ComfyUI"* | nombre del archivo distinto o modelo en otra carpeta | copia el `.safetensors` a `models\checkpoints` y pon el nombre exacto en `COMFYUI_CHECKPOINT` (o déjalo vacío) |
| Las imágenes salen con **texto, logos o manos raras** | el modelo intenta escribir y el prompt no lo evita | usa un checkpoint SDXL (Juggernaut/RealVis), mantén el negative con `text, letters, watermark...`, escribe prompts en inglés y no pidas "poster", "sign" ni "logo"; sube `steps` a 25-30 si hace falta |
| *"La IA no devolvió un JSON válido"* o el guion llega incompleto | respuesta truncada o con adornos | el agente reintenta solo; si insiste, baja `Minutos`/`Escenas`, cambia a `deepseek-v4-pro`, o vuelve a generar; el JSON truncado se intenta "curar" automáticamente |
| `.\start.bat` dice *"No encuentro el entorno virtual"* | falta `.venv` | crea el entorno: `python -m venv .venv` y `pip install -r requirements.txt` |
| Los acentos salen raros en la consola | codificación de Windows | `start.bat` ya hace `chcp 65001`; en la terminal usa `chcp 65001` antes de ejecutar |
| `git: command not found` al subir | Git no instalado o falta reiniciar PowerShell | instala Git (`winget` o GitHub Desktop), cierra y abre PowerShell; `git --version` |

---

## 📚 13. Qué estudiar después (por archivo)

Una forma ordenada de seguir aprendiendo: abre cada archivo, léelo y prueba a
cambiarlo. Todos tienen comentarios en español explicando el porqué.

| Archivo | Concepto de Python / ingeniería | Ejercicio sugerido |
|---|---|---|
| `src/ytagent/config.py` | variables de entorno, `python-dotenv`, `@dataclass`, `pathlib` | añade una variable nueva al `.env` (ej. `MI_NOMBRE`) y muéstrala en `estado` |
| `src/ytagent/schemas.py` | Pydantic, tipos, validadores, propiedades | añade un campo `musica` a `VideoMetadata` y muestra su valor en la pestaña Publicar |
| `src/ytagent/prompts.py` | *prompt engineering*, plantillas con `str.format` | cambia el tono del canal y compara los guiones |
| `src/ytagent/llm.py` | `requests`, JSON, reintentos, clases abstractas (`ABC`), manejo de errores | escribe un `MiLLM` que herede de `LLMBase` (aunque devuelva textos fijos) |
| `src/ytagent/store.py` | SQL, `sqlite3`, claves foráneas, migraciones | añade una consulta que cuente las ideas por video |
| `src/ytagent/image_prompts.py` | composición de prompts, expresiones regulares, CSV | añade la proporción `2:1` a `ASPECTOS` |
| `src/ytagent/comfyui.py` | API HTTP, workflows como JSON, polling, tests con servidor falso | cambia `steps` por defecto y observa la diferencia de tiempo/calidad |
| `src/ytagent/pipeline.py` | arquitectura por capas, callbacks de progreso | haz que `flujo_completo` exporte al final |
| `src/ytagent/dashboard.py` | Streamlit (`st.session_state`, pestañas, formularios) | añade un botón que borre el video actual (`store.borrar_video`) |
| `src/ytagent/exporters.py` | manejo de archivos y rutas, Markdown | exporta también un `.srt` de subtítulos |
| `src/ytagent/cli.py` | `argparse`, subcomandos, entrada/salida por consola | añade un comando `borrar` |
| `tests/` | `pytest`, monkeypatching, servidores falsos | escribe un test para `image_prompts.limpiar_prompt` |

Después de eso, los temas generales que te servirán: Git y GitHub (ramas, pull
requests, conflictos), entornos virtuales y `pip`, APIs REST y JSON, Pydantic,
SQLite/SQL, Streamlit, y fundamentos de generación de imágenes (modelos SDXL,
samplers, CFG, seeds).

---

## ✅ 14. Checklist final

- [ ] Abrí PowerShell en la carpeta del proyecto y activé `.venv`.
- [ ] Verifiqué `streamlit`, `pydantic` y `ytagent` con Python (paso 5).
- [ ] Arranqué la app con `.\start.bat` (o el comando manual) y abrió en el navegador.
- [ ] Creé un video, generé ideas y elegí una.
- [ ] Escribí el guion con 20 escenas.
- [ ] Generé y exporté los prompts masivos (`prompts.txt`).
- [ ] (Opcional) Instalé ComfyUI, puse un modelo y generé imágenes.
- [ ] Generé la ficha (títulos, descripción, tags, miniatura).
- [ ] Exporté el paquete completo a `output/<slug>/`.
- [ ] Instalé Git/GitHub Desktop y creé el repo.
- [ ] Hice el primer commit y `git push -u origin main`.
- [ ] Comprobé con `git check-ignore -v .env` que el `.env` NO se subió.
- [ ] Mi repo en GitHub se ve bien y tiene `README.md`, `docs/` y `LICENSE`.

¡Listo! Ya tienes un agente funcionando y un repo publicado. 🎉
