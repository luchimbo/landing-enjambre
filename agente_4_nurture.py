#!/usr/bin/env python3
"""
Agente 4: Asesor Invisible / Lead Nurturing

Responsabilidades:
- Capturar leads desde formularios de landings
- Guardar en base de datos (SQLite para dev, PostgreSQL para prod)
- Crear mensajes pendientes de nutrición (día 0, 3, 5)
- Enviar emails con secuencia de nurturing
- Registrar eventos (envíos, clicks, bajas, errores)
- Alimentar al Agente 7 (Auditor de Conversión)

Uso:
    python agente_4_nurture.py process [--limit N] [--dry-run]
    python agente_4_nurture.py capture [--limit N] [--dry-run]
    python agente_4_nurture.py status
    python agente_4_nurture.py init-db
"""

import argparse
import hmac
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Importar mailer desde lib/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.mailer import send_email
from lib import nurture_pg

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
DB_PATH = DATA_DIR / "nurture.db"
LEAD_MAGNETS_FILE = DATA_DIR / "lead_magnets.jsonl"
LANDINGS_FILE = DATA_DIR / "landings_aprobadas.jsonl"

# Cargar variables de entorno desde .env si existe
ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

UNSUBSCRIBE_BASE_URL = os.getenv("NURTURE_UNSUBSCRIBE_BASE_URL", "").strip()


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timestamp()
    path = REPORTS_DIR / f"{stamp}-nurture-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def get_db_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email or ""))


def unsubscribe_token(email: str) -> str:
    secret = os.getenv("NURTURE_UNSUBSCRIBE_SECRET") or os.getenv("NURTURE_SMTP_PASS", "")
    return hmac.new(secret.encode("utf-8"), email.lower().encode("utf-8"), hashlib.sha256).hexdigest()


def unsubscribe_url(email: str) -> str:
    if not UNSUBSCRIBE_BASE_URL:
        return ""
    return f"{UNSUBSCRIBE_BASE_URL.rstrip('/')}?email={email.lower()}&token={unsubscribe_token(email)}"


