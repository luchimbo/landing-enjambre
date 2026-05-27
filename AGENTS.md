# AGENTS.md

## Proyecto Activo

- La carpeta activa de desarrollo es `D:\AgentesGuille`.
- Todo el sistema nuevo de generacion automatica de landings debe vivir dentro de `D:\AgentesGuille`.
- La salida publicable del sitio estatico debe generarse en `D:\AgentesGuille\site`.
- El flujo anterior basado en `authority-swarm`, SQLite, Markdown y `outputs/web/` queda deprecated salvo pedido explicito del usuario.
- El sistema objetivo debe publicar automaticamente cuando pasen todas las validaciones automaticas obligatorias.

## Objetivo Principal

Generar automaticamente landings HTML estaticas para un futuro subdominio de PC MIDI Center.

Cada landing debe:

- Responder una pregunta, busqueda o problema real de un posible comprador.
- Tener sentido comercial para productos o categorias vendidas en `https://www.pcmidi.com.ar/`.
- Mantener la misma linea visual que `PC MIDI Landing _standalone_.html`.
- Cambiar textos, categorias y CTAs segun el tema.
- Ser HTML estatico indexable para SEO.
- Enlazar a categorias reales internas de `pcmidi.com.ar`.

## Formato Editorial De Las Landings

- Las proximas landings deben funcionar como una mezcla entre landing comercial y articulo SEO util.
- Deben tener mas texto, mas informacion y mas desarrollo que una landing breve tradicional, sin cambiar el diseno base.
- Apuntar como referencia a unas 1000-1600 palabras por pagina cuando el tema lo permita.
- Incluir una respuesta rapida a la busqueda, desarrollo explicativo, criterios de compra, casos de uso, errores comunes, categorias recomendadas y FAQs completas.
- El contenido debe ayudar genuinamente a decidir que tipo de producto conviene antes de llevar al usuario a los CTAs.
- Los CTAs deben seguir siendo claros y comerciales, pero integrados naturalmente dentro de una guia editorial.
- Evitar relleno generico: cada bloque debe responder al tema, la intencion de busqueda y las categorias reales de PC MIDI.

## Fuente Visual Obligatoria

- `PC MIDI Landing _standalone_.html` es la fuente visual canonica.
- No redisenar la landing sin permiso.
- No cambiar colores, lenguaje visual, estructura general ni componentes base sin permiso.
- Se acepta que la altura de bloques varie por textos mas largos o cortos, pero no se debe romper el layout.
- Corregir el problema del hero/H1 cuando las palabras queden pegadas o sin espacios.
- La IA no debe generar HTML libre ni tocar el diseno; debe generar datos estructurados para inyectar en el template.

## Estructura Esperada

```text
D:\AgentesGuille\
  AGENTS.md
  PC MIDI Landing _standalone_.html
  build_landings.py
  data\
    categorias_pcmidi.json
    productos_pcmidi.json
    temas_semilla.csv
    landings_aprobadas.jsonl
  templates\
    landing-static-template.html
  site\
    index.html
    sitemap.xml
    robots.txt
    landings\
  reports\
```

## Automatizacion

El flujo objetivo es:

1. Partir de temas semilla definidos para PC MIDI.
2. Investigar preguntas, busquedas y problemas reales de usuarios.
3. Filtrar oportunidades que no tengan sentido para PC MIDI.
4. Mapear cada oportunidad a categorias reales permitidas.
5. Usar IA para generar copy unico y estructurado.
6. Validar SEO, claims, unicidad y links.
7. Construir paginas HTML estaticas en `site/landings/`.
8. Generar `site/index.html`, `site/sitemap.xml` y `site/robots.txt`.
9. Publicar automaticamente solo si la validacion y el build terminan sin errores.
10. Guardar reportes auditables de cada ejecucion, aprobacion, bloqueo y publicacion.

## Automatizacion Por Tiempo Y Dependencias

