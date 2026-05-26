"""
Mailer para PC MIDI Center - Agente 4 Nurturing

Configuracion del remitente: Bruno de PC MIDI Labs <lab@pcmidicenter.com>
"""

import os
import smtplib
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


def build_html_body(body_text: str, unsubscribe_url: str = "") -> str:
    """Genera el cuerpo HTML del email con el formato de PC MIDI Labs."""
    unsubscribe_html = ""
    if unsubscribe_url:
        unsubscribe_html = f'''<br>
<span style="font-size: 12px; color: #777;">
Si no queres recibir mas emails de esta guia, podes darte de baja desde
<a href="{unsubscribe_url}" style="color: #777; text-decoration: underline;">este enlace</a>.
</span>'''
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5;">
<div style="max-width: 600px; margin: 20px auto; padding: 30px; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
{body_text.replace(chr(10), '<br>')}
<br><br>
<hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
<p style="font-size: 13px; color: #666; margin: 0;">
<strong>Bruno</strong><br>
PC MIDI Labs - Tecnologia para produccion musical<br>
<a href="https://www.pcmidi.com.ar" style="color: #007bff; text-decoration: none;">www.pcmidi.com.ar</a><br>
<a href="mailto:lab@pcmidicenter.com" style="color: #007bff; text-decoration: none;">lab@pcmidicenter.com</a>
{unsubscribe_html}
</p>
</div>
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
    
    Returns:
        (exito: bool, mensaje_error: str)
    """
    if dry_run:
        print(f"  [DRY-RUN] Email a {to_email}: '{subject}'")
        return True, ""

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]):
        return False, "SMTP no configurado"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = to_email

        # Adjuntar versiones texto y HTML
        if unsubscribe_url:
            body_text = body_text.rstrip() + f"\n\nPara darte de baja de esta secuencia: {unsubscribe_url}"

        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(build_html_body(body_text, unsubscribe_url=unsubscribe_url), "html", "utf-8"))

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
