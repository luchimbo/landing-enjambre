import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
DISTRIBUTION_LOG_PATH = DATA_DIR / "distribution_log.jsonl"
LANDINGS_PATH = DATA_DIR / "landings_aprobadas.jsonl"
SEARCH_TASKS_PATH = DATA_DIR / "distribution_search_tasks.jsonl"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
BASE_URL = "https://blog.pcmidicenter.com"

REDDIT_SUBREDDITS = [
    "edmproduction",
    "WeAreTheMusicMakers",
    "homerecording",
    "audioengineering",
    "ableton",
    "FL_Studio",
    "synthesizers",
    "MusicProduction",
    "podcast",
]

TWITTER_KEYWORDS = [
    "controlador MIDI recomendacion",
    "interfaz de audio home studio",
    "microfono home studio",
    "monitores de estudio recomendacion",
    "como grabar en casa",
    "home studio armado",
    "DAW recomendacion",
    "teclado MIDI recomendacion",
]

BROWSER_SEARCH_CHANNELS = {
    "reddit": "https://www.reddit.com/search/?q={query}&type=link&sort=new",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "linkedin": "https://www.linkedin.com/search/results/content/?keywords={query}",
    "facebook": "https://www.facebook.com/search/posts?q={query}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={query}",
    "twitter": "https://twitter.com/search?q={query}&src=typed_query&f=live",
    "x": "https://x.com/search?q={query}&src=typed_query&f=live",
}

FORBIDDEN_CLAIMS = [
    "stock garantizado",
    "disponibilidad garantizada",
    "distribuidor oficial",
    "soporte tecnico oficial",
    "soporte técnico oficial",
    "canal oficial",
    "exclusividad",
    "precio",
    "precios",
    "cuota",
    "cuotas",
    "mejor precio",
    "yo lo use",
    "yo lo usé",
    "te lo recomiendo",
    "lo recomiendo",
    "lo compré",
    "lo compre",
    "disponible",
    "hay stock",
    "en stock",
]

SPAM_PATTERNS = [
    r"\b(compra\s+ahora|buy\s+now|haz\s+clic|click\s+aqui|oferta\s+limitada|tiempo\s+limitado)\b",
    r"!!+",
    r"\$\d+",
]

STOPWORDS = {
    "a", "al", "and", "con", "de", "del", "el", "en", "for", "la", "las", "los", "of", "on", "para", "por", "the", "to", "un", "una",
}

COMMERCIAL_RELEVANCE_TERMS = {
    "audio", "auriculares", "bateria", "controlador", "guitarra", "home", "interfaz", "keyboard", "midi", "microfono", "mic", "monitor", "podcast", "studio", "synth", "sintetizador", "teclado",
}

# Rate limiting
REDDIT_MIN_DELAY_SECONDS = 60
LINKEDIN_MAX_POSTS_PER_DAY = 3
TWITTER_MIN_DELAY_SECONDS = 30


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


def rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def set_clipboard(text: str) -> bool:
    try:
        subprocess.run(
            ["clip"],
            input=text,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return True
    except Exception:
        return False


def write_report(name: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = REPORTS_DIR / f"{stamp}-publicacion-{name}.json"
    payload = {"timestamp_utc": stamp, **data}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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


def chat_json(system: str, user: str, model: str, temperature: float = 0.4) -> dict:
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
            "X-Title": "PC MIDI Publicacion Agent",
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


def validate_body(body: str) -> list[str]:
    errors = []
    lower = body.lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim.lower() in lower:
            errors.append(f"claim prohibido: {claim}")
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, lower):
            errors.append(f"patron spam: {pattern}")
    if len(body.strip()) < 30:
        errors.append("cuerpo demasiado corto")
    return errors


def load_landings_by_slug() -> dict[str, dict]:
    landings = {}
    if not LANDINGS_PATH.exists():
        return landings
    for line in LANDINGS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            landing = json.loads(line)
            slug = landing.get("slug", "")
            if slug:
                landings[slug] = landing
        except json.JSONDecodeError:
            pass
    return landings


def landing_queries(limit: int) -> list[tuple[str, dict]]:
    landings = list(load_landings_by_slug().values())
    queries = []
    for landing in landings:
        keyword = landing.get("keyword") or landing.get("h1") or landing.get("slug", "")
        if not keyword:
            continue
        queries.append((keyword, landing))
        if len(queries) >= limit:
            break
    return queries


def build_browser_search_url(channel: str, query: str) -> str:
    from urllib.parse import quote_plus

    template = BROWSER_SEARCH_CHANNELS.get(channel)
    if not template:
        raise ValueError(f"Canal no soportado para browser-search: {channel}")
    return template.format(query=quote_plus(query))


def run_browser_search(channel: str, limit: int, open_browser: bool, dry_run: bool) -> dict:
    if channel not in BROWSER_SEARCH_CHANNELS:
        supported = ", ".join(sorted(BROWSER_SEARCH_CHANNELS))
        raise SystemExit(f"Canal no soportado: {channel}. Usar: {supported}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    tasks = []
    for query, landing in landing_queries(limit):
        url = build_browser_search_url(channel, query)
        task = {
            "id": f"{run_id}:{channel}:{landing.get('slug', '')}",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "channel": channel,
            "status": "opened" if open_browser else "planned",
            "query": query,
            "search_url": url,
            "landing_slug": landing.get("slug", ""),
            "landing_url": f"{BASE_URL}/{landing.get('slug', '')}/",
            "mode": "personal_account_browser_assist",
            "notes": "Abrir con Chrome normal ya logueado. Seleccionar una oportunidad visible y usar create-comment-from-context para generar el borrador.",
        }
        tasks.append(task)
        print(f"browser-search [{channel}]: {query}")
        print(f"  {url}")
        if open_browser:
            webbrowser.open(url)

    if tasks and not dry_run:
        append_jsonl(SEARCH_TASKS_PATH, tasks)

    summary = {
        "command": "browser-search",
        "channel": channel,
        "dry_run": dry_run,
        "open_browser": open_browser,
        "tasks": len(tasks),
        "tasks_path": str(SEARCH_TASKS_PATH),
    }
    return summary


def run_create_comment_from_context(channel: str, context: str, url: str, landing_slug: str, model: str, dry_run: bool) -> dict:
    landings = load_landings_by_slug()
    landing = landings.get(landing_slug)
    if not landing:
        raise SystemExit(f"Landing no encontrada: {landing_slug}")
    landing_url = f"{BASE_URL}/{landing_slug}/"
    system = """Sos experto en produccion musical. Escribis respuestas utiles para comunidades.
No menciones precios, stock, disponibilidad, cuotas ni distribuidor oficial.
No finjas experiencia personal. No vendas agresivamente.
La respuesta debe servir como comentario/reply al contexto dado. Devolve SOLO JSON valido."""
    user = f"""Canal: {channel}
URL/contexto origen: {url}
Contexto copiado por el usuario:
{context}

Landing relacionada:
- keyword: {landing.get('keyword', '')}
- H1: {landing.get('h1', '')}
- URL: {landing_url}

Genera un comentario util. JSON:
{{
  "body": "texto del comentario, maximo 260 palabras",
  "link_included": true_o_false,
  "notes": "nota interna de revision"
}}"""
    piece = chat_json(system, user, model=model)
    body = piece.get("body", "")
    errors = validate_body(body)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    record = {
        "id": f"{run_id}:{channel}:{landing_slug}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "landing_slug": landing_slug,
        "landing_url": landing_url,
        "channel": channel,
        "community": channel,
        "content_type": "respuesta_contexto_browser",
        "status": "approved",
        "title": context[:200].replace("\n", " "),
        "body": body,
        "link_included": piece.get("link_included", False),
        "risk_level": "low",
        "requires_manual_review": False,
        "source_thread_url": url,
        "source_thread_title": context[:200].replace("\n", " "),
        "approved_at_utc": datetime.now(timezone.utc).isoformat(),
        "approval_mode": "auto_always_approved",
        "notes": piece.get("notes", "") + (f" ADVERTENCIAS: {'; '.join(errors)}" if errors else ""),
    }
    if not dry_run:
        append_jsonl(DISTRIBUTION_LOG_PATH, [record])
    print("\n--- COMMENT DRAFT ---")
    print(body)
    set_clipboard(body)
    return {"created": 1, "blocked": 0, "record": record}


# ─── Reddit ───────────────────────────────────────────────────────────────────

def get_reddit_instance():
    try:
        import praw
    except ImportError:
        raise RuntimeError("praw no instalado. Ejecuta: pip install praw==7.8.1")

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "pcmidi_distribucion/1.0")

    missing = [k for k, v in {
        "REDDIT_CLIENT_ID": client_id,
        "REDDIT_CLIENT_SECRET": client_secret,
        "REDDIT_USERNAME": username,
        "REDDIT_PASSWORD": password,
    }.items() if not v]

    if missing:
        raise RuntimeError(f"Faltan credenciales Reddit en .env: {', '.join(missing)}")

    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=user_agent,
    )


