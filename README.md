# Sistema de Landings Automatizado — PC MIDI Center

Sistema completo de generacion automatica, publicacion, distribucion y analisis de landings HTML estaticas para `https://blog.pcmidicenter.com/`. Incluye 6 agentes autonomos que operan via codigo Python/Node.js sin dependencias no-code.

## Que hace esta app

Genera automaticamente landings SEO-optimizadas que responden preguntas reales de compradores de equipos de audio/produccion musical, las publica en un subdominio estatico, captura leads, ejecuta nurturing por email, distribuye contenido en redes/comunidades y audita la presencia de la marca en motores de IA.

### Flujo completo

```
Research (Agente 1) → Generate (Agente 2) → Validate → Build → Deploy → Distribution (Agente 5) → Nurture (Agente 3) → Conversion (Agente 6) → GEO Audit (Agente 4) → Feedback → Research
```

## Arquitectura: 6 Agentes

### Agente 1 — Investigador de Oportunidades
Descubre preguntas y busquedas reales de usuarios. Lee `data/temas_semilla.csv`, genera variaciones de keywords, investiga oportunidades web y guarda resultados en `data/oportunidades_research.jsonl`.

### Agente 2 — Creador de Landings y Lead Magnets
Convierte oportunidades aprobadas en landings HTML estaticas con copy unico. Genera lead magnets (checklists, guias, comparativas) cuando la intencion de busqueda lo permite. Valida SEO, claims, links y productos antes de aprobar.

### Agente 3 — Asesor Invisible / Lead Nurturing
Captura leads desde formularios en landings, guarda en PostgreSQL y ejecuta secuencias de email automatizadas:
- **Dia 0:** Entrega del recurso prometido
- **Dia 3:** Tip tecnico util relacionado con la busqueda
- **Dia 5:** Cierre suave hacia categorias/productos relevantes

### Agente 4 — Auditor GEO / Espia de IAs
Mide presencia de PC MIDI Center en respuestas de ChatGPT, Claude, Gemini, Perplexity. Detecta competidores, asigna scores de visibilidad (0-5) y propone gaps de contenido.

### Agente 5 — Distribucion y Comunidades / Voz Externa
Genera piezas de contenido para Reddit, LinkedIn, foros, newsletters y redes sociales. Prioriza valor tecnico sobre promocion directa. Registra cada pieza en `data/distribution_log.jsonl`.

### Agente 6 — Auditor de Conversion
Cruza visitas, clicks, formularios, leads y ventas para detectar landings con trafico pero baja conversion, sugiere mejoras de CTA, copy, lead magnets y secuencias de nurturing.

## Estructura de archivos

```
D:\AgentesGuille\
  AGENTS.md                          # Documentacion completa de agentes
  README.md                          # Este archivo
  build_landings.py                  # Build engine: validate, build, deploy
  swarm.py                           # Orquestador principal
  api_server.py                      # Servidor API local (Flask/FastAPI)
  
  # Agentes
  agente_browser_cdp.py             # Browser automation via Playwright CDP
  agente_conversion.py              # Agente 6: analisis de conversion
  agente_distribucion.py            # Agente 5: generacion de contenido
  agente_geo_audit.py               # Agente 4: auditoria GEO/IA
  agente_lead_magnets.py            # Generador de lead magnets
  agente_publicacion.py             # Publicacion API (Reddit, LinkedIn, Twitter)
  agente_4_nurture.py               # Agente 3: nurturing de leads
  fill_missing_lead_magnets.py      # Script utilitario para lead magnets
  
  # API Endpoints
  api/
    click.py                        # Tracking de clicks
    events.py                       # Tracking de eventos
    leads.py                        # Captura de leads
    nurture.py                      # Procesamiento de nurturing
    stats.py                        # Estadisticas
    unsubscribe.py                  # Gestion de bajas
  
  # Librerias
  lib/
    env.py                          # Carga de variables de entorno
    mailer.py                       # Envio de emails SMTP
    nurture_pg.py                   # PostgreSQL para leads/nurturing
  
  # Datos
  data/
    categorias_pcmidi.json          # Categorias reales de PC MIDI
    productos_pcmidi.json           # Productos reales de PC MIDI
    temas_semilla.csv               # Temas semilla para research
    oportunidades_research.jsonl    # Oportunidades descubiertas
    landings_aprobadas.jsonl        # Landings aprobadas
    lead_magnets.jsonl              # Metadatos de lead magnets
    content_feedback.jsonl          # Feedback de conversion/GEO
    geo_audits.jsonl                # Resultados de auditoria GEO
    geo_prompts.csv                 # Prompts para auditoria
    distribution_log.jsonl          # Log de distribucion
    distribution_search_tasks.jsonl # Tareas de busqueda
    nurture.db / nurture_metrics.json # DB SQLite para desarrollo
  
  # Templates
  templates/
    landing-static-template.html    # Template base de landings
    dashboard.html                  # Dashboard de administracion
  
  # Salida publicable
  site/                             # HTML estatico generado
    index.html
    sitemap.xml
    robots.txt
    <slug>/index.html              # Landings individuales
  
  # Scripts de automatizacion
  scripts/
    build_catalog.js                # Parser de catalogo TN
    daily.ps1                       # Flujo diario
    weekly.ps1                      # Flujo semanal
    setup-schedule.ps1             # Configuracion de scheduler
    auto_distribution_all.ps1      # Distribucion automatica
  
  # Reportes
  reports/                          # Reportes JSON de cada ejecucion
  
  # Sesiones de browser
  session/                          # Perfiles de Chrome (gitignored)
```

