import argparse
import json
import os
import re
import time
import webbrowser
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
LANDINGS_PATH = DATA_DIR / "landings_aprobadas.jsonl"
DISTRIBUTION_LOG_PATH = DATA_DIR / "distribution_log.jsonl"
SITEMAP_PATH = ROOT / "site" / "sitemap.xml"
CONTENT_FEEDBACK_PATH = DATA_DIR / "content_feedback.jsonl"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
BASE_URL = "https://blog.pcmidicenter.com"

FORBIDDEN_CLAIMS = [
    "stock garantizado",
    "disponibilidad garantizada",
    "distribuidor oficial",
    "soporte tecnico oficial",
    "soporte técnico oficial",
    "canal oficial",
    "exclusividad",
    "reparaciones",
    "alquileres",
    "clases formales",
    "precio",
    "precios",
    "cuota",
    "cuotas",
    "mejor precio",
    "yo lo use",
    "yo lo usé",
    "te lo recomiendo",
    "lo recomiendo",
    "lo compré",
    "lo compre",
    "disponible",
    "hay stock",
    "en stock",
]

SPAM_PATTERNS = [
    r"\b(compra\s+ahora|buy\s+now|haz\s+clic|click\s+aqui|oferta\s+limitada|tiempo\s+limitado)\b",
    r"!!+",
    r"\$\d+",
    r"\b(gratis|free|descuento|promo)\b",
]

EVERGREEN_SLUGS = [
    "home-studio",
    "interfaz-de-audio",
    "microfono",
    "monitor",
    "controlador-midi",
    "teclado-midi",
    "interfaz-audio",
]

CHANNEL_COMMUNITIES = {
    "reddit": ["r/ableton", "r/FL_Studio", "r/edmproduction", "r/WeAreTheMusicMakers", "r/homerecording", "r/audioengineering"],
    "forum": ["kvraudio.com/forum", "gearslutz.com/boards", "produccionmusical.es/foro"],
    "linkedin": ["LinkedIn"],
    "social": ["Facebook grupos produccion musical"],
    "newsletter": ["newsletter"],
}

CONTENT_TYPES = {
    "respuesta_tecnica": {
        "channels": ["reddit", "forum"],
        "link_included": True,
        "risk_level": "low",
    },
    "post_educativo": {
        "channels": ["linkedin", "social"],
        "link_included": True,
        "risk_level": "low",
    },
    "snippet_social": {
        "channels": ["social", "newsletter"],
        "link_included": False,
        "risk_level": "low",
    },
    "post_social": {
        "channels": ["facebook", "instagram"],
        "link_included": True,
        "risk_level": "low",
    },
    "post_x": {
        "channels": ["x"],
        "link_included": False,
        "risk_level": "low",
    },
    "respuesta_youtube": {
        "channels": ["youtube"],
        "link_included": True,
        "risk_level": "low",
    },
}


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido en {path}:{line_no}: {exc}") from exc
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = REPORTS_DIR / f"{stamp}-distribution-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_sitemap_slugs() -> set[str]:
    if not SITEMAP_PATH.exists():
        return set()
    try:
        tree = ET.parse(SITEMAP_PATH)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        slugs = set()
        for loc in tree.findall(".//sm:loc", ns):
            text = (loc.text or "").rstrip("/")
            slug = text.rstrip("/").split("/")[-1]
            if slug:
                slugs.add(slug)
        return slugs
    except ET.ParseError:
        return set()


def load_last_deploy_date() -> str | None:
    """Returns the date string of the most recent build report, or None."""
    if not REPORTS_DIR.exists():
        return None
    build_reports = sorted(REPORTS_DIR.glob("*-build.json"), reverse=True)
    if not build_reports:
        # Also check swarm build reports
        build_reports = sorted(REPORTS_DIR.glob("*-swarm-build.json"), reverse=True)
    if not build_reports:
        return None
    # Timestamp is the first 8 chars of the filename (YYYYMMDD)
    stem = build_reports[0].name
    return stem[:8] if len(stem) >= 8 else None


def already_proposed_slugs(log: list[dict], channel_filter: str | None) -> set[str]:
    """Slugs that already have a proposed/published entry in the log."""
    seen = set()
    for entry in log:
        status = entry.get("status", "")
        if status in {"proposed", "published", "approved"}:
            if channel_filter and entry.get("channel") != channel_filter:
                continue
            seen.add(entry.get("landing_slug", ""))
    return seen


