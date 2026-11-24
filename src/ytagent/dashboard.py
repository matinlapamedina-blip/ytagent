r"""Interfaz visual del agente (Streamlit).

Arranca con:
    start.bat
o
    $env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run src\ytagent\dashboard.py

Es una app de una sola página con pestañas, pensada como una "fábrica" de videos:
    Sidebar -> elige o crea un video
    Pestaña Ideas     -> generar y elegir
    Pestaña Guion     -> escribir escenas
    Pestaña Prompts   -> los prompts masivos + referencias + cola ComfyUI
    Pestaña Publicar  -> títulos, descripción, miniaturas y export
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite que Streamlit encuentre el paquete `ytagent` al ejecutar el archivo tal cual
_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(_RAIZ / "src"))

import streamlit as st  # noqa: E402

from ytagent import exporters, pipeline, store  # noqa: E402
from ytagent.config import OUTPUT_DIR, PROJECT_ROOT, settings  # noqa: E402
from ytagent.image_prompts import ASPECTOS, NEGATIVE_BASE  # noqa: E402
from ytagent.llm import LLMError, get_llm  # noqa: E402
from ytagent.schemas import Idea  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración de la página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ytagent · Fábrica de videos",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

ESTILOS_PRESET = {
    "🎥 Cinematográfico (canal)": (
        "cinematic photorealistic, teal and orange color grading, dramatic rim lighting, "
        "film grain, 35mm lens, shallow depth of field, ultra detailed"
    ),
    "🌑 Misterio / Suspense": (
        "dark atmospheric cinematography, deep shadows, cold blue moonlight, volumetric fog, "
        "anamorphic lens, high contrast, film noir, ultra detailed"
    ),
    "🌅 Documental realista": (
        "documentary photography, natural lighting, kodak portra 400, 50mm lens, "
        "candid moment, realistic textures, muted tones"
    ),
    "🌆 Neón / Sci-fi": (
        "cyberpunk neon lighting, magenta and cyan palette, rain-slicked streets, "
        "anamorphic flare, blade runner atmosphere, 35mm, ultra detailed"
    ),
    "☀️ Cálido / Nostálgico": (
        "warm golden hour light, soft haze, vintage film look, kodak gold 200, "
        "dreamy bokeh, nostalgic mood, 50mm lens"
    ),
}

CSS = """
<style>
    /* Estética oscura tipo "panel de control" */
    .stApp { background: linear-gradient(180deg, #0b1220 0%, #0a1020 100%); }
    section[data-testid="stSidebar"] { background: #0d1526; border-right: 1px solid #1c2a44; }
    h1, h2, h3 { letter-spacing: -0.02em; }
    div[data-testid="stMetric"] {
        background: #111c31; border: 1px solid #1e2f4d; border-radius: 12px; padding: 10px 14px;
    }
    .yt-hero {
        background: linear-gradient(120deg, #12314f 0%, #0e2036 60%, #0b1626 100%);
        border: 1px solid #1e3a5f; border-radius: 16px; padding: 18px 22px; margin-bottom: 8px;
    }
    .yt-hero h1 { font-size: 1.6rem; margin: 0; color: #eaf2ff; }
    .yt-hero p { margin: 4px 0 0 0; color: #9fb3d1; font-size: 0.92rem; }
    .yt-card {
        background: #101b2e; border: 1px solid #1e2f4d; border-radius: 14px;
        padding: 14px 16px; margin-bottom: 10px;
    }
    .yt-card h4 { margin: 0 0 6px 0; color: #eaf2ff; font-size: 1.02rem; }
    .yt-card p { margin: 3px 0; color: #a9bcd8; font-size: 0.88rem; line-height: 1.4; }
    .yt-badge {
        display: inline-block; padding: 2px 9px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 600; background: #14304f; color: #7fd0ff;
        border: 1px solid #1f4a75;
    }
    .yt-prompt {
        background: #0e1829; border-left: 3px solid #2d6fb8; border-radius: 8px;
        padding: 9px 12px; margin: 6px 0; font-family: ui-monospace, Consolas, monospace;
        font-size: 0.8rem; color: #b9cbe4; white-space: pre-wrap;
    }
    .yt-num {
        display:inline-block; min-width: 34px; text-align:center; background:#173a5e;
        color:#8fd4ff; border-radius: 6px; font-weight:700; font-size:0.75rem;
        padding: 2px 6px; margin-right: 8px;
    }
    textarea { font-family: ui-monospace, Consolas, monospace !important; font-size: 0.82rem !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Estado de la sesión
# ---------------------------------------------------------------------------
def _init_estado() -> None:
    st.session_state.setdefault("video_id", None)
    st.session_state.setdefault("modo_demo", settings.force_demo)
    st.session_state.setdefault("estilo", settings.visual_style)
    st.session_state.setdefault("aspecto", settings.image_aspect)
    st.session_state.setdefault("tokens", 0)
    st.session_state.setdefault("log", [])


_init_estado()


def _avisar(mensaje: str) -> None:
    """Callback de progreso del pipeline -> barra de la interfaz."""
    st.session_state["log"].append(mensaje)


def _llm():
    """Crea el motor de IA según el toggle de demo y acumula tokens de la sesión."""
    llm = get_llm(forzar_demo=st.session_state["modo_demo"])
    return llm


def _registrar_uso(llm) -> None:
    st.session_state["tokens"] = st.session_state.get("tokens", 0) + llm.usage.total_tokens


def _error(exc: Exception) -> None:
    st.error(f"❌ {exc}")


# ---------------------------------------------------------------------------
# Sidebar: selección de video y estado
# ---------------------------------------------------------------------------
def sidebar() -> int | None:
    with st.sidebar:
        st.markdown("## 🎬 ytagent")
        st.caption("Fábrica de videos con IA · DeepSeek + ComfyUI")

        videos = store.listar_videos()
        if videos:
            opciones = {f"#{v['id']} · {v['titulo'][:34]}": v["id"] for v in videos}
            etiquetas = list(opciones.keys())
            actual = f"#{st.session_state['video_id']} · " if st.session_state["video_id"] else None
            indice = 0
            for i, etiqueta in enumerate(etiquetas):
                if actual and etiqueta.startswith(actual):
                    indice = i
                    break
            elegido = st.selectbox("Video en producción", etiquetas, index=indice)
            st.session_state["video_id"] = opciones[elegido]
            video = store.obtener_video(st.session_state["video_id"])
            if video:
                estado = video["estado"]
                iconos = {
                    "borrador": "📝",
                    "ideas": "💡",
                    "guion": "📖",
                    "prompts": "🖼️",
                    "imagenes": "🎞️",
                    "metadata": "📢",
                    "listo": "✅",
                }
                st.markdown(
                    f"{iconos.get(estado, '•')} Estado: **{estado}**"
                )
        else:
            st.session_state["video_id"] = None
            st.info("Aún no hay videos. Crea el primero abajo 👇")

        st.divider()
        with st.expander("➕ Nuevo video", expanded=not videos):
            with st.form("form_nuevo", clear_on_submit=False):
                titulo = st.text_input("Título de trabajo", placeholder="El turno de las 3 AM")
                tema = st.text_area(
                    "Tema / mundo",
                    placeholder="camioneros misteriosos de noche en Texas",
                    height=70,
                )
                crear = st.form_submit_button("Crear video", use_container_width=True)
            if crear:
                if not titulo.strip():
                    st.warning("Ponle un título.")
                else:
                    nuevo = pipeline.crear_proyecto(titulo.strip(), tema.strip() or titulo.strip())
                    st.session_state["video_id"] = nuevo
                    st.success(f"Video #{nuevo} creado.")
                    st.rerun()

        st.divider()
        with st.expander("⚙️ Ajustes", expanded=False):
            st.session_state["modo_demo"] = st.toggle(
                "Modo demo (sin API)",
                value=st.session_state["modo_demo"],
                help="Genera contenido de ejemplo sin gastar tokens de DeepSeek.",
            )
            llm_actual = "DEMO" if st.session_state["modo_demo"] else settings.deepseek_model
            st.caption(f"Motor de texto: **{llm_actual}**")
            opciones_estilo = list(ESTILOS_PRESET.keys()) + ["✏️ Personalizado"]
            idx = 0
            for i, (_nombre, valor) in enumerate(ESTILOS_PRESET.items()):
                if valor == st.session_state["estilo"]:
                    idx = i
            eleccion = st.selectbox("Estilo visual", opciones_estilo, index=idx)
            if eleccion == "✏️ Personalizado":
                st.session_state["estilo"] = st.text_area(
                    "Estilo (inglés)", value=st.session_state["estilo"], height=90
                )
            else:
                st.session_state["estilo"] = ESTILOS_PRESET[eleccion]
            st.session_state["aspecto"] = st.selectbox(
                "Relación de aspecto",
                list(ASPECTOS.keys()),
                index=list(ASPECTOS.keys()).index(st.session_state["aspecto"])
                if st.session_state["aspecto"] in ASPECTOS
                else 0,
            )
            st.caption(f"Tokens usados en esta sesión: **{st.session_state['tokens']:,}**")
            if st.button("🧹 Limpiar log", use_container_width=True):
                st.session_state["log"] = []

        st.divider()
        st.caption("Datos: `data/ytagent.db` · Salidas: `output/`")
        if st.session_state["modo_demo"]:
            st.warning("MODO DEMO activo: contenido simulado.", icon="🧪")
        else:
            st.success(f"API conectada · {settings.deepseek_model}", icon="🟢")

    return st.session_state["video_id"]


# ---------------------------------------------------------------------------
# Pestaña 1: IDEAS
# ---------------------------------------------------------------------------
def tab_ideas(video_id: int) -> None:
    video = store.obtener_video(video_id) or {}
    st.markdown("### 💡 Ideas")
    st.caption(
        "La IA propone varios ángulos con gancho. Las notas (0-10) te ayudan a elegir la más fuerte."
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        tema = st.text_input(
            "Tema o mundo de las ideas",
            value=video.get("tema") or video.get("titulo", ""),
            key="tema_ideas",
        )
    with col2:
        n_ideas = st.number_input("Cantidad", 1, 12, 6, key="n_ideas")
    with col3:
        st.write("")
        st.write("")
        generar = st.button("✨ Generar ideas", type="primary", use_container_width=True)

    if generar:
        llm = _llm()
        try:
            with st.spinner("Pensando ideas..."):
                pipeline.generar_ideas(
                    video_id, tema, n=n_ideas, llm=llm, progreso=_avisar
                )
            _registrar_uso(llm)
            st.rerun()
        except (LLMError, ValueError) as exc:
            _error(exc)

    ideas = store.listar_ideas(video_id)
    if not ideas:
        st.info("Todavía no hay ideas para este video. Pulsa «Generar ideas».")
        return

    elegida_actual = next((i["id"] for i in ideas if i["elegida"]), None)
    for fila in ideas:
        idea: Idea = fila["idea"]
        marca = "✅ " if fila["elegida"] else ""
        with st.container():
            st.markdown(
                f"""<div class="yt-card">
                <h4>{marca}{idea.titulo} <span class="yt-badge">nota {idea.nota}/10</span></h4>
                <p><b>🎣 Hook:</b> {idea.hook}</p>
                <p><b>📌 Premisa:</b> {idea.premisa}</p>
                <p><b>🌀 Ángulo:</b> {idea.angulo or "—"}</p>
                <p><b>🏁 Final:</b> {idea.final or "—"}</p>
                </div>""",
                unsafe_allow_html=True,
            )
            cols = st.columns([1, 3])
            with cols[0]:
                if st.button(
                    "Usar esta idea",
                    key=f"usar_{fila['id']}",
                    disabled=fila["elegida"] == 1,
                    use_container_width=True,
                ):
                    store.marcar_idea(video_id, fila["id"])
                    st.rerun()
            if elegida_actual == fila["id"]:
                cols[1].success("Esta es la idea elegida. Ve a la pestaña **📖 Guion**.")


# ---------------------------------------------------------------------------
# Pestaña 2: GUION
# ---------------------------------------------------------------------------
def _render_guion(guion) -> None:
    st.markdown(f"## {guion.titulo}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Palabras", f"{guion.palabras:,}")
    c2.metric("Escenas", len(guion.escenas))
    c3.metric("Duración", f"{guion.duracion_total_seg // 60}:{guion.duracion_total_seg % 60:02d} min")

    st.markdown(f"**🎣 Hook:** {guion.hook}")

    sub1, sub2 = st.tabs(["📝 Texto completo", "🎥 Escenas"])
    with sub1:
        st.markdown("**Intro**")
        st.write(guion.intro or "—")
        for i, bloque in enumerate(guion.desarrollo, start=1):
            st.markdown(f"**Bloque {i}**")
            st.write(bloque)
        st.markdown("**Clímax**")
        st.write(guion.clímax or "—")
        st.markdown("**Cierre**")
        st.write(guion.cierre or "—")
        st.markdown("**CTA**")
        st.write(guion.cta or "—")
    with sub2:
        for e in guion.escenas:
            with st.expander(f"Escena {e.numero:02d} · {e.duracion_seg}s · {e.nota_edicion or ''}"):
                st.markdown(f"**Narración:** {e.narracion}")
                st.markdown(f"**Visual:** {e.visual}")
                if e.prompt_imagen:
                    st.markdown(
                        f'<div class="yt-prompt">{e.prompt_imagen}</div>', unsafe_allow_html=True
                    )


def tab_guion(video_id: int) -> None:
    st.markdown("### 📖 Guion")
    st.caption("Primero escribe el texto que se locuta. Después lo divide en escenas con prompts.")

    idea = store.idea_elegida(video_id)
    if idea is None:
        st.warning("Primero elige una idea en la pestaña **💡 Ideas**.")
        return
    st.markdown(
        f'<div class="yt-card"><p><b>Idea elegida:</b> {idea.titulo}</p>'
        f'<p>{idea.premisa}</p></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        duracion = st.number_input("Minutos", 2, 30, 8, key="dur_guion")
    with c2:
        n_escenas = st.number_input("Escenas", 6, 40, 20, key="n_escenas")
    with c3:
        st.write("")
        escribir = st.button("✍️ Escribir guion", type="primary", use_container_width=True)

    if escribir:
        llm = _llm()
        try:
            with st.spinner("Escribiendo guion y escenas (2 llamadas a la IA)..."):
                pipeline.escribir_guion(
                    video_id,
                    duracion_min=int(duracion),
                    n_escenas=int(n_escenas),
                    estilo=st.session_state["estilo"],
                    llm=llm,
                    progreso=_avisar,
                )
            _registrar_uso(llm)
            st.rerun()
        except (LLMError, ValueError) as exc:
            _error(exc)

    guion = store.obtener_guion(video_id)
    if guion:
        _render_guion(guion)
    else:
        st.info("Este video aún no tiene guion.")


# ---------------------------------------------------------------------------
# Pestaña 3: PROMPTS + IMÁGENES
# ---------------------------------------------------------------------------
def _mod_comfyui():
    """Importa el módulo de ComfyUI si existe (puede no estar en versiones tempranas)."""
    try:
        from ytagent import comfyui

        return comfyui
    except ImportError:
        return None


def tab_prompts(video_id: int) -> None:
    video = store.obtener_video(video_id) or {}
    guion = store.obtener_guion(video_id)
    st.markdown("### 🖼️ Prompts masivos")
    st.caption(
        "Cada prompt está listo para ComfyUI, Midjourney, Flux o Leonardo. "
        "El estilo del canal se añade automáticamente."
    )

    if guion is None or not guion.escenas:
        st.warning("Primero escribe el guion en la pestaña **📖 Guion**.")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        regenerar = st.button("🔁 Regenerar prompts", use_container_width=True)
    with c2:
        exportar = st.button("💾 Exportar (txt/csv/json)", use_container_width=True)
    with c3:
        st.caption(f"{len(guion.escenas)} escenas · estilo: {st.session_state['estilo'][:45]}...")

    if regenerar:
        try:
            pipeline.generar_prompts(video_id, progreso=_avisar)
            st.success("Prompts regenerados.")
            st.rerun()
        except ValueError as exc:
            _error(exc)

    if exportar:
        try:
            rutas = pipeline.exportar_prompts(video_id)
            for nombre, ruta in rutas.items():
                st.success(f"{nombre}: {ruta}")
        except ValueError as exc:
            _error(exc)

    prompts = store.listar_prompts(video_id)
    if not prompts:
        st.info("Pulsa «Regenerar prompts» para crearlos desde el guion.")
        return

    if st.session_state["aspecto"] != settings.image_aspect:
        st.caption(
            f"⚠️ El tamaño de las imágenes se cambia en Ajustes (actual: {st.session_state['aspecto']})."
        )

    # --- cola de imágenes -------------------------------------------------
    st.divider()
    col_a, col_b, col_c = st.columns([1.2, 1, 2])
    comfy = _mod_comfyui()
    with col_a:
        st.markdown(f"**🖨️ ComfyUI** · `{settings.comfyui_url}`")
    with col_b:
        if comfy is None:
            st.caption("módulo no instalado todavía")
        else:
            if st.button("🔌 Probar conexión", use_container_width=True):
                info = comfy.diagnostico()
                if info.get("disponible"):
                    st.success(f"Conectado. Checkpoints: {info.get('checkpoints') or 'ninguno'}")
                else:
                    st.error(info.get("error") or "No disponible")
    with col_c:
        pendientes = sum(1 for p in prompts if p["estado"] != "listo")
        pendientes_txt = (
            f"{pendientes} pendientes · {len(prompts) - pendientes} generadas"
        )
        st.caption(pendientes_txt)
        if comfy is not None and st.button(
            f"🚀 Iniciar cola ({pendientes})",
            type="primary",
            disabled=pendientes == 0,
            use_container_width=True,
        ):
            _ejecutar_cola(video_id, comfy)

    # --- referencias -------------------------------------------------------
    with st.expander("03 · Referencias de estilo (opcional)", expanded=False):
        refs = store.listar_referencias()
        st.caption("Sube capturas de estilo que te gusten. Se guardan como inspiración.")
        subidas = st.file_uploader(
            "Imágenes de referencia", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True
        )
        if subidas:
            for archivo in subidas:
                destino = PROJECT_ROOT / "data" / "refs"
                destino.mkdir(parents=True, exist_ok=True)
                ruta = destino / archivo.name
                ruta.write_bytes(archivo.getbuffer())
                store.agregar_referencia(archivo.name, str(ruta))
            st.success(f"{len(subidas)} referencia(s) guardadas.")
            st.rerun()
        if refs:
            cols = st.columns(min(4, len(refs)))
            for i, ref in enumerate(refs):
                with cols[i % len(cols)]:
                    try:
                        st.image(ref["ruta"], caption=ref["nombre"][:18])
                    except Exception:  # noqa: BLE001
                        st.caption(ref["nombre"])
                    if st.button("🗑️", key=f"del_ref_{ref['id']}"):
                        store.borrar_referencia(ref["id"])
                        st.rerun()

    # --- galería / lista de prompts ----------------------------------------
    st.divider()
    ver_galeria = st.toggle("🖼️ Vista de galería", value=True)
    if ver_galeria:
        columnas = st.columns(4)
        for i, p in enumerate(prompts):
            with columnas[i % 4]:
                if p["imagen"] and Path(p["imagen"]).exists():
                    st.image(p["imagen"], use_container_width=True)
                else:
                    st.markdown(
                        f"""<div style="border:1px dashed #24405f; border-radius:10px;
                        height:110px; display:flex; align-items:center; justify-content:center;
                        color:#4a6488; font-size:0.75rem; background:#0c1524;">
                        {p['estado'].upper()}</div>""",
                        unsafe_allow_html=True,
                    )
                st.caption(f"#{p['numero']:03d} · {p['estado']}")
    else:
        for p in prompts:
            with st.expander(f"#{p['numero']:03d} · escena {p['scene_numero']} · {p['estado']}"):
                st.markdown(
                    f'<div class="yt-prompt">{p["prompt"]}</div>', unsafe_allow_html=True
                )
                if p["negative"]:
                    st.caption(f"Negative: {p['negative'][:150]}…")
                st.caption(f"Seed: {p['seed']}")

    st.divider()
    st.markdown("**📋 Pegar a tu generador externo**")
    texto_prompts = "\n".join(f"{p['numero']:03d}. {p['prompt']}" for p in prompts)
    st.download_button(
        "⬇️ Descargar prompts.txt",
        data=texto_prompts.encode("utf-8"),
        file_name=f"prompts_{video.get('slug', video_id)}.txt",
        mime="text/plain",
        use_container_width=True,
    )


def _ejecutar_cola(video_id: int, comfy) -> None:
    """Envía los prompts pendientes a ComfyUI uno por uno, mostrando progreso."""
    pendientes = [p for p in store.listar_prompts(video_id) if p["estado"] != "listo"]
    if not pendientes:
        return
    barra = st.progress(0.0, text="Preparando la cola...")
    estado = st.empty()
    total = len(pendientes)
    hechas = 0

    for p in pendientes:
        estado.info(f"🎨 Generando imagen #{p['numero']} ({hechas + 1}/{total})...")
        store.actualizar_prompt(p["id"], estado="generando", error="")
        try:
            ruta = comfy.generar_imagen(
                prompt=p["prompt"],
                negative=p["negative"] or NEGATIVE_BASE,
                seed=p["seed"],
                width=int(p.get("width") or 1024),
                height=int(p.get("height") or 576),
                destino=OUTPUT_DIR / "_imagenes" / f"img_{p['numero']:03d}.png",
                steps=settings.image_steps,
                cfg=settings.image_cfg,
                sampler=settings.image_sampler,
                scheduler=settings.image_scheduler,
                lora=settings.comfyui_lora or None,
            )
            store.actualizar_prompt(p["id"], estado="listo", imagen=str(ruta))
            hechas += 1
        except Exception as exc:  # noqa: BLE001 - una imagen rota no para la cola
            store.actualizar_prompt(p["id"], estado="error", error=str(exc)[:500])
            estado.warning(f"❌ Imagen #{p['numero']}: {exc}")
        barra.progress(hechas / total, text=f"{hechas}/{total} imágenes")

    store.actualizar_estado(video_id, "imagenes")
    estado.success(f"Cola terminada: {hechas}/{total} imágenes generadas.")
    st.rerun()


# ---------------------------------------------------------------------------
# Pestaña 4: PUBLICAR
# ---------------------------------------------------------------------------
def tab_publicar(video_id: int) -> None:
    guion = store.obtener_guion(video_id)
    st.markdown("### 📢 Publicar")

    if guion is None:
        st.warning("Primero escribe el guion.")
        return

    if st.button("✨ Generar títulos, descripción y tags", type="primary"):
        llm = _llm()
        try:
            with st.spinner("Escribiendo la ficha del video..."):
                pipeline.generar_metadata(video_id, llm=llm, progreso=_avisar)
            _registrar_uso(llm)
            st.rerun()
        except (LLMError, ValueError) as exc:
            _error(exc)

    meta = store.obtener_metadata(video_id)
    if meta is None:
        st.info("Aún no hay ficha. Genérala para tener títulos y descripción listos.")
    else:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("#### 🎯 Títulos (elige uno)")
            for t in meta.titulos:
                st.markdown(f"- {t}")
            st.markdown("#### 📄 Descripción")
            st.code(meta.descripcion, language="text")
            st.markdown("#### 🏷️ Tags")
            st.code(", ".join(meta.tags), language="text")
            if meta.hashtags:
                st.markdown(" ".join(meta.hashtags))
            st.markdown("#### 💬 Comentario fijado")
            st.code(meta.comentario_fijado, language="text")
        with c2:
            st.markdown("#### 🖼️ Miniatura")
            st.markdown(f"**Texto:** `{meta.texto_miniatura}`")
            if meta.prompt_miniatura:
                st.markdown(
                    f'<div class="yt-prompt">{meta.prompt_miniatura}</div>',
                    unsafe_allow_html=True,
                )
            if meta.horas_publicacion:
                st.caption("Mejores horas: " + ", ".join(meta.horas_publicacion))

            imagenes = [p for p in store.listar_prompts(video_id) if p["imagen"]]
            if imagenes:
                st.markdown("#### 🎞️ Tus imágenes")
                sub = st.columns(2)
                for i, p in enumerate(imagenes[:6]):
                    with sub[i % 2]:
                        try:
                            st.image(p["imagen"], caption=f"#{p['numero']:03d}")
                        except Exception:  # noqa: BLE001
                            pass

    st.divider()
    st.markdown("### 📦 Exportar todo")
    if st.button("💾 Exportar paquete completo", use_container_width=True):
        try:
            resultado = exporters.exportar_paquete(video_id)
            for error in resultado.get("errores", []):
                st.warning(error)
            st.success(f"Carpeta: {resultado.get('carpeta')}")
            archivos = exporters.listar_archivos_exportados(video_id)
            for archivo in archivos:
                st.markdown(f"- `{archivo.name}`")
        except ValueError as exc:
            _error(exc)

    archivos = exporters.listar_archivos_exportados(video_id)
    if archivos:
        st.markdown("#### Archivos listos")
        for archivo in archivos:
            try:
                data = archivo.read_bytes()
                st.download_button(
                    f"⬇️ {archivo.name}",
                    data=data,
                    file_name=archivo.name,
                    key=f"dl_{archivo.name}",
                    use_container_width=True,
                )
            except OSError:
                st.caption(f"⚠️ no se pudo leer {archivo.name}")


# ---------------------------------------------------------------------------
# Pantalla principal
# ---------------------------------------------------------------------------
def main() -> None:
    # Aplica a todo el flujo el estilo y el aspecto elegidos en Ajustes
    pipeline.configurar_sesion(
        estilo=st.session_state["estilo"], aspecto=st.session_state["aspecto"]
    )

    st.markdown(
        """<div class="yt-hero">
        <h1>🎬 Fábrica de videos</h1>
        <p>Ideas → guion → prompts masivos → imágenes → título y descripción.
        Todo en un flujo, con DeepSeek para el texto y ComfyUI para la imagen.</p>
        </div>""",
        unsafe_allow_html=True,
    )

    video_id = sidebar()
    if not video_id:
        st.info("👈 Empieza creando un video en la barra lateral.")
        _seccion_como_usar()
        return

    video = store.obtener_video(video_id)
    if not video:
        st.session_state["video_id"] = None
        st.rerun()

    ideas = store.listar_ideas(video_id)
    prompts = store.listar_prompts(video_id)
    listos = sum(1 for p in prompts if p["estado"] == "listo")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💡 Ideas", len(ideas))
    c2.metric("📖 Guion", "✅" if store.obtener_guion(video_id) else "—")
    c3.metric("🖼️ Imágenes", f"{listos}/{len(prompts)}")
    c4.metric("📢 Ficha", "✅" if store.obtener_metadata(video_id) else "—")

    t1, t2, t3, t4, t5 = st.tabs(["💡 Ideas", "📖 Guion", "🖼️ Prompts", "📢 Publicar", "❓ Ayuda"])
    with t1:
        tab_ideas(video_id)
    with t2:
        tab_guion(video_id)
    with t3:
        tab_prompts(video_id)
    with t4:
        tab_publicar(video_id)
    with t5:
        _seccion_como_usar()


def _seccion_como_usar() -> None:
    st.markdown("### ❓ Cómo se usa")
    st.markdown(
        """
1. **Crea un video** en la barra lateral con un título y un tema.
2. **Genera ideas** y marca la que más te guste.
3. **Escribe el guion**: la IA redacta el texto y lo divide en escenas.
4. **Genera los prompts masivos** (uno por escena, 16:9).
5. **Envía la cola a ComfyUI** o descarga `prompts.txt` para Midjourney/Flux.
6. **Genera la ficha**: 5 títulos, descripción con capítulos, tags y miniatura.
7. **Exporta** el paquete y a publicar.

Guía completa: `docs/PASO_A_PASO.md`
"""
    )


if __name__ == "__main__":
    main()
