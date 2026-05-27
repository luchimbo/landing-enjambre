import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
BUILD_SCRIPT = ROOT / "build_landings.py"

PENDING_COMMANDS = set()
LEAD_MAGNET_SCRIPT = ROOT / "agente_lead_magnets.py"
NURTURE_SCRIPT = ROOT / "agente_4_nurture.py"
GEO_AUDIT_SCRIPT = ROOT / "agente_geo_audit.py"
DISTRIBUTION_SCRIPT = ROOT / "agente_distribucion.py"
CONVERSION_SCRIPT = ROOT / "agente_conversion.py"
PUBLICACION_SCRIPT = ROOT / "agente_publicacion.py"
BROWSER_CDP_SCRIPT = ROOT / "agente_browser_cdp.py"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timestamp()
    path = REPORTS_DIR / f"{stamp}-swarm-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_step(step: str, args: list[str], script: Path | None = None) -> dict:
    target_script = str(script) if script else str(BUILD_SCRIPT)
    command = [sys.executable, target_script, *args]
    print(f"swarm: running {step}: {' '.join(command)}")
    started = timestamp()
    result = subprocess.run(command, cwd=ROOT)
    status = "ok" if result.returncode == 0 else "failed"
    return {
        "step": step,
        "command": command,
        "started_utc": started,
        "finished_utc": timestamp(),
        "returncode": result.returncode,
        "status": status,
    }


def lead_magnets_args(args: argparse.Namespace) -> list[str]:
    cmd = ["--limit", str(args.limit)]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def geo_audit_args(args: argparse.Namespace) -> list[str]:
    cmd = ["audit", "--limit", str(args.limit)]
    if args.dry_run:
        cmd.append("--dry-run")
    if getattr(args, "models", ""):
        cmd.extend(["--models", args.models])
    return cmd



def search_threads_args(args: argparse.Namespace) -> list[str]:
    cmd = ["search", "--channel", getattr(args, "channel", "reddit-public") or "reddit-public", "--limit", str(args.limit)]
    if args.dry_run:
        cmd.append("--dry-run")
    if getattr(args, "model", ""):
        cmd.extend(["--model", args.model])
    return cmd


def publish_args(args: argparse.Namespace) -> list[str]:
    cmd = ["publish", "--limit", str(args.limit)]
    if args.dry_run:
        cmd.append("--dry-run")
    if getattr(args, "channel", ""):
        cmd.extend(["--channel", args.channel])
    return cmd


def assist_comment_args(args: argparse.Namespace) -> list[str]:
    cmd = ["assist-comment", "--limit", str(args.limit)]
    if getattr(args, "channel", ""):
        cmd.extend(["--channel", args.channel])
    if getattr(args, "status", ""):
        cmd.extend(["--status", args.status])
    if getattr(args, "no_browser", False):
        cmd.append("--no-browser")
    if getattr(args, "no_copy", False):
        cmd.append("--no-copy")
    return cmd


def browser_search_args(args: argparse.Namespace) -> list[str]:
    cmd = ["browser-search", "--channel", args.channel, "--limit", str(args.limit)]
    if getattr(args, "no_browser", False):
        cmd.append("--no-browser")
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    return cmd


def create_comment_from_context_args(args: argparse.Namespace) -> list[str]:
    cmd = [
        "create-comment-from-context",
        "--channel", args.channel,
        "--landing-slug", args.landing_slug,
        "--context", args.context,
    ]
    if getattr(args, "url", ""):
        cmd.extend(["--url", args.url])
    if getattr(args, "model", ""):
        cmd.extend(["--model", args.model])
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    return cmd


def auto_browser_args(args: argparse.Namespace) -> list[str]:
    cmd = ["auto-browser", "--task", args.task]
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    return cmd


def auto_distribution_args(args: argparse.Namespace) -> list[str]:
    cmd = ["auto-distribution", "--channels", args.channels, "--limit", str(args.limit), "--per-channel", str(args.per_channel)]
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    if getattr(args, "allow_proposed", False):
        cmd.append("--allow-proposed")
    return cmd


