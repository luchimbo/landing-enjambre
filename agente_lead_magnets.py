import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
LEAD_MAGNETS_PATH = DATA_DIR / "lead_magnets.jsonl"
LANDINGS_PATH = DATA_DIR / "landings_aprobadas.jsonl"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

FORBIDDEN_CLAIMS = [
    "stock garantizado",
    "disponibilidad garantizada",
    "distribuidor oficial",
    "soporte tecnico oficial",
    "soporte técnico oficial",
    "canal oficial",
    "exclusividad",
    "reparaciones",
    "alquileres",
    "clases formales",
    "grabacion, mezcla o mastering",
    "grabación, mezcla o mastering",
    "precio",
    "precios",
]


def load_landings() -> list[dict]:
    landings = []
    if not LANDINGS_PATH.exists():
        return landings
    for line_no, line in enumerate(LANDINGS_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            landings.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalido en {LANDINGS_PATH}:{line_no}: {exc}") from exc
    return landings


def load_jsonl(path: Path) -> list[dict]:
    rows = []
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def extract_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("La IA no devolvio un objeto JSON")
    return json.loads(text[start : end + 1])


def chat_json(system: str, user: str, model: str, temperature: float = 0.35) -> dict:
    load_env()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENROUTER_API_KEY en .env o variables de entorno")
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://www.pcmidi.com.ar/",
            "X-Title": "PC MIDI Lead Magnet Generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Error OpenRouter {exc.code}: {detail}") from exc
    content = data["choices"][0]["message"]["content"]
    return extract_json_object(content)


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = REPORTS_DIR / f"{stamp}-lead-magnet-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def validate_lead_magnet(magnet: dict, landing: dict) -> list[str]:
    errors = []
    required = ["title", "description", "cta_text", "resource_type"]
    for field in required:
        if not magnet.get(field):
            errors.append(f"falta {field}")
    
    valid_types = {"checklist", "guia breve", "plantilla", "preset", "comparativa", "configuracion", "script", "mapa de decision"}
    if magnet.get("resource_type") not in valid_types:
        errors.append(f"resource_type invalido: {magnet.get('resource_type')}")
    
    text = json.dumps(magnet, ensure_ascii=False).lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim.lower() in text:
            errors.append(f"claim prohibido detectado: {claim}")
    
    return errors


def generation_prompt(landing: dict) -> tuple[str, str]:
    system = """Sos especialista en marketing de conversion para PC MIDI Center, una tienda de tecnologia para produccion musical en Argentina.

Debes crear lead magnets (recursos descargables/entregables) que aumenten la captura de emails en landings de guias de compra.

Reglas:
- El recurso debe ser REALISTA y especifico para la busqueda de la landing
- NO prometas archivos, presets, scripts o plantillas que no se puedan entregar
- NO afirmes stock, precios, disponibilidad, distribuidor oficial, soporte tecnico, exclusividad
- El recurso debe ser util genuinamente para quien esta investigando antes de comprar
- Devolve SOLO JSON valido, sin markdown ni explicaciones

Tipos de recursos permitidos:
- checklist: lista de verificacion para elegir/comprar/configurar
- guia breve: PDF corto con pasos concretos  
- plantilla: tabla o esquema para completar
- comparativa: tabla comparativa de opciones
- configuracion: pasos para configurar algo
- script: guion de preguntas o proceso
- mapa de decision: diagrama de flujo de decision

La secuencia de nutricion debe aportar valor real y mantener relacion directa con la intencion original.

Tono y estilo de los emails (MUY IMPORTANTE):
- Escribi como una persona real de Argentina que sabe del tema, no como un folleto de marketing.
- Usa voseo natural (tenes, queres, mira, fijate, proba), sin sonar forzado.
- Evita frases vacias de marketing tipo "opciones reales", "segun tu caso de uso", "lleva tu sonido al siguiente nivel", "no te lo podes perder".
- Nada de urgencia falsa ni venta agresiva. El objetivo es ayudar a decidir, no presionar.
- Frases cortas y directas. Que se lea como un mensaje util de alguien que te quiere dar una mano.
- El cierre hacia productos debe ser una invitacion suave y honesta a mirar opciones, no un grito de venta."""

    user = f"""Landing:
- keyword: {landing.get('keyword', '')}
- intencion: {landing.get('intent', '')}
- categoria principal: {landing.get('primary_category_id', '')}
- productos mencionados: {landing.get('product_ids', [])}
- H1: {landing.get('h1', '')}

Genera un lead magnet JSON con exactamente esta forma:
{{
  "title": "nombre especifico y atractivo del recurso (max 60 caracteres)",
  "description": "promesa concreta de que resuelve el recurso (1-2 frases, max 160 caracteres)",
  "cta_text": "texto del boton de captura (ej: Descargar checklist, Recibir guia, etc.)",
  "resource_type": "checklist|guia breve|plantilla|preset|comparativa|configuracion|script|mapa de decision",
  "delivery_subject": "asunto del email de entrega (dia 0)",
  "nurture_sequence": {{
    "day_0": {{
      "subject": "asunto del email",
      "body": "cuerpo del email que entrega el recurso (2-3 parrafos maximo, voseo natural, calido y sin sonar a marketing)"
    }},
    "day_3": {{
      "subject": "asunto del email",
      "body": "tip tecnico util relacionado con la busqueda (2-3 parrafos, voseo natural, sin venta agresiva ni frases hechas)"
    }},
    "day_5": {{
      "subject": "asunto del email",
      "body": "cierre suave hacia categorias o productos relevantes (2-3 parrafos, voseo natural, invitando con honestidad a mirar opciones en pcmidi.com.ar sin presionar)"
    }}
  }},
  "form_fields": ["email", "nombre_opcional"],
  "value_proposition": "por que alguien dejaria su email por esto (1 frase)"
}}

Ejemplos de buenos titles por tipo:
- checklist: "Checklist: 7 puntos antes de comprar tu primera interfaz de audio"
- guia breve: "Guia: Como configurar tu controlador MIDI en 10 minutos"
- comparativa: "Tabla comparativa: Microfonos USB vs XLR para podcast"
- configuracion: "Pasos para calibrar monitores de estudio en cuartos chicos"
- mapa de decision: "Mapa: Que controlador MIDI conviene segun tu DAW"

El recurso debe ser algo que PC MIDI Center PUEDA realmente entregar como PDF, email o pagina web."""
    return system, user


