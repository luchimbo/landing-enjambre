import hmac
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.env import load_env
from lib.mailer import send_email


ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / ".vendor" / "py313"
if VENDOR_DIR.exists():
    vendor_path = str(VENDOR_DIR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)

import psycopg
from psycopg.rows import dict_row

DATA_DIR = ROOT / "data"
LEAD_MAGNETS_FILE = DATA_DIR / "lead_magnets.jsonl"
LANDINGS_FILE = DATA_DIR / "landings_aprobadas.jsonl"
CATEGORIES_FILE = DATA_DIR / "categorias_pcmidi.json"

load_env()

_categories_map: dict[str, dict] | None = None


def load_categories() -> dict[str, dict]:
    """Carga categorias desde el JSON y devuelve un dict por id."""
    global _categories_map
    if _categories_map is not None:
        return _categories_map
    _categories_map = {}
    if not CATEGORIES_FILE.exists():
        return _categories_map
    try:
        data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
        for cat in data:
            cid = cat.get("id")
            if cid:
                _categories_map[cid] = cat
    except (json.JSONDecodeError, OSError):
        pass
    return _categories_map


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def enabled() -> bool:
    return bool(database_url())


def connect():
    return psycopg.connect(database_url(), row_factory=dict_row)


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email or ""))


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def unsubscribe_token(email: str) -> str:
    secret = os.getenv("NURTURE_UNSUBSCRIBE_SECRET") or os.getenv("NURTURE_SMTP_PASS", "")
    return hmac.new(secret.encode("utf-8"), email.lower().encode("utf-8"), hashlib.sha256).hexdigest()


def unsubscribe_url(email: str) -> str:
    base_url = os.getenv("NURTURE_UNSUBSCRIBE_BASE_URL", "").strip()
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}?email={email.lower()}&token={unsubscribe_token(email)}"


def load_jsonl_by_slug(path: Path, nested_key: str | None = None) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        slug = record.get("slug")
        if slug:
            rows[slug] = record.get(nested_key, {}) if nested_key else record
    return rows


def load_landings() -> dict[str, dict]:
    return load_jsonl_by_slug(LANDINGS_FILE)


def load_lead_magnets() -> dict[str, dict]:
    return load_jsonl_by_slug(LEAD_MAGNETS_FILE, "lead_magnet")


def lead_magnet_resource_text(magnet: dict, landing: dict) -> str:
    """Construye el recurso prometido como contenido real dentro del email."""
    title = magnet.get("title") or "Recurso PC MIDI Labs"
    resource_type = (magnet.get("resource_type") or "recurso").lower()
    lines = ["", "---", title]

    if resource_type == "checklist":
        lines.append("Checklist practica:")
        items: list[str] = []
        for component in landing.get("components", [])[:4]:
            cat = component.get("cat") or "Categoria"
            look = component.get("look") or component.get("why") or "Comparar segun tu caso de uso."
            items.append(f"[ ] {cat}: {look}")
        for step in landing.get("steps", [])[:4]:
            title_step = step.get("t") or "Paso recomendado"
            body_step = step.get("b") or "Revisalo antes de decidir."
            items.append(f"[ ] {title_step}: {body_step}")
        if not items:
            items = [
                "[ ] Defini el uso principal antes de elegir.",
                "[ ] Revisa conexiones, espacio disponible y compatibilidad.",
                "[ ] Compara categorias antes de decidir por un modelo.",
            ]
        lines.extend(items[:8])
    elif resource_type == "comparativa":
        lines.append("Puntos de comparacion:")
        for component in landing.get("components", [])[:5]:
            cat = component.get("cat") or "Opcion"
            why = component.get("why") or "Puede servir segun tu setup."
            look = component.get("look") or "Comparar detalles antes de elegir."
            lines.append(f"- {cat}: {why} Que mirar: {look}")
    elif resource_type == "mapa de decision":
        lines.append("Mapa de decision:")
        steps = landing.get("steps", [])[:5]
        if steps:
            for index, step in enumerate(steps, start=1):
                title_step = step.get("t") or "Decision"
                body_step = step.get("b") or "Revisalo antes de avanzar."
                lines.append(f"{index}. Si estas en esta etapa: {title_step}. Criterio: {body_step}")
        else:
            lines.extend([
                "1. Si todavia no definiste el uso principal, empezá por eso.",
                "2. Si ya sabes que queres conectar, revisa entradas y compatibilidad.",
                "3. Si tenes poco espacio, prioriza formatos compactos.",
            ])
    elif resource_type == "configuracion":
        lines.append("Configuracion sugerida:")
        for step in landing.get("steps", [])[:6]:
            title_step = step.get("t") or "Paso"
            body_step = step.get("b") or "Aplicalo segun tu setup."
            lines.append(f"- {title_step}: {body_step}")
    elif resource_type == "plantilla":
        lines.append("Plantilla para completar:")
        lines.append("- Uso principal: ______________________________")
        lines.append("- Equipo que ya tenes: ________________________")
        lines.append("- Que necesitas conectar: _____________________")
        lines.append("- Espacio disponible: _________________________")
        lines.append("- Categoria a comparar primero: _______________")
        for component in landing.get("components", [])[:3]:
            cat = component.get("cat") or "Categoria"
            lines.append(f"- {cat}: cumple / no cumple / revisar")
    elif resource_type == "script":
        lines.append("Guion de preguntas antes de comprar:")
        questions = [faq.get("q") for faq in landing.get("faqs", []) if faq.get("q")]
        if questions:
            for question in questions[:6]:
                lines.append(f"- {question}")
        else:
            lines.extend([
                "- Que uso principal le voy a dar?",
                "- Que necesito conectar hoy?",
                "- Que podria necesitar conectar mas adelante?",
                "- Tengo espacio suficiente para este formato?",
            ])
    elif resource_type == "preset":
        lines.append("Preset recomendado como punto de partida:")
        lines.append("- Guardá esta configuracion como referencia inicial y ajustala segun tu equipo.")
        for step in landing.get("steps", [])[:4]:
            title_step = step.get("t") or "Ajuste"
            body_step = step.get("b") or "Adaptalo a tu flujo de trabajo."
            lines.append(f"- {title_step}: {body_step}")
    else:
        lines.append("Guia breve:")
        for step in landing.get("steps", [])[:5]:
            title_step = step.get("t") or "Paso recomendado"
            body_step = step.get("b") or "Revisalo antes de decidir."
            lines.append(f"- {title_step}: {body_step}")

    primary_category = landing.get("primary_category_id", "")
    if primary_category:
        lines.append("")
        lines.append(f"Categoria principal para revisar: {primary_category}")
    lines.append("Si queres comparar alternativas, podes usar esta lista mientras miras opciones en pcmidi.com.ar.")
    return "\n".join(lines)


