# Configuracion SMTP para DonWeb / Dattatec

## Servidor de salida (SMTP)
- **Servidor:** mail.tudominio.com (o smtp.tudominio.com)
- **Puerto:** 587 (TLS) o 465 (SSL)
- **Autenticacion:** Si (tu email completo + password)

## Obtener datos desde tu panel de DonWeb
1. Ingresa a tu panel de control DonWeb
2. Ve a la seccion "Correos" o "Emails"
3. Ahi veras:
   - Servidor SMTP (ej: c2690515.ferozo.com)
   - Tu direccion de correo (ej: lab@pcmidicenter.com)
   - Puerto recomendado (generalmente 465)

## Configuracion rapida para el agente

Crea un archivo `.env` en la carpeta `D:\AgentesGuille` con:

```env
NURTURE_SMTP_HOST=tu-servidor-smtp
NURTURE_SMTP_PORT=465
NURTURE_SMTP_USER=tu-email@tudominio.com
NURTURE_SMTP_PASS=tu-contraseña-aqui
NURTURE_FROM_EMAIL=tu-email@tudominio.com
NURTURE_FROM_NAME=Bruno de PC MIDI Labs
NURTURE_UNSUBSCRIBE_BASE_URL=https://tu-dominio.com/api/unsubscribe
NURTURE_UNSUBSCRIBE_SECRET=una-clave-larga-privada
```

## Testear configuracion

```bash
# Verificar que lee las variables
python agente_4_nurture.py status

# Enviar un email de prueba (sin guardar en DB)
python -c "
from lib.mailer import send_email
result = send_email('tu-email@tudominio.com', 'Test PC MIDI', 'Este es un email de prueba desde el Agente 4')
print(result)
"
```

## Problemas comunes

### Error de autenticacion
- Verifica que el usuario sea el email completo
- Algunos servidores requieren "App Password" en vez de la contraseña normal

### Error de conexion
- Prueba con puerto 465 en vez de 587
- Verifica que tu firewall no bloquee conexiones salientes

### Emails van a spam
- Configura SPF y DKIM en tu DNS desde el panel de DonWeb
- Usa un email reply-to valido
- Manten el contenido variado (no uses exactamente el mismo texto)