def auto_listen_args(args: argparse.Namespace) -> list[str]:
    cmd = ["auto-listen", "--channels", args.channels, "--searches", str(args.searches), "--per-search", str(args.per_search)]
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    return cmd


def distribution_args(args: argparse.Namespace) -> list[str]:
    action = getattr(args, "distribution_action", "generate") or "generate"
    if action == "approve-all":
        cmd = [action]
        if getattr(args, "channel", ""):
            cmd.extend(["--channel", args.channel])
        if getattr(args, "dry_run", False):
            cmd.append("--dry-run")
        return cmd
    cmd = [action, "--limit", str(args.limit)]
    if getattr(args, "dry_run", False):
        cmd.append("--dry-run")
    if getattr(args, "channel", ""):
        cmd.extend(["--channel", args.channel])
    if action == "generate" and getattr(args, "since_last_deploy", False):
        cmd.append("--since-last-deploy")
    if action == "generate" and getattr(args, "model", ""):
        cmd.extend(["--model", args.model])
    if action == "schedule":
        cmd.extend(["--interval-minutes", str(getattr(args, "interval_minutes", 45))])
        if getattr(args, "start_at", ""):
            cmd.extend(["--start-at", args.start_at])
    if action == "queue" and getattr(args, "ready_only", False):
        cmd.append("--ready-only")
    if action == "assist" and getattr(args, "open_browser", False):
        cmd.append("--open-browser")
    return cmd


def conversion_args(args: argparse.Namespace) -> list[str]:
    if getattr(args, "conversion_action", "run") == "status":
        return ["status"]
    cmd = ["run", "--window-days", str(args.window_days), "--min-views", str(args.min_views), "--limit", str(args.limit)]
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def nurture_args(args: argparse.Namespace) -> list[str]:
    cmd = ["process", "--limit", str(args.limit)]
    if args.dry_run:
        cmd.append("--dry-run")
    if getattr(args, "retry", False):
        cmd.append("--retry")
    return cmd


def require_ok(step_result: dict, steps: list[dict], workflow: str) -> None:
    steps.append(step_result)
    if step_result["returncode"] != 0:
        report_path = write_report(workflow, {"command": workflow, "status": "blocked", "steps": steps})
        raise SystemExit(f"swarm: {step_result['step']} fallo. Flujo bloqueado. Reporte: {report_path}")


def soft_ok(step_result: dict, steps: list[dict]) -> bool:
    steps.append(step_result)
    if step_result["returncode"] != 0:
        print(f"swarm: WARN — {step_result['step']} fallo (no bloqueante). Continua pipeline.")
        return False
    return True


def common_build_args(args: argparse.Namespace) -> list[str]:
    if not args.base_url:
        return []
    return ["--base-url", args.base_url]


def generate_args(args: argparse.Namespace) -> list[str]:
    cmd = ["generate", "--limit", str(args.limit)]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.dry_run:
        cmd.append("--dry-run")
    if args.max_seconds:
        cmd.extend(["--max-seconds", str(args.max_seconds)])
    return cmd


def run_args(args: argparse.Namespace) -> list[str]:
    cmd = ["run", "--limit", str(args.limit)]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.base_url:
        cmd.extend(["--base-url", args.base_url])
    if args.dry_run:
        cmd.append("--dry-run")
    if args.max_seconds:
        cmd.extend(["--max-seconds", str(args.max_seconds)])
    return cmd


def research_args(args: argparse.Namespace) -> list[str]:
    cmd = ["research", "--limit", str(args.limit)]
    if args.no_web:
        cmd.append("--no-web")
    return cmd


