# Blog PC MIDI Center

Generador de landings HTML estaticas para publicar en `https://blog.pcmidicenter.com/`.

Cada landing queda como URL limpia:

```text
https://blog.pcmidicenter.com/controlador-midi-para-fl-studio/
```

## Build local

```powershell
python build_landings.py validate
python build_landings.py build --base-url https://blog.pcmidicenter.com
```

La salida publicable se genera en:

```text
site/
```

## Vercel

El proyecto incluye `vercel.json` con:

```text
Build Command: python build_landings.py build --base-url https://blog.pcmidicenter.com
Output Directory: site
```

En Vercel, agregar el dominio custom:

```text
blog.pcmidicenter.com
```

En Network Solutions, crear el DNS:

```text
Type: CNAME
Host: blog
Value: cname.vercel-dns.com
```

## SEO

El build genera:

```text
site/index.html
site/sitemap.xml
site/robots.txt
site/<slug>/index.html
```

El sitemap final queda en:

```text
https://blog.pcmidicenter.com/sitemap.xml
```

## Generacion

Para generar nuevas landings con IA:

```powershell
python build_landings.py research --limit 120 --no-web
python build_landings.py generate --limit 10 --dry-run
python build_landings.py generate --limit 10
python build_landings.py validate
python build_landings.py build --base-url https://blog.pcmidicenter.com
```

Las landings aprobadas se guardan en:

```text
data/landings_aprobadas.jsonl
```

## Produccion

Variables requeridas en Vercel para leads, nurturing y conversion:

```text
DATABASE_URL=
NURTURE_SMTP_HOST=
NURTURE_SMTP_PORT=465
NURTURE_SMTP_USER=
NURTURE_SMTP_PASS=
NURTURE_FROM_EMAIL=lab@pcmidicenter.com
NURTURE_FROM_NAME=Bruno de PC MIDI Labs
NURTURE_UNSUBSCRIBE_BASE_URL=https://blog.pcmidicenter.com/api/unsubscribe/
NURTURE_TRACK_BASE_URL=https://blog.pcmidicenter.com
NURTURE_UNSUBSCRIBE_SECRET=
NURTURE_CRON_SECRET=
```

Endpoints a verificar despues del deploy:

```powershell
curl https://blog.pcmidicenter.com/api/stats
curl -X POST https://blog.pcmidicenter.com/api/events -H "content-type: application/json" -d '{"event_type":"page_view","slug":"controlador-midi-para-fl-studio","test":true}'
```

El cron de Vercel ejecuta `/api/nurture` cada 4 horas. Para ejecucion manual, usar `?secret=<NURTURE_CRON_SECRET>`.

## Conversion

Auditoria local o desde un runner con acceso a las mismas variables:

```powershell
python swarm.py conversion --window-days 30 --min-views 50 --limit 50
python swarm.py feedback --window-days 30 --min-views 50 --limit 50
python swarm.py conversion status
```

Ventas externas opcionales pueden agregarse en `data/conversion_sales.jsonl`:

```json
{"created_at":"2026-05-26T00:00:00+00:00","slug":"controlador-midi-para-fl-studio","quantity":1,"amount":0}
```

## Chrome real / flujo root69

La automatizacion de browser ya no usa Playwright, Puppeteer, Selenium ni drivers stealth.
El flujo vigente abre Chrome real con perfil persistente y permite trabajar con cuentas ya logueadas:

```powershell
python swarm.py start-browser
python swarm.py browser-search --channel reddit --limit 5
python swarm.py assist-comment --channel reddit --limit 1
python swarm.py auto-browser --task data/auto_browser_example.json
```

`start-browser` usa `session/chrome-personal/` como perfil aislado. Hay que loguearse una vez en ese Chrome y dejarlo abierto. Las tareas comerciales quedan registradas como borradores o asistencia revisable; no se publica automaticamente en comunidades desde cuentas personales.

El comando `auto-browser` ejecuta acciones secuenciales sobre ese Chrome real. Formato del JSON:

```json
{
  "name": "mi_tarea",
  "actions": [
    {"type": "navigate", "url": "https://example.com", "wait_seconds": 2},
    {"type": "wait_for", "selector": "input[name=q]", "timeout_ms": 10000},
    {"type": "type", "selector": "input[name=q]", "text": "controlador MIDI", "clear": true},
    {"type": "press", "key": "Enter"},
    {"type": "wait", "seconds": 2},
    {"type": "click", "selector": "a.resultado"},
    {"type": "extract", "name": "titulos", "selector": "h1", "attribute": "text"}
  ]
}
```

Acciones disponibles: `navigate`, `wait`, `wait_for`, `click`, `type`, `press`, `extract` y `eval`. Cada corrida genera un reporte en `reports/`.

Para publicar automaticamente entradas ya aprobadas en `data/distribution_log.jsonl`:

```powershell
python swarm.py auto-distribution --channels linkedin,reddit --limit 2 --dry-run
python swarm.py auto-distribution --channels linkedin,reddit --limit 2
python swarm.py auto-distribution --channels all --limit 4 --per-channel 1
```

Por defecto solo publica estados `approved`, `bulk_approved`, `ready_to_publish` o `ready_for_publish`. No publica entradas `blocked`.
`all` reparte entre `linkedin`, `reddit`, `facebook` y `x`. Las piezas con canal `social` pueden reutilizarse para `facebook` y `x`.