def init_db() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    whatsapp TEXT,
                    nombre TEXT,
                    slug TEXT NOT NULL,
                    keyword TEXT,
                    category_id TEXT,
                    product_ids JSONB,
                    lead_magnet_slug TEXT,
                    lead_magnet_title TEXT,
                    consentimiento BOOLEAN NOT NULL DEFAULT FALSE,
                    opt_in_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS nurture_messages (
                    id BIGSERIAL PRIMARY KEY,
                    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                    day_number INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    sent_at TIMESTAMPTZ,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    last_retry TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (lead_id, day_number)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_events (
                    id BIGSERIAL PRIMARY KEY,
                    lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    event_data JSONB,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS page_events (
                    id BIGSERIAL PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    slug TEXT,
                    event_data JSONB,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nurture_status ON nurture_messages(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nurture_lead_day ON nurture_messages(lead_id, day_number)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON lead_events(event_type)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_page_events_slug ON page_events(slug)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_page_events_type ON page_events(event_type)")


def create_lead(data: dict) -> tuple[int, str]:
    email = data.get("email", "").strip().lower()
    if not email:
        return 0, "Email requerido"
    if not validate_email(email):
        return 0, "Email invalido"
    if not truthy(data.get("consentimiento", False)):
        return 0, "Consentimiento requerido"
    slug = data.get("slug", "").strip()
    if not slug:
        return 0, "Slug requerido"

    landings = load_landings()
    magnets = load_lead_magnets()
    if slug not in landings:
        return 0, f"Landing '{slug}' no encontrada"
    landing = landings[slug]
    magnet = magnets.get(slug, {})
    sequence = magnet.get("nurture_sequence", {})

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM leads WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "unsubscribed":
                    cur.execute("UPDATE leads SET status = 'active', updated_at = now() WHERE id = %s", (existing["id"],))
                return int(existing["id"]), "Lead ya existente, actualizado"

            cur.execute(
                """
                INSERT INTO leads (email, whatsapp, nombre, slug, keyword, category_id, product_ids,
                                   lead_magnet_slug, lead_magnet_title, consentimiento, opt_in_confirmed, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, 'active')
                RETURNING id
                """,
                (
                    email,
                    data.get("whatsapp", "").strip(),
                    data.get("nombre", "").strip(),
                    slug,
                    landing.get("keyword", ""),
                    landing.get("primary_category_id", ""),
                    json.dumps(landing.get("product_ids", [])),
                    slug,
                    magnet.get("title", ""),
                ),
            )
            lead_id = int(cur.fetchone()["id"])
            cur.execute(
                "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)",
                (lead_id, "captured", json.dumps({"slug": slug, "keyword": landing.get("keyword", ""), "source": "api"})),
            )
            for day_key, msg_data in sequence.items():
                if not msg_data:
                    continue
                day_num = int(day_key.replace("day_", ""))
                subject = msg_data.get("subject", "")
                body = msg_data.get("body", "")
                if subject and body:
                    cur.execute(
                        """
                        INSERT INTO nurture_messages (lead_id, day_number, subject, body, status)
                        VALUES (%s, %s, %s, %s, 'pending')
                        ON CONFLICT (lead_id, day_number) DO NOTHING
                        """,
                        (lead_id, day_num, subject, body),
                    )

            day0 = sequence.get("day_0", {})
            if day0:
                body = day0.get("body", "")
                nombre = data.get("nombre", "").strip()
                if nombre:
                    body = body.replace("¡Hola!", f"¡Hola {nombre}!")
                body = body.rstrip() + "\n" + lead_magnet_resource_text(magnet, landing)
                cat_id = landing.get("primary_category_id", "")
                categories = load_categories()
                cat_info = categories.get(cat_id, {})
                ok, error = send_email(
                    to_email=email,
                    subject=day0.get("subject", "Bienvenido a PC MIDI Center"),
                    body_text=body,
                    unsubscribe_url=unsubscribe_url(email),
                    category_url=cat_info.get("url", ""),
                    category_name=cat_info.get("nombre", ""),
                    lead_id=lead_id,
                    slug=slug,
                    day_number=0,
                )
                if ok:
                    cur.execute("UPDATE nurture_messages SET status = 'sent', sent_at = now() WHERE lead_id = %s AND day_number = 0", (lead_id,))
                    cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (lead_id, "email_sent", json.dumps({"day": 0, "subject": day0.get("subject", ""), "auto": True})))
                else:
                    cur.execute("UPDATE nurture_messages SET status = 'failed', error_message = %s WHERE lead_id = %s AND day_number = 0", (error, lead_id))
                    cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (lead_id, "email_failed", json.dumps({"day": 0, "error": error, "auto": True})))
            return lead_id, "Lead creado exitosamente"


def unsubscribe(email: str, token: str = "") -> tuple[bool, str]:
    email = email.strip().lower()
    if not email:
        return False, "Email requerido"
    if token and not hmac.compare_digest(token, unsubscribe_token(email)):
        return False, "Token invalido"
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM leads WHERE email = %s", (email,))
            row = cur.fetchone()
            if not row:
                return False, "Email no encontrado"
            lead_id = int(row["id"])
            cur.execute("UPDATE leads SET status = 'unsubscribed', updated_at = now() WHERE id = %s", (lead_id,))
            cur.execute("UPDATE nurture_messages SET status = 'cancelled' WHERE lead_id = %s AND status = 'pending'", (lead_id,))
            cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (lead_id, "unsubscribed", json.dumps({"source": "api"})))
    return True, "Baja procesada correctamente"


def stats() -> dict[str, Any]:
    if not enabled():
        return {"leads": {"total": 0, "active": 0, "unsubscribed": 0}, "messages": {"sent": 0, "pending": 0, "failed": 0}}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM leads")
            total = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM leads WHERE status = 'active'")
            active = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM leads WHERE status = 'unsubscribed'")
            unsubscribed = cur.fetchone()["total"]
            cur.execute("SELECT status, COUNT(*) AS total FROM nurture_messages GROUP BY status")
            message_rows = {row["status"]: row["total"] for row in cur.fetchall()}
    return {
        "leads": {"total": total, "active": active, "unsubscribed": unsubscribed},
        "messages": {"sent": message_rows.get("sent", 0), "pending": message_rows.get("pending", 0), "failed": message_rows.get("failed", 0)},
    }


def process_pending(limit: int = 50, dry_run: bool = False) -> dict[str, Any]:
    results = {"processed": 0, "sent": 0, "skipped": 0, "failed": 0, "errors": []}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.lead_id, m.day_number, m.subject, m.body,
                       l.email, l.nombre, l.category_id, l.slug
                FROM nurture_messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE m.status = 'pending'
                  AND l.status = 'active'
                  AND l.opt_in_confirmed = TRUE
                  AND (l.created_at + (m.day_number || ' days')::interval) <= now()
                ORDER BY m.lead_id, m.day_number
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            categories = load_categories()
            for msg in rows:
                results["processed"] += 1
                body = msg["body"]
                if msg.get("nombre"):
                    body = body.replace("¡Hola!", f"¡Hola {msg['nombre']}!")
                    body = body.replace("Hola de nuevo", f"Hola de nuevo {msg['nombre']}")
                cat_info = categories.get(msg.get("category_id", ""), {})
                ok, error = send_email(
                    to_email=msg["email"],
                    subject=msg["subject"],
                    body_text=body,
                    dry_run=dry_run,
                    unsubscribe_url=unsubscribe_url(msg["email"]),
                    category_url=cat_info.get("url", ""),
                    category_name=cat_info.get("nombre", ""),
                    lead_id=msg["lead_id"],
                    slug=msg.get("slug", ""),
                    day_number=msg["day_number"],
                )
                if ok:
                    if not dry_run:
                        cur.execute("UPDATE nurture_messages SET status = 'sent', sent_at = now() WHERE id = %s", (msg["id"],))
                        cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (msg["lead_id"], "email_sent", json.dumps({"day": msg["day_number"], "subject": msg["subject"]})))
                    results["sent"] += 1
                    print(f"  [OK] Enviado dia {msg['day_number']} a {msg['email']}: {msg['subject']}")
                else:
                    if not dry_run:
                        cur.execute("UPDATE nurture_messages SET status = 'failed', error_message = %s WHERE id = %s", (error, msg["id"]))
                        cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (msg["lead_id"], "email_failed", json.dumps({"day": msg["day_number"], "error": error})))
                    results["failed"] += 1
                    results["errors"].append({"lead_id": msg["lead_id"], "email": msg["email"], "error": error})
                    print(f"  [FAIL] Fallo dia {msg['day_number']} a {msg['email']}: {error}")
    return results


