#!/usr/bin/env python3
"""
API Server para recibir leads desde formularios de landings

Endpoints:
    POST /api/leads - Recibe datos del formulario y crea lead + secuencia
    GET  /api/health - Health check
    POST /api/unsubscribe - Procesa bajas

Uso:
    python api_server.py
    
El servidor escucha en http://localhost:5000 por defecto.
"""

import json
import os
import re
import sqlite3
import sys
import hmac
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from collections import Counter
from flask import Flask, jsonify, render_template, request

# Agregar parent al path para importar desde lib/
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.mailer import send_email
from lib import nurture_pg

app = Flask(__name__)

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "nurture.db"
LEAD_MAGNETS_FILE = DATA_DIR / "lead_magnets.jsonl"
LANDINGS_FILE     = DATA_DIR / "landings_aprobadas.jsonl"
REPORTS_DIR       = ROOT / "reports"
ENGAGEMENT_LOG    = DATA_DIR / "engagement_log.jsonl"
DISTRIBUTION_LOG  = DATA_DIR / "distribution_log.jsonl"
GEO_AUDITS_LOG    = DATA_DIR / "geo_audits.jsonl"
CONTENT_FEEDBACK  = DATA_DIR / "content_feedback.jsonl"

# Cargar .env
ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

UNSUBSCRIBE_BASE_URL = os.getenv("NURTURE_UNSUBSCRIBE_BASE_URL", "").strip()


