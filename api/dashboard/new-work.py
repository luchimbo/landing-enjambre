from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    limit = min(int(qs.get("limit", 8)), 20)
    items = list(dd.recent_report_items(limit=limit))
    for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 2):
        channel = rec.get("channel") or rec.get("community") or "distribucion"
        items.append({
            "source": "distribution", "kind": channel,
            "title": f"{channel}: {rec.get('title') or rec.get('source_thread_title') or rec.get('landing_slug') or 'Pieza'}",
            "detail": rec.get("notes") or rec.get("body", "")[:140],
            "status": rec.get("status") or "unknown",
            "ts": dd.norm_ts(rec.get("created_at_utc", "")),
            "url": rec.get("source_thread_url") or rec.get("landing_url") or rec.get("published_url") or "",
        })
    for rec in dd.tail_jsonl(dd.CONTENT_FEEDBACK, n=limit):
        items.append({
            "source": "feedback", "kind": rec.get("type") or rec.get("gap_type") or "feedback",
            "title": "Nueva oportunidad detectada",
            "detail": rec.get("suggestion") or rec.get("prompt") or rec.get("landing_slug") or "",
            "status": rec.get("priority") or "info",
            "ts": dd.norm_ts(rec.get("created_at_utc") or rec.get("timestamp_utc") or ""),
            "url": rec.get("source_url", ""),
        })
    for rec in dd.tail_jsonl(dd.ENGAGEMENT_LOG, n=limit):
        platform = rec.get("platform") or "engagement"
        items.append({
            "source": "engagement", "kind": platform,
            "title": f"{platform}: {rec.get('action') or 'accion'}",
            "detail": rec.get("comment") or rec.get("target_user") or rec.get("target_url") or "",
            "status": rec.get("status") or "unknown",
            "ts": dd.norm_ts(rec.get("ts", "")),
            "url": rec.get("target_url", ""),
        })
    items = [i for i in items if i.get("ts")]
    items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
    return items[:limit]

handler = base_handler(_get)
