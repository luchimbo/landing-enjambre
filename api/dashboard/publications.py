from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    limit = min(int(qs.get("limit", 12)), 50)
    items = []
    for rec in dd.tail_jsonl(dd.DISTRIBUTION_LOG, n=limit * 3):
        items.append(dd.publication_item(rec))
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

handler = base_handler(_get)