El sistema debe funcionar sin control humano obligatorio. Cada agente puede ejecutarse por calendario o por dependencia cuando otro agente produce nueva informacion util.

Principios:

- La publicacion automatica esta permitida solo despues de una compuerta automatica exitosa.
- Si falla cualquier validacion critica, no se publica nada y se guarda un reporte en `reports/`.
- Cada ejecucion debe dejar logs o reportes auditables con fecha, comando, archivos afectados, landings generadas, landings bloqueadas y motivo.
- Ningun agente debe depender de conversaciones libres entre modelos; debe leer y escribir archivos estructurados, base de datos o reportes.
- Debe existir un limite automatico de crecimiento por ejecucion y por dia para evitar publicar tandas masivas por error.
- El limite operativo inicial para creacion de landings es 50 landings nuevas por dia como maximo, siempre sujeto a validacion y build exitosos.
- Antes de publicar, debe conservarse un backup o manifest de la version anterior para permitir rollback.

Frecuencia sugerida por agente:

- Agente 1 Investigador De Oportunidades: ejecutar semanalmente y tambien cuando `data/content_feedback.jsonl` o `data/geo_audits.jsonl` reciban oportunidades nuevas.
- Agente 2 Creador De Landings Y Lead Magnets: ejecutar diariamente si existen oportunidades aprobables nuevas, con limite maximo de 50 landings por dia; tambien puede activarse despues del Investigador o del Auditor De Conversion cuando haya mejoras accionables. Genera landings y, cuando la intencion lo permite, crea el lead magnet inline.
- Agente 3 Asesor Invisible / Lead Nurturing: ejecutar diariamente o cada pocas horas para procesar mensajes pendientes, eventos y secuencias dia 0, dia 3 y dia 5.
- Agente 4 Auditor GEO / Espia De IAs: ejecutar semanalmente o quincenalmente; tambien puede ejecutarse despues de publicar una tanda nueva para medir si empiezan a aparecer nuevas URLs o menciones.
- Agente 5 Distribucion Y Comunidades / Voz Externa: ejecutar despues de publicar landings aprobadas y cuando GEO o Conversion detecten oportunidades de autoridad externa.
- Agente 6 Auditor De Conversion: ejecutar semanalmente y despues de acumular suficientes visitas, clicks, formularios, ventas o eventos nuevos.

Dependencias entre agentes:

```text
Agente 1 research
  -> si genera oportunidades nuevas
  -> Agente 2 generate (landings + lead magnets inline)
  -> validate
  -> build
  -> deploy automatico si todo pasa
  -> report

Agente 4 geo-audit
  -> data/geo_audits.jsonl
  -> data/content_feedback.jsonl
  -> Agente 1 research o Agente 2 generate si detecta oportunidades claras
  -> Agente 5 distribution si detecta necesidad de autoridad externa

Agente 3 nurture
  -> DB leads + lead_events + nurture_messages
  -> Agente 6 conversion cuando haya eventos suficientes

Agente 6 conversion
  -> data/content_feedback.jsonl
  -> Agente 1 research para nuevas oportunidades
  -> Agente 2 generate para mejoras de landings existentes y lead magnets

Agente 5 distribution
  -> publicaciones externas permitidas + eventos de referencia
  -> Agente 4 geo-audit para medir si mejora presencia en IAs
  -> Agente 6 conversion para medir trafico referido y conversion
```

Cadencia operativa sugerida:

```text
Cada 2-4 horas: nurture
Diario: validate de datos criticos, generate hasta 50 landings nuevas si hay oportunidades aprobables, procesamiento de leads pendientes y auditoria liviana de conversion
Semanal: research -> generate -> validate -> build -> deploy -> report
Semanal o quincenal: geo-audit
Despues de cada deploy: report -> distribution -> geo-audit opcional -> conversion cuando existan datos
Mensual: limpieza, revision de duplicados, auditoria de calidad y control de crecimiento
```

Politica de publicacion automatica:

- Publicar automaticamente solo si `validate` y `build` pasan sin errores.
- Bloquear publicacion si hay claims prohibidos, links invalidos, productos inexistentes, duplicados fuertes, HTML fuera de `site/`, sitemap incorrecto o robots.txt incorrecto.
- Bloquear publicacion si una tanda supera el limite configurado de landings nuevas por ejecucion, por dia o por semana.
- Guardar reporte de bloqueo en `reports/` con causa accionable.
- Guardar manifest de publicacion con fecha, slugs publicados, hashes o tamanos de archivos, sitemap generado y resultado del deploy.
- Mantener mecanismo de rollback o backup de la version anterior antes de reemplazar el sitio publicado.
- No publicar landings marcadas como rechazadas, incompletas o con validacion pendiente.

## Regla Codigo-Only

- Queda prohibido usar n8n, Make, Zapier u otras herramientas no-code como parte del flujo principal.
- Toda automatizacion debe resolverse con codigo propio, scripts versionables, APIs controladas, cron jobs, base de datos y archivos estructurados.
- Se permiten GitHub Actions, Vercel Cron, Windows Task Scheduler, cron en VPS y scripts Python propios.
- La publicacion automatica debe resolverse por codigo propio o infraestructura controlada, nunca por herramientas no-code.
- La automatizacion puede investigar, generar, validar, construir, publicar, reportar y bloquear despliegues sin control humano obligatorio.
- La publicacion automatica solo puede ocurrir si pasan las validaciones obligatorias y queda reporte auditable.

## Arquitectura De Agentes

El sistema objetivo se organiza en 6 agentes operativos. Los agentes no deben depender de conversaciones libres entre modelos; deben comunicarse mediante archivos JSONL, CSV, base de datos y reportes auditables.

### Agente 1: Investigador De Oportunidades

Responsabilidad: descubrir preguntas, busquedas y problemas reales de compradores potenciales.

Debe:

- Leer `data/temas_semilla.csv`.
- Generar variaciones de keywords.
- Investigar oportunidades con busquedas web o APIs disponibles.
- Filtrar temas sin relacion comercial con PC MIDI.
- Mapear oportunidades a categorias reales.
- Guardar oportunidades en `data/oportunidades_research.jsonl`.
- Alimentarse tambien de `data/content_feedback.jsonl` y `data/geo_audits.jsonl` cuando existan.
- Activarse por calendario semanal y por dependencia cuando GEO o Feedback generen nuevas oportunidades.

### Agente 2: Creador De Landings Y Lead Magnets

Responsabilidad: convertir oportunidades aprobadas en landings HTML estaticas indexables, con lead magnets inline cuando la intencion de busqueda lo permita.

Debe:

- Generar copy unico y estructurado.
- Cruzar categorias reales de `data/categorias_pcmidi.json`.
- Cruzar productos reales de `data/productos_pcmidi.json`.
- Crear `lead_magnet` inline cuando la landing tenga intencion apta para captura: checklist, guia breve, plantilla, preset, comparativa, configuracion, script o mapa de decision.
- Guardar metadatos del lead magnet en el bloque `lead_magnet` de la landing o en `data/lead_magnets.jsonl`.
- Generar asunto y texto de entrega para la secuencia dia 0 del lead magnet.
- Validar que el recurso prometido sea realista, especifico y relacionado con la busqueda.
- Validar SEO, claims, unicidad, links y productos.
- Construir `site/`.
- Leer feedback desde `data/content_feedback.jsonl` para proponer mejoras o nuevas landings.
- Activarse diariamente si existen oportunidades aprobables pendientes, despues del Investigador cuando haya oportunidades nuevas o despues del Auditor De Conversion cuando haya mejoras accionables.
- Respetar un limite inicial de 50 landings nuevas por dia para no saturar el sitio ni publicar tandas masivas.
- Disparar validacion, build y publicacion automatica solo si la tanda queda aprobada.

No debe:

