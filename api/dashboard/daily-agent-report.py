import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import re
from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    day = qs.get("day", "").strip()
    if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise ValueError("Formato de fecha invalido. Usar YYYY-MM-DD.")
    return dd.daily_report_summary(day)

handler = base_handler(_get)