def init_db() -> None:
    """Crea tablas si no existen."""
    if nurture_pg.enabled():
        nurture_pg.init_db()
        print("nurture: Base de datos PostgreSQL inicializada")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            whatsapp TEXT,
            nombre TEXT,
            slug TEXT NOT NULL,
            keyword TEXT,
            category_id TEXT,
            product_ids TEXT,
            lead_magnet_slug TEXT,
            lead_magnet_title TEXT,
            consentimiento BOOLEAN NOT NULL DEFAULT 0,
            opt_in_confirmed BOOLEAN NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS nurture_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            day_number INTEGER NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            sent_at TIMESTAMP,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            last_retry TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lead_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_nurture_status ON nurture_messages(status);
        CREATE INDEX IF NOT EXISTS idx_nurture_lead_day ON nurture_messages(lead_id, day_number);
        CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id);
        CREATE INDEX IF NOT EXISTS idx_events_type ON lead_events(event_type);
        """
    )

    # Migraciones livianas para bases existentes.
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(nurture_messages)").fetchall()}
    if "retry_count" not in existing_columns:
        cursor.execute("ALTER TABLE nurture_messages ADD COLUMN retry_count INTEGER DEFAULT 0")
    if "last_retry" not in existing_columns:
        cursor.execute("ALTER TABLE nurture_messages ADD COLUMN last_retry TIMESTAMP")

    conn.commit()
    conn.close()
    print(f"nurture: Base de datos inicializada en {DB_PATH}")


def load_lead_magnets() -> dict[str, dict]:
    """Carga lead_magnets.jsonl en un dict indexado por slug."""
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
    """Carga landings_aprobadas.jsonl en un dict indexado por slug."""
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


def create_lead(
    email: str,
    slug: str,
    whatsapp: str = "",
    nombre: str = "",
    keyword: str = "",
    category_id: str = "",
    product_ids: str = "",
    lead_magnet_slug: str = "",
    lead_magnet_title: str = "",
    consentimiento: bool = False,
) -> int:
    """Crea un lead y retorna su ID."""
    email = email.strip().lower()
    if not validate_email(email) or not consentimiento:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO leads 
            (email, whatsapp, nombre, slug, keyword, category_id, product_ids, 
             lead_magnet_slug, lead_magnet_title, consentimiento, opt_in_confirmed, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                whatsapp,
                nombre,
                slug,
                keyword,
                category_id,
                product_ids,
                lead_magnet_slug,
                lead_magnet_title,
                consentimiento,
                consentimiento,
                "active",
            ),
        )
        lead_id = cursor.lastrowid
        conn.commit()

        # Registrar evento de captura
        cursor.execute(
            "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
            (
                lead_id,
                "captured",
                json.dumps({"slug": slug, "keyword": keyword, "source": "landing_form"}),
            ),
        )
        conn.commit()

        return lead_id
    except sqlite3.IntegrityError:
        # Email ya existe, retornar el existente
        cursor.execute("SELECT id FROM leads WHERE email = ?", (email,))
        row = cursor.fetchone()
        return row["id"] if row else 0
    finally:
        conn.close()


def create_nurture_sequence(lead_id: int, lead_magnet: dict, landing: dict) -> None:
    """Crea los mensajes de nurturing para un lead."""
    sequence = lead_magnet.get("nurture_sequence", {})
    if not sequence:
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    for day_key, msg_data in sequence.items():
        if not msg_data:
            continue
        day_num = int(day_key.replace("day_", ""))
        subject = msg_data.get("subject", "")
        body = msg_data.get("body", "")

        if not subject or not body:
            continue

        # Verificar si ya existe
        cursor.execute(
            "SELECT id FROM nurture_messages WHERE lead_id = ? AND day_number = ?",
            (lead_id, day_num),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            INSERT INTO nurture_messages (lead_id, day_number, subject, body, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, day_num, subject, body, "pending"),
        )

    conn.commit()
    conn.close()


def retry_failed_messages(limit: int = 20, dry_run: bool = False) -> dict[str, Any]:
    """Reintenta enviar mensajes fallidos (max 3 reintentos)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT m.id, m.lead_id, m.day_number, m.subject, m.body,
               l.email, l.nombre
        FROM nurture_messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE m.status = 'failed'
          AND l.status = 'active'
          AND (m.retry_count IS NULL OR m.retry_count < 3)
          AND (m.last_retry IS NULL OR 
               datetime(m.last_retry, '+1 hour') <= datetime('now'))
        ORDER BY m.lead_id, m.day_number
        LIMIT ?
        """,
        (limit,),
    )
    
    messages = cursor.fetchall()
    results = {"processed": 0, "sent": 0, "failed": 0}
    
    for msg in messages:
        msg_id = msg["id"]
        lead_id = msg["lead_id"]
        day_num = msg["day_number"]
        
        results["processed"] += 1
        
        nombre = msg["nombre"] or ""
        subject = msg["subject"]
        body = msg["body"]
        
        if nombre:
            body = body.replace("¡Hola!", f"¡Hola {nombre}!")
            body = body.replace("Hola de nuevo", f"Hola de nuevo {nombre}")
        
        success, error = send_email(
            to_email=msg["email"],
            subject=subject,
            body_text=body,
            dry_run=dry_run,
            unsubscribe_url=unsubscribe_url(msg["email"]),
        )
        
        if success and not dry_run:
            cursor.execute(
                """
                UPDATE nurture_messages 
                SET status = 'sent', sent_at = CURRENT_TIMESTAMP, retry_count = COALESCE(retry_count, 0) + 1
                WHERE id = ?
                """,
                (msg_id,),
            )
            cursor.execute(
                "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
                (lead_id, "email_sent", json.dumps({"day": day_num, "subject": subject, "retry": True})),
            )
            conn.commit()
            results["sent"] += 1
            print(f"  [OK-RETRY] Enviado dia {day_num} a {msg['email']}: {subject}")
        elif not dry_run:
            cursor.execute(
                """
                UPDATE nurture_messages 
                SET retry_count = COALESCE(retry_count, 0) + 1, 
                    last_retry = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
                """,
                (error, msg_id),
            )
            conn.commit()
            results["failed"] += 1
            print(f"  [FAIL-RETRY] Fallo dia {day_num} a {msg['email']}: {error}")
    
    conn.close()
    return results


def process_pending_messages(limit: int = 50, dry_run: bool = False) -> dict[str, Any]:
    """Procesa mensajes pendientes de nurturing que deben enviarse hoy."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Calcular fechas de envío según día de creación del lead
    now = datetime.now(timezone.utc)

    cursor.execute(
        """
        SELECT m.id, m.lead_id, m.day_number, m.subject, m.body,
               l.email, l.nombre, l.slug, l.created_at, l.status as lead_status
        FROM nurture_messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE m.status = 'pending'
          AND l.status = 'active'
          AND l.opt_in_confirmed = 1
        ORDER BY m.lead_id, m.day_number
        LIMIT ?
        """,
        (limit,),
    )

    messages = cursor.fetchall()
    results = {
        "processed": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }

    for msg in messages:
        msg_id = msg["id"]
        lead_id = msg["lead_id"]
        day_num = msg["day_number"]
        lead_created_str = msg["created_at"]
        if lead_created_str.endswith("Z"):
            lead_created_str = lead_created_str[:-1] + "+00:00"
        lead_created = datetime.fromisoformat(lead_created_str)
        if lead_created.tzinfo is None:
            lead_created = lead_created.replace(tzinfo=timezone.utc)

        # Verificar si ya es tiempo de enviar
        scheduled_date = lead_created + timedelta(days=day_num)
        if now < scheduled_date:
            results["skipped"] += 1
            continue

        results["processed"] += 1

        # Preparar personalización
        nombre = msg["nombre"] or ""
        subject = msg["subject"]
        body = msg["body"]

        if nombre:
            body = body.replace("¡Hola!", f"¡Hola {nombre}!")
            body = body.replace("Hola de nuevo", f"Hola de nuevo {nombre}")

        success, error = send_email(
            to_email=msg["email"],
            subject=subject,
            body_text=body,
            dry_run=dry_run,
            unsubscribe_url=unsubscribe_url(msg["email"]),
        )

        if success:
            if not dry_run:
                cursor.execute(
                    """
                    UPDATE nurture_messages 
                    SET status = 'sent', sent_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                    """,
                    (msg_id,),
                )
                cursor.execute(
                    "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
                    (
                        lead_id,
                        "email_sent",
                        json.dumps({"day": day_num, "subject": subject}),
                    ),
                )
                conn.commit()
            results["sent"] += 1
            print(f"  [OK] Enviado dia {day_num} a {msg['email']}: {subject}")
        else:
            if not dry_run:
                cursor.execute(
                    """
                    UPDATE nurture_messages 
                    SET status = 'failed', error_message = ? 
                    WHERE id = ?
                    """,
                    (error, msg_id),
                )
                cursor.execute(
                    "INSERT INTO lead_events (lead_id, event_type, event_data) VALUES (?, ?, ?)",
                    (
                        lead_id,
                        "email_failed",
                        json.dumps({"day": day_num, "error": error}),
                    ),
                )
                conn.commit()
            results["failed"] += 1
            results["errors"].append({"lead_id": lead_id, "email": msg["email"], "error": error})
            print(f"  [FAIL] Fallo dia {day_num} a {msg['email']}: {error}")

    conn.close()
    return results


