# Configuracion SMTP - PC MIDI Center

Las credenciales reales viven solo en `.env`, que esta ignorado por Git.

## Remitente
**Bruno de PC MIDI Labs** `<lab@pcmidicenter.com>`

## Variables de entorno requeridas
```env
NURTURE_SMTP_HOST=
NURTURE_SMTP_PORT=465
NURTURE_SMTP_USER=
NURTURE_SMTP_PASS=
NURTURE_FROM_EMAIL=lab@pcmidicenter.com
NURTURE_FROM_NAME=Bruno de PC MIDI Labs
NURTURE_UNSUBSCRIBE_BASE_URL=https://blog.pcmidicenter.com/api/unsubscribe
NURTURE_UNSUBSCRIBE_SECRET=
```

## Test de conexion
```bash
python -c "from lib.mailer import send_email; result = send_email('tu-email@dominio.com', 'Test', 'Mensaje de prueba'); print(result)"
```

## Uso desde Python
```python
from lib.mailer import send_email

# Enviar email
result = send_email(
    to_email="destinatario@ejemplo.com",
    subject="Asunto del email",
    body_text="Cuerpo del mensaje"
)
# result = (True, "") si se envio correctamente
# result = (False, "mensaje de error") si fallo
```
