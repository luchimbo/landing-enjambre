# Plan de limpieza

No ejecutar limpieza destructiva sin confirmacion del usuario.

## Conservar

- `AGENTS.md`
- `PC MIDI Landing _standalone_.html`
- `build_landings.py`
- `data/categorias_pcmidi.json`
- `data/temas_semilla.csv`
- `data/landings_aprobadas.jsonl`
- `templates/landing-static-template.html`
- `site/`
- `.env` salvo confirmacion explicita

## Candidatos a eliminar cuando el flujo nuevo este validado

- `__pycache__/`
- `tmp_ig_debug.html`
- `tmp_debug_ig.py`
- `outputs/`
- `data/app.db`
- `src/authority_swarm/`

## Criterio

Eliminar o archivar solo despues de confirmar que el generador estatico nuevo reemplaza completamente el flujo anterior.
