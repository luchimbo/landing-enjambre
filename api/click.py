import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import nurture_pg


def _secret() -> str:
    return os.getenv("NURTURE_UNSUBSCRIBE_SECRET") or os.getenv("NURTURE_SMTP_PASS", "")


def _valid_token(lead_id: str, slug: str, day: str, url: str, token: str) -> bool:
    secret = _secret()
    if not secret or not token:
        return False
    payload = f"{lead_id}|{slug}|{day}|{url}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, token)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = {key: values[-1] for key, values in parse_qs(urlparse(self.path).query).items()}
        url = query.get("url", "")
        lead_id = query.get("lead_id", "")
        slug = query.get("slug", "")
        day = query.get("day", "")
        token = query.get("token", "")
        if not url.startswith("https://www.pcmidi.com.ar/"):
            self._send_json(400, {"error": "URL no permitida"})
            return
        if not _valid_token(lead_id, slug, day, url, token):
            self._send_json(403, {"error": "Token invalido"})
            return
        try:
            if nurture_pg.enabled():
                nurture_pg.record_email_click(int(lead_id), slug, {"day": day, "url": url})
        except Exception:
            pass
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
