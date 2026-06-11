"""
Pure data functions for the dashboard.
Shared between api_server.py (local Flask) and api/dashboard.py (Vercel serverless).
No Flask, no process detection.
"""
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"

DISTRIBUTION_LOG = DATA_DIR / "distribution_log.jsonl"
ENGAGEMENT_LOG   = DATA_DIR / "engagement_log.jsonl"
GEO_AUDITS_LOG   = DATA_DIR / "geo_audits.jsonl"
CONTENT_FEEDBACK = DATA_DIR / "content_feedback.jsonl"
LANDINGS_FILE    = DATA_DIR / "landings_aprobadas.jsonl"
LEAD_MAGNETS_FILE = DATA_DIR / "lead_magnets.jsonl"
OPOR_FILE        = DATA_DIR / "oportunidades_research.jsonl"
HEARTBEAT_PATH   = DATA_DIR / "agent_heartbeat.json"


# ── File utilities ──────────────────────────────────────────────────────────────

def iter_jsonl(path):
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def tail_jsonl(path, n=50):
    if not path.exists():
        return []
    size = path.stat().st_size
    if size == 0:
        return []
    chunk = min(size, max(n * 4096, 65536))
    with open(path, "rb") as f:
        f.seek(max(0, size - chunk))
        at_start = f.tell() == 0
        raw = f.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    if not at_start and len(lines) > 1:
        lines = lines[1:]
    valid = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            valid.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return valid[-n:]


def count_jsonl_lines(path):
    if not path.exists():
        return 0
    with open(path, "rb") as f:
        return sum(1 for line in f if line.strip())


def count_jsonl_where(path, field, value):
    return sum(1 for r in iter_jsonl(path) if r.get(field) == value)


# ── Timestamps ──────────────────────────────────────────────────────────────────

def norm_ts(ts):
    if not ts:
        return ""
    if "T" in ts:
        return ts.replace("Z", "+00:00")
    try:
        parts = ts.split("-")
        if len(parts) >= 2:
            d, t = parts[0], parts[1]
            micro = parts[2] if len(parts) > 2 else "000000"
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}.{micro}+00:00"
    except Exception:
        pass
    return ts


def sort_ts(value):
    return norm_ts(value)


# ── Report helpers ──────────────────────────────────────────────────────────────

def latest_report(patterns):
    candidates = []
    for pat in patterns:
        candidates.extend(REPORTS_DIR.glob(pat))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.name)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def report_status(raw):
    if raw.get("status"):
        return raw["status"]
    if raw.get("returncode") not in (None, 0):
        return "failed"
    if raw.get("failed", 0):
        return "failed"
    return "ok"