def is_question_post(title: str) -> bool:
    question_signals = ["?", "cual", "cuál", "cómo", "como", "que ", "qué ", "recomendacion", "recomendación", "ayuda", "help", "suggest", "recommend", "cual es", "que es"]
    lower = title.lower()
    return any(s in lower for s in question_signals)


def meaningful_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-zA-ZáéíóúñÁÉÍÓÚÑ0-9]+", text.lower()))
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def has_commercial_relevance(text: str) -> bool:
    words = meaningful_words(text)
    return bool(words & COMMERCIAL_RELEVANCE_TERMS)


def search_reddit_threads(limit: int, dry_run: bool, model: str) -> list[dict]:
    reddit = get_reddit_instance()
    landings_by_slug = load_landings_by_slug()
    existing_log = load_jsonl(DISTRIBUTION_LOG_PATH)
    already_done_urls = {e.get("source_thread_url", "") for e in existing_log}

    keywords_to_landing: list[tuple[str, dict]] = []
    for slug, landing in landings_by_slug.items():
        kw = landing.get("keyword", "")
        if kw:
            keywords_to_landing.append((kw, landing))

    found = []
    checked = 0

    for subreddit_name in REDDIT_SUBREDDITS:
        if len(found) >= limit:
            break
        try:
            subreddit = reddit.subreddit(subreddit_name)
            posts = list(subreddit.new(limit=25))
        except Exception as exc:
            print(f"  reddit: error leyendo r/{subreddit_name}: {exc}")
            continue

        for post in posts:
            if len(found) >= limit:
                break
            checked += 1
            thread_url = f"https://reddit.com{post.permalink}"
            if thread_url in already_done_urls:
                continue
            if post.score > 150:
                continue
            if not is_question_post(post.title):
                continue

            # Find matching landing by keyword overlap
            best_landing = None
            best_score = 0
            if not has_commercial_relevance(post.title):
                continue

            post_words = meaningful_words(post.title)
            for kw, landing in keywords_to_landing:
                kw_words = meaningful_words(kw)
                overlap = len(kw_words & post_words)
                if overlap > best_score:
                    best_score = overlap
                    best_landing = landing

            if best_score < 2 or best_landing is None:
                continue

            slug = best_landing.get("slug", "")
            landing_url = f"{BASE_URL}/{slug}/"

            system = """Sos experto en produccion musical. Respondis preguntas en Reddit de forma util y honesta.
NUNCA menciones precios, stock, disponibilidad, distribuidor oficial ni cuotas.
NUNCA finjas experiencia personal (no uses "yo lo use", "lo compre").
Aportas valor tecnico primero. Solo incluye el link si es genuinamente util.
Devolve SOLO JSON valido."""

            user = f"""Thread de Reddit:
- Subreddit: r/{subreddit_name}
- Titulo: {post.title}
- URL: {thread_url}

Landing relacionada:
- keyword: {best_landing.get('keyword', '')}
- H1: {best_landing.get('h1', '')}
- URL: {landing_url}

FAQs relevantes:
{chr(10).join(f"- P: {f['q']} R: {f['a']}" for f in best_landing.get('faqs', [])[:2])}

Genera una respuesta util para ese thread. JSON:
{{
  "body": "texto de la respuesta (max 300 palabras, util primero, link solo si suma contexto)",
  "link_included": true_o_false,
  "notes": "nota interna de revision antes de publicar"
}}"""

            try:
                piece = chat_json(system, user, model=model)
            except Exception as exc:
                print(f"  reddit: error generando respuesta para {thread_url}: {exc}")
                continue

            body = piece.get("body", "")
            errors = validate_body(body)

            record = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "run_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"),
                "landing_slug": slug,
                "landing_url": landing_url,
                "channel": "reddit",
                "community": f"r/{subreddit_name}",
                "content_type": "respuesta_hilo",
                "status": "approved",
                "title": post.title[:200],
                "body": body,
                "link_included": piece.get("link_included", False),
                "risk_level": "low",
                "requires_manual_review": False,
                "source_thread_url": thread_url,
                "source_thread_title": post.title,
                "source_thread_id": post.id,
                "approved_at_utc": datetime.now(timezone.utc).isoformat(),
                "approval_mode": "auto_always_approved",
                "notes": piece.get("notes", "") + (f" ADVERTENCIAS: {'; '.join(errors)}" if errors else ""),
            }
            found.append(record)
            status_label = "approved"
            print(f"  reddit r/{subreddit_name}: [{status_label}] {post.title[:60]}")

    if not dry_run and found:
        append_jsonl(DISTRIBUTION_LOG_PATH, found)

    print(f"reddit: {len(found)} hilos encontrados (revisados {checked} posts)")
    return found


