from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    audits = list(dd.tail_jsonl(dd.GEO_AUDITS_LOG, n=200))
    scores = [float(a["score"]) for a in audits if a.get("score") is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else None

    competitors: dict[str, int] = {}
    for a in audits:
        for c in (a.get("competitors") or []):
            name = c if isinstance(c, str) else c.get("name") or str(c)
            competitors[name] = competitors.get(name, 0) + 1
    top_competitors = sorted(competitors.items(), key=lambda x: -x[1])[:10]

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
        "avg_score": avg_score,
        "audit_count": len(audits),
        "top_competitors": [{"name": n, "mentions": c} for n, c in top_competitors],
        "recent_gaps": gaps[:10],
    }

handler = base_handler(_get)
