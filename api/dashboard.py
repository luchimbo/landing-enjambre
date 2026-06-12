"""Single Vercel handler for /api/dashboard/*.

Vercel reliably detects top-level Python functions. The rewrite in vercel.json
passes the dashboard sub-route as the _path query parameter.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))
sys.path.insert(0, str(ROOT))

from lib import dashboard_data as dd
from lib import nurture_pg


def _send(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _query(path):
    return {k: v[-1] for k, v in parse_qs(urlparse(path).query).items()}


def _limit(qs, name, default, max_value):
    try:
        return min(int(qs.get(name, default)), max_value)
    except (TypeError, ValueError):
        return default


def _agent_status(_qs):
    heartbeat = dd.read_agent_heartbeat()
    data = {
        "state": "sleeping",
        "active_count": 0,
        "active_agents": [],
        "checked_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }
    if heartbeat:
        data["heartbeat"] = heartbeat
        if heartbeat.get("fresh") and heartbeat.get("state") == "working":
            data["state"] = "active"
        elif heartbeat.get("fresh"):
            data["state"] = "guard"
    return data


def _agents(_qs):
    patterns = {
        "nurture": ["*-nurture-*.json"],
        "conversion": ["*-conversion-*.json"],
        "distribution": ["*-distribution-*.json"],
        "publicacion": ["*-publicacion-*.json"],
        "geo_audit": ["*-geo-audit*.json"],
        "engagement": ["*-engage.json", "*-engage-*.json", "*-engagement-*.json"],
    }
    daily = dd.latest_report(["*-daily.json"])
    daily_steps = {s.get("step", ""): s for s in (daily or {}).get("steps", [])}
    result = {}
    for agent, pats in patterns.items():
        raw = dd.latest_report(pats)
        if raw:
            info = {
                "last_run": raw.get("timestamp_utc", ""),
                "status": dd.report_status(raw),
                "dry_run": raw.get("dry_run", False),
            }
            if agent == "nurture":
                r = raw.get("results", {})
                info.update({"sent": r.get("sent", 0), "pending": r.get("pending", 0), "failed": r.get("failed", 0)})
            elif agent == "conversion":
                info.update({
                    "landings_analyzed": raw.get("landings", raw.get("landings_analyzed", 0)),
                    "recommendations": dd.count_report_items(raw.get("recommendations")),
                })
            elif agent == "distribution":
                info.update({"pieces_proposed": raw.get("pieces_proposed", 0), "pieces_blocked": raw.get("pieces_blocked", 0)})
            elif agent == "publicacion":
                info.update({"published": raw.get("published", 0), "found": raw.get("found", 0)})
            elif agent == "geo_audit":
                info.update({"audited": dd.count_jsonl_lines(dd.GEO_AUDITS_LOG), "gaps_found": dd.count_jsonl_lines(dd.CONTENT_FEEDBACK)})
            elif agent == "engagement":
                info.update({"platform": raw.get("platform", ""), "actions": dd.count_jsonl_lines(dd.ENGAGEMENT_LOG)})
        else:
            fallback = {
                "nurture": "nurture",
                "conversion": "conversion",
                "distribution": "distribution-generate",
                "publicacion": "publish",
                "geo_audit": "geo-audit",
                "engagement": "engagement",
            }.get(agent, agent)
            step = daily_steps.get(fallback, {})
            info = {
                "last_run": step.get("started_utc", ""),
                "status": step.get("status", "unknown"),
                "dry_run": daily.get("dry_run", False) if daily else False,
            }
        result[agent] = info
    return result


def _last_workflow(_qs):
    report = dd.latest_report(["*-daily.json", "*-weekly.json"])
    if not report:
        return {}
    for step in report.get("steps", []):
        t0 = _parse_step_ts(step.get("started_utc"))
        t1 = _parse_step_ts(step.get("finished_utc"))
        step["duration_seconds"] = round((t1 - t0).total_seconds(), 1) if t0 and t1 else None
    return report


def _activity(qs):
    limit = _limit(qs, "limit", 30, 100)
    items = []
    for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit):
        items.append({"_source": "engagement", "_ts": dd.norm_ts(rec.get("ts", "")), **rec})
    for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit):
        items.append({"_source": "distribution", "_ts": dd.norm_ts(rec.get("created_at_utc", "")), **rec})
    for rec in dd.tail_jsonl(dd.GEO_AUDITS_LOG, n=limit):
        light = {k: v for k, v in rec.items() if k != "response_text"}
        items.append({"_source": "geo_audit", "_ts": dd.norm_ts(rec.get("timestamp_utc", "")), **light})
    for rec in dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=limit):
        items.append({"_source": "feedback", "_ts": dd.norm_ts(rec.get("timestamp_utc", "")), **rec})
    items.sort(key=lambda x: x.get("_ts", ""), reverse=True)
    return items[:limit]


def _daily_report(qs):
    day = qs.get("day", "").strip()
    if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return {"error": "Formato de fecha invalido. Usar YYYY-MM-DD."}
    return dd.daily_report_summary(day)


def _weekly_report(qs):
    week = qs.get("week", "").strip()
    if week and not re.match(r"^\d{4}-W\d{2}$", week):
        return {"error": "Formato de semana invalido. Usar YYYY-WNN."}
    return dd.weekly_report_summary(week)


def _new_work(qs):
    limit = _limit(qs, "limit", 8, 20)
    items = list(dd.recent_report_items(limit=limit))
    for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 2):
        channel = rec.get("channel") or rec.get("community") or "distribucion"
        items.append({
            "source": "distribution",
            "kind": channel,
            "title": f"{channel}: {rec.get('title') or rec.get('source_thread_title') or rec.get('landing_slug') or 'Pieza'}",
            "detail": rec.get("notes") or rec.get("body", "")[:140],
            "status": rec.get("status") or "unknown",
            "ts": dd.norm_ts(rec.get("created_at_utc", "")),
            "url": rec.get("source_thread_url") or rec.get("landing_url") or rec.get("published_url") or "",
        })
    for rec in dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=limit):
        items.append({
            "source": "feedback",
            "kind": rec.get("type") or rec.get("gap_type") or "feedback",
            "title": "Nueva oportunidad detectada",
            "detail": rec.get("suggestion") or rec.get("prompt") or rec.get("landing_slug") or "",
            "status": rec.get("priority") or "info",
            "ts": dd.norm_ts(rec.get("created_at_utc") or rec.get("timestamp_utc") or ""),
            "url": rec.get("source_url", ""),
        })
    for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit):
        platform = rec.get("platform") or "engagement"
        items.append({
            "source": "engagement",
            "kind": platform,
            "title": f"{platform}: {rec.get('action') or 'accion'}",
            "detail": rec.get("comment") or rec.get("target_user") or rec.get("target_url") or "",
            "status": rec.get("status") or "unknown",
            "ts": dd.norm_ts(rec.get("ts", "")),
            "url": rec.get("target_url", ""),
        })
    items = [i for i in items if i.get("ts")]
    items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
    return items[:limit]


def _publications(qs):
    limit = _limit(qs, "limit", 12, 50)
    items = [dd.publication_item(rec) for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 3)]
    for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit * 2):
        items.append({
            "source": "engagement",
            "action": rec.get("action") or "comentario",
            "channel": rec.get("platform") or "engagement",
            "community": rec.get("target_user") or rec.get("hashtag") or rec.get("platform") or "",
            "status": rec.get("status") or "unknown",
            "title": rec.get("target_user") or rec.get("target_url") or "Comentario",
            "body": rec.get("comment", ""),
            "target_url": rec.get("target_url", ""),
            "landing_url": "",
            "ts": dd.norm_ts(rec.get("ts", "")),
        })
    items = [i for i in items if i.get("ts")]
    items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
    return items[:limit]


def _published(qs):
    limit = _limit(qs, "limit", 200, 500)
    items = [
        dd.publication_item(rec)
        for rec in dd.iter_jsonl(dd.DISTRIBUTION_LOG)
        if dd.publication_status(rec) == "published"
    ]
    items = [i for i in items if i.get("ts")]
    items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
    return items[:limit]


def _geo_summary(_qs):
    audits = list(dd.tail_jsonl(dd.GEO_AUDITS_LOG, n=200))
    scores = [float(a["score"]) for a in audits if a.get("score") is not None]
    competitors = {}
    for audit in audits:
        for competitor in audit.get("competitors") or []:
            name = competitor if isinstance(competitor, str) else competitor.get("name") or str(competitor)
            competitors[name] = competitors.get(name, 0) + 1
    gaps = [
        {
            "ts": dd.norm_ts(r.get("created_at_utc") or r.get("timestamp_utc") or ""),
            "gap_type": r.get("gap_type") or r.get("type") or "gap",
            "suggestion": r.get("suggestion") or r.get("prompt") or "",
            "priority": r.get("priority") or "medium",
        }
        for r in dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=20)
    ]
    gaps.sort(key=lambda g: dd.sort_ts(g.get("ts", "")), reverse=True)
    return {
        "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
        "audit_count": len(audits),
        "top_competitors": [
            {"name": name, "mentions": count}
            for name, count in sorted(competitors.items(), key=lambda item: -item[1])[:10]
        ],
        "recent_gaps": gaps[:10],
    }


ROUTES = {
    "summary": lambda qs: dd.build_summary(nurture_pg),
    "agent-status": _agent_status,
    "agents": _agents,
    "last-workflow": _last_workflow,
    "activity": _activity,
    "daily-agent-report": _daily_report,
    "weekly-agent-report": _weekly_report,
    "lifetime-agent-report": lambda qs: dd.lifetime_agent_summary(),
    "new-work": _new_work,
    "publications": _publications,
    "published": _published,
    "geo-summary": _geo_summary,
}


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        qs = _query(self.path)
        route = (qs.pop("_path", "") or "").strip("/")
        try:
            get_data = ROUTES.get(route)
            if not get_data:
                _send(self, 404, {"error": f"Ruta no encontrada: {route}"})
                return
            payload = get_data(qs)
            status = 400 if isinstance(payload, dict) and payload.get("error") else 200
            _send(self, status, payload)
        except Exception as exc:
            _send(self, 500, {"error": str(exc)})


def _parse_step_ts(ts):
    if not ts:
        return None
    try:
        return __import__("datetime").datetime.strptime(ts[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None
