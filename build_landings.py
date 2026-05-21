import argparse
import csv
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
ASSETS_DIR = SITE_DIR / "assets"
REPORTS_DIR = ROOT / "reports"

CATEGORIES_PATH = DATA_DIR / "categorias_pcmidi.json"
PRODUCTS_PATH = DATA_DIR / "productos_pcmidi.json"
SEED_TOPICS_PATH = DATA_DIR / "temas_semilla.csv"
LANDINGS_PATH = DATA_DIR / "landings_aprobadas.jsonl"
OPPORTUNITIES_PATH = DATA_DIR / "oportunidades_research.jsonl"
TEMPLATE_PATH = TEMPLATES_DIR / "landing-static-template.html"

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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
CATEGORY_ALIASES = {
    "auriculares-y-monitores": "auriculares-monitores",
    "microfonos-y-streaming": "microfonos-streaming",
    "microfonos-profesionales-y-estudio": "microfonos-profesionales",
    "pads-midi": "controladores-pads",
    "teclados-midi": "controladores-midi",
    "placas-de-sonido": "interfaces-audio",
    "interfaces-de-audio": "interfaces-audio",
    "baterias-electronicas-y-modulos": "baterias-electronicas",
}
PRODUCT_ALIASES = {
    "synido-live-dock-solo": "synido-livedock-live-10",
    "synido-livedock-solo": "synido-livedock-live-10",
    "synido-live-dock-live-10": "synido-livedock-live-10",
    "synido-live-dock-pro-a20": "synido-livedock-pro-a20",
    "synido-livemix-solo": "synido-livemix-solo-gris",
    "synido-live-mix-solo": "synido-livemix-solo-gris",
    "synido-live-mix-solo-gris": "synido-livemix-solo-gris",
    "synido-live-mix-solo-violeta": "synido-livemix-solo-violeta",
}


def slugify(value: str) -> str:
    value = value.lower().strip()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n", "ü": "u"}
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:90]


def load_categories() -> dict[str, dict]:
    categories = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in categories}


def load_products() -> dict[str, dict]:
    if not PRODUCTS_PATH.exists():
        return {}
    products = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in products}


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


def load_seed_topics() -> list[dict]:
    if not SEED_TOPICS_PATH.exists():
        return []
    with SEED_TOPICS_PATH.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def append_landing(landing: dict) -> None:
    LANDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LANDINGS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(landing, ensure_ascii=False, separators=(",", ":")) + "\n")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def category_ids_for(landing: dict) -> list[str]:
    ids = [landing.get("primary_category_id", "")]
    ids.extend(landing.get("secondary_category_ids", []))
    return [item for item in ids if item]


def validate_landings(landings: list[dict], categories: dict[str, dict], products: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, set[str]] = {"slug": set(), "seo_title": set(), "meta_description": set(), "h1": set()}
    required = ["keyword", "intent", "seo_title", "meta_description", "h1", "hero_lede", "primary_category_id"]

    for product_id, product in products.items():
        product_text = f"{product.get('nombre', '')} {product.get('modelo', '')} {product.get('url', '')}".lower()
        if product.get("categoria_id") == "software-vstis" or "/software-" in product_text or "software" in product_text:
            errors.append(f"catalogo: producto de software no permitido en hardware: {product_id}")
        if product.get("marca", "").lower() == "arturia" and re.search(r"\b[a-z0-9-]+\s+v\b", product.get("modelo", "").lower()):
            errors.append(f"catalogo: modelo Arturia V no permitido en hardware: {product_id}")

    for index, landing in enumerate(landings, start=1):
        label = landing.get("slug") or landing.get("keyword") or f"landing #{index}"
        for field in required:
            if not landing.get(field):
                errors.append(f"{label}: falta {field}")

        landing.setdefault("slug", slugify(landing.get("keyword", "")))
        for field in seen:
            value = landing.get(field, "").strip().lower()
            if not value:
                continue
            if value in seen[field]:
                errors.append(f"{label}: {field} duplicado")
            seen[field].add(value)

        ids = category_ids_for(landing)
        if not ids:
            errors.append(f"{label}: no tiene categorias")
        for category_id in ids:
            if category_id not in categories:
                errors.append(f"{label}: categoria no permitida: {category_id}")

        for product_id in landing.get("product_ids", []):
            product = products.get(product_id)
            if not product:
                errors.append(f"{label}: producto no permitido: {product_id}")
                continue
            if product.get("categoria_id") not in categories:
                errors.append(f"{label}: producto con categoria invalida: {product_id}")
            if not str(product.get("url", "")).startswith("https://www.pcmidi.com.ar/productos/"):
                errors.append(f"{label}: URL de producto invalida: {product_id}")

        text = json.dumps(landing, ensure_ascii=False).lower()
        for claim in FORBIDDEN_CLAIMS:
            if claim.lower() in text:
                errors.append(f"{label}: claim prohibido detectado: {claim}")

        for field in ("components", "steps", "faqs"):
            if not landing.get(field):
                errors.append(f"{label}: falta bloque {field}")

    return errors


