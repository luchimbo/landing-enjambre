import argparse
import base64
import csv
import hashlib
import html
import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"
SOCIAL_INTEL_PATH = DATA_DIR / "social_intel.jsonl"
CONTENT_FEEDBACK_PATH = DATA_DIR / "content_feedback.jsonl"
SEARCH_TASKS_PATH = DATA_DIR / "distribution_search_tasks.jsonl"
DISTRIBUTION_LOG_PATH = DATA_DIR / "distribution_log.jsonl"
ACTION_MEMORY_PATH = DATA_DIR / "browser_action_memory.json"
CATALOGO_TN_PATH = DATA_DIR / "catalogoTN.csv"
LEGAL_STATUSES = {"approved", "bulk_approved", "ready_to_publish", "ready_for_publish"}
AUTO_PUBLISH_STATUSES = LEGAL_STATUSES | {"proposed"}
BLOCKED_STATUSES = {"blocked", "failed", "published"}
SUPPORTED_AUTO_CHANNELS = {"linkedin", "reddit", "facebook", "x", "youtube", "instagram"}
CHANNEL_DAILY_LIMITS = {
    "facebook": 2,
    "instagram": 2,
    "youtube": 5,
    "x": 3,
    "linkedin": 3,
    "reddit": 2,
}
CHANNEL_ALIASES = {
    "all": SUPPORTED_AUTO_CHANNELS,
    "twitter": {"x"},
    "social": {"facebook", "x", "instagram"},
}
SEARCH_URLS = {
    "reddit": "https://www.reddit.com/search/?q={query}&type=link&sort=new",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "linkedin": "https://www.linkedin.com/search/results/content/?keywords={query}",
    "facebook": "https://www.facebook.com/search/posts?q={query}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={query}",
    "x": "https://x.com/search?q={query}&src=typed_query&f=live",
}
INSTAGRAM_MUSIC_TAGS = [
    "produccionmusical",
    "musicproduction",
    "homestudio",
    "ableton",
    "flstudio",
    "midicontroller",
    "audiointerface",
]
MUSIC_CONTEXT_TERMS = {
    "ableton",
    "audio",
    "beat",
    "beats",
    "controlador",
    "daw",
    "fl studio",
    "home studio",
    "homestudio",
    "interface",
    "interfaz",
    "midi",
    "mix",
    "mezcla",
    "microfono",
    "micrófono",
    "monitor",
    "musica",
    "música",
    "plugin",
    "podcast",
    "produccion",
    "producción",
    "producer",
    "recording",
    "sinte",
    "sintetizador",
    "studio",
    "synth",
    "vocal",
    "voz",
}
STRICT_MUSIC_CONTEXT_TERMS = MUSIC_CONTEXT_TERMS | {
    "ableton live",
    "akai",
    "arturia",
    "audio interface",
    "auricular",
    "auriculares",
    "bass",
    "controladores",
    "drum machine",
    "guitarra",
    "home recording",
    "keyboard",
    "keylab",
    "keystep",
    "launchpad",
    "minifuse",
    "minilab",
    "monitores",
    "mpc",
    "music",
    "novation",
    "piano",
    "placa de sonido",
    "producing",
    "sintesis",
    "teclado",
    "teclas",
}
FORBIDDEN_CLAIMS = [
    "stock garantizado",
    "disponibilidad garantizada",
    "distribuidor oficial",
    "soporte tecnico oficial",
    "soporte técnico oficial",
    "hay stock",
    "en stock",
    "cuotas",
]
SESSION_DIR = ROOT / "session" / "chrome-personal"
CDP_URL = "http://127.0.0.1:9222"


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = REPORTS_DIR / f"{stamp}-browser-{name}.json"
    path.write_text(json.dumps({"timestamp_utc": stamp, **data}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def chrome_path() -> str:
    candidates = [
        os.environ.get("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return "chrome"


def start_browser() -> dict:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        chrome_path(),
        "--remote-debugging-port=9222",
        f"--user-data-dir={SESSION_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    subprocess.Popen(command, cwd=ROOT)
    return {"command": command, "cdp_url": CDP_URL, "session_dir": str(SESSION_DIR)}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido en {path}:{line_no}: {exc}") from exc
    return rows


def rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def load_catalogo_tn() -> list[dict]:
    if not CATALOGO_TN_PATH.exists():
        return []
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = CATALOGO_TN_PATH.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    reader = csv.DictReader(text.splitlines(), delimiter=";")
    rows = []
    for row in reader:
        if (row.get("Mostrar en tienda") or "").strip().upper() not in {"SI", "SÍ", "YES", "TRUE", "1"}:
            continue
        name = strip_html(row.get("Nombre", ""))
        if not name or "preventa" in name.lower():
            continue
        rows.append({
            "nombre": name,
            "categoria": strip_html(row.get("Categorías", "")),
            "marca": strip_html(row.get("Marca", "")),
            "sku": strip_html(row.get("SKU", "")),
            "descripcion": strip_html(row.get("Descripción", "")),
            "tags": strip_html(row.get("Tags", "")),
        })
    return rows


def concise_product_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\b(profesional|preventa)\b", "", name, flags=re.I)
    name = re.sub(r"\b(controlador midi|teclado controlador midi|placa de sonido|interfaz de audio)\b", "", name, flags=re.I)
    name = re.sub(r"\b(usb|black|white|negro|blanco|champagne|rose quartz|aquamarine)\b", "", name, flags=re.I)
    if name.isupper():
        name = name.title().replace("Midi", "MIDI").replace("Usb", "USB")
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name[:58].strip()


def pick_catalog_product(context: str, intent: str, seed: str) -> str:
    catalog = load_catalogo_tn()
    if not catalog:
        return ""
    if intent == "midi":
        terms = ["controlador midi", "minilab", "keylab", "keystep", "microlab", "tempokey", "midiplus"]
    elif intent == "audio":
        terms = ["interfaz", "interface", "placa de sonido", "minifuse", "studio 2", "studio m", "livemix"]
    elif intent == "beat":
        terms = ["pad", "octapad", "tempopad", "controlador midi", "minilab", "mp200"]
    else:
        terms = ["controlador midi", "interfaz", "minifuse", "minilab", "keylab", "studio"]
    scored = []
    lower_context = context.lower()
    for row in catalog:
        haystack = " ".join([row["nombre"], row["categoria"], row["descripcion"], row["tags"]]).lower()
        score = sum(4 for term in terms if term in haystack)
        score += sum(1 for term in MUSIC_CONTEXT_TERMS if term in lower_context and term in haystack)
        if score:
            scored.append((score, row["nombre"]))
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], item[1]))
    pool = [name for _, name in scored[:12]]
    if intent == "midi":
        preferred = ["minilab 3", "microlab", "tempokey 25", "keylab essential 49", "keylab essential 61", "keystep 37"]
        filtered = [name for name in pool if any(term in name.lower() for term in preferred)]
        if filtered:
            pool = filtered
    elif intent == "audio":
        preferred = ["minifuse 1", "minifuse 2", "studio 2 pro", "studio m", "livemix solo", "livemix duet"]
        filtered = [name for name in pool if any(term in name.lower() for term in preferred)]
        if filtered:
            pool = filtered
    number = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
    return concise_product_name(pool[number % len(pool)])


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remember_action(channel: str, action: str, detail: dict) -> None:
    memory = load_json(ACTION_MEMORY_PATH, {})
    memory.setdefault(channel, {}).setdefault(action, [])
    entry = {"saved_at_utc": datetime.now(timezone.utc).isoformat(), **detail}
    existing = memory[channel][action]
    signature = json.dumps(detail, ensure_ascii=False, sort_keys=True)
    if all(json.dumps({k: v for k, v in item.items() if k != "saved_at_utc"}, ensure_ascii=False, sort_keys=True) != signature for item in existing):
        existing.insert(0, entry)
        del existing[10:]
    write_json(ACTION_MEMORY_PATH, memory)


class CDPClient:
    def __init__(self, ws_url: str, timeout: float = 20.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.next_id = 1

    def __enter__(self) -> "CDPClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.sock:
            self.sock.close()

    def connect(self) -> None:
        parsed = urlparse(self.ws_url)
        if parsed.scheme != "ws":
            raise ValueError(f"URL WebSocket no soportada: {self.ws_url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock = socket.create_connection((host, port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"No se pudo conectar al WebSocket CDP: {response[:200]!r}")

    def send(self, method: str, params: dict | None = None) -> dict:
        message_id = self.next_id
        self.next_id += 1
        payload = {"id": message_id, "method": method, "params": params or {}}
        self._send_text(json.dumps(payload, separators=(",", ":")))
        while True:
            message = json.loads(self._recv_text())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} fallo: {message['error']}")
                return message.get("result", {})

    def _send_text(self, text: str) -> None:
        if not self.sock:
            raise RuntimeError("CDP no conectado")
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 255, length & 255])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_exact(self, size: int) -> bytes:
        if not self.sock:
            raise RuntimeError("CDP no conectado")
        chunks = []
        remaining = size
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("WebSocket cerrado")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_text(self) -> str:
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = int.from_bytes(self._recv_exact(2), "big")
            elif length == 127:
                length = int.from_bytes(self._recv_exact(8), "big")
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 1:
                return payload.decode("utf-8")
            if opcode == 8:
                raise RuntimeError("WebSocket cerrado por Chrome")


