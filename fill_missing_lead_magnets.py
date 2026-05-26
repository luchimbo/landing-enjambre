import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LANDINGS_PATH = ROOT / "data" / "landings_aprobadas.jsonl"
LEAD_MAGNETS_PATH = ROOT / "data" / "lead_magnets.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def resource_type_for(landing: dict) -> str:
    keyword = landing.get("keyword", "").lower()
    intent = landing.get("intent", "").lower()
    if any(term in keyword for term in [" vs ", "comparativa", "comparar"]):
        return "comparativa"
    if any(term in keyword for term in ["setup", "configurar", "cadena"]):
        return "configuracion"
    if any(term in intent for term in ["decidir", "comparar", "elegir"]):
        return "checklist"
    if any(term in keyword for term in ["principiantes", "empezar", "aprender"]):
        return "guia breve"
    return "checklist"


def title_for(landing: dict, resource_type: str) -> str:
    keyword = landing.get("keyword", "tu equipo").strip()
    if resource_type == "comparativa":
        return f"Comparativa practica: {keyword}"[:80]
    if resource_type == "configuracion":
        return f"Guia de configuracion: {keyword}"[:80]
    if resource_type == "guia breve":
        return f"Guia breve para elegir {keyword}"[:80]
    return f"Checklist para elegir {keyword}"[:80]


def cta_for(resource_type: str) -> str:
    return {
        "comparativa": "Recibir comparativa",
        "configuracion": "Recibir guia",
        "guia breve": "Recibir guia breve",
        "plantilla": "Recibir plantilla",
        "mapa de decision": "Recibir mapa",
    }.get(resource_type, "Recibir checklist")


def build_magnet(landing: dict, run_id: str) -> dict:
    slug = landing["slug"]
    keyword = landing.get("keyword", "este equipo")
    resource_type = resource_type_for(landing)
    title = title_for(landing, resource_type)
    primary_category = landing.get("primary_category_id", "")
    product_ids = landing.get("product_ids", [])
    product_text = ", ".join(product_ids[:3]) if product_ids else "opciones de PC MIDI Center"
    subject_base = title.replace("Checklist para elegir ", "Checklist: ").replace("Guia breve para elegir ", "Guia: ")

    day0 = (
        f"¡Hola! Te dejo el recurso para ordenar la eleccion de {keyword}. "
        f"La idea es revisar uso real, conexiones, espacio disponible y categoria principal antes de decidir. "
        f"Tambien vas a ver referencias como {product_text} cuando ayuden a comparar alternativas."
    )
    day3 = (
        f"Hola de nuevo. Un tip util para {keyword}: no mires solo el modelo; revisa primero que parte de tu setup queres mejorar. "
        f"Si el problema es flujo de trabajo, prioriza controles y compatibilidad. Si el problema es audio, prioriza conexiones y monitoreo."
    )
    day5 = (
        f"Si ya tenes mas claro que necesitas, el siguiente paso es comparar la categoria {primary_category or 'relacionada'} en PC MIDI Center. "
        f"Usa el recurso como lista de control y revisa opciones en pcmidi.com.ar segun tu caso de uso."
    )

    return {
        "slug": slug,
        "keyword": keyword,
        "lead_magnet": {
            "title": title,
            "description": f"Una guia concreta para comparar {keyword} segun uso real, conexiones y espacio de trabajo."[:180],
            "cta_text": cta_for(resource_type),
            "resource_type": resource_type,
            "delivery_subject": subject_base[:90],
            "nurture_sequence": {
                "day_0": {"subject": subject_base[:90], "body": day0},
                "day_3": {"subject": f"Tip tecnico para elegir {keyword}"[:90], "body": day3},
                "day_5": {"subject": f"Como seguir comparando {keyword}"[:90], "body": day5},
            },
            "form_fields": ["email", "nombre_opcional"],
            "value_proposition": f"Ordena la compra de {keyword} con criterios simples antes de comparar modelos."[:180],
        },
        "run_id": run_id,
    }


def main() -> None:
    landings = load_jsonl(LANDINGS_PATH)
    existing = load_jsonl(LEAD_MAGNETS_PATH)
    existing_slugs = {item.get("slug") for item in existing}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f-fill-missing")
    missing = [landing for landing in landings if landing.get("slug") not in existing_slugs]
    if not missing:
        print("No faltan lead magnets.")
        return
    with LEAD_MAGNETS_PATH.open("a", encoding="utf-8") as handle:
        for landing in missing:
            handle.write(json.dumps(build_magnet(landing, run_id), ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"Lead magnets agregados: {len(missing)}")


if __name__ == "__main__":
    main()
