#!/usr/bin/env python3
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib import nurture_pg


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
LANDINGS_PATH = DATA_DIR / "landings_aprobadas.jsonl"
CONTENT_FEEDBACK_PATH = DATA_DIR / "content_feedback.jsonl"
SQLITE_DB_PATH = DATA_DIR / "nurture.db"
SALES_PATH = DATA_DIR / "conversion_sales.jsonl"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = timestamp()
    path = REPORTS_DIR / f"{stamp}-conversion-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido en {path}:{line_no}: {exc}") from exc
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_landings() -> dict[str, dict]:
    return {row.get("slug", ""): row for row in load_jsonl(LANDINGS_PATH) if row.get("slug")}


def feedback_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def load_existing_feedback_keys() -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for row in load_jsonl(CONTENT_FEEDBACK_PATH):
        if row.get("source") == "conversion" and row.get("slug") and row.get("signal"):
            period = str(row.get("period") or row.get("timestamp_utc", "")[:6] or "legacy")
            keys.add((str(row["slug"]), str(row["signal"]), period))
    return keys


def load_sales_by_slug(window_days: int) -> dict[str, dict]:
    sales: dict[str, dict] = {}
    cutoff = datetime.now(timezone.utc).timestamp() - (window_days * 86400)
    for row in load_jsonl(SALES_PATH):
        slug = str(row.get("slug", ""))
        if not slug:
            continue
        created_at = str(row.get("created_at") or row.get("timestamp_utc") or "")
        if created_at:
            try:
                normalized = created_at.replace("Z", "+00:00")
                if datetime.fromisoformat(normalized).timestamp() < cutoff:
                    continue
            except ValueError:
                pass
        item = sales.setdefault(slug, {"sales_count": 0, "revenue": 0.0})
        item["sales_count"] += int(row.get("quantity") or 1)
        item["revenue"] += float(row.get("amount") or row.get("revenue") or 0)
    return sales


def rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def empty_metrics(slug: str, landing: dict) -> dict:
    return {
        "slug": slug,
        "keyword": landing.get("keyword", ""),
        "category": landing.get("primary_category_id", ""),
        "page_views": 0,
        "cta_clicks": 0,
        "form_submits": 0,
        "leads": 0,
        "unsubscribes": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "email_clicks": 0,
        "sales_count": 0,
        "revenue": 0.0,
    }


def load_postgres_metrics(window_days: int) -> list[dict]:
    nurture_pg.init_db()
    landings = load_landings()
    metrics = {slug: empty_metrics(slug, landing) for slug, landing in landings.items()}
    with nurture_pg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT slug, event_type, COUNT(*) AS total
                FROM page_events
                WHERE created_at >= now() - (%s || ' days')::interval
                GROUP BY slug, event_type
                """,
                (window_days,),
            )
            for row in cur.fetchall():
                slug = row.get("slug") or ""
                if slug not in metrics:
                    continue
                event_type = row.get("event_type")
                total = int(row.get("total") or 0)
                if event_type == "page_view":
                    metrics[slug]["page_views"] = total
                elif event_type == "cta_click":
                    metrics[slug]["cta_clicks"] = total
                elif event_type == "form_submit":
                    metrics[slug]["form_submits"] = total
                elif event_type == "email_click":
                    metrics[slug]["email_clicks"] = total

            cur.execute(
                """
                SELECT slug, COUNT(*) AS total,
                       SUM(CASE WHEN status = 'unsubscribed' THEN 1 ELSE 0 END) AS unsubscribes
                FROM leads
                WHERE created_at >= now() - (%s || ' days')::interval
                GROUP BY slug
                """,
                (window_days,),
            )
            for row in cur.fetchall():
                slug = row.get("slug") or ""
                if slug in metrics:
                    metrics[slug]["leads"] = int(row.get("total") or 0)
                    metrics[slug]["unsubscribes"] = int(row.get("unsubscribes") or 0)

            cur.execute(
                """
                SELECT l.slug, e.event_type, COUNT(*) AS total
                FROM lead_events e
                JOIN leads l ON l.id = e.lead_id
                WHERE e.created_at >= now() - (%s || ' days')::interval
                  AND e.event_type IN ('email_sent', 'email_failed', 'email_click')
                GROUP BY l.slug, e.event_type
                """,
                (window_days,),
            )
            for row in cur.fetchall():
                slug = row.get("slug") or ""
                if slug not in metrics:
                    continue
                if row.get("event_type") == "email_sent":
                    metrics[slug]["emails_sent"] = int(row.get("total") or 0)
                elif row.get("event_type") == "email_failed":
                    metrics[slug]["emails_failed"] = int(row.get("total") or 0)
                elif row.get("event_type") == "email_click":
                    metrics[slug]["email_clicks"] = int(row.get("total") or 0)
    return list(metrics.values())


def load_sqlite_metrics(window_days: int) -> list[dict]:
    landings = load_landings()
    metrics = {slug: empty_metrics(slug, landing) for slug, landing in landings.items()}
    if not SQLITE_DB_PATH.exists():
        return list(metrics.values())
    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT slug, COUNT(*) AS total,
               SUM(CASE WHEN status = 'unsubscribed' THEN 1 ELSE 0 END) AS unsubscribes
        FROM leads
        WHERE created_at >= datetime('now', ?)
        GROUP BY slug
        """,
        (f"-{window_days} days",),
    )
    for row in cursor.fetchall():
        slug = row["slug"] or ""
        if slug in metrics:
            metrics[slug]["leads"] = int(row["total"] or 0)
            metrics[slug]["unsubscribes"] = int(row["unsubscribes"] or 0)
    cursor.execute(
        """
        SELECT l.slug, e.event_type, COUNT(*) AS total
        FROM lead_events e
        JOIN leads l ON l.id = e.lead_id
        WHERE e.created_at >= datetime('now', ?)
          AND e.event_type IN ('email_sent', 'email_failed', 'email_click')
        GROUP BY l.slug, e.event_type
        """,
        (f"-{window_days} days",),
    )
    for row in cursor.fetchall():
        slug = row["slug"] or ""
        if slug not in metrics:
            continue
        if row["event_type"] == "email_sent":
            metrics[slug]["emails_sent"] = int(row["total"] or 0)
        elif row["event_type"] == "email_failed":
            metrics[slug]["emails_failed"] = int(row["total"] or 0)
        elif row["event_type"] == "email_click":
            metrics[slug]["email_clicks"] = int(row["total"] or 0)
    conn.close()
    return list(metrics.values())


