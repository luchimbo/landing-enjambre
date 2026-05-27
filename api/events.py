import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import nurture_pg


def _read_payload(handler) -> dict:
    length = int(handler.headers.get("content-length") or 0)
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    content_type = handler.headers.get("content-type", "")
    if "application/json" in content_type or raw.strip().startswith("{"):
        return json.loads(raw or "{}")
    return {key: values[-1] for key, values in parse_qs(raw).items()}


def _send(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            nurture_pg.init_db()
            data = _read_payload(self)
            event_type = str(data.get("event_type", "")).strip()
            slug = str(data.get("slug", "")).strip() or None
            extra = {k: v for k, v in data.items() if k not in {"event_type", "slug"}}
            ok, message = nurture_pg.record_page_event(event_type, slug, extra)
            if not ok:
                _send(self, 400, {"error": message})
                return
            _send(self, 200, {"success": True})
        except Exception as exc:
            _send(self, 500, {"error": str(exc)})

    def do_OPTIONS(self):
        _send(self, 204, {})