def score_landing(landing: dict, geo_gap_slugs: set[str]) -> int:
    slug = landing.get("slug", "")
    score = 0
    if slug in geo_gap_slugs:
        score += 10
    for kw in EVERGREEN_SLUGS:
        if kw in slug:
            score += 5
            break
    if "vs" in slug or "comparar" in slug or "mejor" in slug:
        score += 3
    return score


def select_landings(
    landings: list[dict],
    sitemap_slugs: set[str],
    already_done: set[str],
    geo_gap_slugs: set[str],
    limit: int,
    since_last_deploy: bool,
) -> list[dict]:
    last_deploy_date = load_last_deploy_date() if since_last_deploy else None

    candidates = []
    for landing in landings:
        slug = landing.get("slug", "")
        if not slug:
            continue
        if slug not in sitemap_slugs:
            continue
        if slug in already_done:
            continue
        if since_last_deploy and last_deploy_date:
            # We can't know exact publish date from the landing record,
            # so we accept all published slugs when since_last_deploy is set
            # and the deploy happened today.
            pass
        candidates.append(landing)

    candidates.sort(key=lambda l: score_landing(l, geo_gap_slugs), reverse=True)
    return candidates[:limit]


def extract_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("La IA no devolvio un objeto JSON")
    return json.loads(text[start : end + 1])


def chat_json(system: str, user: str, model: str, temperature: float = 0.4) -> dict:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENROUTER_API_KEY en .env o variables de entorno")
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://www.pcmidi.com.ar/",
            "X-Title": "PC MIDI Distribution Agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Error OpenRouter {exc.code}: {detail}") from exc
    content = data["choices"][0]["message"]["content"]
    return extract_json_object(content)


SYSTEM_PROMPT = """Sos experto en produccion musical y escribis contenido util para comunidades online de musicos y productores.
Tu objetivo es ayudar a musicos y productores a tomar mejores decisiones tecnicas antes de comprar equipos.

Reglas absolutas:
- NUNCA menciones precios, stock, disponibilidad ni cuotas.
- NUNCA digas que PC MIDI es distribuidor oficial ni uses esa frase.
- NUNCA simules experiencia personal: no uses "yo lo use", "lo compre", "te lo recomiendo".
- NUNCA uses lenguaje de venta agresiva: "oferta limitada", "compra ahora", etc.
- Solo incluye el link si aporta informacion genuinamente util al lector.
- El contenido debe ser util por si solo, sin necesidad del link.
- Adapta el tono al canal indicado.
- Devolve SOLO JSON valido, sin markdown ni texto adicional."""


def build_user_prompt(landing: dict, content_type: str) -> str:
    slug = landing.get("slug", "")
    keyword = landing.get("keyword", "")
    h1 = landing.get("h1", "")
    intent = landing.get("intent", "")
    url = f"{BASE_URL}/{slug}/"

    faqs = landing.get("faqs", [])
    faqs_text = "\n".join(f"- P: {f['q']}\n  R: {f['a']}" for f in faqs[:3]) if faqs else ""

    steps = landing.get("steps", [])
    steps_text = "\n".join(f"- {s.get('t','')}: {s.get('b','')}" for s in steps[:3]) if steps else ""

    if content_type == "respuesta_tecnica":
        channel_note = "para Reddit o foro tecnico de produccion musical"
        tone_note = "Tono: tecnico, util, sin comercial. Maximo 300 palabras."
        link_note = f'Si suma contexto real, podes mencionar: "{url}"'
        format_note = '"channel": "reddit", "community": "r/edmproduction"'
    elif content_type == "post_educativo":
        channel_note = "para LinkedIn o grupo de Facebook sobre produccion musical"
        tone_note = "Tono: educativo, claro, sin venta agresiva. Maximo 250 palabras."
        link_note = f'Si suma contexto real, menciona: "{url}"'
        format_note = '"channel": "linkedin", "community": "LinkedIn"'
    elif content_type == "post_social":
        channel_note = "para Facebook o Instagram (publico general interesado en musica)"
        tone_note = "Tono: conversacional, cercano, sin jerga tecnica. Maximo 200 palabras. Podes usar 1-2 emojis naturales."
        link_note = f'Incluye al final: "{url}" como referencia para quien quiera profundizar.'
        format_note = '"channel": "facebook", "community": "Facebook grupos produccion musical"'
    elif content_type == "post_x":
        channel_note = "para X (Twitter) — espacio limitado, impacto rapido"
        tone_note = "Tono: directo, informativo. MAXIMO 270 caracteres totales incluyendo espacios. Sin link (penaliza alcance)."
        link_note = "NO incluyas link. El texto debe funcionar solo."
        format_note = '"channel": "x", "community": "X"'
    elif content_type == "respuesta_youtube":
        channel_note = "para comentar en un video de YouTube sobre produccion musical"
        tone_note = "Tono: util, aportando valor tecnico como primer comentario. Maximo 250 palabras."
        link_note = f'Si el tema lo justifica, incluye: "{url}" como recurso adicional.'
        format_note = '"channel": "youtube", "community": "YouTube"'
    else:  # snippet_social
        channel_note = "para newsletter o comunidad que no permite links comerciales"
        tone_note = "Tono: util, breve, sin link directo. Maximo 150 palabras."
        link_note = "NO incluyas el link en el cuerpo."
        format_note = '"channel": "social", "community": "newsletter"'

    return f"""Landing:
- keyword: {keyword}
- intencion: {intent}
- H1: {h1}
- URL: {url}

FAQs relevantes:
{faqs_text}

Pasos clave:
{steps_text}

Tipo de pieza: {content_type} ({channel_note})
{tone_note}
{link_note}

Genera el siguiente JSON:
{{
  "title": "titulo de la pieza (max 80 caracteres)",
  "body": "texto completo de la pieza",
  "link_included": true_o_false,
  {format_note},
  "notes": "nota interna sobre donde publicar o que revisar antes de publicar"
}}"""