def render_template(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{ " + key + " }}", value)
    return template


def compact_catalog(categories: dict[str, dict], products: dict[str, dict]) -> dict:
    return {
        "categorias": [
            {
                "id": item["id"],
                "nombre": item["nombre"],
                "url": item["url"],
                "descripcion": item.get("descripcion", ""),
                "keywords": item.get("keywords", []),
            }
            for item in categories.values()
        ],
        "productos": [
            {
                "id": item["id"],
                "marca": item["marca"],
                "modelo": item["modelo"],
                "nombre": item["nombre"],
                "categoria_id": item["categoria_id"],
                "uso": item.get("uso", ""),
            }
            for item in products.values()
        ],
    }


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
            "X-Title": "PC MIDI Landing Generator",
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


def generation_prompt(topic: dict, categories: dict[str, dict], products: dict[str, dict]) -> tuple[str, str]:
    catalog = compact_catalog(categories, products)
    system = """Sos estratega SEO y especialista en landings comerciales para PC MIDI Center.
Devolves solo JSON valido, sin markdown ni explicaciones.
La landing debe ser unica, concreta, util para un posible comprador y relacionada con hardware vendido por PC MIDI.
No inventes categorias, productos, marcas, modelos ni URLs. Solo usa IDs del catalogo recibido.
No menciones precios, stock, disponibilidad, distribuidor oficial, soporte tecnico oficial, exclusividad, reparaciones, alquileres, clases formales, grabacion, mezcla ni mastering.
No incluyas software Arturia tipo Modular V, CS-80 V, CMI V, Synclavier V ni packs de plugins.
Usa español rioplatense claro y humano."""
    user = f"""Tema semilla:
- keyword: {topic.get('keyword', '')}
- intencion: {topic.get('intencion', '')}
- categorias sugeridas: {topic.get('categorias_sugeridas', '')}

Catalogo cerrado permitido:
{json.dumps(catalog, ensure_ascii=False)}

Genera una landing JSON con exactamente esta forma:
{{
  "slug": "slug-seo-unico",
  "keyword": "busqueda objetivo concreta",
  "intent": "intencion del usuario",
  "seo_title": "title unico de maximo 65 caracteres",
  "meta_description": "meta description unica de 140 a 160 caracteres",
  "h1": "H1 unico y natural",
  "hero_lede": "subtitulo humano de 1 a 2 frases",
  "components_title": "titulo humano y especifico para la seccion de opciones",
  "components_subtitle": "parrafo que mencione productos/modelos reales si ayudan",
  "primary_category_id": "id_categoria",
  "secondary_category_ids": ["id_categoria", "id_categoria"],
  "product_ids": ["id_producto", "id_producto", "id_producto"],
  "components": [
    {{"cat":"Categoria o parte del setup", "shortCat":"ETIQUETA", "why":"para que sirve", "look":"que mirar al elegir"}},
    {{"cat":"Categoria o parte del setup", "shortCat":"ETIQUETA", "why":"para que sirve", "look":"que mirar al elegir"}},
    {{"cat":"Categoria o parte del setup", "shortCat":"ETIQUETA", "why":"para que sirve", "look":"que mirar al elegir"}}
  ],
  "steps": [
    {{"n":"01", "t":"paso concreto", "b":"explicacion breve"}},
    {{"n":"02", "t":"paso concreto", "b":"explicacion breve"}},
    {{"n":"03", "t":"paso concreto", "b":"explicacion breve"}}
  ],
  "faqs": [
    {{"q":"pregunta realista", "a":"respuesta segura"}},
    {{"q":"pregunta realista", "a":"respuesta segura"}},
    {{"q":"pregunta realista", "a":"respuesta segura"}}
  ]
}}

Reglas:
- El primary_category_id y secondary_category_ids deben existir en el catalogo.
- product_ids debe contener 2 a 5 productos reales del catalogo, todos hardware.
- Si un producto no ayuda al tema, no lo uses.
- No uses frases genericas como "lo que entra en juego".
- No afirmes que PC MIDI tiene stock ni disponibilidad.
- La landing debe responder una busqueda o problema real de comprador."""
    return system, user