def capture_new_leads(limit: int = 100, dry_run: bool = False) -> dict[str, Any]:
    """
    Simula captura de leads desde formularios.
    En producción, esto leería desde una API o webhook.
    """
    # Por ahora, solo verificamos que las tablas existan
    # En una implementación real, leeríamos desde una cola de formularios
    print("nurture: capture_new_leads - en una implementación real leería formularios pendientes")
    return {"captured": 0, "note": "Implementar integración con API de formularios"}


def show_status() -> dict[str, Any]:
    """Muestra estado actual de leads y mensajes."""
    if nurture_pg.enabled():
        pg_stats = nurture_pg.stats()
        status = {
            "leads_total": pg_stats["leads"]["total"],
            "leads_active": pg_stats["leads"]["active"],
            "messages_pending": pg_stats["messages"]["pending"],
            "messages_sent": pg_stats["messages"]["sent"],
            "messages_failed": pg_stats["messages"]["failed"],
        }
        print("\n=== ESTADO DEL SISTEMA DE NURTURING (POSTGRES) ===")
        print(f"Leads totales: {status['leads_total']}")
        print(f"Leads activos: {status['leads_active']}")
        print(f"  Pendientes: {status['messages_pending']}")
        print(f"  Enviados: {status['messages_sent']}")
        print(f"  Fallidos: {status['messages_failed']}")
        print("=================================================\n")
        return status

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM leads")
    total_leads = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM leads WHERE status = 'active'")
    active_leads = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages")
    total_messages = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'pending'")
    pending_messages = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'sent'")
    sent_messages = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM nurture_messages WHERE status = 'failed'")
    failed_messages = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM lead_events")
    total_events = cursor.fetchone()["total"]

    conn.close()

    status = {
        "leads_total": total_leads,
        "leads_active": active_leads,
        "messages_total": total_messages,
        "messages_pending": pending_messages,
        "messages_sent": sent_messages,
        "messages_failed": failed_messages,
        "events_total": total_events,
    }

    print("\n=== ESTADO DEL SISTEMA DE NURTURING ===")
    print(f"Leads totales: {total_leads}")
    print(f"Leads activos: {active_leads}")
    print(f"Mensajes totales: {total_messages}")
    print(f"  Pendientes: {pending_messages}")
    print(f"  Enviados: {sent_messages}")
    print(f"  Fallidos: {failed_messages}")
    print(f"Eventos registrados: {total_events}")
    print("========================================\n")

    return status


