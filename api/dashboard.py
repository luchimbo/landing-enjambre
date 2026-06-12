"""
Vercel serverless handler for all /api/dashboard/* endpoints.
Routes by path internally; vercel.json rewrites /api/dashboard/:path* → /api/dashboard.
"""
import json
import os
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

from lib import nurture_pg
from lib import dashboard_data as dd


def _qs(path: str) -> dict:
    return {k: v[-1] for k, v in parse_qs(urlparse(path).query).items()}


def _route(path: str) -> str:
    clean = urlparse(path).path.rstrip("/")
    prefix = "/api/dashboard"
    if clean.startswith(prefix):
        return clean[len(prefix):].lstrip("/")
    return clean.lstrip("/")


def _send(handler, status: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        qs = _qs(self.path)
        # Vercel rewrites pass the sub-path as ?_path=...
        route = qs.pop("_path", None) or _route(self.path)
        try:
            self._dispatch(route, qs)
        except Exception as exc:
            _send(self, 500, {"error": str(exc)})

    def _dispatch(self, route: str, qs: dict) -> None:
        if route == "summary":
            _send(self, 200, dd.build_summary(nurture_pg))

        elif route == "agent-status":
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
            _send(self, 200, data)

        elif route == "agents":
            AGENT_PATTERNS = {
                "nurture":      ["*-nurture-*.json"],
                "conversion":   ["*-conversion-*.json"],
                "distribution": ["*-distribution-*.json"],
                "publicacion":  ["*-publicacion-*.json"],
                "geo_audit":    ["*-geo-audit-*.json"],
                "engagement":   ["*-engage.json", "*-engage-*.json", "*-engagement-*.json"],
            }
            daily = dd.latest_report(["*-daily.json"])
            daily_steps = {}
            if daily:
                for s in (daily.get("steps") or []):
                    daily_steps[s.get("step", "")] = s

            result = {}
            for agent, patterns in AGENT_PATTERNS.items():
                raw = dd.latest_report(patterns)
                if raw:
                    info = {
                        "last_run": raw.get("timestamp_utc", ""),
                        "status":   dd.report_status(raw),
                        "dry_run":  raw.get("dry_run", False),
                    }
                    if agent == "nurture":
                        r = raw.get("results", {})
                        info.update({"sent": r.get("sent", 0), "pending": r.get("pending", 0), "failed": r.get("failed", 0)})
                    elif agent == "conversion":
                        info.update({
                            "landings_analyzed": raw.get("landings", raw.get("landings_analyzed", 0)),
                            "recommendations":   dd.count_report_items(raw.get("recommendations")),
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
                    fallback_key = {
                        "nurture": "nurture", "conversion": "conversion",
                        "distribution": "distribution-generate", "publicacion": "publish",
                        "geo_audit": "geo-audit", "engagement": "engagement",
                    }.get(agent, agent)
                    ds = daily_steps.get(fallback_key, {})
                    info = {
                        "last_run": ds.get("started_utc", ""),
                        "status":   ds.get("status", "unknown"),
                        "dry_run":  daily.get("dry_run", False) if daily else False,
                    }
                result[agent] = info
            _send(self, 200, result)

        elif route == "last-workflow":
            report = dd.latest_report(["*-daily.json", "*-weekly.json"])
            if not report:
                _send(self, 200, {})
                return
            for step in (report.get("steps") or []):
                t0 = _parse_step_ts(step.get("started_utc"))
                t1 = _parse_step_ts(step.get("finished_utc"))
                step["duration_seconds"] = round((t1 - t0).total_seconds(), 1) if t0 and t1 else None
            _send(self, 200, report)

        elif route == "activity":
            limit = min(int(qs.get("limit", 30)), 100)
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
            _send(self, 200, items[:limit])

        elif route == "daily-agent-report":
            day = qs.get("day", "").strip()
            if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
                _send(self, 400, {"error": "Formato de fecha invalido. Usar YYYY-MM-DD."})
                return
            _send(self, 200, dd.daily_report_summary(day))

        elif route == "weekly-agent-report":
            week = qs.get("week", "").strip()
            if week and not re.match(r"^\d{4}-W\d{2}$", week):
                _send(self, 400, {"error": "Formato de semana invalido. Usar YYYY-WNN."})
                return
            _send(self, 200, dd.weekly_report_summary(week))

        elif route == "lifetime-agent-report":
            _send(self, 200, dd.lifetime_agent_summary())

        elif route == "new-work":
            limit = min(int(qs.get("limit", 8)), 20)
            items = list(dd.recent_report_items(limit=limit))
            for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 2):
                channel = rec.get("channel") or rec.get("community") or "distribucion"
                status  = rec.get("status") or "unknown"
                title   = rec.get("title") or rec.get("source_thread_title") or rec.get("landing_slug") or "Pieza de distribucion"
                items.append({
                    "source": "distribution",
                    "kind":   channel,
                    "title":  f"{channel}: {title}",
                    "detail": rec.get("notes") or rec.get("body", "")[:140],
                    "status": status,
                    "ts":     dd.norm_ts(rec.get("created_at_utc", "")),
                    "url":    rec.get("source_thread_url") or rec.get("landing_url") or rec.get("published_url") or "",
                })
            for rec in dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=limit):
                items.append({
                    "source": "feedback",
                    "kind":   rec.get("type") or rec.get("gap_type") or "feedback",
                    "title":  "Nueva oportunidad detectada",
                    "detail": rec.get("suggestion") or rec.get("prompt") or rec.get("landing_slug") or "",
                    "status": rec.get("priority") or "info",
                    "ts":     dd.norm_ts(rec.get("created_at_utc") or rec.get("timestamp_utc") or ""),
                    "url":    rec.get("source_url", ""),
                })
            for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit):
                platform = rec.get("platform") or "engagement"
                items.append({
                    "source": "engagement",
                    "kind":   platform,
                    "title":  f"{platform}: {rec.get('action') or 'accion'}",
                    "detail": rec.get("comment") or rec.get("target_user") or rec.get("target_url") or "",
                    "status": rec.get("status") or "unknown",
                    "ts":     dd.norm_ts(rec.get("ts", "")),
                    "url":    rec.get("target_url", ""),
                })
            items = [i for i in items if i.get("ts")]
            items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
            _send(self, 200, items[:limit])

        elif route == "publications":
            limit = min(int(qs.get("limit", 12)), 50)
            items = []
            for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 3):
                items.append(dd.publication_item(rec))
            for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit * 2):
                items.append({
                    "source":   "engagement",
                    "action":   rec.get("action") or "comentario",
                    "channel":  rec.get("platform") or "engagement",
                    "community": rec.get("target_user") or rec.get("hashtag") or rec.get("platform") or "",
                    "status":   rec.get("status") or "unknown",
                    "title":    rec.get("target_user") or rec.get("target_url") or "Comentario",
                    "body":     rec.get("comment", ""),
                    "target_url": rec.get("target_url", ""),
                    "landing_url": "",
                    "ts":       dd.norm_ts(rec.get("ts", "")),
                })
            items = [i for i in items if i.get("ts")]
            items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
            _send(self, 200, items[:limit])

        elif route == "published":
            limit = min(int(qs.get("limit", 200)), 500)
            items = [
                dd.publication_item(rec)
                for rec in dd.iter_jsonl(dd.DISTRIBUTION_LOG)
                if dd.publication_status(rec) == "published"
            ]
            items = [i for i in items if i.get("ts")]
            items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
            _send(self, 200, items[:limit])

        elif route == "geo-summary":
            from collections import Counter as _Counter
            entries = dd.tail_jsonl(dd.GEO_AUDITS_LOG, n=100)
            scores = [e.get("score", 0) for e in entries if "score" in e]
            all_competitors = []
            for e in entries:
                all_competitors.extend(e.get("competitors") or [])
            recent_gaps = list(dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=5))
            recent_gaps.reverse()
            _send(self, 200, {
                "total_audited":          dd.count_jsonl_lines(dd.GEO_AUDITS_LOG),
                "pcmidi_mentioned_count": sum(1 for e in entries if e.get("pcmidi_mentioned")),
                "avg_score":              round(sum(scores) / len(scores), 2) if scores else 0.0,
                "top_competitors":        [c for c, _ in _Counter(all_competitors).most_common(8)],
                "recent_gaps":            recent_gaps,
            })

        else:
            _send(self, 404, {"error": f"Ruta no encontrada: {route}"})


def _parse_step_ts(ts):
    if not ts:
        return None
    try:
        return __import__("datetime").datetime.strptime(ts[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None
