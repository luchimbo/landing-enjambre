#!/usr/bin/env python3
"""
Agente 4: Auditor GEO / Espia de IAs

Responsabilidades:
- Leer prompts estrategicos desde data/geo_prompts.csv
- Consultar multiples modelos via OpenRouter
- Detectar menciones a PC MIDI Center y competidores
- Asignar score de visibilidad 0-5
- Guardar resultados en data/geo_audits.jsonl
- Proponer oportunidades de contenido en data/content_feedback.jsonl

Uso:
    python agente_geo_audit.py audit [--limit N] [--dry-run] [--models m1,m2]
    python agente_geo_audit.py status
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.env import load_env

load_env()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

GEO_PROMPTS_FILE = DATA_DIR / "geo_prompts.csv"
GEO_AUDITS_FILE = DATA_DIR / "geo_audits.jsonl"
CONTENT_FEEDBACK_FILE = DATA_DIR / "content_feedback.jsonl"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODELS = [
    "deepseek/deepseek-v4-flash",
    "tencent/hy3-preview",
    "openrouter/owl-alpha",
    "google/gemini-2.5-flash-lite",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4-5",
]

# Aliases conocidos de PC MIDI en texto
PCMIDI_PATTERNS = [
    r"pc\s*midi\s*center",
    r"pc\s*midi",
    r"pcmidi",
    r"pcmidicenter",
]

COMPETITORS = [
    "musimundo",
    "parquer",
    "mercado libre",
    "mercadolibre",
    "guitarras quezada",
    "quezada",
    "ferchordsound",
    "ferchor",
    "audiomusica",
    "audio musica",
    "guitar center",
    "sweetwater",
    "thomann",
    "amazon",
    "aliexpress",
    "ebay",
    "baires audio",
    "baires-audio",
    "backstage",
    "casa del musico",
    "el musico",
    "zipppo",
    "zippo music",
]


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timestamp()
    path = REPORTS_DIR / f"{stamp}-geo-audit-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_prompts(limit: int = 0) -> list[dict]:
    if not GEO_PROMPTS_FILE.exists():
        raise SystemExit(f"geo-audit: no se encontro {GEO_PROMPTS_FILE}")
    rows = []
    with open(GEO_PROMPTS_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if limit > 0:
        rows = rows[:limit]
    return rows


def query_openrouter(model: str, prompt: str, api_key: str) -> dict:
    try:
        import openai
    except ImportError:
        raise SystemExit("geo-audit: necesitas instalar openai: pip install openai")

    client = openai.OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        text = completion.choices[0].message.content or ""
        return {"ok": True, "text": text, "error": None}
    except Exception as e:
        return {"ok": False, "text": "", "error": str(e)}


def score_response(text: str) -> int:
    """Asigna score 0-5 segun presencia de PC MIDI Center."""
    lower = text.lower()

    mentioned = any(re.search(p, lower) for p in PCMIDI_PATTERNS)
    if not mentioned:
        return 0

    # Buscar si aparece con link o URL
    if re.search(r"pcmidicenter\.com|pc\s*midi.*https?://", lower):
        # Verificar si es el primero en ser mencionado o referencia principal
        first_mention = min(
            (m.start() for p in PCMIDI_PATTERNS for m in [re.search(p, lower)] if m),
            default=9999,
        )
        # Si aparece en los primeros 300 chars del texto util (excluyendo system)
        if first_mention < 300:
            return 5
        return 4

    # Buscar contexto positivo alrededor de la mencion
    positive_words = ["recomiendo", "recomendable", "confiable", "excelente", "buena opcion", "principal", "mejor"]
    has_positive = any(w in lower for w in positive_words)

    # Detectar si esta entre varias opciones o es la unica
    option_markers = [r"\d\.", r"\*\s", r"-\s", "tambien", "ademas", "otra opcion"]
    is_among_options = any(re.search(m, lower) for m in option_markers)

    if has_positive and not is_among_options:
        return 3
    if is_among_options:
        return 2
    return 1


def detect_competitors(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for comp in COMPETITORS:
        if comp in lower:
            found.append(comp)
    return found


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\)\]\"']+", text)


def build_content_suggestion(prompt_row: dict, score: int, competitors: list[str]) -> str:
    prompt = prompt_row["prompt"]
    category = prompt_row.get("category", "general")
    if score == 0:
        return f"Crear landing o articulo que responda directamente: '{prompt}' — PC MIDI no aparece en ningun modelo para [{category}]"
    if score <= 2:
        comp_str = f" (competidores mencionados: {', '.join(competitors)})" if competitors else ""
        return f"Mejorar autoridad GEO para '{prompt}'{comp_str} — PC MIDI aparece pero con baja visibilidad"
    return f"Reforzar presencia para '{prompt}' — score {score}/5, potencial de mejora"


def run_audit(args: argparse.Namespace) -> None:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("geo-audit: falta OPENROUTER_API_KEY en .env o variables de entorno")

    models = DEFAULT_MODELS
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]

    prompts = load_prompts(limit=args.limit)
    print(f"geo-audit: {len(prompts)} prompts x {len(models)} modelos = {len(prompts) * len(models)} consultas")

    if args.dry_run:
        print("geo-audit: modo dry-run — no se guardaran datos")

    audit_results: list[dict] = []
    feedback_entries: list[dict] = []
    errors: list[dict] = []

    for prompt_row in prompts:
        pid = prompt_row["id"]
        prompt_text = prompt_row["prompt"]
        print(f"  prompt {pid}: {prompt_text[:60]}")

        prompt_scores: list[int] = []

        for model in models:
            print(f"    -> {model} ...", end="", flush=True)
            response = query_openrouter(model, prompt_text, api_key)

            if not response["ok"]:
                print(f" ERROR: {response['error']}")
                errors.append({"prompt_id": pid, "model": model, "error": response["error"]})
                continue

            text = response["text"]
            score = score_response(text)
            competitors = detect_competitors(text)
            urls = extract_urls(text)
            pcmidi_mentioned = score > 0
            content_gap = score < 3

            print(f" score={score}" + (f" competidores={competitors}" if competitors else ""))

            entry = {
                "timestamp_utc": timestamp(),
                "prompt_id": pid,
                "prompt": prompt_text,
                "category": prompt_row.get("category", ""),
                "priority": prompt_row.get("priority", ""),
                "provider": "openrouter",
                "model": model,
                "response_text": text,
                "score": score,
                "pcmidi_mentioned": pcmidi_mentioned,
                "competitors": competitors,
                "urls_cited": urls,
                "content_gap": content_gap,
            }
            audit_results.append(entry)
            prompt_scores.append(score)

        # Generar feedback si el score promedio es bajo
        if prompt_scores:
            avg_score = sum(prompt_scores) / len(prompt_scores)
            all_competitors = list({c for r in audit_results if r["prompt_id"] == pid for c in r["competitors"]})
            if avg_score < 3:
                suggestion = build_content_suggestion(prompt_row, round(avg_score), all_competitors)
                priority = "high" if avg_score < 1 else "medium"
                feedback_entries.append({
                    "source": "geo-audit",
                    "timestamp_utc": timestamp(),
                    "prompt_id": pid,
                    "prompt": prompt_text,
                    "category": prompt_row.get("category", ""),
                    "avg_score": round(avg_score, 2),
                    "gap_type": "no_visibility" if avg_score < 1 else "low_visibility",
                    "suggestion": suggestion,
                    "priority": priority,
                    "competitors_seen": all_competitors,
                })

    # Resumen
    total = len(audit_results)
    scored = [r["score"] for r in audit_results]
    avg = round(sum(scored) / len(scored), 2) if scored else 0
    mentioned_count = sum(1 for r in audit_results if r["pcmidi_mentioned"])

    print(f"\ngeo-audit: {total} respuestas — score promedio={avg} — menciones PC MIDI={mentioned_count}/{total}")
    print(f"geo-audit: {len(feedback_entries)} oportunidades de contenido detectadas")

    if not args.dry_run:
        # Append a geo_audits.jsonl
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(GEO_AUDITS_FILE, "a", encoding="utf-8") as f:
            for entry in audit_results:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"geo-audit: {len(audit_results)} entradas guardadas en {GEO_AUDITS_FILE}")

        # Append a content_feedback.jsonl
        if feedback_entries:
            with open(CONTENT_FEEDBACK_FILE, "a", encoding="utf-8") as f:
                for entry in feedback_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"geo-audit: {len(feedback_entries)} oportunidades guardadas en {CONTENT_FEEDBACK_FILE}")

    report_data = {
        "command": "geo-audit",
        "status": "ok",
        "dry_run": args.dry_run,
        "models": models,
        "prompts_processed": len(prompts),
        "responses_total": total,
        "avg_score": avg,
        "pcmidi_mentions": mentioned_count,
        "content_gaps": len(feedback_entries),
        "errors": errors,
    }
    report_path = write_report("run", report_data)
    print(f"geo-audit: reporte en {report_path}")


def run_status(_args: argparse.Namespace) -> None:
    if not GEO_AUDITS_FILE.exists():
        print("geo-audit: no hay audits previos en", GEO_AUDITS_FILE)
        return

    entries = []
    with open(GEO_AUDITS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if not entries:
        print("geo-audit: archivo vacio")
        return

    total = len(entries)
    scores = [e["score"] for e in entries]
    avg = round(sum(scores) / len(scores), 2)
    mentioned = sum(1 for e in entries if e.get("pcmidi_mentioned"))
    last_ts = max(e["timestamp_utc"] for e in entries)
    models_seen = sorted({e["model"] for e in entries})
    prompts_seen = sorted({e["prompt_id"] for e in entries})

    print(f"geo-audit status:")
    print(f"  total respuestas : {total}")
    print(f"  score promedio   : {avg}/5")
    print(f"  menciones PC MIDI: {mentioned}/{total} ({round(mentioned/total*100)}%)")
    print(f"  ultimo audit     : {last_ts}")
    print(f"  modelos usados   : {', '.join(models_seen)}")
    print(f"  prompts cubiertos: {', '.join(prompts_seen)}")

    if CONTENT_FEEDBACK_FILE.exists():
        gaps = sum(1 for line in CONTENT_FEEDBACK_FILE.read_text(encoding="utf-8").splitlines() if line.strip())
        print(f"  oportunidades    : {gaps} en {CONTENT_FEEDBACK_FILE.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente 4: Auditor GEO / Espia de IAs")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    audit_p = sub.add_parser("audit", help="Ejecutar ciclo completo de auditoria GEO")
    audit_p.add_argument("--limit", type=int, default=0, help="Maximo de prompts a procesar (0=todos)")
    audit_p.add_argument("--dry-run", action="store_true", help="Consulta APIs pero no escribe datos")
    audit_p.add_argument("--models", default="", help="Modelos separados por coma (default: todos)")

    sub.add_parser("status", help="Mostrar resumen del ultimo audit")

    args = parser.parse_args()

    if args.subcommand == "audit":
        run_audit(args)
    elif args.subcommand == "status":
        run_status(args)


if __name__ == "__main__":
    main()
