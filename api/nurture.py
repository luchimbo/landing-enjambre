import json
import os
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()

    def _run(self):
        try:
            secret = os.getenv("NURTURE_CRON_SECRET", "")
            query = {key: values[-1] for key, values in parse_qs(urlparse(self.path).query).items()}
            is_vercel_cron = bool(self.headers.get("x-vercel-cron"))
            if secret and query.get("secret") != secret and not is_vercel_cron:
                _send(self, 403, {"error": "No autorizado"})
                return
            nurture_pg.init_db()
            pending = nurture_pg.process_pending(limit=50, dry_run=False)
            retry = nurture_pg.retry_failed(limit=20, dry_run=False)
            _send(self, 200, {"success": True, "pending": pending, "retry": retry})
        except Exception as exc:
            _send(self, 500, {"error": str(exc)})