def enrich_metrics(row: dict, window_days: int) -> dict:
    row = dict(row)
    row["window_days"] = window_days
    row["lead_rate"] = rate(row["leads"], row["page_views"])
    row["cta_rate"] = rate(row["cta_clicks"], row["page_views"])
    row["form_submit_rate"] = rate(row["form_submits"], row["page_views"])
    row["email_failed_rate"] = rate(row["emails_failed"], row["emails_sent"] + row["emails_failed"])
    row["email_click_rate"] = rate(row["email_clicks"], row["emails_sent"])
    row["unsubscribe_rate"] = rate(row["unsubscribes"], row["leads"])
    row["revenue_per_view"] = rate(row["revenue"], row["page_views"])
    return row


def feedback_row(metric: dict, signal: str, priority: str, target_agent: str, recommendation_type: str, suggestion: str) -> dict:
    return {
        "source": "conversion",
        "timestamp_utc": timestamp(),
        "period": feedback_period(),
        "slug": metric["slug"],
        "keyword": metric.get("keyword", ""),
        "category": metric.get("category", ""),
        "signal": signal,
        "priority": priority,
        "target_agent": target_agent,
        "recommendation_type": recommendation_type,
        "suggestion": suggestion,
        "metrics": {
            "window_days": metric["window_days"],
            "page_views": metric["page_views"],
            "cta_clicks": metric["cta_clicks"],
            "form_submits": metric["form_submits"],
            "leads": metric["leads"],
            "lead_rate": metric["lead_rate"],
            "cta_rate": metric["cta_rate"],
            "form_submit_rate": metric["form_submit_rate"],
            "email_failed_rate": metric["email_failed_rate"],
            "email_click_rate": metric["email_click_rate"],
            "unsubscribe_rate": metric["unsubscribe_rate"],
            "email_clicks": metric["email_clicks"],
            "sales_count": metric["sales_count"],
            "revenue": metric["revenue"],
        },
        "status": "new",
    }