def generate_lead_magnets(limit: int, model: str, dry_run: bool = False) -> dict:
    started_at = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    
    landings = load_landings()
    existing_magnets = load_jsonl(LEAD_MAGNETS_PATH)
    existing_slugs = {item.get("slug") for item in existing_magnets}
    
    created = 0
    created_items = []
    skipped_items = []
    blocked_items = []
    processed = 0
    
    for landing in landings:
        if created >= limit:
            break
            
        slug = landing.get("slug", "")
        processed += 1
        
        if slug in existing_slugs:
            skipped = {"slug": slug, "reason": "already_exists"}
            skipped_items.append(skipped)
            continue
            
        # Solo generar lead magnet para landings con intencion de compra o comparacion
        intent = landing.get("intent", "").lower()
        keyword = landing.get("keyword", "").lower()
        
        # Filtrar landings que no tienen sentido para captura
        skip_keywords = {"gratis", "descargar", "torrent", "crack", "hackear"}
        if any(kw in keyword for kw in skip_keywords):
            skipped = {"slug": slug, "reason": "inappropriate_keyword"}
            skipped_items.append(skipped)
            continue
            
        try:
            system, user = generation_prompt(landing)
            magnet = chat_json(system, user, model=model, temperature=0.4)
        except Exception as exc:
            blocked = {"slug": slug, "reason": "generation_error", "error": str(exc)}
            blocked_items.append(blocked)
            continue
            
        # Validar
        errors = validate_lead_magnet(magnet, landing)
        if errors:
            blocked = {"slug": slug, "reason": "validation_error", "errors": errors}
            blocked_items.append(blocked)
            continue
            
        # Guardar
        record = {
            "slug": slug,
            "keyword": landing.get("keyword", ""),
            "lead_magnet": magnet,
            "run_id": run_id,
        }
        
        if not dry_run:
            append_jsonl(LEAD_MAGNETS_PATH, [record])
            
        created += 1
        created_items.append({"slug": slug, "title": magnet.get("title", "")})
        print(f"Lead magnet generado: {slug} - {magnet.get('title', '')}")
    
    summary = {
        "command": "lead-magnets",
        "status": "ok",
        "model": model,
        "run_id": run_id,
        "dry_run": dry_run,
        "requested_limit": limit,
        "processed_count": processed,
        "created_count": created,
        "skipped_count": len(skipped_items),
        "blocked_count": len(blocked_items),
        "created": created_items,
        "skipped": skipped_items[:100],
        "blocked": blocked_items[:100],
        "elapsed_seconds": round(time.monotonic() - started_at, 2),
    }
    
    report_path = write_report("generation", summary)
    print(f"\nLead magnets generados: {created}")
    print(f"Reporte: {report_path}")
    
    return {**summary, "report": str(report_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente 3: Creador de Lead Magnets para PC MIDI Center")
    parser.add_argument("--limit", type=int, default=10, help="Cantidad maxima de lead magnets a generar")
    parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help="Modelo OpenRouter")
    parser.add_argument("--dry-run", action="store_true", help="Genera sin guardar cambios")
    
    args = parser.parse_args()
    generate_lead_magnets(limit=args.limit, model=args.model, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
