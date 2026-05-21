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