def normalize_generated_landing(landing: dict) -> dict:
    landing["slug"] = slugify(landing.get("slug") or landing.get("keyword", ""))
    landing["primary_category_id"] = CATEGORY_ALIASES.get(landing.get("primary_category_id"), landing.get("primary_category_id"))
    landing["secondary_category_ids"] = [CATEGORY_ALIASES.get(item, item) for item in landing.get("secondary_category_ids", [])]
    landing["secondary_category_ids"] = list(dict.fromkeys(landing.get("secondary_category_ids", [])))[:5]
    landing["product_ids"] = [PRODUCT_ALIASES.get(item, item) for item in landing.get("product_ids", [])]
    landing["product_ids"] = list(dict.fromkeys(landing.get("product_ids", [])))[:5]
    return landing


def topic_key(value: str) -> str:
    return slugify(value).lower()


def topic_key_from_record(record: dict) -> str:
    return topic_key(record.get("keyword") or record.get("busqueda_objetivo") or record.get("h1") or "")


def classify_topic(keyword: str, categories: dict[str, dict], products: dict[str, dict]) -> tuple[list[str], list[str]]:
    text = keyword.lower()
    weak_terms = {"midi", "pads", "sonidos", "kit", "hardware", "software", "home studio", "streaming", "departamento", "arturia"}
    category_scores: list[tuple[int, str]] = []
    for category_id, category in categories.items():
        if category_id == "home":
            continue
        score = 0
        strong_hits = 0
        for term in category.get("keywords", []):
            term_l = term.lower()
            if term_l in text:
                if term_l in weak_terms:
                    score += 1
                else:
                    score += 3
                    strong_hits += 1
        if category["nombre"].lower() in text:
            score += 4
            strong_hits += 1
        if score and (strong_hits or score >= 5):
            category_scores.append((score, category_id))
    product_ids = []
    for product_id, product in products.items():
        terms = [product.get("modelo", ""), product.get("nombre", "")]
        if any(term and term.lower() in text for term in terms):
            product_ids.append(product_id)
            if product.get("categoria_id"):
                category_scores.append((6, product["categoria_id"]))
    category_ids = [item for _, item in sorted(category_scores, reverse=True)]
    category_ids = list(dict.fromkeys(category_ids))[:4]
    product_ids = list(dict.fromkeys(product_ids))[:5]
    return category_ids, product_ids


def opportunity_from_keyword(keyword: str, intent: str, source: str, categories: dict[str, dict], products: dict[str, dict], evidence: str = "") -> dict | None:
    category_ids, product_ids = classify_topic(keyword, categories, products)
    if not category_ids:
        return None
    return {
        "keyword": keyword.strip(),
        "intencion": intent.strip() or "resolver una busqueda de compra",
        "categorias_sugeridas": ";".join(category_ids),
        "product_ids_sugeridos": product_ids,
        "source": source,
        "evidence": evidence[:500],
    }


