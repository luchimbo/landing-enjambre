import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    limit = min(int(qs.get("limit", 200)), 500)
    items = [
        dd.publication_item(rec)
        for rec in dd.iter_jsonl(dd.DISTRIBUTION_LOG)
        if dd.publication_status(rec) == "published"
    ]
    items = [i for i in items if i.get("ts")]
    items.sort(key=lambda i: dd.sort_ts(i.get("ts", "")), reverse=True)
    return items[:limit]

handler = base_handler(_get)