def validate_email(email: str) -> bool:
    """Valida formato de email."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def request_data() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    raw = request.get_data(as_text=True) or ""
    if raw.strip().startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return dict(request.form.items())


def unsubscribe_token(email: str) -> str:
    secret = os.getenv("NURTURE_UNSUBSCRIBE_SECRET") or os.getenv("NURTURE_SMTP_PASS", "")
    return hmac.new(secret.encode("utf-8"), email.lower().encode("utf-8"), hashlib.sha256).hexdigest()


def unsubscribe_url(email: str) -> str:
    if not UNSUBSCRIBE_BASE_URL:
        return ""
    return f"{UNSUBSCRIBE_BASE_URL.rstrip('/')}?email={email.lower()}&token={unsubscribe_token(email)}"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_lead_magnets() -> dict[str, dict]:
    magnets: dict[str, dict] = {}
    if not LEAD_MAGNETS_FILE.exists():
        return magnets
    with open(LEAD_MAGNETS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                slug = record.get("slug")
                if slug:
                    magnets[slug] = record.get("lead_magnet", {})
            except json.JSONDecodeError:
                continue
    return magnets


def load_landings() -> dict[str, dict]:
    landings: dict[str, dict] = {}
    if not LANDINGS_FILE.exists():
        return landings
    with open(LANDINGS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                slug = record.get("slug")
                if slug:
                    landings[slug] = record
            except json.JSONDecodeError:
                continue
    return landings


def lead_magnet_resource_text(magnet: dict, landing: dict) -> str:
    title = magnet.get("title") or "Recurso PC MIDI Labs"
    resource_type = (magnet.get("resource_type") or "recurso").lower()
    lines = ["", "---", title]
    if resource_type == "checklist":
        lines.append("Checklist practica:")
        items = []
        for component in landing.get("components", [])[:4]:
            cat = component.get("cat") or "Categoria"
            look = component.get("look") or component.get("why") or "Comparar segun tu caso de uso."
            items.append(f"[ ] {cat}: {look}")
        for step in landing.get("steps", [])[:4]:
            title_step = step.get("t") or "Paso recomendado"
            body_step = step.get("b") or "Revisalo antes de decidir."
            items.append(f"[ ] {title_step}: {body_step}")
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
        for index, step in enumerate(landing.get("steps", [])[:5], start=1):
            title_step = step.get("t") or "Decision"
            body_step = step.get("b") or "Revisalo antes de avanzar."
            lines.append(f"{index}. Si estas en esta etapa: {title_step}. Criterio: {body_step}")
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
        for question in questions[:6]:
            lines.append(f"- {question}")
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
    lines.append("Si queres comparar alternativas, podes usar esta lista mientras miras opciones en pcmidi.com.ar.")
    return "\n".join(lines)


def create_lead(data: dict) -> tuple[int, str]:
    """Crea un lead y su secuencia de nurturing."""
    email = data.get("email", "").strip().lower()
    
    if not email:
        return 0, "Email requerido"
    
    if not validate_email(email):
        return 0, "Email invalido"
    
    slug = data.get("slug", "").strip()
    if not slug:
        return 0, "Slug requerido"
    
    # Verificar consentimiento
    consentimiento = truthy(data.get("consentimiento", False))
    if not consentimiento:
        return 0, "Consentimiento requerido"
    
    # Cargar landing y lead magnet
    landings = load_landings()
    magnets = load_lead_magnets()
    
    if slug not in landings:
        return 0, f"Landing '{slug}' no encontrada"
    
    landing = landings[slug]
    magnet = magnets.get(slug, {})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verificar si email ya existe
        cursor.execute("SELECT id, status FROM leads WHERE email = ?", (email,))
        existing = cursor.fetchone()
        
        if existing:
            lead_id = existing["id"]
            # Si estaba dado de baja, reactivar
            if existing["status"] == "unsubscribed":
                cursor.execute(
                    "UPDATE leads SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (lead_id,),
                )
                conn.commit()
            return lead_id, "Lead ya existente, actualizado"
        
        # Crear nuevo lead
        cursor.execute(
            """
            INSERT INTO leads 
            (email, whatsapp, nombre, slug, keyword, category_id, product_ids, 
             lead_magnet_slug, lead_magnet_title, consentimiento, opt_in_confirmed, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                True,
                True,
                "active",
            ),
        )
        lead_id = cursor.lastrowid
        
        # Registrar evento
        cursor.execute(
            "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
            (
                lead_id,
                "captured",
                json.dumps({
                    "slug": slug,
                    "keyword": landing.get("keyword", ""),
                    "source": "api",
                    "ip": data.get("ip", "")
                }),
            ),
        )
        
        # Crear secuencia de nurturing
        sequence = magnet.get("nurture_sequence", {})
        for day_key, msg_data in sequence.items():
            if not msg_data:
                continue
            day_num = int(day_key.replace("day_", ""))
            subject = msg_data.get("subject", "")
            body = msg_data.get("body", "")
            
            if subject and body:
                cursor.execute(
                    """
                    INSERT INTO nurture_messages (lead_id, day_number, subject, body, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (lead_id, day_num, subject, body, "pending"),
                )
        
        conn.commit()
        
        # Enviar email de bienvenida/dia 0 inmediatamente
        welcome_msg = sequence.get("day_0", {})
        if welcome_msg:
            nombre = data.get("nombre", "").strip()
            body = welcome_msg.get("body", "")
            if nombre:
                body = body.replace("¡Hola!", f"¡Hola {nombre}!")
            body = body.rstrip() + "\n" + lead_magnet_resource_text(magnet, landing)
            
            success, error = send_email(
                to_email=email,
                subject=welcome_msg.get("subject", "Bienvenido a PC MIDI Center"),
                body_text=body,
                unsubscribe_url=unsubscribe_url(email),
            )
            if success:
                cursor.execute(
                    """
                    UPDATE nurture_messages 
                    SET status = 'sent', sent_at = CURRENT_TIMESTAMP 
                    WHERE lead_id = ? AND day_number = 0
                    """,
                    (lead_id,),
                )
                cursor.execute(
                    "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
                    (lead_id, "email_sent", json.dumps({"day": 0, "subject": welcome_msg.get("subject", ""), "auto": True})),
                )
            else:
                cursor.execute(
                    """
                    UPDATE nurture_messages 
                    SET status = 'failed', error_message = ?
                    WHERE lead_id = ? AND day_number = 0
                    """,
                    (error, lead_id),
                )
                cursor.execute(
                    "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
                    (lead_id, "email_failed", json.dumps({"day": 0, "error": error, "auto": True})),
                )
            conn.commit()
        
        return lead_id, "Lead creado exitosamente"
        
    except Exception as e:
        conn.rollback()
        return 0, f"Error: {str(e)}"
    finally:
        conn.close()


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "service": "agente-4-nurture-api",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/leads", methods=["POST"])
def create_lead_endpoint():
    """
    Recibe datos del formulario de una landing.
    
    Body JSON esperado:
    {
        "email": "usuario@ejemplo.com",
        "nombre": "Nombre",
        "whatsapp": "+549...",
        "slug": "controlador-midi-para-fl-studio",
        "consentimiento": true,
        "ip": "opcional"
    }
    """
    try:
        data = request_data()
        if nurture_pg.enabled():
            lead_id, message = nurture_pg.create_lead(data)
            if lead_id == 0:
                return jsonify({"error": message}), 400
            return jsonify({"success": True, "lead_id": lead_id, "message": message}), 201
        
        lead_id, message = create_lead(data)
        
        if lead_id == 0:
            return jsonify({"error": message}), 400
        
        return jsonify({
            "success": True,
            "lead_id": lead_id,
            "message": message
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    """
    Procesa bajas de leads.
    
    Body JSON esperado:
    {
        "email": "usuario@ejemplo.com"
    }
    """
    try:
        data = request.args.to_dict() if request.method == "GET" else request_data()
        email = data.get("email", "").strip().lower()
        token = data.get("token", "").strip()
        if nurture_pg.enabled():
            ok, message = nurture_pg.unsubscribe(email, token)
            if not ok:
                status = 403 if message == "Token invalido" else 400
                return jsonify({"error": message}), status
            return jsonify({"success": True, "message": message})
        
        if not email:
            return jsonify({"error": "Email requerido"}), 400
        if token and not hmac.compare_digest(token, unsubscribe_token(email)):
            return jsonify({"error": "Token invalido"}), 403
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM leads WHERE email = ?", (email,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({"error": "Email no encontrado"}), 404
        
        lead_id = row["id"]
        
        # Marcar como dado de baja
        cursor.execute(
            "UPDATE leads SET status = 'unsubscribed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (lead_id,),
        )
        
        # Cancelar mensajes pendientes
        cursor.execute(
            "UPDATE nurture_messages SET status = 'cancelled' WHERE lead_id = ? AND status = 'pending'",
            (lead_id,),
        )
        
        # Registrar evento
        cursor.execute(
            "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
            (lead_id, "unsubscribed", json.dumps({"source": "api"})),
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Baja procesada correctamente"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/events", methods=["POST"])
def record_event():
    """Registra eventos de comportamiento desde el frontend (clics en CTAs, envíos de formulario)."""
    try:
        data = request_data()
        event_type = str(data.get("event_type", "")).strip()
        slug = str(data.get("slug", "")).strip() or None
        extra = {k: v for k, v in data.items() if k not in {"event_type", "slug"}}
        if nurture_pg.enabled():
            ok, message = nurture_pg.record_page_event(event_type, slug, extra)
            if not ok:
                return jsonify({"error": message}), 400
            return jsonify({"success": True})
        return jsonify({"success": True, "note": "db_not_configured"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Retorna estadísticas del sistema."""
    if nurture_pg.enabled():
        return jsonify(nurture_pg.stats())

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM leads")
    total_leads = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM leads WHERE status = 'active'")
    active_leads = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM leads WHERE status = 'unsubscribed'")
    unsubscribed_leads = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'sent'")
    sent_messages = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'pending'")
    pending_messages = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'failed'")
    failed_messages = cursor.fetchone()["total"]
    
    conn.close()
    
    return jsonify({
        "leads": {
            "total": total_leads,
            "active": active_leads,
            "unsubscribed": unsubscribed_leads
        },
        "messages": {
            "sent": sent_messages,
            "pending": pending_messages,
            "failed": failed_messages
        }
    })


# ─── Dashboard utilities ───────────────────────────────────────────────────────

def _iter_jsonl(path):
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def _tail_jsonl(path, n=50):
    if not path.exists():
        return []
    size = path.stat().st_size
    if size == 0:
        return []
    chunk = min(size, max(n * 4096, 65536))
    with open(path, "rb") as f:
        f.seek(max(0, size - chunk))
        at_start = f.tell() == 0
        raw = f.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    if not at_start and len(lines) > 1:
        lines = lines[1:]
    valid = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            valid.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return valid[-n:]


def _count_jsonl_lines(path):
    if not path.exists():
        return 0
    with open(path, "rb") as f:
        return sum(1 for line in f if line.strip())


def _count_jsonl_where(path, field, value):
    return sum(1 for r in _iter_jsonl(path) if r.get(field) == value)


def _norm_ts(ts):
    if not ts:
        return ""
    if "T" in ts:
        return ts.replace("Z", "+00:00")
    try:
        parts = ts.split("-")
        if len(parts) >= 2:
            d, t = parts[0], parts[1]
            micro = parts[2] if len(parts) > 2 else "000000"
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}.{micro}+00:00"
    except Exception:
        pass
    return ts


