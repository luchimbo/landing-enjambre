import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
BUILD_SCRIPT = ROOT / "build_landings.py"

PENDING_COMMANDS = {"geo-audit", "distribution", "conversion", "feedback"}
LEAD_MAGNET_SCRIPT = ROOT / "agente_lead_magnets.py"
NURTURE_SCRIPT = ROOT / "agente_4_nurture.py"


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
    elif args.command == "nurture":
        command_args = nurture_args(args)
        step = run_step(args.command, command_args, script=NURTURE_SCRIPT)
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

    lead_parser = sub.add_parser("lead-magnets")
    add_common_generation_options(lead_parser)

    nurture_parser = sub.add_parser("nurture")
    nurture_parser.add_argument("--limit", type=int, default=50, help="Maximo de mensajes a procesar")
    nurture_parser.add_argument("--dry-run", action="store_true", help="Simula sin enviar emails")
    nurture_parser.add_argument("--retry", action="store_true", help="Reintenta mensajes fallidos")

    for command in sorted(PENDING_COMMANDS):
        sub.add_parser(command)

    args = parser.parse_args()
    if args.command == "weekly":
        run_weekly(args)
    elif args.command == "lead-magnets":
        run_single(args)
    elif args.command == "nurture":
        run_single(args)
    elif args.command in PENDING_COMMANDS:
        pending_command(args)
    else:
        run_single(args)


if __name__ == "__main__":
    main()
