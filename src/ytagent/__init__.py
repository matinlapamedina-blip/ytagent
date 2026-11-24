"""Paquete `ytagent`: el motor del agente de YouTube.

Módulos:
    config    -> rutas, claves y preferencias (.env)
    schemas   -> "moldes" de datos validados (Pydantic)
    llm       -> conexión con DeepSeek (+ modo demo)
    prompts   -> instrucciones maestras que recibe la IA
    store     -> base de datos SQLite
    image_prompts -> genera prompts masivos de imagen
    comfyui   -> envía esos prompts a ComfyUI y baja las imágenes
    pipeline  -> une todo el flujo de trabajo
    cli       -> comandos de terminal
    dashboard -> interfaz visual (Streamlit)
"""

__version__ = "0.1.0"
