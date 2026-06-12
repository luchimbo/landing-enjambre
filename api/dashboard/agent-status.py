import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from datetime import datetime, timezone
from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    heartbeat = dd.read_agent_heartbeat()
    data = {
        "state": "sleeping",
        "active_count": 0,
        "active_agents": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if heartbeat:
        data["heartbeat"] = heartbeat
        if heartbeat.get("fresh") and heartbeat.get("state") == "working":
            data["state"] = "active"
        elif heartbeat.get("fresh"):
            data["state"] = "guard"
    return data

handler = base_handler(_get)
