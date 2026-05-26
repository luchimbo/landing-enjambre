import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import nurture_pg


def _send(handler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _payload(handler) -> dict:
    if handler.command == "GET":
        return {key: values[-1] for key, values in parse_qs(urlparse(handler.path).query).items()}
    length = int(handler.headers.get("content-length") or 0)
    raw = handler.rfile.read(length).decode("utf-8") if length else ""
    if "application/json" in handler.headers.get("content-type", ""):
        return json.loads(raw or "{}")
    return {key: values[-1] for key, values in parse_qs(raw).items()}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._unsubscribe()

    def do_POST(self):
        self._unsubscribe()

    def _unsubscribe(self):
        try:
            data = _payload(self)
            ok, message = nurture_pg.unsubscribe(data.get("email", ""), data.get("token", ""))
            if not ok:
                _send(self, 403 if message == "Token invalido" else 400, {"error": message})
                return
            _send(self, 200, {"success": True, "message": message})
        except Exception as exc:
            _send(self, 500, {"error": str(exc)})
