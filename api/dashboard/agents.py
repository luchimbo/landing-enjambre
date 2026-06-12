from api.dashboard._base import base_handler
from lib import dashboard_data as dd

AGENT_PATTERNS = {
    "nurture":      ["*-nurture-*.json"],
    "conversion":   ["*-conversion-*.json"],
    "distribution": ["*-distribution-*.json"],
    "publicacion":  ["*-publicacion-*.json"],
    "geo_audit":    ["*-geo-audit-*.json"],
    "engagement":   ["*-engage.json", "*-engage-*.json", "*-engagement-*.json"],
}

def _get(qs):
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
    return result

handler = base_handler(_get)