def generate_keyword_variations(seed: dict) -> list[tuple[str, str]]:
    keyword = seed.get("keyword", "").strip()
    intent = seed.get("intencion", "").strip()
    if not keyword:
        return []
    prefixes = [
        "que comprar para",
        "como elegir",
        "mejor opcion de",
        "guia para elegir",
        "comparar opciones de",
        "setup con",
    ]
    category_text = seed.get("categorias_sugeridas", "")
    suffixes = ["para principiantes", "para home studio"]
    category_suffixes = {
        "microfonos-streaming": ["para YouTube", "para Twitch", "para podcast", "para clases online", "sin complicarse"],
        "microfonos": ["para voces", "para locucion", "con interfaz de audio", "para grabar covers"],
        "microfonos-profesionales": ["para voz hablada", "para cantar", "con phantom power", "para grabacion casera"],
        "interfaces-audio": ["para dos entradas", "para guitarra", "para voz", "para notebook", "para conectar monitores"],
        "controladores-midi": ["para hacer beats", "para tocar acordes", "para producir en notebook", "para escritorio chico", "con pads"],
        "controladores-pads": ["para finger drumming", "para samples", "para trap", "para live set"],
        "auriculares": ["para grabar voces", "para mezclar de noche", "para tocar guitarra", "para streaming"],
        "monitores-estudio": ["para cuarto chico", "para escritorio", "para producir", "para editar video"],
        "sintetizadores": ["para bajos", "para leads", "para pads", "para directo", "sin computadora"],
        "sintes-analogicos-hibridos": ["para aprender sintesis", "para texturas", "para musica electronica", "con vocoder"],
        "secuenciadores": ["para dawless", "para sintes hardware", "para patrones", "para directo"],
        "baterias-electronicas": ["para practicar de noche", "para chicos", "para grabar MIDI", "para tocar en vivo"],
        "camaras": ["para YouTube", "para streaming", "para podcast de video", "para cursos online"],
    }
    if any(item in category_text for item in ["baterias-electronicas", "auriculares"]):
        suffixes.append("para departamento")
    if any(item in category_text for item in ["microfonos", "microfonos-streaming", "interfaces-audio", "camaras"]):
        suffixes.extend(["para streaming", "para grabar en casa"])
    if "controladores-midi" in category_text:
        suffixes.extend(["compatible con Ableton", "compatible con FL Studio"])
    for category_id, extra_suffixes in category_suffixes.items():
        if category_id in category_text:
            suffixes.extend(extra_suffixes)
    suffixes = list(dict.fromkeys(suffixes))
    variations = [(keyword, intent)]
    for prefix in prefixes:
        variations.append((f"{prefix} {keyword}", intent))
    use_cases = ["home studio chico", "departamento", "creadores de contenido", "principiantes", "setup portable"]
    for use_case in use_cases:
        if use_case not in keyword.lower():
            variations.append((f"{keyword} para {use_case}", intent))
    if any(item in category_text for item in ["microfonos", "interfaces-audio", "auriculares", "monitores-estudio"]):
        variations.extend([
            (f"{keyword} para mejorar audio en casa", intent),
            (f"{keyword} para grabar contenido", intent),
        ])
    if any(item in category_text for item in ["controladores-midi", "controladores-pads", "sintetizadores", "secuenciadores"]):
        variations.extend([
            (f"{keyword} para producir musica electronica", intent),
            (f"{keyword} para workflow sin complicarse", intent),
        ])
    for suffix in suffixes:
        if suffix.lower() not in keyword.lower():
            variations.append((f"{keyword} {suffix}", intent))
    return list(dict.fromkeys(variations))