def json_get(url: str) -> dict | list[dict]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def ensure_browser() -> None:
    try:
        json_get(f"{CDP_URL}/json/version")
    except Exception:
        start_browser()
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                json_get(f"{CDP_URL}/json/version")
                return
            except Exception:
                time.sleep(0.4)
        raise RuntimeError("Chrome no expuso CDP en 127.0.0.1:9222")


def get_page_ws_url() -> str:
    ensure_browser()
    tabs = json_get(f"{CDP_URL}/json")
    assert isinstance(tabs, list)
    for tab in tabs:
        if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
            return tab["webSocketDebuggerUrl"]
    tab = json_get(f"{CDP_URL}/json/new")
    assert isinstance(tab, dict)
    return tab["webSocketDebuggerUrl"]


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def evaluate(client: CDPClient, expression: str, await_promise: bool = False) -> dict:
    return client.send(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
        },
    )


def value_from_result(result: dict):
    remote = result.get("result", {})
    if "exceptionDetails" in result:
        details = result["exceptionDetails"]
        raise RuntimeError(details.get("text") or "Error JS")
    return remote.get("value")


def action_click(client: CDPClient, selector: str) -> dict:
    expr = f"""
    (() => {{
      const el = document.querySelector({js_string(selector)});
      if (!el) return {{ok:false, error:'selector no encontrado'}};
      el.scrollIntoView({{block:'center', inline:'center'}});
      el.click();
      return {{ok:true, selector:{js_string(selector)}}};
    }})()
    """
    return value_from_result(evaluate(client, expr))


def action_type(client: CDPClient, selector: str, text: str, clear: bool = True) -> dict:
    expr = f"""
    (() => {{
      const el = document.querySelector({js_string(selector)});
      if (!el) return {{ok:false, error:'selector no encontrado'}};
      el.focus();
      if ({str(clear).lower()}) el.value = '';
      el.value += {js_string(text)};
      el.dispatchEvent(new Event('input', {{bubbles:true}}));
      el.dispatchEvent(new Event('change', {{bubbles:true}}));
      return {{ok:true, selector:{js_string(selector)}, length: el.value.length}};
    }})()
    """
    return value_from_result(evaluate(client, expr))


def action_fill_active_editor(client: CDPClient, text: str) -> dict:
    expr = f"""
    (() => {{
      const selectors = [
        '[aria-label*="Qu\\u00e9 est\\u00e1s pensando"]',
        '[aria-label*="What\\u2019s on your mind"]',
        '[aria-label*="What is on your mind"]',
        '[aria-label*="Escribe algo"]',
        '[aria-label*="Write something"]',
        '[aria-label*="A\\u00f1ade un comentario"]',
        '[aria-label*="Add a comment"]',
        '.ql-editor[contenteditable="true"]',
        '[data-testid="tweetTextarea_0"]',
        '#contenteditable-root',
        '[aria-label][contenteditable="true"]',
        '[contenteditable="true"][role="textbox"]',
        '[contenteditable="true"]',
        'textarea',
        'div[role="textbox"]'
      ];
      for (const selector of selectors) {{
        const items = Array.from(document.querySelectorAll(selector)).filter((el) => {{
          const style = getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 20 && rect.height > 10;
        }});
        const el = items[items.length - 1];
        if (!el) continue;
        el.scrollIntoView({{block:'center', inline:'center'}});
        el.focus();
        if ('value' in el) {{
          el.value = '';
        }} else {{
          el.textContent = '';
        }}
        el.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'deleteContentBackward', data:null}}));
        el.dispatchEvent(new Event('change', {{bubbles:true}}));
        return {{ok:true, selector}};
      }}
      return {{ok:false, error:'editor visible no encontrado'}};
    }})()
    """
    focused = value_from_result(evaluate(client, expr))
    if not focused.get("ok"):
        return focused
    client.send("Input.insertText", {"text": text})
    return {**focused, "length": len(text)}


def action_click_prompt_and_fill(client: CDPClient, prompt_texts: list[str], text: str) -> dict:
    click = action_click_by_text(client, prompt_texts)
    time.sleep(1.5)
    fill = action_fill_active_editor(client, text)
    return {"ok": bool(fill.get("ok")), "click": click, "fill": fill}