def build_recommendations(metrics: list[dict], min_views: int, limit: int) -> list[dict]:
    existing = load_existing_feedback_keys()
    recommendations: list[dict] = []
    for metric in sorted(metrics, key=lambda row: (row["page_views"], row["leads"], row["cta_clicks"]), reverse=True):
        rows: list[dict] = []
        keyword = metric.get("keyword") or metric["slug"]
        if metric["page_views"] >= min_views and metric["lead_rate"] < 0.01:
            rows.append(feedback_row(
                metric,
                "high_traffic_low_capture",
                "high",
                "agent_2",
                "lead_magnet_update",
                f"Revisar la captura de la landing '{keyword}': tiene trafico suficiente y baja tasa de leads. Probar un lead magnet mas especifico, CTA de formulario mas claro y copy de valor antes del formulario.",
            ))
        if metric["page_views"] >= min_views and metric["cta_rate"] < 0.02:
            rows.append(feedback_row(
                metric,
                "low_commercial_click_rate",
                "medium",
                "agent_2",
                "cta_update",
                f"Mejorar CTAs comerciales para '{keyword}': reforzar el puente entre criterios de compra y categorias reales de PC MIDI sin afirmar stock, precio ni disponibilidad.",
            ))
        if metric["leads"] >= 5 and metric["cta_clicks"] < metric["leads"]:
            rows.append(feedback_row(
                metric,
                "leads_low_commercial_intent",
                "medium",
                "agent_3",
                "nurture_sequence_update",
                f"La landing '{keyword}' genera leads pero pocos clicks comerciales. Ajustar dia 3 y dia 5 para conectar el recurso con categorias relevantes y comparacion de opciones.",
            ))
        if metric["emails_failed"] >= 3 and metric["email_failed_rate"] >= 0.1:
            rows.append(feedback_row(
                metric,
                "email_delivery_issue",
                "high",
                "agent_3",
                "email_delivery_check",
                f"Revisar entrega de emails para '{keyword}': hay fallos de envio relevantes en la ventana analizada.",
            ))
        if metric["leads"] >= 10 and metric["unsubscribe_rate"] >= 0.1:
            rows.append(feedback_row(
                metric,
                "high_unsubscribe_rate",
                "high",
                "agent_3",
                "nurture_sequence_update",
                f"Reducir friccion en nurturing para '{keyword}': la tasa de bajas es alta. Suavizar tono comercial y aumentar utilidad tecnica de la secuencia.",
            ))
        if metric["page_views"] >= min_views and metric["lead_rate"] >= 0.03 and metric["cta_rate"] >= 0.05:
            rows.append(feedback_row(
                metric,
                "strong_conversion_pattern",
                "medium",
                "agent_1",
                "new_opportunity",
                f"Usar '{keyword}' como patron ganador: proponer variaciones cercanas por caso de uso, DAW, espacio o tipo de comprador manteniendo categorias reales.",
            ))

        for row in rows:
            key = (row["slug"], row["signal"], row["period"])
            if key in existing:
                continue
            recommendations.append(row)
            existing.add(key)
            if len(recommendations) >= limit:
                return recommendations
    return recommendations


def run(args: argparse.Namespace) -> int:
    database = "postgres" if nurture_pg.enabled() else "sqlite"
    raw_metrics = load_postgres_metrics(args.window_days) if nurture_pg.enabled() else load_sqlite_metrics(args.window_days)
    sales = load_sales_by_slug(args.window_days)
    for row in raw_metrics:
        sale = sales.get(row["slug"], {})
        row["sales_count"] = int(sale.get("sales_count") or 0)
        row["revenue"] = float(sale.get("revenue") or 0.0)
    metrics = [enrich_metrics(row, args.window_days) for row in raw_metrics]
    active_metrics = [row for row in metrics if row["page_views"] or row["leads"] or row["cta_clicks"] or row["emails_sent"] or row["emails_failed"] or row["sales_count"]]
    recommendations = build_recommendations(active_metrics, args.min_views, args.limit)
    if not args.dry_run:
        append_jsonl(CONTENT_FEEDBACK_PATH, recommendations)
    report_path = write_report("run", {
        "command": "run",
        "database": database,
        "dry_run": args.dry_run,
        "window_days": args.window_days,
        "min_views": args.min_views,
        "landings_analyzed": len(metrics),
        "landings_with_activity": len(active_metrics),
        "recommendations": len(recommendations),
        "sales_file_exists": SALES_PATH.exists(),
        "written_to_feedback": 0 if args.dry_run else len(recommendations),
        "top_metrics": active_metrics[:20],
    })
    print(f"conversion: analizadas {len(metrics)} landings ({len(active_metrics)} con actividad)")
    print(f"conversion: recomendaciones {'simuladas' if args.dry_run else 'guardadas'}: {len(recommendations)}")
    print(f"conversion: reporte en {report_path}")
    return 0


def status() -> int:
    database = "postgres" if nurture_pg.enabled() else "sqlite"
    if nurture_pg.enabled():
        stats = nurture_pg.stats()
    elif SQLITE_DB_PATH.exists():
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM leads")
        leads = int(cursor.fetchone()["total"] or 0)
        cursor.execute("SELECT COUNT(*) AS total FROM lead_events")
        events = int(cursor.fetchone()["total"] or 0)
        conn.close()
        stats = {"leads": {"total": leads}, "events": {"total": events}}
    else:
        stats = {"leads": {"total": 0}, "events": {"total": 0}}
    report_path = write_report("status", {"command": "status", "database": database, "stats": stats})
    print(f"conversion: database={database}")
    print(f"conversion: reporte en {report_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente 6: Auditor De Conversion")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--window-days", type=int, default=30)
    run_parser.add_argument("--min-views", type=int, default=50)
    run_parser.add_argument("--limit", type=int, default=50)
    run_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "run":
        raise SystemExit(run(args))
    if args.command == "status":
        raise SystemExit(status())
    raise SystemExit(f"conversion: comando no soportado: {args.command}")


if __name__ == "__main__":
    main()