- Prometer archivos, presets, scripts o plantillas que el sistema no pueda entregar.
- Usar claims de stock, precio, disponibilidad, cuotas o soporte oficial.
- Crear lead magnets genericos que no dependan de la intencion de busqueda.

### Agente 3: Asesor Invisible / Lead Nurturing

Responsabilidad: transformar visitas en contactos calificados y ejecutar seguimiento por codigo.

Debe:

- Renderizar formularios en landings.
- Capturar email, WhatsApp opcional, nombre opcional, consentimiento, slug, keyword, categoria y productos.
- Guardar leads en base de datos.
- Crear mensajes pendientes de nutricion.
- Enviar el recurso prometido en dia 0.
- Enviar un tip tecnico util en dia 3.
- Enviar un cierre suave hacia categorias o productos permitidos en dia 5.
- Registrar eventos de envio, clicks, bajas y errores.
- Activarse cada 2-4 horas o diariamente, segun volumen, para procesar mensajes pendientes y eventos.
- Alimentar al Agente 6 cuando existan datos suficientes para detectar patrones.

No debe:

- Usar n8n, Make, Zapier ni herramientas no-code.
- Prometer recursos que PC MIDI no pueda entregar.
- Afirmar stock, precios, cuotas, descuentos ni disponibilidad.
- Enviar WhatsApp sin API oficial, opt-in y cumplimiento legal.

### Agente 4: Auditor GEO / Espia De IAs

Responsabilidad: medir presencia de PC MIDI Center en respuestas de asistentes y motores de IA.

Debe:

- Leer prompts estrategicos desde `data/geo_prompts.csv`.
- Consultar APIs disponibles de OpenAI, Anthropic, Gemini, Perplexity u otros proveedores.
- Simular preguntas reales de compradores.
- Detectar menciones a PC MIDI Center.
- Detectar competidores.
- Guardar respuestas completas y URLs citadas.
- Asignar score de visibilidad.
- Proponer oportunidades de contenido en `data/content_feedback.jsonl`.
- Activarse semanal o quincenalmente, y opcionalmente despues de cada tanda publicada.
- Alimentar al Investigador, al Creador y al Agente De Distribucion cuando detecte gaps de contenido, necesidad de autoridad externa o menciones competitivas relevantes.

Score sugerido:

- `0`: PC MIDI no aparece.
- `1`: PC MIDI aparece sin recomendacion clara.
- `2`: PC MIDI aparece como opcion secundaria.
- `3`: PC MIDI aparece como recomendacion fuerte.
- `4`: PC MIDI aparece recomendado con link o cita relevante.
- `5`: PC MIDI aparece como referencia principal para la consulta.

### Agente 5: Distribucion Y Comunidades / Voz Externa

Responsabilidad: ampliar la autoridad externa de las landings en canales permitidos y comunidades relevantes.

Debe:

- Leer landings publicadas, categorias relevantes, prompts GEO, oportunidades de contenido y reportes de conversion.
- Proponer publicaciones, respuestas, snippets tecnicos y piezas de distribucion para Reddit, foros, comunidades, blogs, newsletters o redes donde corresponda.
- Mantener tono util, tecnico y de musico/productor independiente sin suplantar identidades reales.
- Registrar cada publicacion o pieza propuesta en `data/distribution_log.jsonl` con canal, URL, landing vinculada, fecha, estado y responsable/API.
- Priorizar respuestas utiles que aporten contexto real antes de incluir links.
- Activarse despues de cada deploy aprobado y cuando GEO detecte que PC MIDI no aparece en respuestas relevantes.

No debe:

- Crear perfiles falsos, simular usuarios reales, hacer spam ni violar reglas de comunidades.
- Publicar claims comerciales no verificados.
- Automatizar acciones en plataformas donde sus terminos lo prohiban.
- Usar links de forma masiva o repetitiva sin aporte real.

### Agente 6: Auditor De Conversion