def try_comment_or_post(client: CDPClient, channel: str, text: str) -> dict:
    default_strategies = {
        "youtube": [
            {"name": "youtube_placeholder", "open_selector": ["#placeholder-area", "ytd-comment-simplebox-renderer #placeholder-area"], "submit_selector": ["#submit-button button"]},
            {"name": "youtube_text", "open_text": ["add a comment", "añade un comentario"], "submit_text": ["comment", "comentar"]},
        ],
        "facebook": [
            {"name": "facebook_comment", "open_text": ["dejar un comentario", "write a comment", "comentar"], "submit_text": ["publicar", "post"]},
            {"name": "facebook_post_prompt", "open_text": ["¿qué estás pensando", "what's on your mind"], "submit_text": ["publicar", "post"]},
        ],
        "linkedin": [
            {"name": "linkedin_post_prompt", "open_text": ["comenzar publicación", "crear publicación", "start a post"], "submit_text": ["publicar", "post"]},
            {"name": "linkedin_comment", "open_text": ["comentar", "comment"], "submit_text": ["publicar", "post"]},
        ],
        "reddit": [
            {"name": "reddit_comment", "open_text": ["add a comment", "añadir un comentario", "reply"], "submit_text": ["comment", "comentar", "reply"]},
        ],
        "instagram": [
            {"name": "instagram_comment_selector", "open_selector": ['textarea[aria-label*="comment"]', 'textarea[aria-label*="comentario"]', 'form textarea'], "submit_selector": ['form button[type="submit"]'], "submit_text": ["publicar"]},
            {"name": "instagram_comment", "open_text": ["add a comment", "añade un comentario", "reply"], "submit_text": ["post", "publicar"]},
        ],
        "x": [
            {"name": "x_compose", "submit_selector": ['[data-testid="tweetButton"]', '[data-testid="tweetButtonInline"]']},
        ],
    }.get(channel, [])
    memory = load_json(ACTION_MEMORY_PATH, {})
    remembered = [item.get("strategy", {}) for item in memory.get(channel, {}).get("comment_or_post", []) if item.get("strategy")]
    strategies = remembered + [strategy for strategy in default_strategies if strategy not in remembered]
    attempts = []
    for strategy in strategies:
        prep = scroll_and_wait_for_comments(client, channel) if channel in {"youtube", "reddit", "instagram"} else {"ok": True, "skipped": True}
        if strategy.get("open_selector"):
            open_result = action_click_selector(client, strategy["open_selector"])
        elif strategy.get("open_text"):
            open_result = action_click_by_text(client, strategy["open_text"])
        else:
            open_result = {"ok": True, "skipped": True}
        time.sleep(2)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        if strategy.get("submit_selector"):
            submit_result = action_click_selector(client, strategy["submit_selector"])
            if not submit_result.get("ok") and strategy.get("submit_text"):
                submit_result = action_click_by_text(client, strategy["submit_text"])
        else:
            submit_result = action_click_by_text(client, strategy.get("submit_text", ["publicar", "post", "comment"]))
        ok = bool(fill_result.get("ok") and submit_result.get("ok"))
        keyboard_result = {"ok": False, "skipped": True}
        if fill_result.get("ok") and not submit_result.get("ok"):
            keyboard_result = submit_with_keyboard(client)
            ok = bool(keyboard_result.get("ok"))
        attempt = {"strategy": strategy["name"], "ok": ok, "prep": prep, "open": open_result, "fill": fill_result, "submit": submit_result, "keyboard_submit": keyboard_result}
        attempts.append(attempt)
        if ok:
            remember_action(channel, "comment_or_post", {"strategy": strategy})
            return {"ok": True, "mode": "comment_or_post", "attempts": attempts}
    return {"ok": False, "mode": "comment_or_post", "attempts": attempts}