def ddg_research_queries(queries: list[str], limit: int) -> list[tuple[str, str]]:
    try:
        from ddgs import DDGS
    except Exception:
        return []
    results: list[tuple[str, str]] = []
    with DDGS() as ddgs:
        for query in queries:
            if len(results) >= limit:
                break
            try:
                for item in ddgs.text(query, region="ar-es", safesearch="moderate", max_results=5):
                    title = item.get("title") or ""
                    body = item.get("body") or ""
                    candidate = title.strip(" -|PC MIDI Center")
                    if candidate and 8 <= len(candidate) <= 95:
                        results.append((candidate, body))
                    if len(results) >= limit:
                        break
            except Exception:
                continue
    return results


def research_opportunities(limit: int, use_web: bool = True) -> None:
    categories = load_categories()
    products = load_products()
    seeds = load_seed_topics()
    existing_landings = load_landings()
    existing_opps = load_jsonl(OPPORTUNITIES_PATH)
    seen = {topic_key_from_record(item) for item in existing_landings}
    seen.update(topic_key_from_record(item) for item in existing_opps)

    opportunities: list[dict] = []
    for seed in seeds:
        if len(opportunities) >= limit:
            break
        for keyword, intent in generate_keyword_variations(seed):
            key = topic_key(keyword)
            if not key or key in seen:
                continue
            opportunity = opportunity_from_keyword(keyword, intent, "seed_variation", categories, products)
            if not opportunity:
                continue
            opportunities.append(opportunity)
            seen.add(key)
            if len(opportunities) >= limit:
                break

    if use_web and len(opportunities) < limit:
        queries = [f"{seed.get('keyword', '')} opiniones compra Argentina" for seed in seeds[:20]]
        for keyword, evidence in ddg_research_queries(queries, limit - len(opportunities)):
            key = topic_key(keyword)
            if not key or key in seen:
                continue
            opportunity = opportunity_from_keyword(keyword, "busqueda detectada en web", "duckduckgo", categories, products, evidence=evidence)
            if not opportunity:
                continue
            opportunities.append(opportunity)
            seen.add(key)
            if len(opportunities) >= limit:
                break

    append_jsonl(OPPORTUNITIES_PATH, opportunities)
    print(f"Oportunidades nuevas: {len(opportunities)} en {OPPORTUNITIES_PATH}")


def generate_landings(limit: int, model: str, dry_run: bool = False) -> None:
    categories = load_categories()
    products = load_products()
    existing = load_landings()
    existing_slugs = {item.get("slug") for item in existing}
    existing_keywords = {topic_key_from_record(item) for item in existing}
    topics = load_seed_topics() + load_jsonl(OPPORTUNITIES_PATH)
    created = 0

    for topic in topics:
        if created >= limit:
            break
        if topic_key_from_record(topic) in existing_keywords:
            continue
        system, user = generation_prompt(topic, categories, products)
        landing = normalize_generated_landing(chat_json(system, user, model=model))
        if landing["slug"] in existing_slugs:
            landing["slug"] = slugify(f"{landing['slug']}-{created + 1}")
        candidate_list = existing + [landing]
        errors = validate_landings(candidate_list, categories, products)
        if errors:
            print("Saltada por validacion: " + landing.get("slug", topic.get("keyword", "sin-slug")))
            for error in errors:
                print(f"- {error}")
            continue
        print(f"Generada: {landing['slug']} ({landing['keyword']})")
        if not dry_run:
            append_landing(landing)
        existing.append(landing)
        existing_slugs.add(landing["slug"])
        existing_keywords.add(topic_key_from_record(landing))
        created += 1

    print(f"Landings nuevas: {created}")