def fetch_reddit_public_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PC MIDI research assistant/1.0"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def search_reddit_public_threads(limit: int, dry_run: bool, model: str) -> list[dict]:
    """Busca threads publicos de Reddit sin login/API OAuth y genera borradores asistidos."""
    landings_by_slug = load_landings_by_slug()
    existing_log = load_jsonl(DISTRIBUTION_LOG_PATH)
    already_done_urls = {e.get("source_thread_url", "") for e in existing_log}

    keywords_to_landing = [
        (landing.get("keyword", ""), landing)
        for landing in landings_by_slug.values()
        if landing.get("keyword", "")
    ]

    found = []
    checked = 0
    for subreddit_name in REDDIT_SUBREDDITS:
        if len(found) >= limit:
            break
        listing_url = f"https://www.reddit.com/r/{subreddit_name}/new.json?limit=25"
        try:
            data = fetch_reddit_public_json(listing_url)
        except Exception as exc:
            print(f"  reddit-public: error leyendo r/{subreddit_name}: {exc}")
            continue

        posts = data.get("data", {}).get("children", [])
        for child in posts:
            if len(found) >= limit:
                break
            post = child.get("data", {})
            title = post.get("title", "")
            permalink = post.get("permalink", "")
            if not title or not permalink:
                continue
            checked += 1
            thread_url = f"https://www.reddit.com{permalink}"
            if thread_url in already_done_urls:
                continue
            if int(post.get("score") or 0) > 150:
                continue
            if not is_question_post(title):
                continue

            best_landing = None
            best_score = 0
            if not has_commercial_relevance(title):
                continue

            post_words = meaningful_words(title)
            for kw, landing in keywords_to_landing:
                overlap = len(meaningful_words(kw) & post_words)
                if overlap > best_score:
                    best_score = overlap
                    best_landing = landing
            if best_score < 2 or best_landing is None:
                continue

            slug = best_landing.get("slug", "")
            landing_url = f"{BASE_URL}/{slug}/"
            system = """Sos experto en produccion musical. Escribis respuestas utiles para comunidades.
No menciones precios, stock, disponibilidad, cuotas ni distribuidor oficial.
No finjas experiencia personal. No vendas agresivamente.
La respuesta debe poder publicarse como comentario, aportando valor incluso sin link.
Devolve SOLO JSON valido."""
            user = f"""Thread publico de Reddit:
- Subreddit: r/{subreddit_name}
- Titulo: {title}
- URL: {thread_url}

Landing relacionada:
- keyword: {best_landing.get('keyword', '')}
- H1: {best_landing.get('h1', '')}
- URL: {landing_url}

Genera una respuesta util para comentar en ese hilo. JSON:
{{
  "body": "texto del comentario, maximo 280 palabras",
  "link_included": true_o_false,
  "notes": "nota interna de revision"
}}"""
            try:
                piece = chat_json(system, user, model=model)
            except Exception as exc:
                print(f"  reddit-public: error generando respuesta para {thread_url}: {exc}")
                continue

            body = piece.get("body", "")
            errors = validate_body(body)
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            record = {
                "id": f"{run_id}:reddit-public:{post.get('id', '')}",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "landing_slug": slug,
                "landing_url": landing_url,
                "channel": "reddit",
                "community": f"r/{subreddit_name}",
                "content_type": "respuesta_hilo",
                "status": "approved",
                "title": title[:200],
                "body": body,
                "link_included": piece.get("link_included", False),
                "risk_level": "low",
                "requires_manual_review": False,
                "source_thread_url": thread_url,
                "source_thread_title": title,
                "source_thread_id": post.get("id", ""),
                "approved_at_utc": datetime.now(timezone.utc).isoformat(),
                "approval_mode": "auto_always_approved",
                "notes": piece.get("notes", "") + (f" ADVERTENCIAS: {'; '.join(errors)}" if errors else ""),
            }
            found.append(record)
            print(f"  reddit-public r/{subreddit_name}: [{record['status']}] {title[:60]}")

    if not dry_run and found:
        append_jsonl(DISTRIBUTION_LOG_PATH, found)
    print(f"reddit-public: {len(found)} hilos encontrados (revisados {checked} posts)")
    return found


# ─── Twitter/X ────────────────────────────────────────────────────────────────