## Instalacion

### Requisitos
- Python 3.10+
- Node.js 18+ (para scripts de catalogo)
- PostgreSQL (para produccion) o SQLite (para desarrollo)

### Setup

```powershell
# Instalar dependencias Python
pip install -r requirements.txt

# Instalar dependencias Node.js (para engagement/catalogo)
cd scripts && npm install

# Configurar variables de entorno
copy .env.example .env
# Editar .env con tus credenciales
```

## Variables de entorno

Crear archivo `.env`:

```env
# OpenRouter (IA para generacion de contenido)
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini

# Base de datos
DATABASE_URL=postgresql://user:pass@host/dbname

# SMTP (para nurturing)
NURTURE_SMTP_HOST=smtp.donweb.com
NURTURE_SMTP_PORT=465
NURTURE_SMTP_USER=lab@pcmidicenter.com
NURTURE_SMTP_PASS=...
NURTURE_FROM_EMAIL=lab@pcmidicenter.com
NURTURE_FROM_NAME=Bruno de PC MIDI Labs
NURTURE_UNSUBSCRIBE_BASE_URL=https://blog.pcmidicenter.com/api/unsubscribe/
NURTURE_TRACK_BASE_URL=https://blog.pcmidicenter.com
NURTURE_UNSUBSCRIBE_SECRET=...
NURTURE_CRON_SECRET=...

# APIs sociales (opcional, para publicacion automatica)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_AUTHOR_URN=...
TWITTER_BEARER_TOKEN=...
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_TOKEN_SECRET=...

# Chrome (para browser automation)
CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
```

## Comandos principales

### Via `swarm.py` (orquestador recomendado)

```powershell
# Flujo semanal completo
python swarm.py weekly --base-url https://blog.pcmidicenter.com

# Comandos individuales
python swarm.py research --limit 50
python swarm.py generate --limit 10 --dry-run
python swarm.py generate --limit 10
python swarm.py validate
python swarm.py build --base-url https://blog.pcmidicenter.com
python swarm.py deploy --base-url https://blog.pcmidicenter.com

# Agentes especificos
python swarm.py nurture --limit 50
python swarm.py conversion --window-days 30 --min-views 50
python swarm.py geo-audit --limit 10
python swarm.py distribution generate --limit 5
python swarm.py distribution approve --limit 25
python swarm.py distribution schedule --limit 10

# Browser automation (asistido)
python swarm.py start-browser
python swarm.py browser-harvest --channel reddit --searches 3
python swarm.py browser-search --channel linkedin --limit 5
```

### Via `build_landings.py` (motor de build)

```powershell
python build_landings.py validate
python build_landings.py build --base-url https://blog.pcmidicenter.com
python build_landings.py deploy --base-url https://blog.pcmidicenter.com
```

## API Endpoints

El sistema expone endpoints REST para tracking, leads y nurturing:

| Endpoint | Metodo | Descripcion |
|----------|--------|-------------|
| `/api/stats` | GET | Estadisticas de landings |
| `/api/leads` | POST | Captura de leads |
| `/api/events` | POST | Tracking de eventos |
| `/api/click` | GET | Tracking de clicks (con redirect) |
| `/api/nurture` | GET | Ejecuta nurturing (cron) |
| `/api/unsubscribe` | GET | Gestion de bajas |

### Ejemplo: capturar un lead

```powershell
curl -X POST https://blog.pcmidicenter.com/api/leads \
  -H "content-type: application/json" \
  -d '{
    "email": "usuario@ejemplo.com",
    "nombre": "Juan",
    "slug": "controlador-midi-para-fl-studio",
    "keyword": "controlador midi fl studio",
    "lead_magnet": "checklist-home-studio",
    "consent": true
  }'
```

### Ejemplo: tracking de evento

```powershell
curl -X POST https://blog.pcmidicenter.com/api/events \
  -H "content-type: application/json" \
  -d '{
    "event_type": "page_view",
    "slug": "controlador-midi-para-fl-studio",
    "referrer": "google"
  }'
```

## Generacion de landings

### Paso a paso

```powershell
# 1. Investigar oportunidades
python swarm.py research --limit 50

# 2. Generar landings (dry-run primero)
python swarm.py generate --limit 10 --dry-run

# 3. Generar landings reales
python swarm.py generate --limit 10

# 4. Validar
python swarm.py validate

# 5. Build
python swarm.py build --base-url https://blog.pcmidicenter.com

# 6. Deploy
python swarm.py deploy --base-url https://blog.pcmidicenter.com
```

### Limites de seguridad