Responsabilidad: cruzar visitas, clicks, formularios, leads, ventas y facturacion para mejorar landings, lead magnets, nurturing y distribucion.

Debe:

- Leer eventos de visitas, clicks, formularios y conversiones.
- Detectar landings con mucho trafico y baja captura.
- Detectar landings con leads pero pocos clicks comerciales.
- Evaluar lead magnets con mejor y peor rendimiento.
- Cruzar ventas reales, links de pago, ecommerce o facturacion cuando existan integraciones disponibles.
- Sugerir mejoras de CTA, copy, FAQs, seccion central, lead magnet, secuencia de nurturing o enfoque de distribucion.
- Guardar recomendaciones en `data/content_feedback.jsonl`.
- Activarse semanalmente y tambien cuando el Asesor Invisible acumule eventos suficientes.
- Alimentar al Investigador con nuevas oportunidades y al Creador con mejoras de paginas existentes.

## Comunicacion Entre Agentes

Flujo principal:

```text
data/temas_semilla.csv
  -> Agente Investigador
  -> data/oportunidades_research.jsonl
  -> Agente Creador (landings + lead magnets inline)
  -> data/landings_aprobadas.jsonl
  -> site/
  -> validate -> build -> deploy automatico
  -> Agente Asesor Invisible
  -> DB leads + nurture_messages + lead_events
  -> Agente Auditor De Conversion
  -> data/content_feedback.jsonl
  -> Agente Investigador / Agente Creador
```

Flujo GEO:

```text
data/geo_prompts.csv
  -> Agente Auditor GEO
  -> data/geo_audits.jsonl
  -> data/content_feedback.jsonl
  -> Agente Investigador / Agente Creador / Agente Distribucion
```

Flujo de autoridad externa:

```text
deploy aprobado
  -> Agente Distribucion Y Comunidades
  -> data/distribution_log.jsonl
  -> Agente Auditor GEO
  -> Agente Auditor De Conversion
```

## Lead Magnets Y Nutricion

Cada landing puede incluir un bloque `lead_magnet`:

- `title`: nombre del recurso o beneficio.
- `description`: promesa concreta relacionada con la busqueda.
- `cta_text`: texto del boton de captura.
- `resource_type`: checklist, guia breve, plantilla, preset, comparativa o configuracion.
- `delivery_subject`: asunto sugerido para el primer mensaje.

Cada landing puede incluir un bloque `nurture_sequence`:

- Dia 0: entrega del recurso prometido.
- Dia 3: tip tecnico util relacionado con la busqueda.
- Dia 5: cierre suave hacia categoria o productos relevantes.

La secuencia debe aportar valor real y mantener relacion directa con la intencion original del usuario. No enviar spam generico.

## Captura De Leads

Las landings pueden incluir un formulario visible para capturar:

- Email.
- WhatsApp opcional.
- Nombre opcional.
- Slug de landing.
- Keyword objetivo.
- Categoria principal.
- Productos mencionados.
- Lead magnet solicitado.
- Consentimiento del usuario.

Como el sitio estatico no debe guardar datos por si mismo, el formulario debe enviar los datos a una API propia, por ejemplo `POST /api/leads`.

No guardar leads dentro de `site/`.

## Auditor GEO

El Auditor GEO debe simular consultas reales de potenciales compradores y registrar:

- Si PC MIDI Center aparece mencionado.
- En que posicion o contexto aparece.
- Si aparecen competidores.
- Que argumentos usa la IA para recomendar una tienda.
- Si cita landings, categorias o URLs de PC MIDI.
- Si la respuesta contiene informacion incorrecta o desactualizada.
- Que temas parecen faltar en el ecosistema de contenido.

Ejemplos de consultas validas:

- Donde comprar un controlador MIDI en Argentina.
- Tiendas confiables para comprar interfaces de audio en Buenos Aires.
- Mejor lugar para comprar microfonos para podcast en Argentina.
- Donde comprar sintetizadores Arturia en Argentina.
- Tiendas de audio profesional para home studio.
- Que tienda recomendas para armar un home studio en Argentina.
- Donde conseguir controladores MIDI para Ableton en Argentina.

