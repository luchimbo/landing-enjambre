"""Helpers compartidos para los handlers del dashboard."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))
sys.path.insert(0, str(ROOT))


def send(handler, status: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def qs(path: str) -> dict:
    from urllib.parse import parse_qs, urlparse
    return {k: v[-1] for k, v in parse_qs(urlparse(path).query).items()}


def base_handler(get_fn):
    """Decorator que envuelve una función en un BaseHTTPRequestHandler."""
    from http.server import BaseHTTPRequestHandler

    class handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.end_headers()

        def do_GET(self):
            try:
                result = get_fn(qs(self.path))
                send(self, 200, result)
            except Exception as exc:
                send(self, 500, {"error": str(exc)})

    return handler
