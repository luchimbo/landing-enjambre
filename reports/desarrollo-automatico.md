# Plan de desarrollo automatico

## Estado actual

- `AGENTS.md` ya declara el flujo nuevo como principal.
- `build_landings.py` ya valida datos y construye HTML estatico en `site/`.
- `data/categorias_pcmidi.json` es el catalogo cerrado de URLs permitidas.
- `data/landings_aprobadas.jsonl` contiene la primera tanda manual de prueba.
- `templates/landing-static-template.html` mantiene la linea visual del standalone en formato estatico e indexable.

## Proxima automatizacion

1. Agregar comando `research`.
   - Leer `data/temas_semilla.csv`.
   - Buscar preguntas relacionadas en fuentes publicas.
   - Guardar oportunidades en `reports/oportunidades.jsonl`.

2. Agregar comando `generate` con IA.
   - Pasar a la IA una oportunidad y el catalogo cerrado de categorias.
   - Exigir respuesta JSON estructurada.
   - Rechazar salida si inventa URLs o categorias.
   - Guardar solo landings validas en `data/landings_aprobadas.jsonl`.

3. Agregar scoring de pertinencia.
   - Debe existir relacion clara con productos PC MIDI.
   - Debe haber intencion de compra, comparacion o armado de setup.
   - Debe mapear a una o mas categorias reales.

4. Agregar control de similitud.
   - Comparar H1, title, meta description y bloques principales.
   - Rechazar landings casi iguales.

5. Escalar por tandas.
   - 20 landings iniciales.
   - 100 si pasan revision visual/SEO.
   - 500 si se sostiene calidad y diferenciacion.

## Prompt base para IA

La IA debe recibir:

- busqueda objetivo
- evidencia o razon de la oportunidad
- catalogo permitido de categorias
- claims prohibidos
- estructura JSON esperada

Regla central:

```text
Genera una landing unica para PC MIDI Center. Debe responder una pregunta, busqueda o problema real de un posible comprador. Solo puede elegir categorias desde el catalogo permitido. No inventes URLs, productos, stock, precios, disponibilidad ni servicios no soportados. Devuelve solo JSON valido.
```

## Limpieza

La limpieza se ejecuta solo despues de validar que este flujo reemplaza al anterior. Ver `reports/cleanup-plan.md`.
