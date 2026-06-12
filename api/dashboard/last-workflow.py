import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from datetime import datetime
from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _parse_step_ts(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None

def _get(qs):
    report = dd.latest_report(["*-daily.json", "*-weekly.json"])
    if not report:
        return {}
    for step in (report.get("steps") or []):
        t0 = _parse_step_ts(step.get("started_utc"))
        t1 = _parse_step_ts(step.get("finished_utc"))
        step["duration_seconds"] = round((t1 - t0).total_seconds(), 1) if t0 and t1 else None
    return report

handler = base_handler(_get)