Evitar preguntas que obliguen a la IA a afirmar claims no verificados como stock, precios, cuotas, soporte tecnico oficial o disponibilidad.

## Base De Datos Objetivo

Para produccion se recomienda PostgreSQL en Neon, Supabase, Vercel Postgres u otro proveedor equivalente.

SQLite puede usarse solo para desarrollo local o pruebas.

Tablas minimas:

- `leads`
- `lead_events`
- `nurture_messages`
- `geo_audits`
- `content_feedback`
- `distribution_events`

## Orquestador Objetivo

El sistema puede incluir un `swarm.py` para ejecutar agentes por comando.

Comandos objetivo:

```bash
python swarm.py research
python swarm.py generate
python swarm.py build
python swarm.py nurture
python swarm.py geo-audit
python swarm.py distribution
python swarm.py conversion
python swarm.py feedback
python swarm.py weekly
python swarm.py deploy
python swarm.py rollback
```

El comando semanal deberia ejecutar:

```text
validate -> research -> generate -> validate -> build -> deploy -> distribution -> report
```

La publicacion automatica queda permitida dentro de `weekly` y `deploy` solo si todas las validaciones pasan.

Comandos calendarizados sugeridos:

```text
python swarm.py nurture       cada 2-4 horas
python swarm.py validate      diario
python swarm.py generate      diario, hasta 50 landings nuevas si hay oportunidades aprobables
python swarm.py weekly        semanal
python swarm.py geo-audit     semanal o quincenal
python swarm.py distribution  despues de cada deploy aprobado
python swarm.py conversion    semanal o por volumen de eventos
python swarm.py feedback      alias compatible para conversion/content_feedback
```

El orquestador debe cortar el flujo si una etapa critica falla. Por ejemplo, si `validate` falla despues de `generate`, no debe ejecutar `build` ni `deploy`.

## Relevancia Para PC MIDI

No generar una landing si la busqueda no puede ser respondida por productos o categorias reales de PC MIDI Center.

Temas validos tipicos:

- controlador MIDI para FL Studio
- controlador MIDI para Ableton
- interfaz de audio para grabar voz en casa
- placa de sonido para guitarra
- microfono para podcast
- microfono para streaming
- monitores de estudio para home studio chico
- auriculares cerrados para grabar voces
- sintetizador para aprender sintesis
- bateria electronica para departamento
- setup de streaming con buen audio
- Arturia MiniLab 3 vs KeyLab
- home studio para principiantes

Temas a descartar:

- Busquedas sin relacion clara con productos vendidos por PC MIDI.
- Temas puramente informativos sin camino util a categoria/producto.
- Duplicados con cambios minimos de wording.
- Temas que requieren servicios no soportados como reparaciones, alquileres, clases formales, grabacion, mezcla o mastering.

## Links Permitidos

- Los CTAs y links comerciales deben apuntar a categorias reales dentro de `https://www.pcmidi.com.ar/`.
- La IA no puede inventar URLs.
- La IA solo puede elegir URLs desde `data/categorias_pcmidi.json`.
- Preferir categorias especificas antes que la home.
- La home se usa solo cuando no exista una categoria segura.
- Cada landing debe tener un CTA principal y links secundarios coherentes con el tema.

## Marcas Y Modelos Permitidos

- La IA puede mencionar marcas y modelos solo si existen en `data/productos_pcmidi.json`.
- No inventar productos, modelos, marcas ni URLs de producto.
- Los productos mencionados deben estar publicados en `https://www.pcmidi.com.ar/productos/`.
- Priorizar hardware. No incluir software Arturia tipo `Modular V`, `CS-80 V`, `CMI V`, `Synclavier V` ni packs de plugins salvo pedido explicito del usuario.
- La landing puede usar productos como ejemplos de referencia, pero no debe afirmar stock, precio ni disponibilidad.
- El CTA principal debe priorizar categorias; los productos pueden aparecer como referencias o links secundarios cuando ayuden a responder la busqueda.
- Cada producto debe estar conectado con una categoria aprobada de `data/categorias_pcmidi.json`.