def render_landing(landing: dict, categories: dict[str, dict], products: dict[str, dict], base_url: str) -> str:
    primary = categories[landing["primary_category_id"]]
    category_ids = category_ids_for(landing)
    selected = [categories[item] for item in category_ids]
    selected_products = [products[item] for item in landing.get("product_ids", []) if item in products]

    components = landing.get("components", [])
    components_html = []
    for index, component in enumerate(components, start=1):
        category = selected[min(index - 1, len(selected) - 1)]
        components_html.append(
            f'<article class="comp-card"><div class="comp-head"><span class="comp-num">{index:02d}</span>'
            f'<span class="mono-label dim">{esc(component.get("shortCat", category["nombre"]))}</span></div>'
            f'<h3 class="comp-name">{esc(component.get("cat", category["nombre"]))}</h3>'
            f'<p class="comp-text"><strong>Para que sirve:</strong> {esc(component.get("why", category["descripcion"]))}</p>'
            f'<p class="comp-text"><strong>Que mirar:</strong> {esc(component.get("look", "Comparar alternativas segun tu caso de uso."))}</p>'
            f'<a class="comp-link" href="{esc(category["url"])}" target="_blank" rel="noopener"><span>Ver categoria en pcmidi.com.ar</span><span>↗</span></a></article>'
        )

    steps_html = []
    for step in landing.get("steps", []):
        steps_html.append(
            f'<li class="step-item"><div><span class="step-num-big">{esc(step.get("n", ""))}</span></div>'
            f'<div><h3 class="step-title">{esc(step.get("t", ""))}</h3><p class="step-text">{esc(step.get("b", ""))}</p></div></li>'
        )

    faqs_html = []
    faq_entities = []
    for faq in landing.get("faqs", []):
        question = str(faq.get("q", ""))
        answer = str(faq.get("a", ""))
        faqs_html.append(f'<article class="faq-item"><h3>{esc(question)}</h3><p>{esc(answer)}</p></article>')
        faq_entities.append({"@type": "Question", "name": question, "acceptedAnswer": {"@type": "Answer", "text": answer}})

    faq_json_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_entities}, ensure_ascii=False)
    vu_bars = "".join(f'<span style="height:{height}px; --i:{index}"></span>' for index, height in enumerate([42, 70, 94, 132, 156, 120, 86, 58, 144, 168, 124, 92, 64, 112, 150, 78]))
    step_leds = "".join(f'<span style="--i:{index}"></span>' for index in range(16))
    slug = landing.get("slug") or slugify(landing["keyword"])
    canonical_url = f"{base_url.rstrip('/')}/{quote(slug)}/" if base_url else f"/{quote(slug)}/"
    components_title = landing.get("components_title") or f"Opciones para resolver: {landing['keyword']}"
    components_subtitle = landing.get("components_subtitle") or (
        f"Estas categorias ayudan a comparar {primary['nombre'].lower()} y accesorios relacionados segun el uso real: "
        f"que queres conectar, como vas a producir y que parte del setup necesitas mejorar primero."
    )
    product_links_html = ""
    if selected_products:
        product_items = []
        for product in selected_products:
            product_items.append(
                f'<a class="product-pill" href="{esc(product["url"])}" target="_blank" rel="noopener">'
                f'<span>{esc(product["marca"])} {esc(product["modelo"])}</span>'
                f'<small>{esc(product["uso"])}</small></a>'
            )
        product_links_html = '<div class="product-strip"><span class="mono-label dim">Productos mencionados</span><div class="product-strip-grid">' + "".join(product_items) + "</div></div>"

    values = {
        "seo_title": esc(landing["seo_title"]),
        "meta_description": esc(landing["meta_description"]),
        "canonical_url": esc(canonical_url),
        "faq_json_ld": esc(faq_json_ld).replace("&quot;", '"'),
        "primary_url": esc(primary["url"]),
        "primary_name": esc(primary["nombre"]),
        "cta_text": "Ver opciones en PC MIDI Center",
        "code": esc("PC MIDI · " + slug[:18].upper()),
        "eyebrow": esc("Guia tecnica · " + primary["nombre"]),
        "h1": esc(landing["h1"]),
        "hero_lede": esc(landing["hero_lede"]),
        "keyword": esc(landing["keyword"]),
        "components_title": esc(components_title),
        "components_subtitle": esc(components_subtitle),
        "product_links_html": product_links_html,
        "components_html": "\n".join(components_html),
        "steps_html": "\n".join(steps_html),
        "faqs_html": "\n".join(faqs_html),
        "vu_bars": vu_bars,
        "step_leds": step_leds,
    }
    return render_template(TEMPLATE_PATH.read_text(encoding="utf-8"), values)