- Maximo 50 landings nuevas por dia
- Validacion automatica de claims prohibidos (precios, stock, disponibilidad)
- Links solo a categorias reales de `data/categorias_pcmidi.json`
- Productos solo de `data/productos_pcmidi.json`

## Lead Magnets

La app puede generar lead magnets automaticos segun la intencion de busqueda:

- **Checklist:** "Checklist para armar tu home studio"
- **Guia breve:** "Guia de compra de interfaces de audio"
- **Comparativa:** "MiniLab 3 vs KeyLab: cual elegir"
- **Plantilla:** "Plantilla de configuracion de DAW"
- **Preset:** "Presets de EQ para voces"

Los metadatos se guardan en `data/lead_magnets.jsonl` y el contenido se entrega por email via `agente_4_nurture.py`.

## Distribucion en redes

### Canales soportados

| Canal | Modo | Descripcion |
|-------|------|-------------|
| Reddit | API + Browser | Respuestas en subreddits de produccion musical |
| LinkedIn | API | Posts educativos B2B |
| Twitter/X | API | Replies y threads |
| Facebook Page | API | Posts de pagina |
| Instagram | Browser assist | Reels/carruseles (asistido) |
| YouTube | Browser assist | Comentarios en videos relevantes |
| Newsletter | Automatico | Digest semanal de landings |

### Flujo de distribucion

```powershell
# Generar piezas de contenido
python swarm.py distribution generate --limit 5

# Aprobar para publicacion
python swarm.py distribution approve --limit 25

# Programar publicacion
python swarm.py distribution schedule --limit 10 --interval-minutes 45

# Ver cola
python swarm.py distribution queue --ready-only

# Publicar automaticamente (APIs oficiales)
python swarm.py auto-distribution --channels linkedin,reddit --limit 2
```

## Nurturing de leads

Secuencia automatica de emails para leads capturados:

1. **Dia 0:** Email de bienvenida + entrega del recurso prometido
2. **Dia 3:** Tip tecnico util relacionado con la busqueda original
3. **Dia 5:** Cierre suave con recomendaciones de productos/categorias

Configuracion:
- Ejecutar cada 2-4 horas via cron
- En Vercel: endpoint `/api/nurture` con `NURTURE_CRON_SECRET`
- Base de datos PostgreSQL para produccion, SQLite para desarrollo

## Auditoria GEO

Mide si PC MIDI aparece en respuestas de IAs cuando usuarios preguntan sobre equipos de audio en Argentina.

```powershell
# Ejecutar auditoria
python swarm.py geo-audit --limit 10

# Ver resultados
cat data/geo_audits.jsonl
```

Scores:
- 0: No aparece
- 3: Aparece como recomendacion fuerte
- 5: Referencia principal

## Conversion y metricas

Analisis de rendimiento de landings:

```powershell
# Ejecutar auditoria de conversion
python swarm.py conversion --window-days 30 --min-views 50

# Ver status
python swarm.py conversion status
```

Metricas analizadas:
- Page views por landing
- Tasa de captura de leads
- Clicks en CTAs comerciales
- Tasa de apertura de emails
- Ventas cruzadas (si hay integracion)

## Despliegue

### Vercel (recomendado)

El proyecto incluye `vercel.json`:

```json
{
  "buildCommand": "python build_landings.py build --base-url https://blog.pcmidicenter.com",
  "outputDirectory": "site"
}
```

1. Conectar repositorio a Vercel
2. Agregar dominio custom: `blog.pcmidicenter.com`
3. Configurar variables de entorno en dashboard de Vercel
4. Deploy automatico en cada push a `main`

### DNS

```
Type: CNAME
Host: blog
Value: cname.vercel-dns.com
```

## Reglas de contenido

### Claims prohibidos
- stock garantizado
- precios / cuotas
- disponibilidad
- distribuidor oficial
- soporte tecnico oficial
- exclusividad
- reparaciones / alquileres / clases

### Wording seguro
- "PC MIDI Center comercializa tecnologia para produccion musical"
- "Ver opciones en PC MIDI Center"
- "Comparar alternativas segun tu caso de uso"

## Desarrollo

### Tests

```powershell
python test_conversion_agent.py
python test_email_preview.py
```

### Scripts utilitarios

```powershell
# Generar catalogo de productos desde CSV
node scripts/build_catalog.js

# Completar lead magnets faltantes
python fill_missing_lead_magnets.py

# Flujo diario completo
.\scripts\daily.ps1

# Flujo semanal completo
.\scripts\weekly.ps1
```

## Stack tecnologico

- **Python 3.10+:** Motor principal, agentes, API
- **Node.js:** Scripts de catalogo y engagement
- **PostgreSQL:** Base de datos para leads y eventos
- **OpenRouter:** APIs de IA (GPT-4o, Claude, etc.)
- **Playwright:** Browser automation
- **Vercel:** Hosting estatico + serverless functions
- **SMTP:** Envio de emails (DonWeb/otro)

## Licencia

MIT — Uso interno para PC MIDI Center.

## Contacto

Para soporte o consultas: `lab@pcmidicenter.com`
