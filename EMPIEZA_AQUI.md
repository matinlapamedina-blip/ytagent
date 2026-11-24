# ⚡ TUS ENLACES Y COMANDOS (empieza por aquí)

Todo está en marcha en tu PC. Guarda este archivo: es tu “panel de control”.

---

## 1. Ahora mismo está todo encendido

| Qué | Dónde | Estado |
|---|---|---|
| 🎬 **Tu app** (fábrica de videos) | http://127.0.0.1:8501 | ✅ funcionando |
| 🖨️ **ComfyUI** (genera las imágenes) | http://127.0.0.1:8188 | ✅ funcionando |
| ☁️ **Tu proyecto en GitHub** | https://github.com/matinlapamedina-blip/ytagent | ✅ subido |

Abre la app en el navegador y prueba: ya hay un video de ejemplo (**El turno de las 3 AM**)
con 18 imágenes generadas.

---

## 2. Cómo lo vuelves a encender (después de reiniciar el PC)

Abre **dos** ventanas de PowerShell en la carpeta del proyecto:

```powershell
cd "C:\Users\LENGION\Downloads\vide de teerros shors"
```

**Ventana 1 — ComfyUI** (las imágenes). La primera vez tarda 1-2 minutos:

```powershell
.\abrir_comfyui.bat
```

**Ventana 2 — la app:**

```powershell
.\start.bat
```

Luego abre http://127.0.0.1:8501 en el navegador.

> Si el puerto 8501 está ocupado, prueba `--server.port 8502` al final del comando,
> o cierra la ventana vieja.

---

## 3. El flujo de trabajo (lo que hace el agente)

```
1. Creas un video        →  barra lateral: "➕ Nuevo video"
2. Generas ideas         →  pestaña 💡 Ideas (te da 6 con nota)
3. Eliges una            →  botón "Usar esta idea"
4. Escribe el guion      →  pestaña 📖 Guion (texto + 18 escenas)
5. Genera prompts        →  pestaña 🖼️ Prompts (18 prompts 16:9)
6. Genera las imágenes   →  "🔌 Probar conexión" → "🚀 Iniciar cola"
7. Genera la ficha       →  pestaña 📢 Publicar (5 títulos, descripción, tags)
8. Exporta               →  "💾 Exportar paquete completo" (sale en output/)
```

Cada video queda en `output/<nombre-del-video>/` con: guion.md, guion.txt,
prompts.txt, prompts.csv, prompts.json, metadata.md, metadata.json y paquete.zip.

---

## 4. Desde la terminal (sin interfaz)

```powershell
$env:PYTHONPATH="src"

# ver tus videos y el estado
.\.venv\Scripts\python.exe -m ytagent.cli estado

# un video nuevo
.\.venv\Scripts\python.exe -m ytagent.cli nuevo "Mi primer video" --tema "camioneros"

# hacer TODO automático para el video 1 (ideas + guion + prompts + ficha)
.\.venv\Scripts\python.exe -m ytagent.cli automatico 1

# solo el guion
.\.venv\Scripts\python.exe -m ytagent.cli guion 1 --duracion 8 --escenas 18

# comprobar claves y ComfyUI
.\.venv\Scripts\python.exe -m ytagent.cli probar
```

---

## 5. Cosas que puedes tocar

| Quiero... | Dónde |
|---|---|
| Cambiar la clave o el modelo | archivo `.env` (nunca se sube a GitHub) |
| Cambiar el estilo visual | `.env` → `VISUAL_STYLE`, o ⚙️ Ajustes en la app |
| Otro modelo de imágenes | `.env` → `COMFYUI_CHECKPOINT` (nombre exacto del .safetensors) |
| Más rápido / más lento | `.env` → `IMAGE_STEPS` (4 = rápido con el LoRA, 20 = calidad máxima) |
| Subir cambios a GitHub | ver sección 7 |

---

## 6. Cuánto cuesta

- **Texto (DeepSeek):** el video completo de ejemplo costó **$0.006** (medio centavo).
  Usa `deepseek-flash`; para guiones más “inteligentes” cambia a `deepseek-v4-pro`.
- **Imágenes (ComfyUI):** **$0** (todo corre en tu gráfica).
- **Modo demo:** si borras la clave del `.env`, todo funciona con texto de ejemplo y
  ningún gasto.

---

## 7. Subir tus cambios a GitHub (el ciclo diario)

Después de editar algo en el proyecto:

```powershell
cd "C:\Users\LENGION\Downloads\vide de teerros shors"
$env:Path = "D:\herramientas\gh\bin;C:\Program Files\Git\cmd;" + $env:Path

git status                      # ver qué cambió
git add -A                      # preparar todo
git commit -m "mi primer cambio"  # guardar en el historial
git push                        # subir a GitHub
```

Y para ver el resultado: https://github.com/matinlapamedina-blip/ytagent

> 🔒 El archivo `.env` (tu clave) está bloqueado por `.gitignore`: Git lo ignora y
> **nunca** se sube. Compruébalo con: `git check-ignore -v .env`

---

## 8. Dónde aprender cada cosa

| Archivo / carpeta | Qué es |
|---|---|
| `docs/PASO_A_PASO.md` | **La guía completa**: instalar, usar, GitHub, solución de problemas |
| `docs/COMO_FUNCIONA.md` | Cómo funciona por dentro, archivo por archivo |
| `src/ytagent/config.py` | Lee el `.env`: claves, rutas, estilo |
| `src/ytagent/schemas.py` | Los “moldes” de datos (Pydantic valida la IA) |
| `src/ytagent/llm.py` | Conexión con DeepSeek + modo demo |
| `src/ytagent/prompts.py` | **Los prompts maestros** (aquí se cambia el estilo de la IA) |
| `src/ytagent/store.py` | Base de datos SQLite (videos, guiones, prompts) |
| `src/ytagent/image_prompts.py` | Compone los prompts de imagen (estilo, 16:9, negative) |
| `src/ytagent/comfyui.py` | Habla con ComfyUI (workflow, cola, descargas) |
| `src/ytagent/pipeline.py` | El flujo completo, paso a paso |
| `src/ytagent/dashboard.py` | La interfaz visual (Streamlit) |
| `tests/` | 52 tests automáticos (puedes romper cosas sin miedo) |

---

## 9. Si algo falla

```powershell
# comprobar todo de una vez
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m ytagent.cli probar

# correr los tests
.\.venv\Scripts\python.exe -m pytest tests -q
```

| Problema | Solución rápida |
|---|---|
| “ComfyUI no disponible” | abre `abrir_comfyui.bat` y espera a que diga `127.0.0.1:8188` |
| “No module named ytagent” | falta `$env:PYTHONPATH="src"` en esa ventana |
| PowerShell no deja ejecutar `.ps1` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Imágenes con texto raro | ya está el negative prompt; sube `IMAGE_STEPS` a 8 |
| La app no abre | cierra la ventana vieja: el puerto 8501 estaba ocupado |
| Clave inválida (HTTP 401) | revisa `DEEPSEEK_API_KEY` en `.env` |

La guía completa está en [`docs/PASO_A_PASO.md`](docs/PASO_A_PASO.md).
