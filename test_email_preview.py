"""
Script para previsualizar como se ve el email con CTA y formato mejorado.
Genera un archivo HTML de prueba que podes abrir en el navegador.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.mailer import build_html_body

# Simular un email de dia 0 para microfonos condensadores
body_text = """¡Hola Lucio! Te dejo el recurso para ordenar la eleccion de microfono condensador para voz. La idea es revisar uso real, conexiones, espacio disponible y categoria principal antes de decidir. Tambien vas a ver referencias como audio-technica-at2020, alctron-mc001, midiplus-bm800 cuando ayuden a comparar alternativas.

---
Checklist para elegir microfono condensador para voz

Checklist practica:
[ ] Microfonos Condensadores: Busca patrones polares y sensibilidad.
[ ] Accesorios para Microfonos: Considera brazos, filtros pop y cables.
[ ] Interfaces de Audio: Verifica la cantidad de entradas y calidad de conversion.
[ ] Define tu presupuesto: Establece cuanto estas dispuesto a invertir en un microfono.
[ ] Investiga los tipos de microfonos: Conoce las diferencias entre microfonos dinamicos y condensadores.
[ ] Prueba antes de comprar: Si es posible, prueba los microfonos en una tienda para escuchar como suenan.

Categoria principal para revisar: microfonos-profesionales
Si queres comparar alternativas, podes usar esta lista mientras miras opciones en pcmidi.com.ar."""

html = build_html_body(
    body_text=body_text,
    unsubscribe_url="https://blog.pcmidicenter.com/api/unsubscribe?email=luciopcmidi@gmail.com&token=demo123",
    category_url="https://www.pcmidi.com.ar/microfonos/profesionales/",
    category_name="Microfonos profesionales"
)

output_path = ROOT / "email_preview.html"
output_path.write_text(html, encoding="utf-8")
print(f"Previsualizacion guardada en: {output_path}")
print("Abri el archivo en tu navegador para ver como queda.")