def _latest_report(patterns):
    candidates = []
    for pat in patterns:
        candidates.extend(REPORTS_DIR.glob(pat))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.name)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def _count_report_items(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    return 0


def _report_status(raw):
    if raw.get("status"):
        return raw["status"]
    if raw.get("returncode") not in (None, 0):
        return "failed"
    if raw.get("failed", 0):
        return "failed"
    return "ok"


# ─── Dashboard endpoints ────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/dashboard/summary")
def dashboard_summary():
    leads = {"total": 0, "active": 0, "unsubscribed": 0}
    emails = {"sent": 0, "pending": 0, "failed": 0}
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM leads")
        leads["total"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM leads WHERE status='active'")
        leads["active"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM leads WHERE status='unsubscribed'")
        leads["unsubscribed"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nurture_messages WHERE status='sent'")
        emails["sent"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nurture_messages WHERE status='pending'")
        emails["pending"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM nurture_messages WHERE status='failed'")
        emails["failed"] = cur.fetchone()[0]
        conn.close()
    except Exception:
        pass

    posts = {
        "published": _count_jsonl_where(DISTRIBUTION_LOG, "status", "published"),
        "proposed":  _count_jsonl_where(DISTRIBUTION_LOG, "status", "proposed"),
        "blocked":   _count_jsonl_where(DISTRIBUTION_LOG, "status", "blocked"),
    }

    eng_total = _count_jsonl_lines(ENGAGEMENT_LOG)
    eng_dry   = _count_jsonl_where(ENGAGEMENT_LOG, "status", "dry_run")
    engagement = {
        "total":   eng_total,
        "dry_run": eng_dry,
        "live":    eng_total - eng_dry,
    }

    return jsonify({
        "leads":      leads,
        "emails":     emails,
        "posts":      posts,
        "engagement": engagement,
        "geo_audits": {
            "total":      _count_jsonl_lines(GEO_AUDITS_LOG),
            "gaps_found": _count_jsonl_lines(CONTENT_FEEDBACK),
        },
    })


@app.route("/api/dashboard/agents")
def dashboard_agents():
    AGENT_PATTERNS = {
        "nurture":      ["*-nurture-*.json"],
        "conversion":   ["*-conversion-*.json"],
        "distribution": ["*-distribution-*.json"],
        "publicacion":  ["*-publicacion-*.json"],
        "geo_audit":    ["*-geo-audit-*.json"],
        "engagement":   ["*-engage.json", "*-engage-*.json", "*-engagement-*.json"],
    }
    daily = _latest_report(["*-daily.json"])
    daily_steps = {}
    if daily:
        for s in (daily.get("steps") or []):
            daily_steps[s.get("step", "")] = s

    result = {}
    for agent, patterns in AGENT_PATTERNS.items():
        raw = _latest_report(patterns)
        if raw:
            info = {
                "last_run": raw.get("timestamp_utc", ""),
                "status":   _report_status(raw),
                "dry_run":  raw.get("dry_run", False),
            }
            if agent == "nurture":
                r = raw.get("results", {})
                info.update({"sent": r.get("sent", 0), "pending": r.get("pending", 0), "failed": r.get("failed", 0)})
            elif agent == "conversion":
                info.update({
                    "landings_analyzed": raw.get("landings", raw.get("landings_analyzed", 0)),
                    "recommendations":   _count_report_items(raw.get("recommendations")),
                })
            elif agent == "distribution":
                info.update({"pieces_proposed": raw.get("pieces_proposed", 0), "pieces_blocked": raw.get("pieces_blocked", 0)})
            elif agent == "publicacion":
                info.update({"published": raw.get("published", 0), "found": raw.get("found", 0)})
            elif agent == "geo_audit":
                info.update({"audited": _count_jsonl_lines(GEO_AUDITS_LOG), "gaps_found": _count_jsonl_lines(CONTENT_FEEDBACK)})
            elif agent == "engagement":
                info.update({"platform": raw.get("platform", ""), "actions": _count_jsonl_lines(ENGAGEMENT_LOG)})
        else:
            fallback_key = {
                "nurture": "nurture", "conversion": "conversion",
                "distribution": "distribution-generate", "publicacion": "publish",
                "geo_audit": "geo-audit", "engagement": "engagement",
            }.get(agent, agent)
            ds = daily_steps.get(fallback_key, {})
            info = {
                "last_run": ds.get("started_utc", ""),
                "status":   ds.get("status", "unknown"),
                "dry_run":  daily.get("dry_run", False) if daily else False,
            }
        result[agent] = info
    return jsonify(result)


@app.route("/api/dashboard/last-workflow")
def dashboard_last_workflow():
    report = _latest_report(["*-daily.json", "*-weekly.json"])
    if not report:
        return jsonify({})

    def _parse_step_ts(ts):
        if not ts:
            return None
        try:
            return datetime.strptime(ts[:15], "%Y%m%d-%H%M%S")
        except ValueError:
            return None

    for step in (report.get("steps") or []):
        t0 = _parse_step_ts(step.get("started_utc"))
        t1 = _parse_step_ts(step.get("finished_utc"))
        step["duration_seconds"] = round((t1 - t0).total_seconds(), 1) if t0 and t1 else None
    return jsonify(report)


@app.route("/api/dashboard/activity")
def dashboard_activity():
    limit = min(int(request.args.get("limit", 30)), 100)
    items = []

    for rec in _tail_jsonl(ENGAGEMENT_LOG, n=limit):
        items.append({"_source": "engagement", "_ts": _norm_ts(rec.get("ts", "")), **rec})

    for rec in _tail_jsonl(DISTRIBUTION_LOG, n=limit):
        items.append({"_source": "distribution", "_ts": _norm_ts(rec.get("created_at_utc", "")), **rec})

    for rec in _tail_jsonl(GEO_AUDITS_LOG, n=limit):
        light = {k: v for k, v in rec.items() if k != "response_text"}
        items.append({"_source": "geo_audit", "_ts": _norm_ts(rec.get("timestamp_utc", "")), **light})

    for rec in _tail_jsonl(CONTENT_FEEDBACK, n=limit):
        items.append({"_source": "feedback", "_ts": _norm_ts(rec.get("timestamp_utc", "")), **rec})

    items.sort(key=lambda x: x.get("_ts", ""), reverse=True)
    return jsonify(items[:limit])


@app.route("/api/dashboard/geo-summary")
def dashboard_geo_summary():
    entries = _tail_jsonl(GEO_AUDITS_LOG, n=100)
    scores = [e.get("score", 0) for e in entries if "score" in e]
    all_competitors = []
    for e in entries:
        all_competitors.extend(e.get("competitors") or [])

    recent_gaps = list(_tail_jsonl(CONTENT_FEEDBACK, n=5))
    recent_gaps.reverse()

    return jsonify({
        "total_audited":          _count_jsonl_lines(GEO_AUDITS_LOG),
        "pcmidi_mentioned_count": sum(1 for e in entries if e.get("pcmidi_mentioned")),
        "avg_score":              round(sum(scores) / len(scores), 2) if scores else 0.0,
        "top_competitors":        [c for c, _ in Counter(all_competitors).most_common(8)],
        "recent_gaps":            recent_gaps,
    })


if __name__ == "__main__":
    print("API Server iniciado en http://localhost:5000")
    print("Endpoints:")
    print("  GET  /api/health")
    print("  POST /api/leads")
    print("  POST /api/events")
    print("  POST /api/unsubscribe")
    print("  GET  /api/stats")
    print("  GET  /dashboard")
    app.run(host="0.0.0.0", port=5000, debug=False)
