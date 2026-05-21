# Uso de generacion con IA

## Comando basico

```bash
python build_landings.py generate --limit 20
python build_landings.py validate
python build_landings.py build --base-url https://blog.pcmidicenter.com
```

## Prueba sin guardar

```bash
python build_landings.py generate --limit 3 --dry-run
```

## Investigar oportunidades

Antes de generar una tanda grande, crear oportunidades nuevas a partir de temas semilla y variaciones controladas:

```bash
python build_landings.py research --limit 120 --no-web
```

Sin `--no-web`, el comando intenta usar `ddgs` si esta instalado para sumar ideas detectadas en web:

```bash
python build_landings.py research --limit 120
```

La salida queda en `data/oportunidades_research.jsonl` y `generate` la consume automaticamente junto con `data/temas_semilla.csv`.

Flujo recomendado para escalar:

```bash
python build_landings.py research --limit 120 --no-web
python build_landings.py generate --limit 10 --dry-run
python build_landings.py generate --limit 10
python build_landings.py validate
python build_landings.py build --base-url https://blog.pcmidicenter.com
```

Para llegar a 500, repetir por tandas chicas o medianas, revisando visual y calidad cada tanda antes de ampliar el limite.

## Publicacion en blog.pcmidicenter.com

El build genera URLs limpias para Vercel:

```text
site/
  index.html
  sitemap.xml
  robots.txt
  assets/
  controlador-midi-para-fl-studio/
    index.html
```

Cada landing queda publicada como:

```text
https://blog.pcmidicenter.com/controlador-midi-para-fl-studio/
```

No se usa `/landings/` ni `.html` en produccion. Para publicar en Vercel, configurar el proyecto para servir la carpeta `site/` y agregar el dominio `blog.pcmidicenter.com`. En Network Solutions, crear un CNAME:

```text
Host: blog
Value: cname.vercel-dns.com
```

## Modelo

Por defecto usa `OPENROUTER_MODEL` desde `.env` si existe. Si no, usa `openai/gpt-4o-mini`.

Tambien se puede pasar manualmente:

```bash
python build_landings.py generate --limit 20 --model openai/gpt-4o-mini
```

## Seguridad

- La IA devuelve solo JSON estructurado.
- No puede escribir HTML.
- Solo puede usar categorias de `data/categorias_pcmidi.json`.
- Solo puede usar productos de `data/productos_pcmidi.json`.
- El validador rechaza productos de software y modelos Arturia tipo `V`.
- El validador rechaza claims prohibidos como stock, disponibilidad, precios, distribuidor oficial y soporte tecnico oficial.

## Ultima prueba documentada

Se generaron 3 landings nuevas:

- `controlador-midi-para-ableton-comparativa`
- `placa-sonido-guitarra`
- `microfono-para-podcast-usb-o-xlr`

El sitio quedo con 5 landings en `site/landings/`.
