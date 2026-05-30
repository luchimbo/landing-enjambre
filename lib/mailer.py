"""
Mailer para PC MIDI Center - Agente 4 Nurturing

Configuracion del remitente: Bruno de PC MIDI Labs <lab@pcmidicenter.com>
"""

import os
import re
import smtplib
import hmac
import hashlib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Cargar variables de entorno desde .env si existe
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# Configuracion del remitente
DEFAULT_FROM_NAME = os.getenv("NURTURE_FROM_NAME", "Bruno de PC MIDI Labs")
DEFAULT_FROM_EMAIL = os.getenv("NURTURE_FROM_EMAIL", "lab@pcmidicenter.com")

# Configuracion SMTP
SMTP_HOST = os.getenv("NURTURE_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("NURTURE_SMTP_PORT", "465"))
SMTP_USER = os.getenv("NURTURE_SMTP_USER", "")
SMTP_PASS = os.getenv("NURTURE_SMTP_PASS", "").strip()


def _tracking_secret() -> str:
    return os.getenv("NURTURE_UNSUBSCRIBE_SECRET") or os.getenv("NURTURE_SMTP_PASS", "")


def _tracking_base_url() -> str:
    explicit = os.getenv("NURTURE_TRACK_BASE_URL", "").strip()
    if explicit:
        return explicit
    raw = os.getenv("NURTURE_UNSUBSCRIBE_BASE_URL", "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw


def signed_tracking_url(category_url: str, lead_id: int | None = None, slug: str = "", day_number: int | None = None) -> str:
    if not category_url or not lead_id:
        return category_url
    base_url = _tracking_base_url().strip().rstrip("/")
    secret = _tracking_secret()
    if not base_url or not secret:
        return category_url
    day = "" if day_number is None else str(day_number)
    payload = f"{lead_id}|{slug}|{day}|{category_url}"
    token = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    query = urllib.parse.urlencode({"lead_id": lead_id, "slug": slug, "day": day, "url": category_url, "token": token})
    return f"{base_url}/api/click?{query}"


def _parse_email_body(body_text: str) -> str:
    """Convierte texto plano a HTML semantico con checkboxes, listas y titulos."""
    lines = body_text.splitlines()
    html_parts: list[str] = []
    in_list: str | None = None
    list_items: list[str] = []
    in_checklist: bool = False
    checklist_items: list[str] = []

    def flush_list():
        nonlocal in_list, list_items, in_checklist, checklist_items
        if in_checklist:
            items_html = "\n".join(checklist_items)
            html_parts.append(
                f'<div style="background: #fef6f1; border-left: 4px solid #EB6517; padding: 16px 20px; margin: 16px 0; border-radius: 0 8px 8px 0;">'
                f'<ul style="list-style: none; padding: 0; margin: 0;">{items_html}</ul></div>'
            )
            in_checklist = False
            checklist_items = []
        elif in_list == "ul" and list_items:
            items_html = "\n".join(list_items)
            html_parts.append(f'<ul style="padding-left: 20px; margin: 12px 0;">{items_html}</ul>')
            list_items = []
        elif in_list == "ol" and list_items:
            items_html = "\n".join(list_items)
            html_parts.append(f'<ol style="padding-left: 20px; margin: 12px 0;">{items_html}</ol>')
            list_items = []
        in_list = None

    for line in lines:
        stripped = line.strip()

        if stripped == "---":
            flush_list()
            html_parts.append('<hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">')
            continue

        if stripped.startswith("[ ] ") or stripped.startswith("[x] "):
            checked = stripped.startswith("[x] ")
            text = stripped[4:]
            checkbox_icon = "&#x2611;" if checked else "&#x2610;"
            if not in_checklist:
                flush_list()
                in_checklist = True
            checklist_items.append(
                f'<li style="padding: 6px 0; font-size: 15px; line-height: 1.5;">'
                f'<span style="color: #EB6517; font-size: 18px; margin-right: 8px; display: inline-block; width: 20px;">{checkbox_icon}</span>'
                f'<span style="color: #333;">{text}</span></li>'
            )
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            if in_list != "ul":
                flush_list()
                in_list = "ul"
            list_items.append(f'<li style="padding: 4px 0; color: #333;">{text}</li>')
            continue

        if re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s", "", stripped)
            if in_list != "ol":
                flush_list()
                in_list = "ol"
            list_items.append(f'<li style="padding: 4px 0; color: #333;">{text}</li>')
            continue

        if in_list or in_checklist:
            flush_list()

        if not stripped:
            html_parts.append("<br>")
            continue

        # Detectar titulos: lineas cortas sin puntuacion final que parecen titulos
        # o lineas que vienen justo despues de un separador
        is_title = (
            len(stripped) < 80
            and not stripped.endswith((".", ",", "!", "?", ":", ";"))
            and stripped[0].isupper()
            and not re.match(r"^(Si |Para |Tambien |La idea |Si queres)", stripped, re.IGNORECASE)
        )

        if is_title and html_parts and html_parts[-1].startswith("<hr"):
            html_parts.append(
                f'<h2 style="font-size: 20px; color: #1D1D1B; margin: 20px 0 12px 0; font-weight: 600;">{stripped}</h2>'
            )
        elif is_title and not html_parts:
            html_parts.append(
                f'<h2 style="font-size: 20px; color: #1D1D1B; margin: 20px 0 12px 0; font-weight: 600;">{stripped}</h2>'
            )
        else:
            html_parts.append(f'<p style="margin: 0 0 12px 0; font-size: 15px; line-height: 1.6; color: #333;">{stripped}</p>')

    flush_list()
    return "\n".join(html_parts)


def _build_cta_html(category_url: str, category_name: str) -> str:
    """Genera un CTA visual con link a la categoria de PC MIDI."""
    if not category_url:
        return ""
    display_name = category_name or "Ver opciones"
    return f'''
<div style="margin: 28px 0; text-align: center;">
  <div style="background: linear-gradient(135deg, #fef6f1 0%, #fff 100%); border: 2px solid #EB6517; border-radius: 12px; padding: 24px;">
    <p style="margin: 0 0 16px 0; font-size: 16px; color: #1D1D1B; font-weight: 600;">¿Querés ver modelos concretos?</p>
    <p style="margin: 0 0 20px 0; font-size: 14px; color: #666;">Mirá los {display_name} que tenemos en PC MIDI Center y compará según lo que estés buscando.</p>
    <a href="{category_url}" style="display: inline-block; background: linear-gradient(135deg, #EB6517 0%, #d45a14 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 15px; font-weight: 600; letter-spacing: 0.5px; box-shadow: 0 4px 12px rgba(235,101,23,0.3);">Ver {display_name}</a>
  </div>
</div>'''


def build_html_body(body_text: str, unsubscribe_url: str = "", category_url: str = "", category_name: str = "") -> str:
    """Genera el cuerpo HTML del email con el formato de PC MIDI Labs."""
    unsubscribe_html = ""
    if unsubscribe_url:
        unsubscribe_html = f'''<div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid #eee;">
<span style="font-size: 12px; color: #888;">
Si ya no querés recibir estos correos, podés
<a href="{unsubscribe_url}" style="color: #EB6517; text-decoration: underline;">darte de baja acá</a>.
</span></div>'''

    content_html = _parse_email_body(body_text)
    cta_html = _build_cta_html(category_url, category_name)

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f0f0f0; margin: 0; padding: 0;">
<table role="presentation" style="width: 100%; border-collapse: collapse;">
<tr><td align="center" style="padding: 30px 10px;">
<table role="presentation" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); overflow: hidden;">
<tr><td style="background: linear-gradient(135deg, #1D1D1B 0%, #2d2d2b 100%); padding: 28px 32px; text-align: center;">
<div style="font-size: 22px; font-weight: 700; color: #F4F1EA; letter-spacing: 2px;">PC MIDI <span style="color: #EB6517;">LABS</span></div>
<div style="font-size: 12px; color: #aaa; margin-top: 4px; letter-spacing: 1px;">TECNOLOGIA PARA PRODUCCION MUSICAL</div>
</td></tr>
<tr><td style="padding: 32px;">
{content_html}
{cta_html}
</td></tr>
<tr><td style="background-color: #fafafa; padding: 24px 32px; border-top: 1px solid #eee;">
<p style="font-size: 13px; color: #666; margin: 0; line-height: 1.6;">
<strong style="color: #1D1D1B;">Bruno</strong><br>
<span style="color: #888;">PC MIDI Labs - Tecnologia para produccion musical</span><br>
<a href="https://www.pcmidi.com.ar" style="color: #EB6517; text-decoration: none;">www.pcmidi.com.ar</a><br>
<a href="mailto:lab@pcmidicenter.com" style="color: #EB6517; text-decoration: none;">lab@pcmidicenter.com</a>
</p>
{unsubscribe_html}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    from_name: str = DEFAULT_FROM_NAME,
    from_email: str = DEFAULT_FROM_EMAIL,
    dry_run: bool = False,
    unsubscribe_url: str = "",
    category_url: str = "",
    category_name: str = "",
    lead_id: int | None = None,
    slug: str = "",
    day_number: int | None = None,
) -> tuple[bool, str]:
    """
    Envia un email via SMTP.
    
    Args:
        to_email: Destinatario
        subject: Asunto
        body_text: Cuerpo en texto plano
        from_name: Nombre del remitente (default: Bruno de PC MIDI Labs)
        from_email: Email del remitente (default: lab@pcmidicenter.com)
        dry_run: Si True, solo simula el envio
        category_url: URL de la categoria de PC MIDI para el CTA
        category_name: Nombre de la categoria para mostrar en el CTA
    
    Returns:
        (exito: bool, mensaje_error: str)
    """
    if dry_run:
        print(f"  [DRY-RUN] Email a {to_email}: '{subject}'")
        return True, ""

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        return False, "SMTP no configurado"

    try:
        tracked_category_url = signed_tracking_url(category_url, lead_id=lead_id, slug=slug, day_number=day_number)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email

        # Adjuntar versiones texto y HTML
        if unsubscribe_url:
            body_text = body_text.rstrip() + f"\n\nSi ya no querés recibir estos correos, podés darte de baja acá: {unsubscribe_url}"

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(build_html_body(
            body_text,
            unsubscribe_url=unsubscribe_url,
            category_url=tracked_category_url,
            category_name=category_name,
        ), "html", "utf-8"))

        # Enviar via SSL (puerto 465) o STARTTLS (otros puertos)
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(from_email, [to_email], msg.as_string())

        return True, ""
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    # Test rapido
    result = send_email(
        "lab@pcmidicenter.com",
        "Test Mailer PC MIDI Labs",
        "Este es un email de prueba desde el modulo mailer.py."
    )
    print(f"Resultado: {result}")