def detect_spam(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, lower):
            found.append(pattern)
    return found


def validate_piece(piece: dict, sitemap_slugs: set[str]) -> list[str]:
    errors = []
    body = piece.get("body", "")
    title = piece.get("title", "")
    full_text = f"{title} {body}".lower()

    for claim in FORBIDDEN_CLAIMS:
        if claim.lower() in full_text:
            errors.append(f"claim prohibido: {claim}")

    spam = detect_spam(full_text)
    for s in spam:
        errors.append(f"patron spam: {s}")

    # Validate link if included
    if piece.get("link_included"):
        url_matches = re.findall(r"https?://[^\s\"']+", body)
        for url in url_matches:
            slug = url.rstrip("/").split("/")[-1]
            if slug and slug not in sitemap_slugs and "pcmidi" not in url and "blog.pcmidicenter" not in url:
                errors.append(f"link no pertenece a sitemap: {url}")

    if not body.strip() or len(body.strip()) < 50:
        errors.append("cuerpo demasiado corto o vacio")

    if not title.strip():
        errors.append("titulo vacio")

    return errors


def build_distribution_record(
    landing: dict,
    piece: dict,
    content_type: str,
    status: str,
    errors: list[str] | None = None,
    run_id: str = "",
) -> dict:
    slug = landing.get("slug", "")
    url = f"{BASE_URL}/{slug}/"
    channel = piece.get("channel", CONTENT_TYPES[content_type]["channels"][0])
    community = piece.get("community", channel)
    link_included = piece.get("link_included", CONTENT_TYPES[content_type]["link_included"])

    status = "approved"
    requires_review = False
    notes = piece.get("notes", "")
    if errors:
        notes = f"ADVERTENCIAS: {'; '.join(errors)}. " + notes

    return {
        "id": f"{run_id}:{slug}:{content_type}:{channel}:{int(time.time() * 1000)}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "landing_slug": slug,
        "landing_url": url,
        "channel": channel,
        "community": community,
        "content_type": content_type,
        "status": status,
        "title": piece.get("title", ""),
        "body": piece.get("body", ""),
        "link_included": link_included,
        "risk_level": CONTENT_TYPES[content_type]["risk_level"],
        "requires_manual_review": requires_review,
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "scheduled_for_utc": "",
        "prepared_at_utc": "",
        "published_url": "",
        "notes": notes,
    }


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def update_log_records(predicate, updater, dry_run: bool) -> tuple[list[dict], list[dict]]:
    rows = load_jsonl(DISTRIBUTION_LOG_PATH)
    changed = []
    new_rows = []
    for row in rows:
        if predicate(row):
            updated = dict(row)
            updater(updated)
            changed.append(updated)
            new_rows.append(updated)
        else:
            new_rows.append(row)
    if changed and not dry_run:
        rewrite_jsonl(DISTRIBUTION_LOG_PATH, new_rows)
    return changed, new_rows


def record_matches(row: dict, channel: str | None, status: set[str] | None) -> bool:
    if channel and row.get("channel") != channel:
        return False
    if status and row.get("status") not in status:
        return False
    return True


