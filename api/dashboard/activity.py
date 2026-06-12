from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
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
    return items[:limit]

handler = base_handler(_get)
