"""Interfaz de terminal (CLI) del agente.

Uso:
    python -m ytagent.cli --help
    python -m ytagent.cli estado
    python -m ytagent.cli nuevo "Mi video" --tema "camioneros"
    python -m ytagent.cli ideas 1 --n 6
    python -m ytagent.cli guion 1 --duracion 8 --escenas 20
    python -m ytagent.cli prompts 1
    python -m ytagent.cli metadata 1
    python -m ytagent.cli automatico 1
    python -m ytagent.cli exportar 1
    python -m ytagent.cli probar
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar `python src/ytagent/cli.py` además de `python -m ytagent.cli`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "ytagent"

try:
    from . import exporters, pipeline, store
    from .config import PROJECT_ROOT, settings
    from .llm import LLMError, get_llm
except ImportError:  # pragma: no cover - ejecución directa del archivo
    from ytagent import exporters, pipeline, store
    from ytagent.config import PROJECT_ROOT, settings
    from ytagent.llm import LLMError, get_llm


# ---------------------------------------------------------------------------
# Utilidades de presentación
# ---------------------------------------------------------------------------


def _utf8() -> None:
    """En Windows la consola puede no soportar tildes; lo forzamos."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def titulo(texto: str) -> None:
    print(f"\n{'=' * 60}\n  {texto}\n{'=' * 60}")


def linea(etiqueta: str, valor: object) -> None:
    print(f"  {etiqueta:<22} {valor}")


def paso(mensaje: str) -> None:
    print(f"  -> {mensaje}")


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_estado(args: argparse.Namespace) -> int:
    titulo("ESTADO DEL PROYECTO")
    linea("Carpeta:", PROJECT_ROOT)
    linea("Modo IA:", "DEMO (sin API)" if settings.demo_mode else f"API {settings.deepseek_model}")
    linea("ComfyUI:", settings.comfyui_url)
    linea("Estilo:", settings.visual_style[:50] + "...")
    videos = store.listar_videos()
    titulo(f"VIDEOS ({len(videos)})")
    if not videos:
        print("  Todavía no hay videos. Crea uno con:")
        print('  python -m ytagent.cli nuevo "Mi primer video" --tema "camioneros"')
        return 0
    print(f"  {'ID':<4} {'ESTADO':<10} {'PROMPTS':<9} TÍTULO")
    for v in videos:
        prompts = f"{v['n_listos']}/{v['n_prompts']}"
        print(f"  {v['id']:<4} {v['estado']:<10} {prompts:<9} {v['titulo'][:45]}")
    return 0


def cmd_nuevo(args: argparse.Namespace) -> int:
    video_id = pipeline.crear_proyecto(args.titulo, args.tema or args.titulo)
    print(f"\n  Video creado con id {video_id}.")
    print(f"  Siguiente paso: python -m ytagent.cli ideas {video_id} --n 6")
    return 0


def cmd_ideas(args: argparse.Namespace) -> int:
    llm = get_llm(forzar_demo=True if args.demo else None)
    titulo(f"GENERANDO {args.n} IDEAS (motor: {llm.modo})")
    tema = args.tema or (store.obtener_video(args.video_id) or {}).get("tema", "")
    ideas = pipeline.generar_ideas(args.video_id, tema, n=args.n, llm=llm, progreso=paso)

    for i, idea in enumerate(sorted(ideas, key=lambda x: x.nota, reverse=True), start=1):
        print(f"\n  [{i}] {idea.titulo}   (nota {idea.nota}/10)")
        print(f"      Hook: {idea.hook}")
        print(f"      Premisa: {idea.premisa}")

    # Elige automáticamente la mejor idea (puedes cambiarla desde la app)
    filas = store.listar_ideas(args.video_id)
    if filas:
        store.marcar_idea(args.video_id, filas[0]["id"])
        print(f"\n  Idea elegida automáticamente: {filas[0]['titulo']}")
    return 0


def cmd_guion(args: argparse.Namespace) -> int:
    llm = get_llm(forzar_demo=True if args.demo else None)
    titulo(f"ESCRIBIENDO GUION (motor: {llm.modo})")
    guion = pipeline.escribir_guion(
        args.video_id, duracion_min=args.duracion, n_escenas=args.escenas, llm=llm, progreso=paso
    )
    print(f"\n  {guion.titulo}")
    print(f"  {guion.palabras} palabras | {len(guion.escenas)} escenas | "
          f"{guion.duracion_total_seg // 60} min {guion.duracion_total_seg % 60} s")
    print("\n  --- HOOK ---")
    print(f"  {guion.hook}")
    return 0