def run_single(args: argparse.Namespace) -> None:
    if args.command == "generate":
        command_args = generate_args(args)
        step = run_step(args.command, command_args)
    elif args.command == "run":
        command_args = run_args(args)
        step = run_step(args.command, command_args)
    elif args.command == "research":
        command_args = research_args(args)
        step = run_step(args.command, command_args)
    elif args.command == "build":
        command_args = ["build", *common_build_args(args)]
        step = run_step(args.command, command_args)
    elif args.command == "deploy":
        command_args = ["deploy", *common_build_args(args)]
        step = run_step(args.command, command_args)
    elif args.command == "lead-magnets":
        command_args = lead_magnets_args(args)
        step = run_step(args.command, command_args, script=LEAD_MAGNET_SCRIPT)
    elif args.command == "geo-audit":
        command_args = geo_audit_args(args)
        step = run_step(args.command, command_args, script=GEO_AUDIT_SCRIPT)
    elif args.command == "nurture":
        command_args = nurture_args(args)
        step = run_step(args.command, command_args, script=NURTURE_SCRIPT)
    elif args.command == "distribution":
        command_args = distribution_args(args)
        step = run_step(args.command, command_args, script=DISTRIBUTION_SCRIPT)
    elif args.command in {"conversion", "feedback"}:
        command_args = conversion_args(args)
        step = run_step(args.command, command_args, script=CONVERSION_SCRIPT)
    elif args.command == "search-threads":
        command_args = search_threads_args(args)
        step = run_step(args.command, command_args, script=PUBLICACION_SCRIPT)
    elif args.command == "publish":
        command_args = publish_args(args)
        step = run_step(args.command, command_args, script=PUBLICACION_SCRIPT)
    elif args.command == "assist-comment":
        command_args = assist_comment_args(args)
        step = run_step(args.command, command_args, script=PUBLICACION_SCRIPT)
    elif args.command == "browser-search":
        command_args = browser_search_args(args)
        step = run_step(args.command, command_args, script=PUBLICACION_SCRIPT)
    elif args.command == "create-comment-from-context":
        command_args = create_comment_from_context_args(args)
        step = run_step(args.command, command_args, script=PUBLICACION_SCRIPT)
    elif args.command == "start-browser":
        step = run_step(args.command, ["start-browser"], script=BROWSER_CDP_SCRIPT)
    elif args.command == "auto-browser":
        command_args = auto_browser_args(args)
        step = run_step(args.command, command_args, script=BROWSER_CDP_SCRIPT)
    elif args.command == "auto-distribution":
        command_args = auto_distribution_args(args)
        step = run_step(args.command, command_args, script=BROWSER_CDP_SCRIPT)
    elif args.command == "auto-listen":
        command_args = auto_listen_args(args)
        step = run_step(args.command, command_args, script=BROWSER_CDP_SCRIPT)
    elif args.command in {"validate", "rollback", "selftest"}:
        command_args = [args.command]
        step = run_step(args.command, command_args)
    else:
        raise SystemExit(f"swarm: comando no soportado: {args.command}")

    report_path = write_report(args.command, {"command": args.command, "status": step["status"], "steps": [step]})
    if step["returncode"] != 0:
        raise SystemExit(f"swarm: {args.command} fallo. Reporte: {report_path}")
    print(f"swarm: {args.command} OK. Reporte: {report_path}")


def run_weekly(args: argparse.Namespace) -> None:
    steps: list[dict] = []
    workflow = "weekly"
    require_ok(run_step("validate-before", ["validate"]), steps, workflow)
    require_ok(run_step("research", research_args(args)), steps, workflow)
    require_ok(run_step("generate", generate_args(args)), steps, workflow)
    require_ok(run_step("lead-magnets", lead_magnets_args(args), script=LEAD_MAGNET_SCRIPT), steps, workflow)
    require_ok(run_step("validate-after", ["validate"]), steps, workflow)
    require_ok(run_step("build", ["build", *common_build_args(args)]), steps, workflow)

    if args.dry_run:
        steps.append({"step": "deploy", "status": "skipped", "reason": "dry_run"})
    else:
        require_ok(run_step("deploy", ["deploy", *common_build_args(args)]), steps, workflow)

    report_path = write_report(workflow, {"command": workflow, "status": "ok", "dry_run": args.dry_run, "steps": steps})
    print(f"swarm: weekly OK. Reporte: {report_path}")