def submit_with_keyboard(client: CDPClient) -> dict:
    try:
        client.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
        client.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "modifiers": 2})
        client.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "modifiers": 2})
        client.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Control", "code": "ControlLeft", "windowsVirtualKeyCode": 17})
        time.sleep(1)
        return {"ok": True, "method": "ctrl_enter"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def scroll_and_wait_for_comments(client: CDPClient, channel: str) -> dict:
    if channel == "youtube":
        expr = """
        new Promise((resolve) => {
          let tries = 0;
          const tick = () => {
            window.scrollBy(0, 700);
            const found = document.querySelector('ytd-comment-simplebox-renderer, #placeholder-area, #contenteditable-root, [contenteditable=true]');
            const comments = document.querySelector('ytd-comments, #comments');
            tries += 1;
            if (found) resolve({ok:true, tries, tag: found.tagName || found.id || ''});
            else if (tries >= 18) resolve({ok:false, tries, comments_found: !!comments});
            else setTimeout(tick, 900);
          };
          tick();
        })
        """
        return value_from_result(evaluate(client, expr, await_promise=True))
    if channel == "reddit":
        return value_from_result(evaluate(client, "(() => { for (let i=0;i<8;i++) window.scrollBy(0,650); return {ok:true}; })()"))
    if channel == "instagram":
        expr = """
        new Promise((resolve) => {
          let tries = 0;
          const tick = () => {
            window.scrollBy(0, 450);
            const found = document.querySelector('textarea[aria-label*="comment"], textarea[aria-label*="comentario"], form textarea');
            tries += 1;
            if (found) resolve({ok:true, tries, tag: found.tagName || ''});
            else if (tries >= 8) resolve({ok:false, tries});
            else setTimeout(tick, 700);
          };
          tick();
        })
        """
        return value_from_result(evaluate(client, expr, await_promise=True))
    return {"ok": True, "skipped": True}


def action_click_by_text(client: CDPClient, texts: list[str]) -> dict:
    expr = f"""
    (() => {{
      const texts = {json.dumps([text.lower() for text in texts], ensure_ascii=False)};
      const candidates = Array.from(document.querySelectorAll('button, [role="button"], a, div[aria-label], span[aria-label]'));
      for (const el of candidates) {{
        const label = ((el.innerText || el.textContent || el.getAttribute('aria-label') || '') + '').replace(/\\s+/g, ' ').trim().toLowerCase();
        if (!label) continue;
        if (!texts.some((text) => label === text || label.includes(text))) continue;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.visibility === 'hidden' || style.display === 'none' || rect.width < 5 || rect.height < 5) continue;
        el.scrollIntoView({{block:'center', inline:'center'}});
        el.click();
        return {{ok:true, label}};
      }}
      return {{ok:false, error:'boton por texto no encontrado', texts}};
    }})()
    """
    return value_from_result(evaluate(client, expr))


def action_click_selector(client: CDPClient, selectors: list[str]) -> dict:
    expr = f"""
    (() => {{
      const selectors = {json.dumps(selectors, ensure_ascii=False)};
      for (const selector of selectors) {{
        const el = document.querySelector(selector);
        if (!el) continue;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (style.visibility === 'hidden' || style.display === 'none' || rect.width < 5 || rect.height < 5) continue;
        el.scrollIntoView({{block:'center', inline:'center'}});
        el.click();
        return {{ok:true, selector}};
      }}
      return {{ok:false, error:'selector no encontrado', selectors}};
    }})()
    """
    return value_from_result(evaluate(client, expr))


def dismiss_common_popups(client: CDPClient) -> list[dict]:
    results = []
    for texts in (
        ["ahora no", "not now"],
        ["rechazar", "decline"],
        ["cerrar", "close"],
    ):
        result = action_click_by_text(client, texts)
        if result.get("ok"):
            results.append(result)
            time.sleep(0.8)
    return results


def action_like_or_react(client: CDPClient, channel: str) -> dict:
    selectors = {
        "youtube": ['button[aria-label^="poner Me gusta"]', '#segmented-like-button button', 'button[aria-label*="Me gusta"]', 'button[aria-label*="like"]'],
        "x": ['[data-testid="like"]'],
        "facebook": ['[aria-label="Me gusta"]', '[aria-label="Like"]'],
        "instagram": ['svg[aria-label="Me gusta"]', 'svg[aria-label="Like"]'],
        "linkedin": ['button[aria-label*="Reaccionar"]', 'button[aria-label*="React"]', 'button[aria-label*="Me gusta"]'],
        "reddit": ['button[aria-label*="upvote"]', 'button[aria-label*="Votar positivo"]'],
    }.get(channel, [])
    result = action_click_selector(client, selectors) if selectors else {"ok": False, "error": "sin selectores de like"}
    if result.get("ok"):
        return {"ok": True, "mode": "selector", **result}
    if channel == "youtube":
        return {"ok": False, "mode": "selector_only", "error": "like de YouTube no encontrado sin usar texto ambiguo"}
    text_result = action_click_by_text(client, ["me gusta", "like", "upvote", "votar positivo", "reaccionar"])
    return {"ok": bool(text_result.get("ok")), "mode": "text", **text_result}


def action_wait_for(client: CDPClient, selector: str, timeout_ms: int) -> dict:
    expr = f"""
    new Promise((resolve) => {{
      const selector = {js_string(selector)};
      const deadline = Date.now() + {int(timeout_ms)};
      const tick = () => {{
        const el = document.querySelector(selector);
        if (el) resolve({{ok:true, selector}});
        else if (Date.now() > deadline) resolve({{ok:false, error:'timeout', selector}});
        else setTimeout(tick, 150);
      }};
      tick();
    }})
    """
    return value_from_result(evaluate(client, expr, await_promise=True))


def action_extract(client: CDPClient, name: str, selector: str, attribute: str | None) -> dict:
    attr_expr = "el.innerText" if not attribute or attribute == "text" else f"el.getAttribute({js_string(attribute)})"
    expr = f"""
    (() => {{
      const items = Array.from(document.querySelectorAll({js_string(selector)}));
      return items.map((el) => ({attr_expr} || '').trim()).filter(Boolean);
    }})()
    """
    return {"name": name, "values": value_from_result(evaluate(client, expr)) or []}


def run_task(task_path: Path, dry_run: bool = False) -> dict:
    task = json.loads(task_path.read_text(encoding="utf-8"))
    actions = task.get("actions", [])
    if not isinstance(actions, list) or not actions:
        raise ValueError("El task debe tener una lista actions")

    results = []
    extracts: dict[str, list[str]] = {}
    with CDPClient(get_page_ws_url()) as client:
        client.send("Page.enable")
        client.send("Runtime.enable")
        for index, action in enumerate(actions, start=1):
            kind = action.get("type")
            if dry_run and kind in {"click", "type", "press", "submit"}:
                result = {"ok": True, "dry_run": True, "skipped": kind}
            elif kind == "navigate":
                url = action["url"]
                client.send("Page.navigate", {"url": url})
                time.sleep(float(action.get("wait_seconds", 2)))
                result = {"ok": True, "url": url}
            elif kind == "wait":
                time.sleep(float(action.get("seconds", 1)))
                result = {"ok": True, "seconds": action.get("seconds", 1)}
            elif kind == "wait_for":
                result = action_wait_for(client, action["selector"], int(action.get("timeout_ms", 10000)))
            elif kind == "click":
                result = action_click(client, action["selector"])
            elif kind == "type":
                result = action_type(client, action["selector"], action.get("text", ""), bool(action.get("clear", True)))
            elif kind == "press":
                key = action.get("key", "Enter")
                client.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
                client.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
                result = {"ok": True, "key": key}
            elif kind == "extract":
                result = action_extract(client, action.get("name", f"extract_{index}"), action["selector"], action.get("attribute"))
                extracts[result["name"]] = result["values"]
            elif kind == "eval":
                result = {"ok": True, "value": value_from_result(evaluate(client, action["expression"], bool(action.get("await_promise", False))))}
            else:
                raise ValueError(f"Accion no soportada en #{index}: {kind}")
            result_record = {"index": index, "type": kind, "result": result}
            results.append(result_record)
            if isinstance(result, dict) and result.get("ok") is False and action.get("critical", True):
                raise RuntimeError(f"Accion #{index} fallo: {result}")

    summary = {
        "command": "auto-browser",
        "task_path": str(task_path),
        "task_hash": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "dry_run": dry_run,
        "actions": len(actions),
        "results": results,
        "extracts": extracts,
    }
    report = write_report("auto-browser", summary)
    summary["report"] = str(report)
    return summary


def validate_distribution_entry(entry: dict, allow_proposed: bool) -> list[str]:
    errors = []
    status = entry.get("status", "")
    allowed = AUTO_PUBLISH_STATUSES if allow_proposed else LEGAL_STATUSES
    if status in BLOCKED_STATUSES or status not in allowed:
        errors.append(f"status no publicable: {status}")
    body = (entry.get("body") or "").strip()
    if len(body) < 40:
        errors.append("body demasiado corto")
    lower = body.lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim in lower:
            errors.append(f"claim prohibido: {claim}")
    if not distribution_entry_is_music_relevant(entry):
        errors.append("contexto no relacionado con musica/produccion/audio")
    return errors


def distribution_entry_is_music_relevant(entry: dict) -> bool:
    channel = normalize_channel(entry.get("channel", ""))
    if channel not in SUPPORTED_AUTO_CHANNELS:
        return True
    context = " ".join(
        str(entry.get(key) or "")
        for key in (
            "source_thread_title",
            "source_title",
            "source_context",
            "title",
            "community",
        )
    ).lower()
    if len(context.strip()) < 20:
        return channel in {"x", "facebook", "linkedin"}
    return any(term in context for term in STRICT_MUSIC_CONTEXT_TERMS)


def parse_channels(channels_text: str) -> set[str]:
    channels: set[str] = set()
    for raw in re.split(r"[, ]+", channels_text):
        channel = normalize_channel(raw)
        if not channel:
            continue
        channels.update(CHANNEL_ALIASES.get(channel, {channel}))
    return channels


def target_channels_for_row(row: dict, requested_channels: set[str]) -> list[str]:
    source = normalize_channel(row.get("channel", ""))
    if source == "social":
        possible = {"facebook", "x"}
    elif source == "twitter":
        possible = {"x"}
    elif source == "youtube":
        possible = {"youtube"}
    elif source == "instagram":
        url = row.get("source_thread_url") or row.get("source_url") or ""
        possible = {"instagram"} if re.search(r"instagram\.com/(p|reel)/", url) else set()
    elif source in SUPPORTED_AUTO_CHANNELS:
        possible = {source}
    else:
        possible = set()
    return sorted(possible & requested_channels)


def channel_already_published(row: dict, channel: str) -> bool:
    published = row.get("auto_published_channels", {})
    if isinstance(published, dict) and published.get(channel):
        return True
    return False


def posts_today_by_channel(log: list[dict]) -> dict[str, int]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counts: dict[str, int] = {}
    for row in log:
        if row.get("status") != "published" and not row.get("auto_published_channels"):
            continue
        date = row.get("date", "") or (row.get("published_at") or "")[:10]
        if date != today:
            continue
        channel = row.get("channel", "")
        if channel:
            counts[channel] = counts.get(channel, 0) + 1
        for ch in row.get("auto_published_channels", {}):
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def distribution_candidates(channels: set[str], limit: int, per_channel: int, allow_proposed: bool) -> tuple[list[dict], list[dict]]:
    log_path = DATA_DIR / "distribution_log.jsonl"
    rows = load_jsonl(log_path)
    today_counts = posts_today_by_channel(rows)
    candidates = []
    blocked = []
    per_channel_counts = {channel: 0 for channel in channels}
    for index, row in reversed(list(enumerate(rows))):
        target_channels = target_channels_for_row(row, channels)
        if not target_channels:
            continue
        errors = validate_distribution_entry(row, allow_proposed)
        if errors:
            for channel in target_channels:
                blocked.append({"index": index, "entry": row, "channel": channel, "errors": errors})
            continue
        for channel in target_channels:
            if channel_already_published(row, channel):
                continue
            if per_channel_counts[channel] >= per_channel:
                continue
            daily_limit = CHANNEL_DAILY_LIMITS.get(channel, 3)
            if today_counts.get(channel, 0) + per_channel_counts[channel] >= daily_limit:
                continue
            candidates.append({"index": index, "entry": row, "channel": channel, "errors": []})
            per_channel_counts[channel] += 1
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break
    return candidates, blocked


def normalize_channel(channel: str) -> str:
    channel = (channel or "").strip().lower()
    if channel in {"twitter"}:
        return "x"
    if channel in {"social", "newsletter", "forum"}:
        return channel
    return channel


def post_url_for_entry(entry: dict, channel: str) -> str:
    source_url = entry.get("source_thread_url") or entry.get("source_url") or ""
    if channel == "linkedin":
        return source_url if "linkedin.com" in source_url else "https://www.linkedin.com/feed/"
    if channel == "x":
        return "https://x.com/compose/post"
    if channel == "facebook":
        return source_url if "facebook.com" in source_url else "https://www.facebook.com/"
    if channel == "reddit":
        return source_url or "https://www.reddit.com/"
    if channel == "youtube":
        url = source_url
        if "youtube.com/watch" not in url and "youtu.be/" not in url:
            raise ValueError("YouTube requiere source_thread_url de un video")
        return url
    if channel == "instagram":
        url = source_url or "https://www.instagram.com/"
        return url
    raise ValueError(f"Canal no soportado por auto-distribution: {channel}")


def search_url_for(channel: str, query: str, index: int) -> str:
    if channel == "instagram":
        lower = query.lower()
        tag = INSTAGRAM_MUSIC_TAGS[index % len(INSTAGRAM_MUSIC_TAGS)]
        if "ableton" in lower:
            tag = "ableton"
        elif "fl studio" in lower or "flstudio" in lower:
            tag = "flstudio"
        elif "interfaz" in lower or "audio" in lower:
            tag = "audiointerface"
        elif "midi" in lower:
            tag = "midicontroller"
        elif "home studio" in lower or "homestudio" in lower:
            tag = "homestudio"
        return f"https://www.instagram.com/explore/tags/{tag}/"
    return SEARCH_URLS[channel].format(query=quote(query))


def looks_music_related(text: str) -> bool:
    lower = (text or "").lower()
    return any(term in lower for term in STRICT_MUSIC_CONTEXT_TERMS)


def build_distribution_body(channel: str, landing: dict, item: dict) -> tuple[str, bool]:
    query = landing["query"]
    query_text = landing.get("query", "").lower()
    context = f"{query_text} {item.get('title', '')} {item.get('context', '')}".lower()
    if channel == "instagram":
        seed = f"{landing.get('slug', '')}:{item.get('url', '')}:{item.get('title', '')}"
        def pick(options: list[str]) -> str:
            number = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
            return options[number % len(options)]

        if any(term in context for term in ["ableton", "midi", "controlador"]):
            return pick([
                "Buen enfoque. Para Ableton/MIDI, el punto suele ser elegir controles que realmente uses: pads si disparas clips, knobs si automatizas, teclas si compones.",
                "Esto esta bueno. Un controlador chico bien mapeado termina rindiendo mas que uno enorme si el flujo ya esta claro.",
                "Me gusta ese tipo de setup. Para producir rapido, suele importar mas la integracion con el DAW que la cantidad de botones.",
            ]), False
        if any(term in context for term in ["interfaz", "interface", "audio", "vocal", "voz", "microfono", "micrófono"]):
            return pick([
                "Muy real esto. Para grabar en casa, una interfaz simple con buena ganancia y monitoreo directo suele resolver mas que sumar mil cosas.",
                "Totalmente. Antes de cambiar todo el setup, conviene mirar ruido de sala, distancia al micro y si la interfaz banca bien la ganancia.",
                "Buen punto. En audio casero la decision clave suele ser cadena completa: micro, entrada, monitoreo y comodidad para repetir tomas.",
            ]), False
        if any(term in context for term in ["beat", "beats", "fl studio", "flstudio", "producer", "produccion", "producción"]):
            return pick([
                "Suena bien. Muchas veces el salto no es otro plugin, sino una cadena comoda: controlador, monitoreo y una plantilla que no te frene.",
                "Buen laburo. Se nota cuando el setup esta armado para terminar ideas, no solo para acumular equipo.",
                "Me gusta ese enfoque. Para beats, tener pads o teclas que inviten a tocar cambia mas el flujo que abrir veinte ventanas.",
            ]), False
        return pick([
            "Buen laburo. Se nota cuando el setup esta pensado para crear rapido; ahi la eleccion de controlador, audio y monitoreo pesa bastante.",
            "Me gusta la vibra del setup. Cuando todo queda a mano, producir se siente mas natural y tambien es mas facil elegir que equipo falta de verdad.",
            "Esto esta bueno. El mejor setup suele ser el que te deja terminar ideas sin pelearte con la tecnica ni comprar cosas al azar.",
            "Muy bueno. Hay algo clave en tener un flujo simple y repetible antes de decidir que sumar al home studio.",
        ]), False
    body = (
        f"Para quien este investigando {query}, conviene comparar el caso de uso antes de elegir: "
        "integracion con el DAW, cantidad de controles, espacio disponible y si se busca grabar, producir o tocar en vivo. "
        f"Dejo una guia relacionada para ordenar la decision: {landing['landing_url']}"
    )
    return body, True


def build_product_distribution_body(channel: str, landing: dict, item: dict) -> tuple[str, bool]:
    query_text = landing.get("query", "").lower()
    context = f"{query_text} {item.get('title', '')} {item.get('context', '')}".lower()
    seed = f"{landing.get('slug', '')}:{item.get('url', '')}:{item.get('title', '')}"
    with_link = channel in {"youtube", "reddit", "linkedin", "facebook"}

    def pick(options: list[str]) -> str:
        number = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16)
        return options[number % len(options)]

    audio_query = any(term in query_text for term in ["interfaz", "audio", "grabar voz", "placa de sonido", "microfono", "micr"])
    beat_query = any(term in query_text for term in ["beat", "fl studio", "flstudio", "producer", "produccion", "producci"])
    midi_query = any(term in query_text for term in ["ableton", "midi", "controlador"])

    if (midi_query or any(term in context for term in ["ableton", "midi", "controlador"])) and not audio_query and not beat_query:
        product = pick_catalog_product(context, "midi", seed)
        body = pick([
            f"Buen enfoque. Para Ableton/MIDI, algo tipo {product} tiene sentido si vas a usar teclas, pads y knobs de verdad, no solo por llenar el escritorio.",
            f"Esto esta bueno. En un setup asi miraria algo tipo {product}: compacto, mapeable y con controles que realmente entren en el flujo.",
            f"Me gusta ese tipo de setup. Para producir rapido, prefiero algo como {product} antes que un controlador enorme que despues no se aprovecha.",
        ])
        return body, with_link
    if audio_query:
        product = pick_catalog_product(context, "audio", seed)
        body = pick([
            f"Muy real esto. Para grabar en casa, algo tipo {product} suele tener mas sentido que sumar mil cosas: entrada limpia y monitoreo comodo.",
            f"Totalmente. Antes de cambiar todo el setup, miraria si con una interfaz tipo {product} ya resolves ganancia, monitoreo y latencia.",
            f"Buen punto. En audio casero la decision clave suele ser cadena completa; una opcion tipo {product} puede ordenar bastante el flujo.",
        ])
        return body, with_link
    if beat_query:
        product = pick_catalog_product(context, "beat", seed)
        body = pick([
            f"Suena bien. Muchas veces el salto no es otro plugin, sino algo tipo {product}: tocar ideas rapido y no cortar el momento creativo.",
            f"Buen laburo. Para beats, un controlador tipo {product} puede cambiar mas el flujo que abrir veinte ventanas y dibujar todo con mouse.",
            f"Me gusta ese enfoque. Si la idea es producir rapido, algo como {product} ayuda cuando queres tocar y decidir sin tanta vuelta.",
        ])
        return body, with_link
    if any(term in context for term in ["interfaz", "interface", "audio", "vocal", "voz", "microfono", "micrÃ³fono"]):
        product = pick_catalog_product(context, "audio", seed)
        body = pick([
            f"Muy real esto. Para grabar en casa, algo tipo {product} suele tener mas sentido que sumar mil cosas: entrada limpia y monitoreo comodo.",
            f"Totalmente. Antes de cambiar todo el setup, miraria si con una interfaz tipo {product} ya resolves ganancia, monitoreo y latencia.",
            f"Buen punto. En audio casero la decision clave suele ser cadena completa; una opcion tipo {product} puede ordenar bastante el flujo.",
        ])
        return body, with_link
    if any(term in context for term in ["beat", "beats", "fl studio", "flstudio", "producer", "produccion", "producciÃ³n"]):
        product = pick_catalog_product(context, "beat", seed)
        body = pick([
            f"Suena bien. Muchas veces el salto no es otro plugin, sino algo tipo {product}: tocar ideas rapido y no cortar el momento creativo.",
            f"Buen laburo. Para beats, un controlador tipo {product} puede cambiar mas el flujo que abrir veinte ventanas y dibujar todo con mouse.",
            f"Me gusta ese enfoque. Si la idea es producir rapido, algo como {product} ayuda cuando queres tocar y decidir sin tanta vuelta.",
        ])
        return body, with_link
    product = pick_catalog_product(context, "general", seed)
    body = pick([
        f"Buen laburo. En un setup asi, algo tipo {product} tiene sentido si realmente mejora el flujo y no queda solo de adorno.",
        f"Me gusta la vibra del setup. A veces sumar algo como {product} ordena mas el proceso que comprar varias cosas sin rol claro.",
        f"Esto esta bueno. El mejor setup suele ser el que te deja terminar ideas; algo tipo {product} sirve si entra en ese flujo.",
        f"Muy bueno. Antes de sumar equipo, miraria si una pieza tipo {product} resuelve una necesidad concreta del home studio.",
    ])
    return body, with_link