## Reglas Para IA

La IA debe generar landings distintas entre si.

Cada landing debe tener:

- busqueda objetivo
- intencion del usuario
- title SEO unico
- meta description unica
- H1 unico
- hero/subtitulo unico
- problema concreto que resuelve
- criterios de compra
- categorias PC MIDI relevantes
- marcas/modelos reales de PC MIDI cuando aporten claridad
- FAQs
- CTA principal
- CTAs secundarios

No generar landings genericas, duplicadas o sin relacion clara con productos PC MIDI.

## Claims Prohibidos

No afirmar:

- stock garantizado
- precios
- disponibilidad
- distribuidor oficial
- soporte tecnico oficial
- exclusividad
- reparaciones
- alquileres
- clases formales
- grabacion, mezcla o mastering
- que PC MIDI fabrica productos de terceros

Wording seguro:

- `PC MIDI Center comercializa tecnologia para produccion musical`
- `ver opciones en PC MIDI Center`
- `comparar alternativas segun tu caso de uso`
- `consultar opciones disponibles en pcmidi.com.ar`

## SEO Requerido

Cada pagina debe incluir:

- HTML estatico con contenido visible en el codigo fuente.
- `<html lang="es-AR">`.
- `<title>` unico.
- `<meta name="description">` unica.
- Canonical configurable.
- Un solo H1.
- H2/H3 logicos.
- FAQ visible.
- FAQ JSON-LD cuando aplique.
- Links a categorias relevantes de PC MIDI.
- Diseno responsive.
- Inclusion en `sitemap.xml`.
- Referencia desde `robots.txt`.

## Validacion Obligatoria

Antes de aprobar una tanda:

- Todos los archivos generados deben estar dentro de `site/`.
- Cada landing debe tener slug, title, meta description y H1 unicos.
- Cada landing debe responder una pregunta o busqueda concreta.
- Cada landing debe mapear a una o mas categorias aprobadas.
- Cada link comercial debe existir en `data/categorias_pcmidi.json`.
- Cada producto o modelo mencionado debe existir en `data/productos_pcmidi.json`.
- No debe haber claims prohibidos.
- No debe haber paginas casi iguales.
- `sitemap.xml` debe incluir todas las landings generadas.
- `robots.txt` debe referenciar el sitemap.
- El deploy automatico debe bloquearse si cualquiera de estas validaciones falla.
- Cada bloqueo debe generar reporte en `reports/` con los slugs afectados y el motivo.
- Cada publicacion exitosa debe generar manifest con fecha, comando, archivos publicados y resultado.

## Limpieza Del Proyecto

El plan incluye eliminar o archivar lo que no sea importante para el nuevo funcionamiento.

No borrar archivos sensibles o potencialmente utiles sin revisar. En particular:

- No borrar `.env` sin confirmacion.
- No borrar `PC MIDI Landing _standalone_.html`.
- No borrar datos utiles de categorias, temas, reportes o landings aprobadas.

Candidatos a eliminar/archivar cuando el nuevo flujo este estable:

- `__pycache__/`
- archivos temporales `tmp_*`
- `outputs/` viejo
- `data/app.db` si ya no se usa
- `src/authority_swarm/` si se confirma que queda totalmente reemplazado

## Comandos Esperados

Desde `D:\AgentesGuille`:

```bash
python build_landings.py validate
python build_landings.py build
python -m py_compile build_landings.py
```

## Estrategia De Escala

- Generar primero una tanda chica de prueba.
- Revisar visual, SEO, links y pertinencia comercial.
- Escalar a 100 solo si la tanda chica esta bien.
- Escalar a 500 solo si la calidad y diferenciacion se sostienen.