def approve_records(limit: int, channel: str | None, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    def predicate(row: dict) -> bool:
        nonlocal count
        if count >= limit:
            return False
        if not record_matches(row, channel, {"proposed"}):
            return False
        if row.get("requires_manual_review") and row.get("risk_level") not in {"low", "medium"}:
            return False
        count += 1
        return True

    def updater(row: dict) -> None:
        row["status"] = "bulk_approved"
        row["approved_at_utc"] = now
        row["approval_mode"] = "bulk_content_only"
        row["notes"] = (row.get("notes", "") + " Aprobado masivamente como contenido; requiere confirmacion final por pieza en canales externos.").strip()

    changed, _ = update_log_records(predicate, updater, dry_run)
    summary = {"command": "distribution approve", "status": "ok", "dry_run": dry_run, "approved": len(changed), "channel": channel}
    report_path = write_report("approve", summary)
    print(f"distribution approve: {len(changed)} registros aprobados como contenido. Reporte: {report_path}")
    return {**summary, "report": str(report_path)}


def approve_all_records(channel: str | None, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat()

    def predicate(row: dict) -> bool:
        if channel and row.get("channel") != channel:
            return False
        return row.get("status") not in {"published"}

    def updater(row: dict) -> None:
        previous = row.get("status", "")
        row["status"] = "approved"
        row["approved_at_utc"] = row.get("approved_at_utc") or now
        row["requires_manual_review"] = False
        row["approval_mode"] = "auto_always_approved"
        row["previous_status"] = previous
        note = row.get("notes", "")
        marker = "Marcado como approved por politica auto_always_approved."
        row["notes"] = f"{note} {marker}".strip() if marker not in note else note

    changed, _ = update_log_records(predicate, updater, dry_run)
    summary = {
        "command": "distribution approve-all",
        "status": "ok",
        "dry_run": dry_run,
        "approved": len(changed),
        "channel": channel,
    }
    report_path = write_report("approve-all", summary)
    print(f"distribution approve-all: {len(changed)} registros marcados approved. Reporte: {report_path}")
    return {**summary, "report": str(report_path)}


def schedule_records(limit: int, channel: str | None, interval_minutes: int, start_at: str, dry_run: bool) -> dict:
    start = parse_dt(start_at) if start_at else datetime.now(timezone.utc)
    if start is None:
        raise SystemExit("distribution schedule: --start-at debe ser ISO-8601, ej: 2026-05-26T18:00:00Z")
    scheduled_count = 0

    def predicate(row: dict) -> bool:
        nonlocal scheduled_count
        if scheduled_count >= limit:
            return False
        if not record_matches(row, channel, {"bulk_approved"}):
            return False
        if row.get("scheduled_for_utc"):
            return False
        scheduled_count += 1
        return True

    def updater(row: dict) -> None:
        index = scheduled_count - 1
        row["status"] = "scheduled"
        row["scheduled_for_utc"] = (start + timedelta(minutes=interval_minutes * index)).isoformat()
        row["schedule_mode"] = "manual_publish_required_for_third_party"

    changed, _ = update_log_records(predicate, updater, dry_run)
    summary = {
        "command": "distribution schedule",
        "status": "ok",
        "dry_run": dry_run,
        "scheduled": len(changed),
        "channel": channel,
        "interval_minutes": interval_minutes,
        "first_scheduled_for_utc": changed[0].get("scheduled_for_utc") if changed else "",
    }
    report_path = write_report("schedule", summary)
    print(f"distribution schedule: {len(changed)} registros programados. Reporte: {report_path}")
    return {**summary, "report": str(report_path)}


def queue_records(limit: int, channel: str | None, ready_only: bool) -> dict:
    now = datetime.now(timezone.utc)
    rows = load_jsonl(DISTRIBUTION_LOG_PATH)
    items = []
    for row in rows:
        if channel and row.get("channel") != channel:
            continue
        if row.get("status") not in {"bulk_approved", "scheduled", "ready_for_manual_publish"}:
            continue
        scheduled = parse_dt(row.get("scheduled_for_utc", ""))
        if ready_only and scheduled and scheduled > now:
            continue
        items.append(row)
        if len(items) >= limit:
            break
    summary = {
        "command": "distribution queue",
        "status": "ok",
        "channel": channel,
        "ready_only": ready_only,
        "items": [
            {
                "id": item.get("id", ""),
                "status": item.get("status", ""),
                "scheduled_for_utc": item.get("scheduled_for_utc", ""),
                "channel": item.get("channel", ""),
                "community": item.get("community", ""),
                "landing_slug": item.get("landing_slug", ""),
                "title": item.get("title", ""),
            }
            for item in items
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def assist_records(limit: int, channel: str | None, open_browser: bool, dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    prepared = []

    def predicate(row: dict) -> bool:
        if len(prepared) >= limit:
            return False
        if channel and row.get("channel") != channel:
            return False
        if row.get("status") not in {"bulk_approved", "scheduled", "ready_for_manual_publish"}:
            return False
        scheduled = parse_dt(row.get("scheduled_for_utc", ""))
        if scheduled and scheduled > now:
            return False
        prepared.append(row)
        return True

    def updater(row: dict) -> None:
        row["status"] = "ready_for_manual_publish"
        row["prepared_at_utc"] = now.isoformat()

    changed, _ = update_log_records(predicate, updater, dry_run)
    for item in changed:
        print("\n--- DISTRIBUTION DRAFT ---")
        print(f"ID: {item.get('id', '')}")
        print(f"Canal: {item.get('channel', '')} / {item.get('community', '')}")
        print(f"Landing: {item.get('landing_url', '')}")
        print(f"Titulo: {item.get('title', '')}")
        print(item.get("body", ""))
        if open_browser and item.get("landing_url"):
            webbrowser.open(item["landing_url"])
    summary = {"command": "distribution assist", "status": "ok", "dry_run": dry_run, "prepared": len(changed), "channel": channel}
    report_path = write_report("assist", summary)
    print(f"\ndistribution assist: {len(changed)} drafts listos para confirmacion por pieza. Reporte: {report_path}")
    return {**summary, "report": str(report_path)}


def run_distribution(
    limit: int,
    dry_run: bool,
    channel_filter: str | None,
    since_last_deploy: bool,
    model: str,
) -> dict:
    load_env()
    started_at = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    # Load inputs
    landings = load_jsonl(LANDINGS_PATH)
    sitemap_slugs = load_sitemap_slugs()
    existing_log = load_jsonl(DISTRIBUTION_LOG_PATH)
    geo_feedback = load_jsonl(CONTENT_FEEDBACK_PATH)

    geo_gap_slugs: set[str] = {
        entry.get("slug", "") for entry in geo_feedback if entry.get("type") == "gap"
    }

    already_done = already_proposed_slugs(existing_log, channel_filter)

    selected = select_landings(
        landings=landings,
        sitemap_slugs=sitemap_slugs,
        already_done=already_done,
        geo_gap_slugs=geo_gap_slugs,
        limit=limit,
        since_last_deploy=since_last_deploy,
    )

    print(f"distribution: {len(selected)} landings seleccionadas de {len(landings)} aprobadas ({len(sitemap_slugs)} en sitemap)")

    proposed = []
    blocked = []
    errors_summary = []

    piece_types = list(CONTENT_TYPES.keys())
    if channel_filter:
        piece_types = [pt for pt, cfg in CONTENT_TYPES.items() if channel_filter in cfg["channels"]]
        if not piece_types:
            piece_types = list(CONTENT_TYPES.keys())

    for landing in selected:
        slug = landing.get("slug", "")
        print(f"  generando piezas para: {slug}")

        for content_type in piece_types:
            try:
                user_prompt = build_user_prompt(landing, content_type)
                piece = chat_json(SYSTEM_PROMPT, user_prompt, model=model)
            except Exception as exc:
                err_record = build_distribution_record(
                    landing, {"title": "", "body": "", "channel": channel_filter or "unknown"},
                    content_type, "blocked", [f"error_generacion: {exc}"], run_id,
                )
                blocked.append(err_record)
                errors_summary.append({"slug": slug, "type": content_type, "reason": str(exc)})
                print(f"    blocked ({content_type}): {exc}")
                continue

            validation_errors = validate_piece(piece, sitemap_slugs)
            if validation_errors:
                rec = build_distribution_record(landing, piece, content_type, "blocked", validation_errors, run_id)
                blocked.append(rec)
                errors_summary.append({"slug": slug, "type": content_type, "errors": validation_errors})
                print(f"    blocked ({content_type}): {validation_errors}")
            else:
                rec = build_distribution_record(landing, piece, content_type, "proposed", None, run_id)
                proposed.append(rec)
                print(f"    proposed ({content_type}): {piece.get('title', '')[:60]}")

    if not dry_run:
        all_records = proposed + blocked
        if all_records:
            append_jsonl(DISTRIBUTION_LOG_PATH, all_records)

    summary = {
        "command": "distribution",
        "status": "ok",
        "model": model,
        "run_id": run_id,
        "dry_run": dry_run,
        "channel_filter": channel_filter,
        "since_last_deploy": since_last_deploy,
        "landings_selected": len(selected),
        "pieces_proposed": len(proposed),
        "pieces_blocked": len(blocked),
        "proposed": [{"slug": p["landing_slug"], "type": p["content_type"], "title": p["title"]} for p in proposed],
        "blocked": errors_summary[:50],
        "elapsed_seconds": round(time.monotonic() - started_at, 2),
    }

    report_path = write_report("run", summary)
    print(f"\ndistribution: {len(proposed)} propuestas generadas, {len(blocked)} bloqueadas")
    if not dry_run:
        print(f"distribution: guardado en {DISTRIBUTION_LOG_PATH}")
    print(f"distribution: reporte en {report_path}")

    return {**summary, "report": str(report_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente 5: Distribucion y Comunidades para PC MIDI Center")
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Genera piezas y las guarda como proposed")
    generate_parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima de landings a procesar")
    generate_parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help="Modelo OpenRouter")
    generate_parser.add_argument("--dry-run", action="store_true", help="Genera piezas sin guardar en disco")
    generate_parser.add_argument("--channel", default="", help="Filtrar por canal: reddit, forum, linkedin, social, newsletter")
    generate_parser.add_argument("--since-last-deploy", action="store_true", help="Prioriza landings del ultimo deploy")

    approve_parser = subparsers.add_parser("approve", help="Aprueba masivamente contenido proposed")
    approve_parser.add_argument("--limit", type=int, default=25)
    approve_parser.add_argument("--channel", default="")
    approve_parser.add_argument("--dry-run", action="store_true")

    approve_all_parser = subparsers.add_parser("approve-all", help="Marca todos los registros actuales como approved")
    approve_all_parser.add_argument("--channel", default="")
    approve_all_parser.add_argument("--dry-run", action="store_true")

    schedule_parser = subparsers.add_parser("schedule", help="Programa piezas bulk_approved para preparacion asistida")
    schedule_parser.add_argument("--limit", type=int, default=25)
    schedule_parser.add_argument("--channel", default="")
    schedule_parser.add_argument("--interval-minutes", type=int, default=45)
    schedule_parser.add_argument("--start-at", default="", help="ISO-8601 UTC opcional, ej: 2026-05-26T18:00:00Z")
    schedule_parser.add_argument("--dry-run", action="store_true")

    queue_parser = subparsers.add_parser("queue", help="Muestra cola aprobada/programada")
    queue_parser.add_argument("--limit", type=int, default=25)
    queue_parser.add_argument("--channel", default="")
    queue_parser.add_argument("--ready-only", action="store_true")

    assist_parser = subparsers.add_parser("assist", help="Prepara drafts vencidos para revision y confirmacion por pieza")
    assist_parser.add_argument("--limit", type=int, default=5)
    assist_parser.add_argument("--channel", default="")
    assist_parser.add_argument("--open-browser", action="store_true", help="Abre la landing de referencia en el navegador")
    assist_parser.add_argument("--dry-run", action="store_true")

    # Backward compatible default: `python agente_distribucion.py --limit 5` still generates.
    parser.add_argument("--limit", type=int, default=5, help=argparse.SUPPRESS)
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--channel", default="", help=argparse.SUPPRESS)
    parser.add_argument("--since-last-deploy", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()
    command = args.command or "generate"
    if command == "generate":
        run_distribution(
            limit=args.limit,
            dry_run=args.dry_run,
            channel_filter=args.channel or None,
            since_last_deploy=args.since_last_deploy,
            model=args.model,
        )
    elif command == "approve":
        approve_records(args.limit, args.channel or None, args.dry_run)
    elif command == "approve-all":
        approve_all_records(args.channel or None, args.dry_run)
    elif command == "schedule":
        schedule_records(args.limit, args.channel or None, args.interval_minutes, args.start_at, args.dry_run)
    elif command == "queue":
        queue_records(args.limit, args.channel or None, args.ready_only)
    elif command == "assist":
        assist_records(args.limit, args.channel or None, args.open_browser, args.dry_run)
    else:
        raise SystemExit(f"Comando no soportado: {command}")


if __name__ == "__main__":
    main()
