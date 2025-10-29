# Authenology Telegram Bot

Un asistente virtual de Telegram para Authenology, empresa especializada en firmas electrónicas en Venezuela.

## Características

- 🤖 Chatbot interactivo con menús y respuestas automáticas
- 📅 Sistema de agendamiento de citas con integración a Google Calendar
- 🎤 Procesamiento de mensajes de voz
- ❓ Preguntas frecuentes organizadas por categorías
- 📞 Información de contacto y soporte
- 💾 Base de datos para gestión de usuarios y citas

## Requisitos Previos

- Python 3.8 o superior
- Cuenta de Telegram y un bot de Telegram (obtén el token de @BotFather)
- Cuenta de Google para la API de Google Calendar
- Acceso a una base de datos (SQLite por defecto, pero se puede configurar PostgreSQL/MySQL)

## Instalación

1. Clona el repositorio:
   ```bash
   git clone [URL_DEL_REPOSITORIO]
   cd chatbotN
   ```

2. Crea un entorno virtual y actívalo:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Configura las variables de entorno:
   - Copia el archivo `.env.example` a `.env`
   - Edita el archivo `.env` con tus credenciales

5. Configura Google Calendar API:
   - Ve a [Google Cloud Console](https://console.cloud.google.com/)
   - Crea un nuevo proyecto o selecciona uno existente
   - Habilita la API de Google Calendar
   - Crea credenciales (OAuth 2.0 Client ID)
   - Descarga el archivo JSON de credenciales y guárdalo como `credentials.json` en la raíz del proyecto

## Configuración

### Variables de entorno

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=tu_token_aquí

# Google Calendar API
GOOGLE_CALENDAR_CREDENTIALS=credentials.json
GOOGLE_CALENDAR_ID=tu_calendario@group.calendar.google.com

# Database Configuration
DATABASE_URL=sqlite:///authenology_bot.db

# App Settings
ADMIN_USER_IDS=123456789,987654321  # IDs de administradores separados por comas
SUPPORT_EMAIL=conctacto@authenology.com.ve
SUPPORT_PHONE=+584123379711

# Company Information
COMPANY_NAME=AUTHENTICSING, C.A.
BRAND_NAME=AUTHENOLOGY
WEBSITE=www.authenology.com.ve

# Business Hours (24h format)
BUSINESS_HOURS_START=8
BUSINESS_HOURS_END=17

# Timezone (IANA format)
TIMEZONE=America/Caracas
```

## Uso

1. Inicia el bot:
   ```bash
   python bot.py
   ```

2. Abre Telegram y busca tu bot
3. Usa el comando `/start` para comenzar

## Comandos Disponibles

- `/start` - Inicia el bot y muestra el menú principal
- `/help` - Muestra la ayuda y comandos disponibles
- `/cancel` - Cancela la operación actual

## Estructura del Proyecto

```
chatbotN/
├── .env                    # Variables de entorno
├── .env.example           # Ejemplo de variables de entorno
├── requirements.txt       # Dependencias de Python
├── README.md              # Este archivo
├── bot.py                 # Punto de entrada principal del bot
├── credentials.json       # Credenciales de Google API (no incluido en el repositorio)
├── database/
│   └── models.py          # Modelos de la base de datos
├── services/
│   ├── calendar_service.py # Integración con Google Calendar
│   └── voice_handler.py    # Procesamiento de mensajes de voz
└── token.pickle           # Token de autenticación de Google (se genera automáticamente)
```

## Personalización

### Preguntas Frecuentes
Puedes editar las preguntas frecuentes en `database/models.py` en la función `init_db()`. Las preguntas se cargan automáticamente al iniciar la aplicación.

### Estilos de Mensajes

Los mensajes del bot están en formato Markdown. Puedes personalizar los mensajes en las funcion correspondientes en `bot.py`.

## Despliegue

### En producción

Para ejecutar el bot en producción, se recomienda usar un proceso manager como PM2 o systemd. Aquí hay un ejemplo de configuración para systemd:
{{ ... }}
```ini
# /etc/systemd/system/authenology-bot.service
[Unit]
Description=Authenology Telegram Bot
After=network.target

[Service]
User=usuario
WorkingDirectory=/ruta/al/chatbotN
Environment="PATH=/ruta/al/venv/bin"
ExecStart=/ruta/al/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Luego, recarga systemd y habilita el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable authenology-bot
sudo systemctl start authenology-bot
```

### Con Docker Compose

Esta repo incluye `docker-compose.yml` para levantar todo el stack: bot (Python), mailer (PHP/Apache) y Postgres.

1. Copia variables de entorno y configúralas:
   ```bash
   cp .env.example .env
   # Edita .env y coloca:
   # TELEGRAM_BOT_TOKEN=...
   # SMTP_* para el servicio mailer (host, usuario, app password, etc.)
   # Opcional: precios, ADMIN_NOTIFY_EMAILS, etc.
   ```

2. Levanta los servicios:
   ```bash
   docker compose up -d --build
   ```

3. Servicios:
   - Bot: corre en segundo plano y se conecta a Telegram con `TELEGRAM_BOT_TOKEN`.
   - Mailer: disponible en `http://localhost:8081` (puedes cambiar el puerto en `docker-compose.yml`).
   - Postgres: persistencia en volumen `pgdata`.

4. Logs y estado:
   ```bash
   docker compose ps
   docker compose logs -f bot
   docker compose logs -f mailer
   docker compose logs -f postgres
   ```

5. Variables importantes en Compose:
   - `APPOINTMENTS_DB_URL` y `QUESTIONS_DB_URL` se sobreescriben adentro del contenedor para apuntar a `postgres` por hostname.
   - `MAILER_URL` por defecto es `http://mailer` dentro de la red de Docker.

### Buenas prácticas de seguridad

- No comprometas secretos. El archivo `.gitignore` ya excluye `.env`, `credentials.json` y otros.
- Si un token o contraseña ya estuvo expuesto (por ejemplo en `.env` local), rota esas credenciales (Telegram BotFather, contraseña/app password SMTP) antes de publicar.
- Usa `.env.example` como plantilla segura para compartir configuración sin secretos.

## Solución de Problemas

### Error de autenticación de Google Calendar

Si recibes errores de autenticación de Google Calendar:

1. Asegúrate de que el archivo `credentials.json` esté en el directorio raíz
2. Verifica que hayas habilitado la API de Google Calendar
3. Elimina el archivo `token.pickle` y vuelve a ejecutar el bot para autenticarte de nuevo

### Problemas con la base de datos

Si hay problemas con la base de datos:

1. Verifica que la URL de la base de datos en `.env` sea correcta
2. Asegúrate de que el usuario de la base de datos tenga los permisos necesarios
3. Si usas SQLite, verifica que el directorio tenga permisos de escritura

## Contribuir

Las contribuciones son bienvenidas. Por favor, crea un issue para discutir los cambios propuestos antes de hacer un pull request.

## Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

