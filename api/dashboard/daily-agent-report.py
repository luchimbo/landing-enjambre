import re
from api.dashboard._base import base_handler, send
from lib import dashboard_data as dd
from http.server import BaseHTTPRequestHandler

def _get(qs):
    day = qs.get("day", "").strip()
    if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise ValueError("Formato de fecha invalido. Usar YYYY-MM-DD.")
    return dd.daily_report_summary(day)

handler = base_handler(_get)
