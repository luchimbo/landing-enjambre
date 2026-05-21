# AGENTS.md

## Proyecto Activo

- La carpeta activa de desarrollo es `D:\AgentesGuille`.
- Todo el sistema nuevo de generacion automatica de landings debe vivir dentro de `D:\AgentesGuille`.
- La salida publicable del sitio estatico debe generarse en `D:\AgentesGuille\site`.
- El flujo anterior basado en `authority-swarm`, SQLite, Markdown y `outputs/web/` queda deprecated salvo pedido explicito del usuario.
- No publicar automaticamente. El usuario decidira cuando subir `site/` al subdominio.

## Objetivo Principal

Generar automaticamente landings HTML estaticas para un futuro subdominio de PC MIDI Center.

Cada landing debe:

- Responder una pregunta, busqueda o problema real de un posible comprador.
- Tener sentido comercial para productos o categorias vendidas en `https://www.pcmidi.com.ar/`.
- Mantener la misma linea visual que `PC MIDI Landing _standalone_.html`.
- Cambiar textos, categorias y CTAs segun el tema.
- Ser HTML estatico indexable para SEO.
- Enlazar a categorias reales internas de `pcmidi.com.ar`.

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