def cmd_prompts(args: argparse.Namespace) -> int:
    titulo("GENERANDO PROMPTS MASIVOS")
    prompts = pipeline.generar_prompts(args.video_id, progreso=paso)
    for p in prompts[:5]:
        print(f"\n  [{p.numero:03d}] {p.prompt[:110]}...")
    if len(prompts) > 5:
        print(f"\n  ... y {len(prompts) - 5} más.")
    print(f"\n  Total: {len(prompts)} prompts guardados.")
    print(f"  Exporta con: python -m ytagent.cli exportar {args.video_id}")
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    llm = get_llm(forzar_demo=True if args.demo else None)
    titulo("GENERANDO TÍTULOS Y DESCRIPCIÓN")
    meta = pipeline.generar_metadata(args.video_id, llm=llm, progreso=paso)
    print("\n  TÍTULOS:")
    for t in meta.titulos:
        print(f"   - {t}")
    print("\n  DESCRIPCIÓN:")
    print("  " + meta.descripcion.replace("\n", "\n  ")[:800])
    return 0


def cmd_automatico(args: argparse.Namespace) -> int:
    llm = get_llm(forzar_demo=True if args.demo else None)
    titulo(f"FLUJO COMPLETO (motor: {llm.modo})")
    resultado = pipeline.flujo_completo(
        args.video_id,
        n_ideas=args.n,
        duracion_min=args.duracion,
        n_escenas=args.escenas,
        llm=llm,
        progreso=paso,
    )
    print(f"\n  Idea elegida: {resultado['idea'].titulo}")
    print(f"  Escenas: {len(resultado['guion'].escenas)}")
    print(f"  Prompts: {len(resultado['prompts'])}")
    print(f"  Uso: {resultado['usage'].total_tokens} tokens")
    return cmd_exportar(args)


def cmd_exportar(args: argparse.Namespace) -> int:
    titulo("EXPORTANDO PAQUETE")
    resultado = exporters.exportar_paquete(args.video_id)
    for clave, valor in resultado.items():
        if clave in ("errores", "carpeta"):
            continue
        print(f"  {clave:<12} {valor}")
    if resultado.get("errores"):
        for error in resultado["errores"]:
            print(f"  [aviso] {error}")
    print(f"\n  Carpeta: {resultado['carpeta']}")
    return 0


def cmd_probar(_: argparse.Namespace) -> int:
    titulo("PRUEBA DE CONEXIÓN")
    llm = get_llm()
    print(f"  Motor: {llm.modo}")
    if hasattr(llm, "probar_conexion"):
        ok, mensaje = llm.probar_conexion()  # type: ignore[attr-defined]
        print(f"  {'OK' if ok else 'ERROR'}: {mensaje}")
    else:
        print("  Modo demo: no se llama a ninguna API (todo funciona sin internet).")

    try:
        from . import comfyui

        info = comfyui.diagnostico()
        print(f"  ComfyUI {info.get('url')}: "
              f"{'disponible' if info.get('disponible') else 'NO disponible'}")
        if info.get("error"):
            print(f"    {info['error']}")
        if info.get("checkpoints"):
            print(f"    checkpoints: {', '.join(info['checkpoints'][:5])}")
    except ImportError:
        print("  (módulo comfyui no instalado todavía)")
    except Exception as exc:  # noqa: BLE001 - diagnóstico nunca debe romper
        print(f"  ComfyUI: error inesperado ({exc})")
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytagent",
        description="Agente de IA para crear contenido de YouTube desde la terminal.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("estado", help="Ver videos y configuración")
    p.set_defaults(func=cmd_estado)

    p = sub.add_parser("nuevo", help="Crear un video nuevo")
    p.add_argument("titulo", help="Título de trabajo")
    p.add_argument("--tema", default="", help="Tema o mundo de las ideas")
    p.set_defaults(func=cmd_nuevo)

    p = sub.add_parser("ideas", help="Generar ideas para un video")
    p.add_argument("video_id", type=int)
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--tema", default="")
    p.add_argument("--demo", action="store_true", help="Forzar modo demo (sin API)")
    p.set_defaults(func=cmd_ideas)

    p = sub.add_parser("guion", help="Escribir el guion y las escenas")
    p.add_argument("video_id", type=int)
    p.add_argument("--duracion", type=int, default=8, help="Minutos objetivo")
    p.add_argument("--escenas", type=int, default=20, help="Número de escenas")
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_guion)

    p = sub.add_parser("prompts", help="Generar prompts masivos de imagen")
    p.add_argument("video_id", type=int)
    p.set_defaults(func=cmd_prompts)

    p = sub.add_parser("metadata", help="Generar títulos, descripción y tags")
    p.add_argument("video_id", type=int)
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_metadata)

    p = sub.add_parser("automatico", help="Hacer todo el flujo de una vez")
    p.add_argument("video_id", type=int)
    p.add_argument("--n", type=int, default=6, help="Número de ideas")
    p.add_argument("--duracion", type=int, default=8)
    p.add_argument("--escenas", type=int, default=20)
    p.add_argument("--demo", action="store_true")
    p.set_defaults(func=cmd_automatico)

    p = sub.add_parser("exportar", help="Exportar guion, prompts y metadata")
    p.add_argument("video_id", type=int)
    p.set_defaults(func=cmd_exportar)

    p = sub.add_parser("probar", help="Comprobar API de IA y ComfyUI")
    p.set_defaults(func=cmd_probar)

    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (LLMError, ValueError) as exc:
        print(f"\n  [ERROR] {exc}\n")
        return 1
    except KeyboardInterrupt:
        print("\n  Cancelado.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