def get_twitter_client():
    try:
        import tweepy
    except ImportError:
        raise RuntimeError("tweepy no instalado. Ejecuta: pip install tweepy==4.14.0")

    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")
    api_key = os.environ.get("TWITTER_API_KEY")
    api_secret = os.environ.get("TWITTER_API_SECRET")
    access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
    access_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET")

    missing = [k for k, v in {
        "TWITTER_BEARER_TOKEN": bearer_token,
        "TWITTER_API_KEY": api_key,
        "TWITTER_API_SECRET": api_secret,
        "TWITTER_ACCESS_TOKEN": access_token,
        "TWITTER_ACCESS_TOKEN_SECRET": access_secret,
    }.items() if not v]

    if missing:
        raise RuntimeError(f"Faltan credenciales Twitter en .env: {', '.join(missing)}")

    import tweepy
    client = tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
        wait_on_rate_limit=True,
    )
    return client


def search_twitter_threads(limit: int, dry_run: bool, model: str) -> list[dict]:
    client = get_twitter_client()
    landings_by_slug = load_landings_by_slug()
    existing_log = load_jsonl(DISTRIBUTION_LOG_PATH)
    already_done_ids = {e.get("source_tweet_id", "") for e in existing_log}

    found = []

    for keyword in TWITTER_KEYWORDS:
        if len(found) >= limit:
            break

        query = f"{keyword} lang:es -is:retweet -is:reply"
        try:
            import tweepy
            response = client.search_recent_tweets(
                query=query,
                max_results=10,
                tweet_fields=["created_at", "text", "author_id"],
            )
        except Exception as exc:
            print(f"  twitter: error buscando '{keyword}': {exc}")
            print("  twitter: si el error es 403, verificar que tenes el Basic tier ($100/mes)")
            continue

        if not response.data:
            continue

        for tweet in response.data:
            if len(found) >= limit:
                break
            tweet_id = str(tweet.id)
            if tweet_id in already_done_ids:
                continue

            tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"

            # Find matching landing
            best_landing = None
            best_score = 0
            tweet_words = set(tweet.text.lower().split())
            for slug, landing in landings_by_slug.items():
                kw_words = set(landing.get("keyword", "").lower().split())
                overlap = len(kw_words & tweet_words)
                if overlap > best_score:
                    best_score = overlap
                    best_landing = landing

            if best_landing is None:
                # Use the first landing that matches keyword category
                kw_lower = keyword.lower()
                for slug, landing in landings_by_slug.items():
                    if any(w in landing.get("keyword", "").lower() for w in kw_lower.split()):
                        best_landing = landing
                        break

            if best_landing is None:
                continue

            slug = best_landing.get("slug", "")
            landing_url = f"{BASE_URL}/{slug}/"

            system = """Sos experto en produccion musical. Respondis tweets con informacion util.
NUNCA menciones precios, stock, disponibilidad ni distribuidor oficial.
NUNCA finjas experiencia personal.
La respuesta debe tener MAXIMO 260 caracteres (Twitter/X).
Solo incluye el link si suma contexto real. Devolve SOLO JSON valido."""

            user = f"""Tweet a responder:
"{tweet.text}"
URL: {tweet_url}

Landing relacionada:
- keyword: {best_landing.get('keyword', '')}
- URL: {landing_url}

Genera una respuesta util en maximo 260 caracteres. JSON:
{{
  "body": "texto del reply (max 260 caracteres, util primero)",
  "link_included": true_o_false,
  "notes": "nota de revision"
}}"""

            try:
                piece = chat_json(system, user, model=model)
            except Exception as exc:
                print(f"  twitter: error generando reply para {tweet_id}: {exc}")
                continue

            body = piece.get("body", "")
            # Enforce 280 char limit
            if len(body) > 280:
                body = body[:277] + "..."

            errors = validate_body(body)

            record = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "run_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f"),
                "landing_slug": slug,
                "landing_url": landing_url,
                "channel": "twitter",
                "community": "twitter",
                "content_type": "respuesta_hilo",
                "status": "approved",
                "title": tweet.text[:200],
                "body": body,
                "link_included": piece.get("link_included", False),
                "risk_level": "low",
                "requires_manual_review": False,
                "source_tweet_id": tweet_id,
                "source_thread_url": tweet_url,
                "source_thread_title": tweet.text[:200],
                "approved_at_utc": datetime.now(timezone.utc).isoformat(),
                "approval_mode": "auto_always_approved",
                "notes": piece.get("notes", "") + (f" ADVERTENCIAS: {'; '.join(errors)}" if errors else ""),
            }
            found.append(record)
            status_label = "approved"
            print(f"  twitter [{status_label}]: {tweet.text[:60]}")

    if not dry_run and found:
        append_jsonl(DISTRIBUTION_LOG_PATH, found)

    print(f"twitter: {len(found)} tweets encontrados")
    return found