def count_report_items(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    return 0


def report_day_from_path(path: Path) -> str:
    name = path.name
    if re.match(r"^\d{8}-", name):
        stamp = name[:8]
        return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"
    return ""


def agent_from_report_name(name: str, raw: dict) -> str:
    command_value = raw.get("command") or ""
    if isinstance(command_value, list):
        command_value = " ".join(str(part) for part in command_value)
    command = str(command_value).lower()
    haystack = f"{name.lower()} {command}"
    if "geo-audit" in haystack:
        return "GEO Audit"
    if "nurture" in haystack:
        return "Nurture"
    if "conversion" in haystack or "feedback" in haystack:
        return "Conversion"
    if "distribution" in haystack or "publicacion" in haystack or "publish" in haystack:
        return "Distribucion/Publicacion"
    if "lead-magnet" in haystack:
        return "Lead magnets"
    if "generate" in haystack:
        return "Landings"
    if "validate" in haystack:
        return "Validacion"
    if "build" in haystack or "deploy" in haystack or "manifest" in haystack:
        return "Build/Deploy"
    if "swarm" in haystack or command in {"daily", "weekly", "watch", "midday"}:
        return "Orquestador"
    return "Otros"


def int_field(raw: dict, *names: str) -> int:
    for name in names:
        value = raw.get(name)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return 0


# ── Publication helpers ─────────────────────────────────────────────────────────

def publication_status(rec: dict) -> str:
    if rec.get("auto_published_channels"):
        return "published"
    if rec.get("auto_publish_failures"):
        return "failed"
    return rec.get("status") or "unknown"


def publication_item(rec: dict) -> dict:
    publish_result = rec.get("auto_publish_result") or {}
    channel = rec.get("channel") or rec.get("community") or "distribucion"
    action = "publicacion" if rec.get("content_type") in {"post_educativo", "snippet_social"} else "comentario"
    if rec.get("approval_mode") == "auto_listen":
        action = "respuesta"
    return {
        "source": "distribution",
        "action": action,
        "channel": channel,
        "community": rec.get("community") or channel,
        "status": publication_status(rec),
        "title": rec.get("title") or rec.get("source_thread_title") or rec.get("landing_slug") or "Publicacion",
        "body": rec.get("body", ""),
        "target_url": (
            rec.get("published_url")
            or rec.get("source_thread_url")
            or publish_result.get("url")
            or rec.get("landing_url")
            or ""
        ),
        "landing_url": rec.get("landing_url", ""),
        "published_channels": sorted((rec.get("auto_published_channels") or {}).keys()),
        "failure_channels": sorted((rec.get("auto_publish_failures") or {}).keys()),
        "ts": norm_ts(
            rec.get("published_at")
            or rec.get("auto_publish_attempted_at_utc")
            or rec.get("approved_at_utc")
            or rec.get("created_at_utc")
            or ""
        ),
    }


# ── Recent report items ─────────────────────────────────────────────────────────

def recent_report_items(limit=8):
    allowed = (
        "swarm-daily", "swarm-weekly", "nurture-process", "conversion-run",
        "distribution-run", "publicacion-publish", "publicacion-search",
        "geo-audit-run", "swarm-engage", "generate", "build",
    )
    candidates = []
    for path in REPORTS_DIR.glob("*.json"):
        if not any(token in path.name for token in allowed):
            continue
        candidates.append(path)
    candidates.sort(key=lambda p: p.name, reverse=True)

    items = []
    for path in candidates[:limit * 2]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        command = raw.get("command") or path.stem
        status = report_status(raw)
        title = {
            "daily": "Flujo diario ejecutado",
            "weekly": "Flujo semanal ejecutado",
            "process": "Nurture procesado",
            "run": "Agente ejecutado",
            "distribution": "Piezas de distribucion generadas",
            "publish": "Publicacion procesada",
            "search": "Busqueda de hilos procesada",
            "build": "Sitio estatico construido",
            "generate": "Landings generadas",
            "engage": "Engagement ejecutado",
        }.get(command, command)
        detail_bits = []
        if raw.get("steps"):
            detail_bits.append(f"{len(raw.get('steps') or [])} pasos")
        if raw.get("landings_selected") is not None:
            detail_bits.append(f"{raw.get('landings_selected')} landings")
        if raw.get("pieces_proposed") is not None:
            detail_bits.append(f"{raw.get('pieces_proposed')} propuestas")
        if raw.get("pieces_blocked") is not None:
            detail_bits.append(f"{raw.get('pieces_blocked')} bloqueadas")
        if raw.get("published") is not None:
            detail_bits.append(f"{raw.get('published')} publicadas")
        if raw.get("landings_analyzed") is not None:
            detail_bits.append(f"{raw.get('landings_analyzed')} landings analizadas")
        if raw.get("results"):
            results = raw.get("results") or {}
            detail_bits.append(
                f"{results.get('sent', 0)} enviados, {results.get('failed', 0)} fallidos"
            )
        items.append({
            "source": "report",
            "kind": command,
            "title": title,
            "detail": " · ".join(detail_bits) or path.name,
            "status": status,
            "ts": norm_ts(raw.get("timestamp_utc", "")),
        })
    return items


# ── Daily / weekly / lifetime summaries ────────────────────────────────────────

def daily_report_summary(day: str = "") -> dict:
    reports = []
    for path in REPORTS_DIR.glob("*.json"):
        report_day = report_day_from_path(path)
        if not report_day:
            continue
        if day and report_day != day:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append((path, report_day, raw))

    days = sorted({d for _, d, _ in reports}, reverse=True)
    if not day:
        day = days[0] if days else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reports = [(p, d, r) for p, d, r in reports if d == day]

    agent_rows = {}
    totals = Counter()
    events = []
    statuses = Counter()

    for path, _, raw in reports:
        status = report_status(raw)
        statuses[status] += 1
        agent = agent_from_report_name(path.name, raw)
        row = agent_rows.setdefault(agent, {
            "agent": agent,
            "runs": 0, "ok": 0, "failed": 0, "warnings": 0,
            "created": 0, "skipped": 0, "blocked": 0,
            "published": 0, "sent": 0, "proposed": 0,
            "last_status": status,
            "last_run": raw.get("timestamp_utc") or path.name,
            "notes": [],
        })
        row["runs"] += 1
        row["last_status"] = status
        row["last_run"] = raw.get("timestamp_utc") or path.name
        if status in {"ok", "snapshot", "pending_configuration"}:
            row["ok"] += 1
        elif "warning" in str(status):
            row["warnings"] += 1
        else:
            row["failed"] += 1

        created   = int_field(raw, "created_count")
        skipped   = int_field(raw, "skipped_count")
        blocked   = int_field(raw, "blocked_count", "pieces_blocked")
        published = int_field(raw, "published")
        proposed  = int_field(raw, "pieces_proposed")

        if raw.get("results") and isinstance(raw["results"], dict):
            sent   = int_field(raw["results"], "sent")
            failed = int_field(raw["results"], "failed")
            row["sent"]   += sent
            row["failed"] += failed
            totals["emails_sent"] += sent

        row["created"]   += created
        row["skipped"]   += skipped
        row["blocked"]   += blocked
        row["published"] += published
        row["proposed"]  += proposed
        totals["created"]   += created
        totals["skipped"]   += skipped
        totals["blocked"]   += blocked
        totals["published"] += published
        totals["proposed"]  += proposed

        note_bits = []
        if created:
            note_bits.append(f"{created} creados")
        if proposed:
            note_bits.append(f"{proposed} propuestas")
        if published:
            note_bits.append(f"{published} publicados")
        if blocked:
            note_bits.append(f"{blocked} bloqueados")
        if raw.get("landings_analyzed") is not None:
            note_bits.append(f"{raw.get('landings_analyzed')} landings analizadas")
        if raw.get("reason"):
            note_bits.append(str(raw.get("reason")))
        if note_bits and len(row["notes"]) < 3:
            row["notes"].append(" / ".join(note_bits))

        events.append({
            "agent": agent,
            "command": raw.get("command") or path.stem,
            "status": status,
            "ts": norm_ts(raw.get("timestamp_utc") or path.name),
            "detail": " / ".join(note_bits) or path.name,
        })

    events.sort(key=lambda item: item.get("ts", ""), reverse=True)
    rows = sorted(agent_rows.values(), key=lambda item: item["agent"])
    return {
        "day": day,
        "available_days": days[:30],
        "report_count": len(reports),
        "status_counts": dict(statuses),
        "totals": dict(totals),
        "agents": rows,
        "events": events[:24],
    }


def week_key_from_day(day: str) -> str:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return ""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def week_label(week_key: str) -> str:
    try:
        year, week = week_key.split("-W", 1)
        start = datetime.fromisocalendar(int(year), int(week), 1).date()
        end   = datetime.fromisocalendar(int(year), int(week), 7).date()
        return f"{start.strftime('%d/%m/%Y')} al {end.strftime('%d/%m/%Y')}"
    except Exception:
        return week_key


def weekly_report_summary(week: str = "") -> dict:
    reports = []
    for path in REPORTS_DIR.glob("*.json"):
        report_day = report_day_from_path(path)
        if not report_day:
            continue
        report_week = week_key_from_day(report_day)
        if not report_week:
            continue
        if week and report_week != week:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append((path, report_day, report_week, raw))

    weeks = sorted({w for _, _, w, _ in reports}, reverse=True)
    if not week:
        week = weeks[0] if weeks else week_key_from_day(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        reports = [(p, d, w, r) for p, d, w, r in reports if w == week]

    agent_rows = {}
    day_rows = {}
    totals = Counter()
    statuses = Counter()
    events = []

    for path, report_day, _, raw in reports:
        status = report_status(raw)
        statuses[status] += 1
        agent = agent_from_report_name(path.name, raw)
        row = agent_rows.setdefault(agent, {
            "agent": agent,
            "runs": 0, "ok": 0, "failed": 0, "warnings": 0,
            "created": 0, "skipped": 0, "blocked": 0,
            "published": 0, "sent": 0, "proposed": 0,
        })
        day = day_rows.setdefault(report_day, {
            "day": report_day,
            "runs": 0, "created": 0, "proposed": 0,
            "published": 0, "blocked": 0, "skipped": 0, "failed": 0,
        })

        row["runs"] += 1
        day["runs"] += 1
        if status in {"ok", "snapshot", "pending_configuration"}:
            row["ok"] += 1
        elif "warning" in str(status):
            row["warnings"] += 1
        else:
            row["failed"] += 1
            day["failed"] += 1

        created   = int_field(raw, "created_count")
        skipped   = int_field(raw, "skipped_count")
        blocked   = int_field(raw, "blocked_count", "pieces_blocked")
        published = int_field(raw, "published")
        proposed  = int_field(raw, "pieces_proposed")

        if raw.get("results") and isinstance(raw["results"], dict):
            sent   = int_field(raw["results"], "sent")
            failed = int_field(raw["results"], "failed")
            row["sent"]   += sent
            row["failed"] += failed
            totals["emails_sent"] += sent

        for dest in (row, day):
            dest["created"]   += created
            dest["skipped"]   += skipped
            dest["blocked"]   += blocked
            dest["published"] += published
            dest["proposed"]  += proposed

        totals["created"]   += created
        totals["skipped"]   += skipped
        totals["blocked"]   += blocked
        totals["published"] += published
        totals["proposed"]  += proposed

        note_bits = []
        if created:
            note_bits.append(f"{created} creados")
        if proposed:
            note_bits.append(f"{proposed} propuestas")
        if published:
            note_bits.append(f"{published} publicados")
        if blocked:
            note_bits.append(f"{blocked} bloqueados")

        events.append({
            "agent": agent,
            "command": raw.get("command") or path.stem,
            "status": status,
            "ts": norm_ts(raw.get("timestamp_utc") or path.name),
            "detail": " / ".join(note_bits) or path.name,
        })

    events.sort(key=lambda item: item.get("ts", ""), reverse=True)
    agents = sorted(agent_rows.values(), key=lambda item: item["agent"])
    days   = sorted(day_rows.values(),   key=lambda item: item["day"], reverse=True)
    return {
        "week": week,
        "label": week_label(week),
        "available_weeks": weeks[:26],
        "report_count": len(reports),
        "status_counts": dict(statuses),
        "totals": dict(totals),
        "agents": agents,
        "days": days,
        "events": events[:24],
    }


def lifetime_agent_summary() -> dict:
    all_days = sorted({
        report_day_from_path(p)
        for p in REPORTS_DIR.glob("*.json")
        if report_day_from_path(p)
    })
    day_summaries = [daily_report_summary(d) for d in all_days]

    totals = Counter()
    agents = {}
    publication_rows = []
    publication_statuses = Counter()
    action_counts = Counter()
    published_channel_counts = Counter()
    planned_channel_counts = Counter()
    generic_social_count = 0

    for summary in day_summaries:
        totals.update(summary.get("totals") or {})
        for agent in summary.get("agents") or []:
            row = agents.setdefault(agent["agent"], {
                "agent": agent["agent"],
                "runs": 0, "ok": 0, "failed": 0, "warnings": 0,
                "created": 0, "skipped": 0, "blocked": 0,
                "published": 0, "sent": 0, "proposed": 0,
            })
            for k in ("runs", "ok", "failed", "warnings", "created",
                      "skipped", "blocked", "published", "sent", "proposed"):
                row[k] += agent.get(k, 0)

    for rec in iter_jsonl(DISTRIBUTION_LOG):
        item = publication_item(rec)
        publication_rows.append(item)
        st = item["status"]
        publication_statuses[st] += 1
        action_counts[item["action"]] += 1
        for ch in item.get("published_channels") or []:
            published_channel_counts[ch] += 1
        ch_val = item.get("channel") or ""
        if ch_val:
            planned_channel_counts[ch_val] += 1
        if not item.get("published_channels") and not item.get("target_url"):
            generic_social_count += 1

    published_items = [i for i in publication_rows if i["status"] == "published"]
    published_items.sort(key=lambda i: sort_ts(i.get("ts", "")), reverse=True)

    return {
        "date_start": all_days[0] if all_days else "",
        "date_end":   all_days[-1] if all_days else "",
        "days_count": len(all_days),
        "report_count": sum(s.get("report_count", 0) for s in day_summaries),
        "totals": dict(totals),
        "agents": sorted(agents.values(), key=lambda item: item["agent"]),
        "publications": {
            "total": len(publication_rows),
            "statuses": dict(publication_statuses),
            "actions": dict(action_counts),
            "channels": dict(published_channel_counts),
            "planned_channels": dict(planned_channel_counts),
            "generic_social": generic_social_count,
            "published": len(published_items),
            "published_items": published_items[:500],
        },
    }


# ── Heartbeat (read-only, works on Vercel since file is in repo) ────────────────

def read_agent_heartbeat() -> dict:
    if not HEARTBEAT_PATH.exists():
        return {}
    try:
        heartbeat = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    updated = heartbeat.get("updated_at") or ""
    try:
        dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        heartbeat["age_seconds"] = max(0, round((datetime.now(timezone.utc) - dt).total_seconds()))
        heartbeat["fresh"] = heartbeat["age_seconds"] <= 90
    except Exception:
        heartbeat["age_seconds"] = None
        heartbeat["fresh"] = False
    return heartbeat


# ── Summary (Postgres or JSONL counts) ─────────────────────────────────────────

def build_summary(nurture_pg_mod=None) -> dict:
    leads  = {"total": 0, "active": 0, "unsubscribed": 0}
    emails = {"sent": 0, "pending": 0, "failed": 0}

    if nurture_pg_mod and nurture_pg_mod.enabled():
        pg = nurture_pg_mod.stats()
        leads  = pg["leads"]
        emails = pg["messages"]

    post_statuses = Counter(publication_status(r) for r in iter_jsonl(DISTRIBUTION_LOG))
    posts = {
        "published": post_statuses.get("published", 0),
        "approved":  post_statuses.get("approved",  0),
        "proposed":  post_statuses.get("proposed",  0),
        "failed":    post_statuses.get("failed",    0),
        "blocked":   post_statuses.get("blocked",   0),
    }

    eng_total = count_jsonl_lines(ENGAGEMENT_LOG)
    eng_dry   = count_jsonl_where(ENGAGEMENT_LOG, "status", "dry_run")

    return {
        "leads":  leads,
        "emails": emails,
        "posts":  posts,
        "engagement": {
            "total":   eng_total,
            "dry_run": eng_dry,
            "live":    eng_total - eng_dry,
        },
        "geo_audits": {
            "total":      count_jsonl_lines(GEO_AUDITS_LOG),
            "gaps_found": count_jsonl_lines(CONTENT_FEEDBACK),
        },
        "landings": {
            "total":        count_jsonl_lines(LANDINGS_FILE),
            "lead_magnets": count_jsonl_lines(LEAD_MAGNETS_FILE),
            "opportunities": count_jsonl_lines(OPOR_FILE),
        },
    }