def run_daily(args: argparse.Namespace) -> None:
    steps: list[dict] = []
    workflow = "daily"
    has_warnings = False

    # Crítico: si SMTP/BD falla los emails no salen; no tiene sentido continuar
    require_ok(
        run_step("nurture", nurture_args(args), script=NURTURE_SCRIPT),
        steps,
        workflow,
    )

    # Analiza métricas y escribe content_feedback.jsonl (lo lee distribution-generate)
    if not soft_ok(
        run_step(
            "conversion",
            ["run", "--window-days", "30", "--min-views", "50", "--limit", "50"],
            script=CONVERSION_SCRIPT,
        ),
        steps,
    ):
        has_warnings = True

    # Lee content_feedback.jsonl, genera piezas de distribución → distribution_log.jsonl
    dist_args = ["generate", "--limit", str(args.limit)]
    if args.dry_run:
        dist_args.append("--dry-run")
    if not soft_ok(
        run_step("distribution-generate", dist_args, script=DISTRIBUTION_SCRIPT),
        steps,
    ):
        has_warnings = True

    # Aprueba en bulk las piezas generadas (proposed → bulk_approved)
    approve_args = ["approve", "--limit", str(args.limit)]
    if args.dry_run:
        approve_args.append("--dry-run")
    if not soft_ok(
        run_step("distribution-approve", approve_args, script=DISTRIBUTION_SCRIPT),
        steps,
    ):
        has_warnings = True

    # Busca hilos Reddit públicos → distribution_search_tasks.jsonl
    if not soft_ok(
        run_step("search-threads", search_threads_args(args), script=PUBLICACION_SCRIPT),
        steps,
    ):
        has_warnings = True

    # Publica entradas bulk_approved (sin browser, rate-limited)
    if not soft_ok(
        run_step("publish", publish_args(args), script=PUBLICACION_SCRIPT),
        steps,
    ):
        has_warnings = True

    final_status = "ok_with_warnings" if has_warnings else "ok"
    report_path = write_report(
        workflow,
        {"command": workflow, "status": final_status, "dry_run": args.dry_run, "steps": steps},
    )
    print(f"swarm: daily {final_status.upper()}. Reporte: {report_path}")


def pending_command(args: argparse.Namespace) -> None:
    report_path = write_report(
        args.command,
        {
            "command": args.command,
            "status": "pending",
            "reason": "agent_not_implemented",
            "message": "Comando reservado para agente futuro; no modifica archivos de datos ni site.",
        },
    )
    raise SystemExit(f"swarm: {args.command} pendiente de implementacion. Reporte: {report_path}")