def process_command(args: argparse.Namespace) -> int:
    """Procesa mensajes pendientes de nurturing."""
    print(f"nurture: Procesando mensajes pendientes (limit={args.limit}, dry_run={args.dry_run})")

    if nurture_pg.enabled():
        nurture_pg.init_db()
        results = nurture_pg.process_pending(limit=args.limit, dry_run=args.dry_run)
        if args.retry and not args.dry_run:
            retry_results = nurture_pg.retry_failed(limit=20, dry_run=args.dry_run)
            results["retry_processed"] = retry_results["processed"]
            results["retry_sent"] = retry_results["sent"]
            results["retry_failed"] = retry_results["failed"]
        report_path = write_report("process", {"command": "process", "database": "postgres", "dry_run": args.dry_run, "limit": args.limit, "results": results})
        print(f"nurture: Procesados {results['processed']} mensajes")
        print(f"  Enviados: {results['sent']}")
        print(f"  Fallidos: {results['failed']}")
        print(f"Reporte: {report_path}")
        return 0

    if not DB_PATH.exists():
        print("nurture: Base de datos no existe. Ejecutar 'init-db' primero.")
        return 1

    results = process_pending_messages(limit=args.limit, dry_run=args.dry_run)
    
    # Reintentar fallidos si se solicita
    if args.retry and not args.dry_run:
        print("nurture: Reintentando mensajes fallidos...")
        retry_results = retry_failed_messages(limit=20, dry_run=args.dry_run)
        results["retry_processed"] = retry_results["processed"]
        results["retry_sent"] = retry_results["sent"]
        results["retry_failed"] = retry_results["failed"]
        print(f"  Reintentados: {retry_results['processed']}")
        print(f"  Enviados en retry: {retry_results['sent']}")
        print(f"  Fallidos en retry: {retry_results['failed']}")

    # Exportar métricas automáticamente
    if not args.dry_run:
        export_metrics()

    report_path = write_report(
        "process",
        {
            "command": "process",
            "dry_run": args.dry_run,
            "limit": args.limit,
            "results": results,
        },
    )

    print(f"nurture: Procesados {results['processed']} mensajes")
    print(f"  Enviados: {results['sent']}")
    print(f"  Fallidos: {results['failed']}")
    print(f"  Saltados: {results['skipped']}")
    print(f"Reporte: {report_path}")

    return 0


