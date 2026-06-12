import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import re
from api.dashboard._base import base_handler
from lib import dashboard_data as dd

def _get(qs):
    week = qs.get("week", "").strip()
    if week and not re.match(r"^\d{4}-W\d{2}$", week):
        raise ValueError("Formato de semana invalido. Usar YYYY-WNN.")
    return dd.weekly_report_summary(week)

handler = base_handler(_get)