# ─── Publish ──────────────────────────────────────────────────────────────────

def publish_to_reddit(entry: dict, dry_run: bool) -> tuple[bool, str]:
    reddit = get_reddit_instance()
    thread_url = entry.get("source_thread_url", "")
    if not thread_url:
        return False, "sin source_thread_url"

    # Extract submission ID from URL
    match = re.search(r"/comments/([a-z0-9]+)/", thread_url)
    if not match:
        return False, f"no se pudo extraer submission ID de: {thread_url}"

    submission_id = match.group(1)

    if dry_run:
        print(f"  [dry-run] reddit reply a {thread_url}: {entry['body'][:80]}...")
        return True, "dry_run"

    try:
        submission = reddit.submission(id=submission_id)
        submission.reply(entry["body"])
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def publish_to_linkedin(entry: dict, dry_run: bool) -> tuple[bool, str]:
    access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    author_urn = os.environ.get("LINKEDIN_AUTHOR_URN")

    if not access_token or not author_urn:
        return False, "Faltan LINKEDIN_ACCESS_TOKEN o LINKEDIN_AUTHOR_URN en .env"

    body = entry.get("body", "")
    if entry.get("link_included") and entry.get("landing_url"):
        if entry["landing_url"] not in body:
            body = body + f"\n\n{entry['landing_url']}"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": body},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    if dry_run:
        print(f"  [dry-run] linkedin post: {body[:80]}...")
        return True, "dry_run"

    try:
        request = urllib.request.Request(
            "https://api.linkedin.com/v2/ugcPosts",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
        return True, "ok"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"LinkedIn API {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)


def publish_to_twitter(entry: dict, dry_run: bool) -> tuple[bool, str]:
    client = get_twitter_client()
    tweet_id = entry.get("source_tweet_id")
    body = entry.get("body", "")

    if len(body) > 280:
        body = body[:277] + "..."

    if dry_run:
        print(f"  [dry-run] twitter reply a {tweet_id}: {body[:80]}...")
        return True, "dry_run"

    try:
        if tweet_id:
            client.create_tweet(text=body, in_reply_to_tweet_id=tweet_id)
        else:
            client.create_tweet(text=body)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def run_publish(channel_filter: str | None, limit: int, dry_run: bool) -> dict:
    log = load_jsonl(DISTRIBUTION_LOG_PATH)
    approved = [
        e for e in log
        if e.get("status") == "approved"
        and (not channel_filter or e.get("channel") == channel_filter)
    ]

    if not approved:
        print("publish: no hay entradas con status=approved en distribution_log.jsonl")
        return {"published": 0, "failed": 0, "skipped": 0}

    print(f"publish: {len(approved)} entradas aprobadas, procesando hasta {limit}")
    approved = approved[:limit]

    published_count = 0
    failed_count = 0
    skipped_count = 0
    results = []

    linkedin_posts_today = sum(
        1 for e in log
        if e.get("channel") == "linkedin"
        and e.get("status") == "published"
        and e.get("date") == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    log_dirty = False
    published_at = datetime.now(timezone.utc).isoformat()

    for entry in approved:
        channel = entry.get("channel")
        print(f"  publicando [{channel}]: {entry.get('title', '')[:60]}")

        if channel == "reddit":
            ok, msg = publish_to_reddit(entry, dry_run)
            if ok and not dry_run:
                time.sleep(REDDIT_MIN_DELAY_SECONDS)
        elif channel == "linkedin":
            if linkedin_posts_today >= LINKEDIN_MAX_POSTS_PER_DAY:
                print(f"  linkedin: limite diario alcanzado ({LINKEDIN_MAX_POSTS_PER_DAY} posts)")
                skipped_count += 1
                results.append({"slug": entry.get("landing_slug"), "channel": channel, "status": "skipped", "reason": "daily_limit"})
                continue
            ok, msg = publish_to_linkedin(entry, dry_run)
            if ok:
                linkedin_posts_today += 1
        elif channel == "twitter":
            ok, msg = publish_to_twitter(entry, dry_run)
            if ok and not dry_run:
                time.sleep(TWITTER_MIN_DELAY_SECONDS)
        else:
            print(f"  skip [{channel}]: publicacion manual requerida")
            skipped_count += 1
            results.append({"slug": entry.get("landing_slug"), "channel": channel, "status": "skipped", "reason": "manual_channel"})
            continue

        if ok:
            published_count += 1
            new_status = "published" if not dry_run else "approved"
            results.append({"slug": entry.get("landing_slug"), "channel": channel, "status": "published", "note": msg})
        else:
            failed_count += 1
            results.append({"slug": entry.get("landing_slug"), "channel": channel, "status": "failed", "error": msg})
            print(f"  error publicando: {msg}")
            new_status = "failed"

        if not dry_run:
            entry_id = entry.get("id")
            entry_url = entry.get("source_thread_url")
            entry_slug = entry.get("landing_slug")
            for row in log:
                if row.get("status") != "approved":
                    continue
                if entry_id and row.get("id") == entry_id:
                    row["status"] = new_status
                    row["published_at"] = published_at
                    log_dirty = True
                elif not entry_id and row.get("source_thread_url") == entry_url and row.get("landing_slug") == entry_slug:
                    row["status"] = new_status
                    row["published_at"] = published_at
                    log_dirty = True

    if log_dirty:
        rewrite_jsonl(DISTRIBUTION_LOG_PATH, log)

    return {"published": published_count, "failed": failed_count, "skipped": skipped_count, "results": results}


def run_assist_comment(channel_filter: str | None, limit: int, status: str, open_browser: bool, copy: bool) -> dict:
    log = load_jsonl(DISTRIBUTION_LOG_PATH)
    candidates = [
        entry for entry in log
        if entry.get("status") == status
        and entry.get("source_thread_url")
        and (not channel_filter or entry.get("channel") == channel_filter)
    ][:limit]

    if not candidates:
        print(f"assist-comment: no hay entradas status={status} con source_thread_url")
        return {"prepared": 0, "items": []}

    prepared = []
    for entry in candidates:
        body = entry.get("body", "")
        print("\n--- COMMENT DRAFT ---")
        print(f"ID: {entry.get('id', '')}")
        print(f"Canal: {entry.get('channel', '')} / {entry.get('community', '')}")
        print(f"Thread: {entry.get('source_thread_url', '')}")
        print(f"Titulo: {entry.get('source_thread_title') or entry.get('title', '')}")
        print(body)
        copied = set_clipboard(body) if copy else False
        if copied:
            print("Comentario copiado al portapapeles.")
        if open_browser:
            webbrowser.open(entry["source_thread_url"])
        prepared.append({"id": entry.get("id", ""), "thread": entry.get("source_thread_url", ""), "copied": copied})

    return {"prepared": len(prepared), "items": prepared}


# ─── Status ───────────────────────────────────────────────────────────────────

def run_status() -> None:
    log = load_jsonl(DISTRIBUTION_LOG_PATH)
    if not log:
        print("distribution_log.jsonl vacio o no existe")
        return

    from collections import Counter
    by_status = Counter(e.get("status", "unknown") for e in log)
    by_channel = Counter(e.get("channel", "unknown") for e in log)

    print(f"\ndistribution_log: {len(log)} entradas totales")
    print("\nPor status:")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")
    print("\nPor canal:")
    for channel, count in sorted(by_channel.items()):
        print(f"  {channel}: {count}")

    proposed = [e for e in log if e.get("status") == "proposed"]
    if proposed:
        print(f"\nUltimas {min(5, len(proposed))} propuestas:")
        for e in proposed[-5:]:
            print(f"  [{e.get('channel')}] {e.get('landing_slug')} - {e.get('title', '')[:50]}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Agente 5b: Publicacion en Canales para PC MIDI Center")
    sub = parser.add_subparsers(dest="command", required=True)

    search_parser = sub.add_parser("search", help="Busca hilos/tweets relevantes y genera respuestas")
    search_parser.add_argument("--channel", default="reddit-public", help="Canal a buscar: reddit-public, reddit, twitter")
    search_parser.add_argument("--limit", type=int, default=5, help="Maximo de oportunidades a encontrar")
    search_parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help="Modelo OpenRouter")
    search_parser.add_argument("--dry-run", action="store_true", help="Genera sin guardar en distribution_log")

    publish_parser = sub.add_parser("publish", help="Publica entradas con status=approved")
    publish_parser.add_argument("--channel", default="", help="Filtrar por canal: reddit, linkedin, twitter")
    publish_parser.add_argument("--limit", type=int, default=10, help="Maximo de entradas a publicar")
    publish_parser.add_argument("--dry-run", action="store_true", help="Simula publicacion sin postear")

    assist_parser = sub.add_parser("assist-comment", help="Abre el hilo y copia el comentario para aprobacion/publicacion manual")
    assist_parser.add_argument("--channel", default="reddit", help="Filtrar por canal")
    assist_parser.add_argument("--limit", type=int, default=1, help="Cantidad de comentarios a preparar")
    assist_parser.add_argument("--status", default="proposed", help="Status a preparar: proposed, bulk_approved, ready_for_manual_publish")
    assist_parser.add_argument("--no-browser", action="store_true", help="No abre el navegador")
    assist_parser.add_argument("--no-copy", action="store_true", help="No copia al portapapeles")

    browser_search_parser = sub.add_parser("browser-search", help="Abre busquedas en tu navegador normal ya logueado")
    browser_search_parser.add_argument("--channel", required=True, choices=sorted(BROWSER_SEARCH_CHANNELS), help="Red donde buscar")
    browser_search_parser.add_argument("--limit", type=int, default=5, help="Cantidad de busquedas a abrir")
    browser_search_parser.add_argument("--no-browser", action="store_true", help="Solo imprime/guarda URLs, no abre navegador")
    browser_search_parser.add_argument("--dry-run", action="store_true", help="No guarda tareas")

    context_parser = sub.add_parser("create-comment-from-context", help="Genera comentario desde contexto copiado manualmente")
    context_parser.add_argument("--channel", required=True, help="Canal de origen")
    context_parser.add_argument("--landing-slug", required=True, help="Slug de landing relacionada")
    context_parser.add_argument("--url", default="", help="URL del post/hilo/comentario")
    context_parser.add_argument("--context", required=True, help="Texto copiado del post o comentario a responder")
    context_parser.add_argument("--model", default=os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL), help="Modelo OpenRouter")
    context_parser.add_argument("--dry-run", action="store_true", help="No guarda el borrador")

    sub.add_parser("status", help="Muestra resumen del distribution_log")

    args = parser.parse_args()
    load_env()

    if args.command == "search":
        started = time.monotonic()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

        if args.channel == "reddit-public":
            results = search_reddit_public_threads(limit=args.limit, dry_run=args.dry_run, model=args.model)
        elif args.channel == "reddit":
            results = search_reddit_threads(limit=args.limit, dry_run=args.dry_run, model=args.model)
        elif args.channel == "twitter":
            results = search_twitter_threads(limit=args.limit, dry_run=args.dry_run, model=args.model)
        else:
            raise SystemExit(f"Canal no soportado para search: {args.channel}. Usar: reddit-public, reddit, twitter")

        proposed = sum(1 for r in results if r.get("status") == "proposed")
        blocked = sum(1 for r in results if r.get("status") == "blocked")

        summary = {
            "command": "search",
            "channel": args.channel,
            "dry_run": args.dry_run,
            "run_id": run_id,
            "found": len(results),
            "proposed": proposed,
            "blocked": blocked,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        report_path = write_report("search", summary)
        print(f"\npublicacion search: {proposed} propuestas, {blocked} bloqueadas")
        print(f"reporte: {report_path}")

    elif args.command == "publish":
        started = time.monotonic()
        summary = run_publish(
            channel_filter=args.channel or None,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        summary["command"] = "publish"
        summary["dry_run"] = args.dry_run
        summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = write_report("publish", summary)
        print(f"\npublicacion publish: {summary.get('published')} publicadas, {summary.get('failed')} fallidas, {summary.get('skipped')} salteadas")
        print(f"reporte: {report_path}")

    elif args.command == "assist-comment":
        started = time.monotonic()
        summary = run_assist_comment(
            channel_filter=args.channel or None,
            limit=args.limit,
            status=args.status,
            open_browser=not args.no_browser,
            copy=not args.no_copy,
        )
        summary["command"] = "assist-comment"
        summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = write_report("assist-comment", summary)
        print(f"\npublicacion assist-comment: {summary.get('prepared')} preparados")
        print(f"reporte: {report_path}")

    elif args.command == "browser-search":
        started = time.monotonic()
        summary = run_browser_search(
            channel=args.channel,
            limit=args.limit,
            open_browser=not args.no_browser,
            dry_run=args.dry_run,
        )
        summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = write_report("browser-search", summary)
        print(f"\npublicacion browser-search: {summary.get('tasks')} busquedas")
        print(f"reporte: {report_path}")

    elif args.command == "create-comment-from-context":
        started = time.monotonic()
        summary = run_create_comment_from_context(
            channel=args.channel,
            context=args.context,
            url=args.url,
            landing_slug=args.landing_slug,
            model=args.model,
            dry_run=args.dry_run,
        )
        summary["command"] = "create-comment-from-context"
        summary["dry_run"] = args.dry_run
        summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
        report_path = write_report("create-comment-from-context", summary)
        print(f"\npublicacion create-comment-from-context: creado={summary.get('created')} bloqueado={summary.get('blocked')}")
        print(f"reporte: {report_path}")

    elif args.command == "status":
        run_status()


if __name__ == "__main__":
    main()