def compose_text(entry: dict) -> str:
    body = (entry.get("body") or "").strip()
    if normalize_channel(entry.get("channel", "")) == "instagram":
        return body[:300]
    if entry.get("link_included") or not entry.get("landing_url"):
        return body
    if len(body) + len(entry["landing_url"]) + 2 > 270 and normalize_channel(entry.get("channel", "")) in {"x", "twitter"}:
        return body
    return f"{body}\n\n{entry['landing_url']}"


def publish_entry(client: CDPClient, entry: dict, channel: str, dry_run: bool) -> dict:
    text = compose_text(entry)
    url = post_url_for_entry(entry, channel)
    client.send("Page.navigate", {"url": url})
    time.sleep(5)
    if dry_run:
        return {"ok": True, "dry_run": True, "url": url, "text_length": len(text)}

    if channel == "linkedin":
        open_result = action_click_by_text(client, ["comenzar publicación", "start a post", "crear publicación", "post"])
        time.sleep(1.5)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["publicar", "post"])
        return {"ok": bool(post_result.get("ok")), "url": url, "open": open_result, "fill": fill_result, "post": post_result}

    if channel == "x":
        fill_result = action_fill_active_editor(client, text[:275])
        time.sleep(1)
        post_result = action_click_by_text(client, ["postear", "post", "tweet"])
        return {"ok": bool(post_result.get("ok")), "url": url, "fill": fill_result, "post": post_result}

    if channel == "facebook":
        open_result = action_click_by_text(client, ["¿qué estás pensando", "what's on your mind", "crear publicación"])
        time.sleep(2)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["publicar", "post"])
        return {"ok": bool(post_result.get("ok")), "url": url, "open": open_result, "fill": fill_result, "post": post_result}

    if channel == "reddit":
        open_result = action_click_by_text(client, ["añadir un comentario", "add a comment", "comment"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["comentar", "comment", "reply"])
        return {"ok": bool(post_result.get("ok")), "url": url, "open": open_result, "fill": fill_result, "post": post_result}

    if channel == "youtube":
        open_result = action_click_by_text(client, ["añade un comentario", "add a comment", "comment"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["comentar", "comment"])
        return {"ok": bool(post_result.get("ok")), "url": url, "open": open_result, "fill": fill_result, "post": post_result}

    if channel == "instagram":
        if entry.get("media_path"):
            return {"ok": False, "url": url, "error": "Instagram media upload todavia no implementado por CDP puro"}
        open_result = action_click_by_text(client, ["añade un comentario", "add a comment", "reply"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["publicar", "post"])
        return {"ok": bool(post_result.get("ok")), "url": url, "open": open_result, "fill": fill_result, "post": post_result}

    return {"ok": False, "error": f"canal no soportado: {channel}"}


def publish_entry_v2(client: CDPClient, entry: dict, channel: str, dry_run: bool) -> dict:
    text = compose_text(entry)
    url = post_url_for_entry(entry, channel)
    client.send("Page.navigate", {"url": url})
    time.sleep(5)
    dismissed = dismiss_common_popups(client)
    if dry_run:
        return {"ok": True, "dry_run": True, "url": url, "text_length": len(text)}

    interaction = try_comment_or_post(client, channel, text[:275] if channel == "x" else text)
    if interaction.get("ok"):
        return {"ok": True, "url": url, "dismissed": dismissed, "interaction": interaction}

    if channel == "x":
        fill_result = action_fill_active_editor(client, text[:275])
        time.sleep(1)
        post_result = action_click_selector(client, ['[data-testid="tweetButton"]', '[data-testid="tweetButtonInline"]'])
        if not post_result.get("ok"):
            post_result = action_click_by_text(client, ["postear", "tweet"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    if channel == "youtube":
        evaluate(client, "window.scrollTo(0, Math.max(700, document.body.scrollHeight * 0.35))")
        time.sleep(2)
        open_result = action_click_selector(client, ["#placeholder-area", "ytd-comment-simplebox-renderer #placeholder-area"])
        if not open_result.get("ok"):
            open_result = action_click_by_text(client, ["añade un comentario", "add a comment"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_selector(client, ["#submit-button button", "ytd-comment-dialog-renderer #submit-button button"])
        if not post_result.get("ok"):
            post_result = action_click_by_text(client, ["comentar"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "open": open_result, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    if channel == "linkedin":
        open_result = action_click_by_text(client, ["comenzar publicación", "start a post", "crear publicación", "post"])
        time.sleep(3)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_selector(client, [".share-actions__primary-action button", "button.share-actions__primary-action"])
        if not post_result.get("ok"):
            post_result = action_click_by_text(client, ["publicar"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "open": open_result, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    if channel == "facebook":
        open_result = action_click_by_text(client, ["¿qué estás pensando", "what's on your mind", "crear publicación"])
        time.sleep(3)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["publicar"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "open": open_result, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    if channel == "reddit":
        evaluate(client, "window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        open_result = action_click_by_text(client, ["añadir un comentario", "add a comment"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["comentar", "comment", "reply"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "open": open_result, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    if channel == "instagram":
        if entry.get("media_path"):
            return {"ok": False, "url": url, "error": "Instagram media upload todavia no implementado por CDP puro"}
        open_result = action_click_by_text(client, ["añade un comentario", "add a comment", "reply"])
        time.sleep(1)
        fill_result = action_fill_active_editor(client, text)
        time.sleep(1)
        post_result = action_click_by_text(client, ["publicar", "post"])
        ok = bool(fill_result.get("ok") and post_result.get("ok"))
        like_result = {"ok": False, "skipped": True} if ok else action_like_or_react(client, channel)
        return {"ok": bool(ok or like_result.get("ok")), "url": url, "dismissed": dismissed, "open": open_result, "fill": fill_result, "post": post_result, "fallback_like": like_result}

    return {"ok": False, "error": f"canal no soportado: {channel}"}


def run_auto_distribution(channels_text: str, limit: int, per_channel: int, dry_run: bool, allow_proposed: bool) -> dict:
    channels = parse_channels(channels_text)
    unsupported = sorted(channels - SUPPORTED_AUTO_CHANNELS)
    channels &= SUPPORTED_AUTO_CHANNELS
    candidates, blocked = distribution_candidates(channels, limit, per_channel, allow_proposed)
    log_path = DATA_DIR / "distribution_log.jsonl"
    rows = load_jsonl(log_path)
    results = []
    with CDPClient(get_page_ws_url()) as client:
        client.send("Page.enable")
        client.send("Runtime.enable")
        for candidate in candidates:
            entry = candidate["entry"]
            channel = candidate["channel"]
            try:
                result = publish_entry_v2(client, entry, channel, dry_run)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}
            results.append({"id": entry.get("id"), "channel": channel, "slug": entry.get("landing_slug"), "result": result})
            if not dry_run:
                row = rows[candidate["index"]]
                row["auto_publish_attempted_at_utc"] = datetime.now(timezone.utc).isoformat()
                row["auto_publish_result"] = result
                row.setdefault("auto_published_channels", {})
                if result.get("ok"):
                    row["auto_published_channels"][channel] = {
                        "published_at_utc": datetime.now(timezone.utc).isoformat(),
                        "result": result,
                    }
                    row["status"] = "published"
                    row["published_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    row.setdefault("auto_publish_failures", {})
                    row["auto_publish_failures"][channel] = {
                        "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                        "result": result,
                    }

    if not dry_run and candidates:
        rewrite_jsonl(log_path, rows)

    summary = {
        "command": "auto-distribution",
        "channels": sorted(channels),
        "unsupported_channels": unsupported,
        "limit": limit,
        "per_channel": per_channel,
        "dry_run": dry_run,
        "allow_proposed": allow_proposed,
        "published_or_attempted": len(results),
        "blocked_seen": len(blocked),
        "results": results,
        "blocked_sample": [
            {
                "id": item["entry"].get("id"),
                "channel": item["channel"],
                "status": item["entry"].get("status"),
                "errors": item["errors"],
            }
            for item in blocked[:10]
        ],
    }
    report = write_report("auto-distribution", summary)
    summary["report"] = str(report)
    return summary


def load_landing_queries(limit: int) -> list[dict]:
    rows = load_jsonl(DATA_DIR / "landings_aprobadas.jsonl")
    out = []
    for row in rows:
        slug = row.get("slug", "")
        query = row.get("keyword") or row.get("h1") or slug.replace("-", " ")
        if slug and query:
            out.append({"slug": slug, "query": query, "landing_url": f"https://blog.pcmidicenter.com/{slug}/"})
        if len(out) >= limit:
            break
    return out


def extract_visible_items(client: CDPClient, channel: str, max_items: int) -> list[dict]:
    expr = f"""
    (() => {{
      const channel = {js_string(channel)};
      const maxItems = {int(max_items)};
      const anchors = Array.from(document.querySelectorAll('a[href]'));
      const out = [];
      const seen = new Set();
      for (const a of anchors) {{
        const href = new URL(a.href, location.href).href;
        const box = a.closest('article, ytd-video-renderer, ytd-rich-item-renderer, [role="article"], div, li') || a;
        const title = (a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
        const mediaText = Array.from(a.querySelectorAll('img, video')).map((el) => el.getAttribute('alt') || el.getAttribute('aria-label') || '').join(' ');
        const context = ((box.innerText || box.textContent || title || mediaText) || '').replace(/\\s+/g, ' ').trim();
        if (!href || seen.has(href)) continue;
        if (channel === 'youtube' && !href.includes('/watch')) continue;
        if (channel === 'reddit' && !href.includes('/comments/')) continue;
        if (channel === 'linkedin' && !href.includes('linkedin.com')) continue;
        if (channel === 'x' && !/x\\.com\\/.+\\/status\\//.test(href)) continue;
        if (channel === 'instagram' && !/instagram\\.com\\/(p|reel)\\//.test(href)) continue;
        if (channel === 'facebook' && !href.includes('facebook.com')) continue;
        if (channel !== 'instagram' && context.length < 30) continue;
        seen.add(href);
        out.push({{url: href, title: title.slice(0, 220), context: context.slice(0, 1200)}});
        if (out.length >= maxItems) break;
      }}
      return out;
    }})()
    """
    return value_from_result(evaluate(client, expr)) or []


def run_auto_listen(channels_text: str, searches: int, per_search: int, dry_run: bool) -> dict:
    channels = parse_channels(channels_text)
    channels &= set(SEARCH_URLS)
    queries = load_landing_queries(searches)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    intel_rows = []
    task_rows = []
    feedback_rows = []
    distribution_rows = []

    with CDPClient(get_page_ws_url()) as client:
        client.send("Page.enable")
        client.send("Runtime.enable")
        for channel in sorted(channels):
            for query_index, landing in enumerate(queries):
                url = search_url_for(channel, landing["query"], query_index)
                client.send("Page.navigate", {"url": url})
                time.sleep(5)
                items = extract_visible_items(client, channel, per_search)
                for item in items:
                    item_context = f"{item.get('title', '')} {item.get('context', '')} {item.get('url', '')} {url}"
                    source_context = f"{item.get('title', '')} {item.get('context', '')}"
                    if not looks_music_related(source_context):
                        continue
                    base = {
                        "id": f"{run_id}:{channel}:{len(intel_rows)}",
                        "created_at_utc": datetime.now(timezone.utc).isoformat(),
                        "run_id": run_id,
                        "channel": channel,
                        "query": landing["query"],
                        "landing_slug": landing["slug"],
                        "landing_url": landing["landing_url"],
                        "source_url": item.get("url", ""),
                        "source_title": item.get("title", ""),
                        "source_context": item.get("context", ""),
                    }
                    intel_rows.append(base)
                    task_rows.append({
                        **base,
                        "status": "approved",
                        "search_url": url,
                        "mode": "auto_browser_listen",
                        "notes": "Oportunidad detectada por Chrome real; disponible para agente de distribucion.",
                    })
                    feedback_rows.append({
                        "created_at_utc": base["created_at_utc"],
                        "source": "auto_listen",
                        "type": "distribution_opportunity",
                        "priority": "medium",
                        "channel": channel,
                        "landing_slug": landing["slug"],
                        "suggestion": f"Responder o publicar sobre: {item.get('title', '')[:160]}",
                        "source_url": item.get("url", ""),
                    })
                    if channel in SUPPORTED_AUTO_CHANNELS and item.get("url"):
                        body, link_included = build_product_distribution_body(channel, landing, item)
                        distribution_rows.append({
                            "id": f"{run_id}:{channel}:auto-listen:{len(distribution_rows)}",
                            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                            "created_at_utc": base["created_at_utc"],
                            "run_id": run_id,
                            "landing_slug": landing["slug"],
                            "landing_url": landing["landing_url"],
                            "channel": channel,
                            "community": channel,
                            "content_type": "respuesta_auto_listen",
                            "status": "approved",
                            "title": item.get("title", "")[:200],
                            "body": body,
                            "link_included": link_included,
                            "risk_level": "low",
                            "requires_manual_review": False,
                            "approved_at_utc": base["created_at_utc"],
                            "approval_mode": "auto_listen",
                            "source_thread_url": item.get("url", ""),
                            "source_thread_title": item.get("title", "")[:200],
                            "source_context": item.get("context", "")[:1200],
                            "notes": "Borrador aprobado generado desde auto-listen.",
                        })

    if not dry_run and intel_rows:
        append_jsonl(SOCIAL_INTEL_PATH, intel_rows)
        append_jsonl(SEARCH_TASKS_PATH, task_rows)
        append_jsonl(CONTENT_FEEDBACK_PATH, feedback_rows)
        append_jsonl(DISTRIBUTION_LOG_PATH, distribution_rows)

    summary = {
        "command": "auto-listen",
        "channels": sorted(channels),
        "searches": searches,
        "per_search": per_search,
        "dry_run": dry_run,
        "items": len(intel_rows),
        "distribution_drafts": len(distribution_rows),
        "social_intel_path": str(SOCIAL_INTEL_PATH),
        "search_tasks_path": str(SEARCH_TASKS_PATH),
        "content_feedback_path": str(CONTENT_FEEDBACK_PATH),
        "sample": intel_rows[:10],
    }
    report = write_report("auto-listen", summary)
    summary["report"] = str(report)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre Chrome real con perfil persistente para el flujo root69")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start-browser", help="Abre Chrome real con puerto CDP y perfil persistente")
    auto_parser = sub.add_parser("auto-browser", help="Ejecuta acciones JSON sobre Chrome real ya logueado")
    auto_parser.add_argument("--task", required=True, help="Ruta a un JSON con acciones")
    auto_parser.add_argument("--dry-run", action="store_true", help="Navega/extrrae pero no ejecuta clicks ni escritura")
    distribution_parser = sub.add_parser("auto-distribution", help="Publica entradas aprobadas con Chrome real")
    distribution_parser.add_argument("--channels", default="linkedin,reddit", help="Canales separados por coma; usar all para todos los soportados")
    distribution_parser.add_argument("--limit", type=int, default=1, help="Maximo de publicaciones")
    distribution_parser.add_argument("--per-channel", type=int, default=1, help="Maximo por red en esta corrida")
    distribution_parser.add_argument("--dry-run", action="store_true", help="No hace clicks de publicar")
    distribution_parser.add_argument("--allow-proposed", action="store_true", help="Permite publicar status=proposed ademas de aprobadas")
    listen_parser = sub.add_parser("auto-listen", help="Lee oportunidades en redes y alimenta agentes")
    listen_parser.add_argument("--channels", default="all", help="Canales separados por coma; usar all")
    listen_parser.add_argument("--searches", type=int, default=3, help="Cantidad de landings/queries")
    listen_parser.add_argument("--per-search", type=int, default=3, help="Items por busqueda")
    listen_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.command == "start-browser":
        result = start_browser()
        report = write_report("start-browser", {"command": "start-browser", **result})
        print(f"Chrome iniciado. Logueate una vez y dejalo abierto. CDP: {CDP_URL}. Reporte: {report}")
    elif args.command == "auto-browser":
        summary = run_task(Path(args.task).resolve(), args.dry_run)
        print(f"auto-browser: {summary['actions']} acciones. Reporte: {summary['report']}")
    elif args.command == "auto-distribution":
        summary = run_auto_distribution(args.channels, args.limit, args.per_channel, args.dry_run, args.allow_proposed)
        print(f"auto-distribution: {summary['published_or_attempted']} intentos. Reporte: {summary['report']}")
    elif args.command == "auto-listen":
        summary = run_auto_listen(args.channels, args.searches, args.per_search, args.dry_run)
        print(f"auto-listen: {summary['items']} items. Reporte: {summary['report']}")


if __name__ == "__main__":
    main()