def retry_failed(limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
    results = {"processed": 0, "sent": 0, "failed": 0}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.lead_id, m.day_number, m.subject, m.body,
                       l.email, l.nombre, l.category_id, l.slug
                FROM nurture_messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE m.status = 'failed'
                  AND l.status = 'active'
                  AND COALESCE(m.retry_count, 0) < 3
                  AND (m.last_retry IS NULL OR m.last_retry + interval '1 hour' <= now())
                ORDER BY m.lead_id, m.day_number
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            categories = load_categories()
            for msg in rows:
                results["processed"] += 1
                body = msg["body"]
                if msg.get("nombre"):
                    body = body.replace("¡Hola!", f"¡Hola {msg['nombre']}!")
                    body = body.replace("Hola de nuevo", f"Hola de nuevo {msg['nombre']}")
                cat_info = categories.get(msg.get("category_id", ""), {})
                ok, error = send_email(
                    to_email=msg["email"],
                    subject=msg["subject"],
                    body_text=body,
                    dry_run=dry_run,
                    unsubscribe_url=unsubscribe_url(msg["email"]),
                    category_url=cat_info.get("url", ""),
                    category_name=cat_info.get("nombre", ""),
                    lead_id=msg["lead_id"],
                    slug=msg.get("slug", ""),
                    day_number=msg["day_number"],
                )
                if ok:
                    if not dry_run:
                        cur.execute("UPDATE nurture_messages SET status = 'sent', sent_at = now(), retry_count = COALESCE(retry_count, 0) + 1 WHERE id = %s", (msg["id"],))
                        cur.execute("INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)", (msg["lead_id"], "email_sent", json.dumps({"day": msg["day_number"], "subject": msg["subject"], "retry": True})))
                    results["sent"] += 1
                else:
                    if not dry_run:
                        cur.execute("UPDATE nurture_messages SET retry_count = COALESCE(retry_count, 0) + 1, last_retry = now(), error_message = %s WHERE id = %s", (error, msg["id"]))
                    results["failed"] += 1
    return results


ALLOWED_EVENT_TYPES = {"cta_click", "form_submit", "page_view", "email_click"}


def record_page_event(event_type: str, slug: str | None, extra: dict | None = None) -> tuple[bool, str]:
    if event_type not in ALLOWED_EVENT_TYPES:
        return False, f"Tipo de evento no permitido: {event_type}"
    if not enabled():
        return False, "Base de datos no configurada"
    event_data = extra or {}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO page_events (event_type, slug, event_data) VALUES (%s, %s, %s)",
                (event_type, slug or "", json.dumps(event_data)),
            )
    return True, "ok"


def record_email_click(lead_id: int, slug: str, extra: dict | None = None) -> tuple[bool, str]:
    if not enabled():
        return False, "Base de datos no configurada"
    event_data = {"slug": slug, **(extra or {})}
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (%s, %s, %s)",
                (lead_id, "email_click", json.dumps(event_data)),
            )
            cur.execute(
                "INSERT INTO page_events (event_type, slug, event_data) VALUES (%s, %s, %s)",
                ("email_click", slug or "", json.dumps(event_data)),
            )
    return True, "ok"