def build(base_url: str = "") -> None:
    categories = load_categories()
    products = load_products()
    landings = load_landings()
    errors = validate_landings(landings, categories, products)
    if errors:
        raise SystemExit("Validacion fallida:\n" + "\n".join(f"- {error}" for error in errors))

    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    for logo in ("LogoPCMIDIBlanco.png", "LogoPCMIDINegro.png"):
        source = ROOT / logo
        if source.exists():
            shutil.copy2(source, ASSETS_DIR / logo)

    index_items = []
    sitemap_urls = []
    for landing in landings:
        slug = landing.get("slug") or slugify(landing["keyword"])
        html_text = render_landing(landing, categories, products, base_url)
        landing_dir = SITE_DIR / slug
        landing_dir.mkdir(parents=True, exist_ok=True)
        output = landing_dir / "index.html"
        output.write_text(html_text, encoding="utf-8")
        index_items.append(f'<li><a href="/{esc(slug)}/">{esc(landing["h1"])}</a><span>{esc(landing["keyword"])}</span></li>')
        loc = f"{base_url.rstrip('/')}/{quote(slug)}/" if base_url else f"/{quote(slug)}/"
        sitemap_urls.append(loc)

    index_html = """<!DOCTYPE html>
<html lang="es-AR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Landings PC MIDI Center</title><meta name="description" content="Indice de landings estaticas SEO de PC MIDI Center."><style>body{font-family:Arial,sans-serif;background:#F4F1EA;color:#1D1D1B;margin:0;padding:40px}main{max-width:980px;margin:auto}a{color:#EB6517;font-weight:700}li{margin:18px 0}span{display:block;color:#79766F;margin-top:4px}</style></head><body><main><h1>Landings PC MIDI Center</h1><p>Indice generado automaticamente.</p><ul>__ITEMS__</ul></main></body></html>""".replace("__ITEMS__", "\n".join(index_items))
    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")

    sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc in sitemap_urls:
        sitemap_xml += f"  <url><loc>{esc(loc)}</loc></url>\n"
    sitemap_xml += "</urlset>\n"
    (SITE_DIR / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    sitemap_ref = f"Sitemap: {base_url.rstrip('/')}/sitemap.xml" if base_url else "Sitemap: sitemap.xml"
    (SITE_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\n{sitemap_ref}\n", encoding="utf-8")


def validate_command() -> None:
    categories = load_categories()
    products = load_products()
    landings = load_landings()
    errors = validate_landings(landings, categories, products)
    if errors:
        raise SystemExit("Validacion fallida:\n" + "\n".join(f"- {error}" for error in errors))
    print(f"OK: {len(landings)} landings, {len(categories)} categorias y {len(products)} productos validados.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador estatico de landings PC MIDI Center")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--base-url", default="", help="URL del subdominio para canonical/sitemap")
    research_parser = sub.add_parser("research")
    research_parser.add_argument("--limit", type=int, default=50, help="Cantidad maxima de oportunidades nuevas")
    research_parser.add_argument("--no-web", action="store_true", help="No intenta buscar sugerencias web")
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima de landings nuevas")
    generate_parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help="Modelo OpenRouter")
    generate_parser.add_argument("--dry-run", action="store_true", help="Genera y valida sin guardar")
    args = parser.parse_args()
    if args.command == "validate":
        validate_command()
    elif args.command == "build":
        build(base_url=args.base_url)
        print(f"Sitio generado en {SITE_DIR}")
    elif args.command == "research":
        research_opportunities(limit=args.limit, use_web=not args.no_web)
    elif args.command == "generate":
        generate_landings(limit=args.limit, model=args.model, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