def add_common_generation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima a procesar")
    parser.add_argument("--model", default="", help="Modelo para generacion cuando aplique")
    parser.add_argument("--dry-run", action="store_true", help="Ejecuta sin guardar cambios cuando aplique")
    parser.add_argument("--max-seconds", type=int, default=0, help="Corta generacion despues de N segundos")


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestador codigo-only para agentes PC MIDI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate")
    sub.add_parser("rollback")
    sub.add_parser("selftest")

    build_parser = sub.add_parser("build")
    build_parser.add_argument("--base-url", default="", help="URL del subdominio para canonical/sitemap")

    deploy_parser = sub.add_parser("deploy")
    deploy_parser.add_argument("--base-url", default="", help="URL del subdominio para canonical/sitemap")

    research_parser = sub.add_parser("research")
    research_parser.add_argument("--limit", type=int, default=50, help="Cantidad maxima de oportunidades nuevas")
    research_parser.add_argument("--no-web", action="store_true", help="No intenta buscar sugerencias web")

    generate_parser = sub.add_parser("generate")
    add_common_generation_options(generate_parser)

    run_parser = sub.add_parser("run")
    add_common_generation_options(run_parser)
    run_parser.add_argument("--base-url", default="", help="URL del subdominio para canonical/sitemap")

    weekly_parser = sub.add_parser("weekly")
    add_common_generation_options(weekly_parser)
    weekly_parser.add_argument("--base-url", default="", help="URL del subdominio para canonical/sitemap")
    weekly_parser.add_argument("--no-web", action="store_true", help="No intenta buscar sugerencias web")

    daily_parser = sub.add_parser("daily")
    daily_parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima por paso")
    daily_parser.add_argument("--dry-run", action="store_true", help="Simula sin enviar/publicar")
    daily_parser.add_argument("--channel", default="reddit-public", help="Canal para search-threads")
    daily_parser.add_argument("--model", default="", help="Modelo OpenRouter")
    daily_parser.add_argument("--retry", action="store_true", help="Reintenta nurture fallidos")

    geo_parser = sub.add_parser("geo-audit")
    geo_parser.add_argument("--limit", type=int, default=0, help="Maximo de prompts a procesar (0=todos)")
    geo_parser.add_argument("--dry-run", action="store_true", help="Consulta APIs pero no escribe datos")
    geo_parser.add_argument("--models", default="", help="Modelos separados por coma")

    lead_parser = sub.add_parser("lead-magnets")
    add_common_generation_options(lead_parser)

    nurture_parser = sub.add_parser("nurture")
    nurture_parser.add_argument("--limit", type=int, default=50, help="Maximo de mensajes a procesar")
    nurture_parser.add_argument("--dry-run", action="store_true", help="Simula sin enviar emails")
    nurture_parser.add_argument("--retry", action="store_true", help="Reintenta mensajes fallidos")

    distribution_parser = sub.add_parser("distribution")
    distribution_parser.add_argument(
        "distribution_action",
        nargs="?",
        default="generate",
        choices=["generate", "approve", "approve-all", "schedule", "queue", "assist"],
        help="Accion: generate, approve, approve-all, schedule, queue, assist",
    )
    distribution_parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima a procesar")
    distribution_parser.add_argument("--model", default="", help="Modelo OpenRouter")
    distribution_parser.add_argument("--dry-run", action="store_true", help="Genera piezas sin guardar en disco")
    distribution_parser.add_argument("--channel", default="", help="Filtrar por canal: reddit, forum, linkedin, social, newsletter")
    distribution_parser.add_argument("--since-last-deploy", action="store_true", help="Prioriza landings del ultimo deploy")

    conversion_parser = sub.add_parser("conversion")
    conversion_parser.add_argument("conversion_action", nargs="?", default="run", choices=["run", "status"], help="Accion del auditor")
    conversion_parser.add_argument("--window-days", type=int, default=30, help="Ventana de analisis en dias")
    conversion_parser.add_argument("--min-views", type=int, default=50, help="Minimo de page views para recomendaciones de trafico")
    conversion_parser.add_argument("--limit", type=int, default=50, help="Maximo de recomendaciones nuevas")
    conversion_parser.add_argument("--dry-run", action="store_true", help="Audita sin escribir content_feedback")

    feedback_parser = sub.add_parser("feedback")
    feedback_parser.add_argument("conversion_action", nargs="?", default="run", choices=["run", "status"], help="Accion del auditor")
    feedback_parser.add_argument("--window-days", type=int, default=30, help="Ventana de analisis en dias")
    feedback_parser.add_argument("--min-views", type=int, default=50, help="Minimo de page views para recomendaciones de trafico")
    feedback_parser.add_argument("--limit", type=int, default=50, help="Maximo de recomendaciones nuevas")
    feedback_parser.add_argument("--dry-run", action="store_true", help="Audita sin escribir content_feedback")
    distribution_parser.add_argument("--interval-minutes", type=int, default=45, help="Intervalo para schedule")
    distribution_parser.add_argument("--start-at", default="", help="Inicio ISO-8601 para schedule")
    distribution_parser.add_argument("--ready-only", action="store_true", help="queue: mostrar solo vencidos/listos")
    distribution_parser.add_argument("--open-browser", action="store_true", help="assist: abre landing de referencia")

    search_parser = sub.add_parser("search-threads")
    search_parser.add_argument("--channel", default="reddit-public", help="Canal a buscar: reddit-public, reddit, twitter")
    search_parser.add_argument("--limit", type=int, default=5, help="Maximo de oportunidades a encontrar")
    search_parser.add_argument("--model", default="", help="Modelo OpenRouter")
    search_parser.add_argument("--dry-run", action="store_true", help="Genera sin guardar en distribution_log")

    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("--channel", default="", help="Filtrar por canal: reddit, linkedin, twitter")
    publish_parser.add_argument("--limit", type=int, default=10, help="Maximo de entradas a publicar")
    publish_parser.add_argument("--dry-run", action="store_true", help="Simula publicacion sin postear")

    assist_comment_parser = sub.add_parser("assist-comment")
    assist_comment_parser.add_argument("--channel", default="reddit", help="Filtrar por canal")
    assist_comment_parser.add_argument("--limit", type=int, default=1, help="Cantidad de comentarios a preparar")
    assist_comment_parser.add_argument("--status", default="proposed", help="Status a preparar")
    assist_comment_parser.add_argument("--no-browser", action="store_true", help="No abre el navegador")
    assist_comment_parser.add_argument("--no-copy", action="store_true", help="No copia al portapapeles")

    browser_search_parser = sub.add_parser("browser-search")
    browser_search_parser.add_argument("--channel", required=True, choices=["facebook", "instagram", "linkedin", "reddit", "twitter", "x", "youtube"])
    browser_search_parser.add_argument("--limit", type=int, default=5)
    browser_search_parser.add_argument("--no-browser", action="store_true", help="Solo imprime/guarda URLs")
    browser_search_parser.add_argument("--dry-run", action="store_true", help="No guarda tareas")

    context_parser = sub.add_parser("create-comment-from-context")
    context_parser.add_argument("--channel", required=True)
    context_parser.add_argument("--landing-slug", required=True)
    context_parser.add_argument("--url", default="")
    context_parser.add_argument("--context", required=True)
    context_parser.add_argument("--model", default="")
    context_parser.add_argument("--dry-run", action="store_true")

    sub.add_parser("start-browser")

    auto_browser_parser = sub.add_parser("auto-browser")
    auto_browser_parser.add_argument("--task", required=True, help="Ruta a un JSON de acciones")
    auto_browser_parser.add_argument("--dry-run", action="store_true", help="No ejecuta clicks ni escritura")

    auto_distribution_parser = sub.add_parser("auto-distribution")
    auto_distribution_parser.add_argument("--channels", default="linkedin,reddit", help="Canales separados por coma; usar all para todos")
    auto_distribution_parser.add_argument("--limit", type=int, default=1, help="Maximo de publicaciones")
    auto_distribution_parser.add_argument("--per-channel", type=int, default=1, help="Maximo por red en esta corrida")
    auto_distribution_parser.add_argument("--dry-run", action="store_true", help="No hace clicks de publicar")
    auto_distribution_parser.add_argument("--allow-proposed", action="store_true", help="Permite publicar status=proposed")

    auto_listen_parser = sub.add_parser("auto-listen")
    auto_listen_parser.add_argument("--channels", default="all", help="Canales separados por coma; usar all")
    auto_listen_parser.add_argument("--searches", type=int, default=3, help="Cantidad de landings/queries")
    auto_listen_parser.add_argument("--per-search", type=int, default=3, help="Items por busqueda")
    auto_listen_parser.add_argument("--dry-run", action="store_true")

    for command in sorted(PENDING_COMMANDS):
        sub.add_parser(command)

    args = parser.parse_args()
    if args.command == "weekly":
        run_weekly(args)
    elif args.command == "daily":
        run_daily(args)
    elif args.command == "lead-magnets":
        run_single(args)
    elif args.command == "geo-audit":
        run_single(args)
    elif args.command == "nurture":
        run_single(args)
    elif args.command == "distribution":
        run_single(args)
    elif args.command in {"conversion", "feedback"}:
        run_single(args)
    elif args.command == "search-threads":
        run_single(args)
    elif args.command == "publish":
        run_single(args)
    elif args.command == "assist-comment":
        run_single(args)
    elif args.command in {"browser-search", "create-comment-from-context", "start-browser", "auto-browser", "auto-distribution", "auto-listen"}:
        run_single(args)
    elif args.command in PENDING_COMMANDS:
        pending_command(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
