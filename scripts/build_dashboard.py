"""
Copia templates/dashboard.html → site/dashboard/index.html durante el build de Vercel.
Reemplaza la variable Jinja2 {{ auth_b64 }} por string vacío (el dashboard es abierto).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src  = ROOT / "templates" / "dashboard.html"
dest = ROOT / "site" / "dashboard" / "index.html"

dest.parent.mkdir(parents=True, exist_ok=True)
content = src.read_text(encoding="utf-8")
content = content.replace("{{ auth_b64 }}", "")
dest.write_text(content, encoding="utf-8")
print(f"Dashboard copiado a {dest}")