def export_metrics() -> dict[str, Any]:
    """Exporta métricas para el Agente 6 (Auditor de Conversión)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Métricas por landing
    cursor.execute(
        """
        SELECT 
            l.slug,
            COUNT(*) as total_leads,
            SUM(CASE WHEN l.status = 'active' THEN 1 ELSE 0 END) as active_leads,
            SUM(CASE WHEN l.status = 'unsubscribed' THEN 1 ELSE 0 END) as unsubscribed_leads
        FROM leads l
        GROUP BY l.slug
        """
    )
    landing_stats = [dict(row) for row in cursor.fetchall()]
    
    # Métricas de emails
    cursor.execute(
        """
        SELECT 
            m.day_number,
            COUNT(*) as total,
            SUM(CASE WHEN m.status = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN m.status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN m.status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM nurture_messages m
        GROUP BY m.day_number
        """
    )
    email_stats = [dict(row) for row in cursor.fetchall()]
    
    # Eventos recientes (últimos 7 días)
    cursor.execute(
        """
        SELECT 
            event_type,
            COUNT(*) as count
        FROM lead_events
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY event_type
        """
    )
    recent_events = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "landings": landing_stats,
        "emails": email_stats,
        "recent_events": recent_events,
    }
    
    # Guardar en archivo para el Agente 6
    metrics_file = DATA_DIR / "nurture_metrics.json"
    metrics_file.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    
    return metrics


def export_command(args: argparse.Namespace) -> int:
    """Exporta métricas para el Agente 6."""
    if not DB_PATH.exists():
        print("nurture: Base de datos no existe.")
        return 1
    
    metrics = export_metrics()
    print("nurture: Métricas exportadas")
    print(f"  Landings: {len(metrics['landings'])}")
    print(f"  Días de secuencia: {len(metrics['emails'])}")
    print(f"  Eventos recientes: {len(metrics['recent_events'])}")
    print(f"Archivo: {DATA_DIR / 'nurture_metrics.json'}")
    
    return 0


def capture_command(args: argparse.Namespace) -> int:
    """Captura nuevos leads."""
    print(f"nurture: Capturando leads (limit={args.limit}, dry_run={args.dry_run})")

    if not DB_PATH.exists():
        print("nurture: Base de datos no existe. Ejecutar 'init-db' primero.")
        return 1

    results = capture_new_leads(limit=args.limit, dry_run=args.dry_run)

    report_path = write_report(
        "capture",
        {
            "command": "capture",
            "dry_run": args.dry_run,
            "limit": args.limit,
            "results": results,
        },
    )

    print(f"nurture: Leads capturados: {results['captured']}")
    print(f"Reporte: {report_path}")

    return 0


def status_command(args: argparse.Namespace) -> int:
    """Muestra estado del sistema."""
    if not DB_PATH.exists():
        print("nurture: Base de datos no existe.")
        return 1

    show_status()
    return 0


def init_db_command(args: argparse.Namespace) -> int:
    """Inicializa la base de datos."""
    init_db()
    return 0


def add_test_lead_command(args: argparse.Namespace) -> int:
    """Agrega un lead de prueba para testing."""
    if not DB_PATH.exists():
        print("nurture: Base de datos no existe. Ejecutar 'init-db' primero.")
        return 1

    magnets = load_lead_magnets()
    landings = load_landings()

    # Usar primera landing como ejemplo
    test_slug = args.slug or "controlador-midi-para-fl-studio"
    test_email = args.email or "test@example.com"

    if test_slug not in landings:
        print(f"nurture: Landing '{test_slug}' no encontrada")
        return 1

    landing = landings[test_slug]
    magnet = magnets.get(test_slug, {})

    lead_id = create_lead(
        email=test_email,
        slug=test_slug,
        nombre="Test User",
        keyword=landing.get("keyword", ""),
        category_id=landing.get("primary_category_id", ""),
        product_ids=json.dumps(landing.get("product_ids", [])),
        lead_magnet_slug=test_slug,
        lead_magnet_title=magnet.get("title", ""),
        consentimiento=True,
    )

    if lead_id:
        create_nurture_sequence(lead_id, magnet, landing)
        print(f"nurture: Lead de prueba creado (ID: {lead_id}) para '{test_slug}'")
        print(f"  Email: {test_email}")

        # Mostrar mensajes creados
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT day_number, subject FROM nurture_messages WHERE lead_id = ? ORDER BY day_number",
            (lead_id,),
        )
        for row in cursor.fetchall():
            print(f"  Día {row['day_number']}: {row['subject']}")
        conn.close()
    else:
        print(f"nurture: Lead ya existe o error al crear")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente 4: Asesor Invisible / Lead Nurturing")
    sub = parser.add_subparsers(dest="command", required=True)

    # process
    process_parser = sub.add_parser("process", help="Procesa mensajes pendientes de nurturing")
    process_parser.add_argument("--limit", type=int, default=50, help="Máximo de mensajes a procesar")
    process_parser.add_argument("--dry-run", action="store_true", help="Simula sin enviar emails")
    process_parser.add_argument("--retry", action="store_true", help="También reintenta mensajes fallidos")

    # capture
    capture_parser = sub.add_parser("capture", help="Captura nuevos leads desde formularios")
    capture_parser.add_argument("--limit", type=int, default=100, help="Máximo de leads a capturar")
    capture_parser.add_argument("--dry-run", action="store_true", help="Simula sin guardar")

    # status
    sub.add_parser("status", help="Muestra estado del sistema")

    # init-db
    sub.add_parser("init-db", help="Inicializa la base de datos")

    # export
    sub.add_parser("export", help="Exporta métricas para el Agente 6")

    # add-test-lead
    test_parser = sub.add_parser("add-test-lead", help="Agrega un lead de prueba")
    test_parser.add_argument("--email", default="", help="Email del lead de prueba")
    test_parser.add_argument("--slug", default="", help="Slug de la landing")

    args = parser.parse_args()

    commands = {
        "process": process_command,
        "capture": capture_command,
        "status": status_command,
        "init-db": init_db_command,
        "export": export_command,
        "add-test-lead": add_test_lead_command,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
