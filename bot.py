import os
import logging
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional
import re
import smtplib
from email.mime.text import MIMEText
from difflib import SequenceMatcher
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
    AIORateLimiter,
)
from dotenv import load_dotenv
import pytz

# Import database models and services
from database.appointments_db import (
    User, Appointment, init_db as init_appt_db, get_db as get_appt_db,
    UserType, AppointmentStatus, SessionLocal as ApptSession
)
from database.questions_db import (
    FAQ, UserQuestion, Feedback, init_db as init_q_db, seed_faqs, SessionLocal as QuestionsSession
)
from services.voice_handler import VoiceHandler

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define conversation states
(
    START,
    HANDLE_MENU,
    SCHEDULE_APPOINTMENT,
    SELECT_DATE,
    SELECT_TIME,
    CONFIRM_APPOINTMENT,
    HANDLE_FAQ,
    HANDLE_CONTACT,
    HANDLE_VOICE,
    COLLECT_EMAIL,
) = range(10)

# Initialize services
voice_handler = VoiceHandler()

# Settings
TIMEZONE = os.getenv('TIMEZONE', 'America/Caracas')
PRICE_PERSONA_NATURAL = os.getenv('PRICE_PERSONA_NATURAL', '').strip()
PRICE_PERSONA_JURIDICA = os.getenv('PRICE_PERSONA_JURIDICA', '').strip()
PRICE_RENOVACION = os.getenv('PRICE_RENOVACION', '').strip()
PRICE_TOKEN = os.getenv('PRICE_TOKEN', '').strip()
PRICE_EMPRESARIAL = os.getenv('PRICE_EMPRESARIAL', '').strip()
BUSINESS_HOURS_START = int(os.getenv('BUSINESS_HOURS_START', '8'))
BUSINESS_HOURS_END = int(os.getenv('BUSINESS_HOURS_END', '17'))
# Mailer microservicio (PHPMailer vía HTTP)
MAILER_URL = os.getenv('MAILER_URL', 'http://mailer')
# QR signed URL config
QR_BASE_URL = os.getenv('QR_BASE_URL', 'https://app.authenology.com.ve')
QR_SECRET = os.getenv('QR_SECRET', '')
EMAILJS_FROM = os.getenv('SMTP_FROM', os.getenv('MAIL_FROM', os.getenv('EMAILJS_FROM', 'no-reply@authenology.com.ve')))
# Admin notify (comma-separated emails)
ADMIN_NOTIFY_EMAILS = [e.strip() for e in os.getenv('ADMIN_NOTIFY_EMAILS', '').split(',') if e.strip()]

def get_tznow():
    return datetime.now(pytz.timezone(TIMEZONE))

def support_blurb() -> str:
    return (
        "❓ No tengo esa respuesta en este momento. Para más información, por favor contacta a soporte:\n\n"
        "📧 Correo: contacto@authenology.com.ve\n"
        "📞 Teléfono: 0412-3379711\n\n"
        "También puedo agendarte una cita si lo prefieres."
    )

def build_confirmation_html(user_name: str, appointment_date: str, appointment_time: str,
                            location: str, support_phone: str, support_email: str) -> str:
    """Devuelve una plantilla HTML con estilo inline para máxima compatibilidad en clientes de correo."""
    # Colores Authenology
    primary = "#00bcd4"   # Cyan
    accent = "#1de9b6"    # Teal/green accent
    text = "#0a2540"
    bg = "#f8fafc"
    card = "#ffffff"
    soft = "#e2f5f7"
    soft2 = "#e0fcf7"

    html = f"""
    <div style="background:{bg}; padding:28px 12px;">
      <div style="font-family:Arial,Helvetica,sans-serif; color:{text}; padding:0; border-radius:16px; max-width:620px; margin:auto; box-shadow:0 8px 28px rgba(10,37,64,0.08); overflow:hidden; background:#ffffff;">
        <!-- Header / Hero -->
        <div style="background:linear-gradient(135deg, {primary} 0%, {accent} 100%); padding:24px 20px; text-align:center;">
          <img src="https://app.authenology.com.ve/imagenes/logo01.png" alt="Authenology" style="width:84px;height:84px;margin-bottom:10px;border-radius:12px;background:#ffffff; padding:6px;">
          <h1 style="margin:6px 0 4px 0; font-size:22px; line-height:1.25; color:#ffffff; font-weight:800;">Confirmación de cita</h1>
          <p style="margin:0; color:#eafffb; font-size:15px;">Hola {user_name}, tu cita ha sido agendada con éxito.</p>
        </div>

        <!-- Intro copy -->
        <div style="padding:20px 22px; font-size:15px; line-height:1.6;">
          <p style="margin:0 0 16px 0;">A continuación encontrarás el detalle de tu cita. Si necesitas reprogramar o cancelar, responde a este correo y con gusto te ayudaremos.</p>
        </div>

        <!-- Appointment card -->
        <div style="margin:0 22px 16px 22px; background:{soft2}; border:1px solid {soft}; border-radius:12px; padding:16px 18px;">
          <div style="font-weight:700; color:{primary}; margin-bottom:8px;">Detalles de la cita</div>
          <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="font-size:14px; color:{text};">
            <tr><td style="padding:6px 0;"><strong>Fecha:</strong></td><td style="padding:6px 0;">{appointment_date}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Hora:</strong></td><td style="padding:6px 0;">{appointment_time}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Ubicación:</strong></td><td style="padding:6px 0;">{location}</td></tr>
          </table>
        </div>

        <!-- Primary CTA -->
        <div style="text-align:center; padding:0 22px 16px 22px;">
          <a href="https://app.authenology.com.ve" style="display:inline-block; background:{primary}; color:#ffffff; text-decoration:none; font-weight:700; padding:12px 18px; border-radius:999px; box-shadow:0 6px 18px rgba(0,188,212,0.35);">Ir a mi panel</a>
        </div>

        <!-- Contact card -->
        <div style="margin:0 22px 16px 22px; background:#ffffff; border:1px solid {soft}; border-radius:12px; padding:14px 16px;">
          <div style="font-weight:700; color:{primary};">Información de contacto</div>
          <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="font-size:14px; color:{text}; margin-top:6px;">
            <tr><td style="padding:6px 0;"><strong>Teléfono:</strong></td><td style="padding:6px 0;">{support_phone}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Correo:</strong></td><td style="padding:6px 0;"><a href="mailto:{support_email}" style="color:{accent}; text-decoration:underline;">{support_email}</a></td></tr>
          </table>
        </div>

        <!-- Quick links -->
        <div style="padding:0 22px 20px 22px;">
          <div style="font-weight:700; color:{primary}; margin-bottom:6px;">Accesos rápidos</div>
          <div>
            <a href="mailto:{support_email}" style="margin-right:14px; color:{accent}; text-decoration:underline;">Escribir a soporte</a>
            <a href="https://wa.me/584123379711" style="margin-right:14px; color:{accent}; text-decoration:underline;">WhatsApp</a>
            <a href="https://app.authenology.com.ve" style="color:{text}; text-decoration:none;">App Authenology</a>
          </div>
        </div>

        <!-- Footer -->
        <div style="background:{bg}; padding:14px 18px; text-align:center; font-size:12px; color:#64748b;">
          Este mensaje fue generado automáticamente por Authenology. Gracias por confiar en nosotros.
        </div>
      </div>
    </div>
    """
    return html

def build_admin_notify_html(user_name: str, user_email: str, appointment_date: str, appointment_time: str,
                            location: str) -> str:
    primary = "#00bcd4"
    text = "#0a2540"
    bg = "#f8fafc"
    soft = "#e2f5f7"
    html = f"""
    <div style="background:{bg}; padding:24px 12px;">
      <div style="font-family:Arial,Helvetica,sans-serif; color:{text}; padding:0; border-radius:12px; max-width:640px; margin:auto; background:#ffffff; box-shadow:0 6px 24px rgba(10,37,64,0.08);">
        <div style="padding:16px 18px; border-bottom:1px solid {soft};">
          <h2 style="margin:0; font-size:18px; color:{primary};">Nueva cita agendada</h2>
        </div>
        <div style="padding:16px 18px; font-size:14px;">
          <p style="margin:0 0 10px 0;">Se registró una nueva cita desde el chatbot.</p>
          <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;">
            <tr><td style="padding:6px 0; width:160px;"><strong>Cliente:</strong></td><td style="padding:6px 0;">{user_name}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Email:</strong></td><td style="padding:6px 0;">{user_email}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Fecha:</strong></td><td style="padding:6px 0;">{appointment_date}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Hora:</strong></td><td style="padding:6px 0;">{appointment_time}</td></tr>
            <tr><td style="padding:6px 0;"><strong>Ubicación:</strong></td><td style="padding:6px 0;">{location}</td></tr>
          </table>
        </div>
      </div>
    </div>
    """
    return html

def notify_admin_appointment(to_list: List[str], user_name: str, user_email: str, formatted_date: str, formatted_time: str):
    if not to_list:
        return
    subject = "[Authenology] Nueva cita agendada"
    location = 'Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda'
    body = (
        "Nueva cita registrada desde el chatbot.\n\n"
        f"Cliente: {user_name}\n"
        f"Email: {user_email}\n"
        f"Fecha: {formatted_date}\n"
        f"Hora: {formatted_time}\n"
        f"Ubicación: {location}\n"
    )
    html = build_admin_notify_html(user_name, user_email, formatted_date, formatted_time, location)
    for admin_email in to_list:
        try:
            send_email_emailjs(admin_email, subject, body, {'html': html, 'reply_to': user_email})
        except Exception:
            pass

def smalltalk_answer(text: str) -> Optional[str]:
    """Handle simple courtesy/ack phrases like 'gracias', 'ok', 'listo'."""
    if not text:
        return None
    t = text.lower().strip()
    thanks = ['gracias', 'muchas gracias', 'gracias!', 'gracias.', 'gracias!!', 'grac']
    oks = ['ok', 'okey', 'vale', 'listo', 'perfecto', 'entendido']
    greets = ['hola', 'buenos dias', 'buenos días', 'buenas', 'buenas tardes', 'buenas noches']
    byes = ['adios', 'adiós', 'chao', 'hasta luego', 'nos vemos']
    if any(x in t for x in thanks):
        return "¡Con gusto! ¿Necesitas algo más?"
    if any(x == t or x in t for x in oks):
        return "Perfecto. Si quieres, puedo agendar una cita o mostrarte los precios."
    if any(x in t for x in greets):
        return "¡Hola! ¿Sobre qué te gustaría saber? Precios, citas o contacto están a un clic."
    if any(x in t for x in byes):
        return "¡Hasta luego! Cuando necesites, estaré aquí para ayudarte."
    return None

def support_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Agendar cita", callback_data="schedule_appt")],
        [InlineKeyboardButton("❓ Ver FAQs", callback_data="back_to_categories")],
        [InlineKeyboardButton("📞 Contacto", callback_data="contact_info")],
    ])

def feedback_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍 Útil", callback_data="fb_up"),
            InlineKeyboardButton("👎 No útil", callback_data="fb_down"),
        ]
    ])

def suggestions_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Precios", callback_data="back_to_categories")],
        [InlineKeyboardButton("📅 Agendar cita", callback_data="schedule_appt")],
        [InlineKeyboardButton("📞 Contacto", callback_data="contact_info")],
    ])

async def safe_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode: str = 'Markdown'):
    """Send a message safely whether the trigger was a message or a callback query."""
    try:
        # show typing indicator briefly
        chat_id = update.effective_chat.id
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        if update.message:
            return await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        if update.callback_query:
            # Prefer sending a new message to avoid losing previous context
            await update.callback_query.answer()
            return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
        # Fallback
        return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"safe_send error: {e}")
        raise

def ensure_tz(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in configured TIMEZONE."""
    if dt.tzinfo is None:
        return pytz.timezone(TIMEZONE).localize(dt)
    return dt.astimezone(pytz.timezone(TIMEZONE))

def best_faq_answer(query_text: str) -> Optional[FAQ]:
    """Return the most relevant active FAQ combining token overlap and fuzzy similarity."""
    if not query_text:
        return None
    text = query_text.lower()
    tokens = {t for t in text.replace('\n', ' ').split() if len(t) > 2}
    if not tokens:
        return None
    qdb = QuestionsSession()
    try:
        faqs = qdb.query(FAQ).filter(FAQ.is_active == True).all()
        best, best_score = None, 0.0
        for f in faqs:
            q_text = str(f.question).lower()
            a_text = str(f.answer).lower()
            q_tokens = set(q_text.split())
            a_tokens = set(a_text.split())
            overlap = len(tokens & q_tokens) * 2 + len(tokens & a_tokens)
            fuzzy_q = SequenceMatcher(None, text, q_text).ratio()
            fuzzy_a = SequenceMatcher(None, text, a_text).ratio()
            score = overlap + 3.0 * max(fuzzy_q, fuzzy_a)
            if score > best_score:
                best, best_score = f, score
        # Minimum threshold to accept an answer
        if best and best_score >= 3.0 or (best and SequenceMatcher(None, text, str(best.question).lower()).ratio() >= 0.35):
            return best
        return None
    finally:
        qdb.close()

def pricing_answer(text: str) -> Optional[str]:
    """Detect pricing intent for multiple products and build a rich answer."""
    if not text:
        return None
    t = text.lower()
    triggers = [
        'precio', 'precios', 'coste', 'costo', 'vale', 'cuesta', 'tarifa', 'tarifas', 'presupuesto', 'presupuestos',
        'precio aproximado', 'cuanto vale', 'cuánto vale', 'cuanto cuesta', 'cuánto cuesta'
    ]
    if not any(w in t for w in triggers):
        return None

    product = None
    title = None
    price_line = None

    if 'persona natural' in t or 'natural' in t:
        product = 'natural'
        title = '💳 Precio de la firma electrónica para Persona Natural'
        price_line = f"Precio: {PRICE_PERSONA_NATURAL}" if PRICE_PERSONA_NATURAL else "Precio: contáctanos para la cotización actualizada."
    elif 'persona juridica' in t or 'persona jurídica' in t or 'empresa' in t or 'juridica' in t or 'jurídica' in t:
        product = 'juridica'
        title = '🏢 Precio de la firma electrónica para Persona Jurídica/Empresas'
        price_line = f"Precio: {PRICE_PERSONA_JURIDICA}" if PRICE_PERSONA_JURIDICA else "Precio: contáctanos para la cotización actualizada."
    elif 'renovación' in t or 'renovacion' in t:
        product = 'renovacion'
        title = '♻️ Precio de renovación de firma/certificado'
        price_line = f"Precio: {PRICE_RENOVACION}" if PRICE_RENOVACION else "Precio: contáctanos para la cotización actualizada."
    elif 'token' in t or 'dispositivo' in t:
        product = 'token'
        title = '🔐 Precio de token/dispositivo criptográfico'
        price_line = f"Precio: {PRICE_TOKEN}" if PRICE_TOKEN else "Precio: contáctanos para la cotización actualizada."
    elif 'empresarial' in t or 'corporativo' in t or 'plan empresa' in t:
        product = 'empresarial'
        title = '🏢 Planes empresariales/corporativos'
        price_line = f"Precio: {PRICE_EMPRESARIAL}" if PRICE_EMPRESARIAL else "Precio: contáctanos para la cotización actualizada."

    if not product:
        # No product specified: return a concise summary with all available prices
        items = []
        if PRICE_PERSONA_NATURAL:
            items.append(f"• Persona Natural: {PRICE_PERSONA_NATURAL}")
        if PRICE_PERSONA_JURIDICA:
            items.append(f"• Persona Jurídica/Empresas: {PRICE_PERSONA_JURIDICA}")
        if PRICE_RENOVACION:
            items.append(f"• Renovación: {PRICE_RENOVACION}")
        if PRICE_TOKEN:
            items.append(f"• Token/Dispositivo: {PRICE_TOKEN}")
        if PRICE_EMPRESARIAL:
            items.append(f"• Plan Empresarial: {PRICE_EMPRESARIAL}")

        title = '💳 Precios disponibles'
        if items:
            summary = f"{title}\n\n" + "\n".join(items)
        else:
            summary = (
                f"{title}\n\n"
                "Para enviarte una cotización actualizada, por favor contáctanos o indícame qué producto te interesa."
            )
        common = (
            "\n\n¿Qué incluye?\n"
            "• Emisión/gestión del certificado digital\n"
            "• Validación de identidad\n"
            "• Soporte para firma de documentos exclusivamente PDFs\n"
            "• Acompañamiento de instalación y uso\n\n"
            "Formas de pago: transferencia bancaria, pago móvil y USD.\n\n"
            "Si deseas, puedo agendarte una cita para realizar el proceso o te envío el enlace de pago."
        )
        return summary + common

    common = (
        "\n\n¿Qué incluye?\n"
        "• Emisión/gestión del certificado digital\n"
        "• Validación de identidad\n"
        "• Soporte para firma de documentos exclusivamente PDFs\n"
        "• Acompañamiento de instalación y uso\n\n"
        "Formas de pago: transferencia bancaria, pago móvil y USD.\n\n"
        "Si deseas, puedo agendarte una cita para realizar el proceso o te envío el enlace de pago."
    )
    return f"{title}\n\n{price_line}{common}"

def services_answer(text: str) -> Optional[str]:
    """Detect queries about services (API/SDK/Empresarial)."""
    if not text:
        return None
    t = text.lower()
    cues = ['servicio', 'servicios', 'api', 'sdk', 'integración', 'integracion', 'empres', 'empresa', 'volumen']
    if not any(c in t for c in cues):
        return None
    return (
        "🧩 Servicios disponibles\n\n"
        "• Integración por API para automatizar emisión y validación de firmas.\n"
        "• Integración por SDK para apps y sistemas propios.\n"
        "• Servicios para empresas con planes por volumen (onboarding y soporte dedicado).\n\n"
        "¿Te interesa una integración o un plan por volumen? Puedo agendarte una reunión técnica o ponerte en contacto con nuestro equipo."
    )

def renewal_info_answer(text: str) -> Optional[str]:
    """Detect informational queries about renewing the certificate."""
    if not text:
        return None
    t = text.lower()
    cues = ['renovar', 'renovación', 'renovacion', 'renove', 'renovarse']
    if not any(c in t for c in cues):
        return None
    return (
        "♻️ Renovación del Certificado Electrónico\n\n"
        "Renovar el certificado es el mismo proceso que adquirirlo por primera vez: validación de identidad, emisión/activación y soporte.\n\n"
        "Si lo deseas, puedo agendarte una cita para realizar la renovación o enviarte la información de pago."
    )

def get_user_info(update: Update) -> tuple:
    """Extract user information from update"""
    user = update.effective_user
    return (
        user.id,
        user.username,
        user.first_name,
        user.last_name or "",
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input."""
    user_id, username, first_name, last_name = get_user_info(update)
    
    # Create or update user in database (appointments DB)
    db = ApptSession()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            user = User(
                telegram_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                user_type=UserType.CUSTOMER,
            )
            db.add(user)
            db.commit()
    finally:
        db.close()
    
    # Welcome message
    welcome_text = (
        f"¡Hola {first_name}! 👋\n"
        "Bienvenido a *Authenology*, tu solución de firma electrónica en Venezuela.\n\n"
        "¿En qué puedo ayudarte hoy?"
    )
    
    # Create keyboard
    keyboard = [
        ["📅 Agendar cita"],
        ["❓ Preguntas frecuentes", "📞 Contacto"],
        ["ℹ️ Acerca de Authenology"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await safe_send(update, context, welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    # quick suggestions
    await safe_send(update, context, "Puedo ayudarte con precios, citas, contacto y más.", reply_markup=suggestions_markup())
    # mark current state
    context.user_data['current_state'] = 'HANDLE_MENU'
    return HANDLE_MENU

async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect and save user's email, then create appointment and email confirmation."""
    email = (update.message.text or '').strip()
    if not valid_email(email):
        await safe_send(update, context, "El correo no parece válido. Por favor, envíame un correo válido (ej: nombre@dominio.com).")
        return COLLECT_EMAIL

    db = ApptSession()
    try:
        user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
        if not user:
            await safe_send(update, context, "No pude encontrar tu usuario. Envía /start para reiniciar.")
            return HANDLE_MENU
        user.email = email
        db.commit()

        appointment_time = context.user_data.get('appointment_time')
        if not appointment_time:
            await safe_send(update, context, "No tengo el horario de la cita. Por favor intenta agendar nuevamente.")
            return HANDLE_MENU
        # Ensure availability again and save
        if not is_slot_available(appointment_time, appointment_time + timedelta(minutes=30)):
            await safe_send(update, context, "El horario seleccionado ya no está disponible. Intenta con otro horario.")
            return HANDLE_MENU

        appt = Appointment(
            user_id=user.id,
            appointment_date=appointment_time,
            duration_minutes=30,
            status=AppointmentStatus.CONFIRMED
        )
        db.add(appt)
        db.commit()

        formatted_date = appointment_time.strftime('%A, %d de %B de %Y')
        formatted_time = appointment_time.strftime('%I:%M %p')

        await safe_send(update, context,
            "✅ *¡Cita confirmada!*\n\n"
            f"*Fecha:* {formatted_date}\n"
            f"*Hora:* {formatted_time}\n\n"
            "Te he enviado un correo de confirmación.",
            reply_markup=support_markup(),
            parse_mode='Markdown')

        # Send email via mailer
        try:
            body = (
                "Hola,\n\n"
                f"Tu cita ha sido confirmada para el {formatted_date} a las {formatted_time}.\n\n"
                "Ubicación: Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n"
                "Teléfono: 0412-3379711\n\n"
                "Si necesitas reprogramar, responde a este correo.\n\n"
                "Gracias."
            )
            html = build_confirmation_html(
                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                appointment_date=formatted_date,
                appointment_time=formatted_time,
                location='Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                support_phone='0412-3379711',
                support_email='contacto@authenology.com.ve',
            )
            send_email_emailjs(user.email, "Confirmación de cita - Authenology", body, {
                'appointment_date': formatted_date,
                'appointment_time': formatted_time,
                'user_name': f"{user.first_name} {user.last_name or ''}".strip(),
                'location': 'Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                'support_phone': '0412-3379711',
                'support_email': 'contacto@authenology.com.ve',
                'html': html,
            })
            # Notificar a administradores
            notify_admin_appointment(
                ADMIN_NOTIFY_EMAILS,
                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                user_email=user.email or 'sin-email',
                formatted_date=formatted_date,
                formatted_time=formatted_time,
            )
        except Exception:
            pass
    finally:
        db.close()

    context.user_data.pop('await_email', None)
    return HANDLE_MENU

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Transcribir audio y enrutarlo como si fuera texto en cualquier estado."""
    try:
        text = await voice_handler.handle_voice_message(update, context)
    except Exception as e:
        logger.error(f"voice handler error: {e}")
        text = ""
    if not text:
        await safe_send(update, context, "No pude entender el audio. ¿Puedes repetir o escribir tu consulta?")
        return context.user_data.get('current_state', HANDLE_MENU)

    # Guardar la pregunta de voz
    qdb = QuestionsSession()
    try:
        uid, uname, fname, lname = get_user_info(update)
        qdb.add(UserQuestion(
            telegram_id=uid,
            username=uname,
            first_name=fname,
            last_name=lname,
            question_text=text,
            source='voice'
        ))
        qdb.commit()
    finally:
        qdb.close()

    lt = text.lower()
    # Confirmación/cancelación por voz si estamos en estado de confirmación
    if context.user_data.get('current_state') == 'CONFIRM_APPOINTMENT':
        if any(w in lt for w in ['confirmar', 'sí', 'si', 'listo', 'ok']):
            # Reutilizar lógica de guardado similar a save_appointment() sin callback
            user_id = update.effective_user.id
            db = next(get_appt_db())
            try:
                user = db.query(User).filter(User.telegram_id == user_id).first()
                if not user:
                    await safe_send(update, context, "❌ Error: no encontré tu usuario. Envía /start para reiniciar.")
                    return HANDLE_MENU
                appt_time = context.user_data.get('appointment_time')
                if not appt_time:
                    await safe_send(update, context, "No tengo la hora seleccionada. Dime un día y hora para reagendar.")
                    return HANDLE_MENU
                if not user.email:
                    await safe_send(update, context, "✉️ Antes de confirmar, por favor escribe tu correo electrónico.")
                    context.user_data['await_email'] = True
                    return COLLECT_EMAIL
                if not is_slot_available(appt_time, appt_time + timedelta(minutes=30)):
                    await safe_send(update, context, "El horario ya no está disponible. Dime otra hora o día.")
                    return HANDLE_MENU
                appointment = Appointment(
                    user_id=user.id,
                    appointment_date=appt_time,
                    duration_minutes=30,
                    status=AppointmentStatus.CONFIRMED
                )
                db.add(appointment)
                db.commit()
                formatted_date = appt_time.strftime('%A, %d de %B de %Y')
                formatted_time = appt_time.strftime('%I:%M %p')
                await safe_send(update, context,
                    "✅ *¡Cita confirmada!*\n\n"
                    f"*Fecha:* {formatted_date}\n"
                    f"*Hora:* {formatted_time}\n\n"
                    "Te enviaremos un recordatorio antes de tu cita.",
                    parse_mode='Markdown')
                try:
                    body = (
                        "Hola,\n\n"
                        f"Tu cita ha sido confirmada para el {formatted_date} a las {formatted_time}.\n\n"
                        "Ubicación: Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n"
                        "Teléfono: 0412-3379711\n\n"
                        "Si necesitas reprogramar, responde a este correo.\n\n"
                        "Gracias."
                    )
                    html = build_confirmation_html(
                        user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                        appointment_date=formatted_date,
                        appointment_time=formatted_time,
                        location='Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                        support_phone='0412-3379711',
                        support_email='contacto@authenology.com.ve',
                    )
                    send_email_emailjs(user.email, "Confirmación de cita - Authenology", body, {
                        'appointment_date': formatted_date,
                        'appointment_time': formatted_time,
                        'user_name': f"{user.first_name} {user.last_name or ''}".strip(),
                        'location': 'Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                        'support_phone': '0412-3379711',
                        'support_email': 'contacto@authenology.com.ve',
                        'email_type': 'appointment_confirmation',
                        'html': html,
                    })
                    notify_admin_appointment(
                        ADMIN_NOTIFY_EMAILS,
                        user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                        user_email=user.email or 'sin-email',
                        formatted_date=formatted_date,
                        formatted_time=formatted_time,
                    )
                except Exception:
                    pass
                context.user_data['current_state'] = 'HANDLE_MENU'
                return HANDLE_MENU
            finally:
                db.close()
        if any(w in lt for w in ['cancelar', 'no', 'anular', 'cancel']):
            await safe_send(update, context, "❌ Cita cancelada. Dime otro día para reintentar.")
            context.user_data['current_state'] = 'HANDLE_MENU'
            return HANDLE_MENU

    # Priorizar intención de agendar por voz y salto directo a fecha/hora
    appointment_keywords = ['agendar', 'agenda', 'agendame', 'agéndame', 'cita', 'reservar', 'programar']
    parsed_date = parse_spanish_date(lt)
    parsed_time = parse_spanish_time(lt)
    if any(k in lt for k in appointment_keywords) or parsed_date or parsed_time:
        target_date = parsed_date or get_tznow().date() + timedelta(days=1)
        if parsed_time:
            slot = pick_best_slot_for_datetime(target_date, parsed_time[0], parsed_time[1])
            if slot:
                # Auto-confirmar si ya tenemos email del usuario
                user_id = update.effective_user.id
                db = next(get_appt_db())
                try:
                    user = db.query(User).filter(User.telegram_id == user_id).first()
                    if user and user.email:
                        appt_time = slot['start']
                        if not is_slot_available(appt_time, appt_time + timedelta(minutes=30)):
                            # Si justo se ocupó, mostrar horarios del día
                            await safe_send(update, context, "Ese horario acaba de ocuparse. Te muestro opciones disponibles para ese día:")
                            return await show_time_slots_for_date(update, context, target_date)
                        appointment = Appointment(
                            user_id=user.id,
                            appointment_date=appt_time,
                            duration_minutes=30,
                            status=AppointmentStatus.CONFIRMED
                        )
                        db.add(appointment)
                        db.commit()
                        formatted_date = appt_time.strftime('%A, %d de %B de %Y')
                        formatted_time = appt_time.strftime('%I:%M %p')
                        await safe_send(update, context,
                            "✅ *¡Cita confirmada por voz!*\n\n"
                            f"*Fecha:* {formatted_date}\n"
                            f"*Hora:* {formatted_time}\n\n"
                            "Te enviaremos un recordatorio antes de tu cita.",
                            parse_mode='Markdown')
                        # Enviar correos (usuario y admin)
                        try:
                            body = (
                                "Hola,\n\n"
                                f"Tu cita ha sido confirmada para el {formatted_date} a las {formatted_time}.\n\n"
                                "Ubicación: Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n"
                                "Teléfono: 0412-3379711\n\n"
                                "Si necesitas reprogramar, responde a este correo.\n\n"
                                "Gracias."
                            )
                            html = build_confirmation_html(
                                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                                appointment_date=formatted_date,
                                appointment_time=formatted_time,
                                location='Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                                support_phone='0412-3379711',
                                support_email='contacto@authenology.com.ve',
                            )
                            send_email_emailjs(user.email, "Confirmación de cita - Authenology", body, {
                                'appointment_date': formatted_date,
                                'appointment_time': formatted_time,
                                'user_name': f"{user.first_name} {user.last_name or ''}".strip(),
                                'location': 'Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                                'support_phone': '0412-3379711',
                                'support_email': 'contacto@authenology.com.ve',
                                'email_type': 'appointment_confirmation',
                                'html': html,
                            })
                            notify_admin_appointment(
                                ADMIN_NOTIFY_EMAILS,
                                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                                user_email=user.email or 'sin-email',
                                formatted_date=formatted_date,
                                formatted_time=formatted_time,
                            )
                        except Exception:
                            pass
                        context.user_data['current_state'] = 'HANDLE_MENU'
                        return HANDLE_MENU
                    else:
                        # Pedir correo y mantener hora en contexto
                        context.user_data['appointment_date'] = slot['start'].date()
                        context.user_data['appointment_time'] = slot['start']
                        context.user_data['await_email'] = True
                        await safe_send(update, context, "✉️ Antes de confirmar, por favor escribe tu correo electrónico para enviarte la confirmación.")
                        return COLLECT_EMAIL
                finally:
                    db.close()
                # Si por algún motivo no se pudo auto-confirmar, mostrar confirmación UI
                return await ask_confirm_for_time(update, context, slot['start'])
        await safe_send(update, context, "Entendido. Vamos a agendar tu cita.")
        return await show_time_slots_for_date(update, context, target_date)

    pa = pricing_answer(lt)
    if pa:
        await safe_send(update, context, pa)
        await safe_send(update, context, "¿Fue útil esta información?", reply_markup=feedback_markup())
        context.user_data['current_state'] = 'HANDLE_MENU'
        return HANDLE_MENU
    st = smalltalk_answer(lt)
    if st:
        await safe_send(update, context, st, reply_markup=suggestions_markup())
        context.user_data['current_state'] = 'HANDLE_MENU'
        return HANDLE_MENU
    sa = services_answer(lt)
    if sa:
        await safe_send(update, context, sa, reply_markup=support_markup())
        await safe_send(update, context, "¿Fue útil esta información?", reply_markup=feedback_markup())
        context.user_data['current_state'] = 'HANDLE_MENU'
        return HANDLE_MENU
    if 'agendar' in lt or 'cita' in lt:
        return await schedule_appointment(update, context)
    if 'pregunta' in lt or 'faq' in lt:
        return await show_faq_categories(update, context)
    if 'contacto' in lt or 'ayuda' in lt:
        return await show_contact_info(update, context)
    if 'acerca' in lt or 'authenology' in lt:
        return await show_about(update, context)
    faq = best_faq_answer(lt)
    if faq:
        await safe_send(update, context, f"*{faq.question}*\n\n{faq.answer}")
        await safe_send(update, context, "¿Necesitas más ayuda?", reply_markup=feedback_markup())
        context.user_data['current_state'] = 'HANDLE_MENU'
        return HANDLE_MENU
    await safe_send(update, context, support_blurb(), reply_markup=support_markup())
    await safe_send(update, context, "También puedes elegir una opción:", reply_markup=suggestions_markup())
    context.user_data['current_state'] = 'HANDLE_MENU'
    return HANDLE_MENU

async def render_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show a compact main menu and remember previous state to allow a quick return."""
    query = update.callback_query
    prev = context.user_data.get('current_state', 'HANDLE_MENU')
    context.user_data['prev_state'] = prev
    buttons = [
        [InlineKeyboardButton("📅 Agendar cita", callback_data="schedule_appt"), InlineKeyboardButton("📞 Contacto", callback_data="contact_info")],
        [InlineKeyboardButton("❓ Preguntas frecuentes", callback_data="back_to_categories")],
    ]
    if prev and prev != 'HANDLE_MENU':
        buttons.append([InlineKeyboardButton("⬅️ Volver donde estaba", callback_data="back_prev")])
    markup = InlineKeyboardMarkup(buttons)
    text = "Menú principal"
    if query:
        await query.answer()
        await query.message.edit_text(text, reply_markup=markup)
    else:
        await safe_send(update, context, text, reply_markup=markup)
    context.user_data['current_state'] = 'HANDLE_MENU'
    return HANDLE_MENU

async def back_prev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prev = context.user_data.get('prev_state', 'HANDLE_MENU')
    if prev == 'HANDLE_FAQ':
        return await show_faq_categories(update, context)
    if prev == 'HANDLE_CONTACT':
        return await show_contact_info(update, context)
    if prev in ('SCHEDULE_APPOINTMENT', 'SELECT_DATE', 'SELECT_TIME', 'CONFIRM_APPOINTMENT'):
        return await schedule_appointment(update, context)
    # default to main welcome
    return await start(update, context)

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle any unexpected callback to keep the bot responsive."""
    query = update.callback_query
    try:
        if query:
            await query.answer()
            logger.warning(f"Unknown callback received: {query.data}")
    except Exception:
        pass
    await safe_send(update, context, "No entendí esa acción. Te muestro el menú principal.")
    return await start(update, context)

async def handle_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Persist feedback thumbs up/down."""
    query = update.callback_query
    await query.answer()
    val = 'up' if query.data == 'fb_up' else 'down'
    db = QuestionsSession()
    try:
        text = None
        if update.effective_message and update.effective_message.reply_to_message:
            text = update.effective_message.reply_to_message.text
        db.add(Feedback(
            telegram_id=update.effective_user.id,
            value=val,
            question_text=text,
            message_id=update.effective_message.message_id if update.effective_message else None,
        ))
        db.commit()
    finally:
        db.close()
    await query.answer(text="¡Gracias por tu feedback!", show_alert=False)
    return HANDLE_MENU
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle main menu selection"""
    # Support both text messages and callback queries
    if update.message and update.message.text:
        text = update.message.text.lower()
    else:
        text = ""
    
    # Log user question if it's free text (not a menu keyword)
    keywords = ['agendar', 'cita', 'pregunta', 'faq', 'contacto', 'ayuda', 'acerca', 'authenology']
    if not any(k in text for k in keywords):
        # Try pricing intent first
        pa = pricing_answer(text)
        if pa:
            await safe_send(update, context, pa)
            await safe_send(update, context, "¿Fue útil esta información?", reply_markup=feedback_markup())
            return HANDLE_MENU
        # Small-talk intent
        st = smalltalk_answer(text)
        if st:
            await safe_send(update, context, st, reply_markup=suggestions_markup())
            return HANDLE_MENU
        # Services intent
        sa = services_answer(text)
        if sa:
            await safe_send(update, context, sa, reply_markup=support_markup())
            await safe_send(update, context, "¿Fue útil esta información?", reply_markup=feedback_markup())
            return HANDLE_MENU
        qdb = QuestionsSession()
        try:
            uid, uname, fname, lname = get_user_info(update)
            qdb.add(UserQuestion(
                telegram_id=uid,
                username=uname,
                first_name=fname,
                last_name=lname,
                question_text=text,
                source='text'
            ))
            qdb.commit()
        finally:
            qdb.close()
        # Renewal info intent
        ra = renewal_info_answer(text)
        if ra:
            await safe_send(update, context, ra, reply_markup=support_markup())
            await safe_send(update, context, "¿Fue útil esta información?", reply_markup=feedback_markup())
            return HANDLE_MENU
        # Try to answer using FAQs
        faq = best_faq_answer(text)
        if faq:
            await safe_send(update, context, f"*{faq.question}*\n\n{faq.answer}")
            await safe_send(update, context, "¿Necesitas más ayuda?", reply_markup=feedback_markup())
            return HANDLE_MENU
        else:
            await safe_send(update, context, support_blurb(), reply_markup=support_markup())
            await safe_send(update, context, "También puedes elegir una opción:", reply_markup=suggestions_markup())
            return HANDLE_MENU
    
    if 'agendar' in text or 'cita' in text:
        return await schedule_appointment(update, context)
    elif 'pregunta' in text or 'faq' in text:
        return await show_faq_categories(update, context)
    elif 'contacto' in text or 'ayuda' in text:
        return await show_contact_info(update, context)
    elif 'acerca' in text or 'authenology' in text:
        return await show_about(update, context)
    else:
        await safe_send(update, context, "No entendí tu solicitud. Por favor, selecciona una opción del menú.")
        return HANDLE_MENU

async def schedule_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the appointment scheduling process"""
    # Get available dates (next 14 days)
    today = get_tznow().date()
    available_dates = [today + timedelta(days=i) for i in range(1, 15)]
    
    # Create keyboard with available dates
    keyboard = []
    row = []
    for i, date in enumerate(available_dates, 1):
        row.append(InlineKeyboardButton(
            date.strftime('%d/%m'),
            callback_data=f"date_{date.isoformat()}"
        ))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:  # Add remaining buttons
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "📅 *Selecciona una fecha para tu cita:*\n"
        "Las citas están disponibles de lunes a viernes de 8:00 AM a 5:00 PM."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await safe_send(update, context, text, reply_markup=reply_markup, parse_mode='Markdown')
    
    context.user_data['current_state'] = 'SELECT_DATE'
    return SELECT_DATE

async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show available time slots for the selected date"""
    query = update.callback_query
    await query.answer()
    
    # Extract selected date from callback data
    selected_date = datetime.strptime(query.data.split('_')[1], '%Y-%m-%d').date()
    context.user_data['appointment_date'] = selected_date
    
    # Get available time slots from DB
    time_slots = get_available_slots_from_db(selected_date)
    
    if not time_slots:
        await query.message.reply_text(
            "Lo siento, no hay horarios disponibles para la fecha seleccionada. "
            "Por favor, selecciona otra fecha.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Seleccionar otra fecha", callback_data="back_to_dates")]
            ])
        )
        return SELECT_DATE
    
    # Create time slot buttons
    keyboard = []
    row = []
    for i, slot in enumerate(time_slots, 1):
        time_str = slot['start'].strftime('%H:%M')
        row.append(InlineKeyboardButton(
            time_str,
            callback_data=f"time_{slot['start'].isoformat()}"
        ))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:  # Add remaining buttons
        keyboard.append(row)
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Seleccionar otra fecha", callback_data="back_to_dates")])
    
    await query.edit_message_text(
        f"⏰ *Selecciona un horario para el {selected_date.strftime('%d/%m/%Y')}:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['current_state'] = 'SELECT_TIME'
    return SELECT_TIME

def parse_spanish_time(text: str):
    """Parse simple Spanish time mentions: '2 pm', '2 de la tarde', '14:30', 'a las 9', returns (hour, minute) or None."""
    import re
    t = text.lower()
    # Explicit HH:MM or H:MM
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
    # Patterns like 'a las 2', 'a la 1'
    m = re.search(r"a\s+l[ao]s?\s+(\d{1,2})\b", t)
    ampm = None
    if 'de la tarde' in t or 'de la noche' in t or 'pm' in t:
        ampm = 'pm'
    if 'de la mañana' in t or 'de la manana' in t or 'am' in t:
        ampm = ampm or 'am'
    if m:
        h = int(m.group(1))
        mi = 0
        if ampm == 'pm' and h < 12:
            h += 12
        if ampm == 'am' and h == 12:
            h = 0
        if 0 <= h <= 23:
            return h, mi
    # Single hour with 'pm/am'
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", t)
    if m:
        h = int(m.group(1))
        mi = 0
        if m.group(2) == 'pm' and h < 12:
            h += 12
        if m.group(2) == 'am' and h == 12:
            h = 0
        return h, mi
    # Phrases 'a las dos de la tarde' without digits are not handled yet
    return None

def pick_best_slot_for_datetime(target_date, hour: int, minute: int):
    """Pick the closest available slot on target_date at or after the given time. Returns slot dict or None."""
    slots = get_available_slots_from_db(target_date)
    if not slots:
        return None
    target_dt = ensure_tz(datetime.combine(target_date, dtime(hour, minute)))
    # Prefer exact hour/minute match if exists
    exact = [s for s in slots if s['start'].hour == hour and s['start'].minute == minute]
    if exact:
        return exact[0]
    # Otherwise next available after target
    after = [s for s in slots if s['start'] >= target_dt]
    if after:
        after.sort(key=lambda s: s['start'])
        return after[0]
    # Or the last of the day as fallback
    slots.sort(key=lambda s: s['start'])
    return slots[-1] if slots else None

async def ask_confirm_for_time(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_time: datetime) -> int:
    """Send confirmation UI for a concrete selected_time without needing a callback prior."""
    context.user_data['appointment_date'] = selected_time.date()
    context.user_data['appointment_time'] = selected_time
    formatted_date = selected_time.strftime('%A, %d de %B de %Y')
    formatted_time = selected_time.strftime('%I:%M %p')
    keyboard = [[
        InlineKeyboardButton("✅ Confirmar", callback_data="confirm_appt"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel_appt")
    ]]
    await safe_send(
        update,
        context,
        "📝 *Confirmación de cita*\n\n"
        f"*Fecha:* {formatted_date}\n"
        f"*Hora:* {formatted_time}\n\n"
        "¿Deseas confirmar esta cita?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    context.user_data['current_state'] = 'CONFIRM_APPOINTMENT'
    return CONFIRM_APPOINTMENT

def parse_spanish_date(text: str):
    """Parse simple Spanish date mentions: hoy, mañana, pasado mañana, weekdays.
    Returns a datetime.date or None.
    """
    if not text:
        return None
    t = text.lower()
    now = get_tznow().date()
    if 'pasado mañana' in t or 'pasado manana' in t:
        return now + timedelta(days=2)
    if 'mañana' in t or 'manana' in t:
        return now + timedelta(days=1)
    if 'hoy' in t:
        return now
    weekdays = {
        'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2, 'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6
    }
    for name, idx in weekdays.items():
        if name in t:
            today_idx = now.weekday()
            delta = (idx - today_idx) % 7
            delta = 7 if delta == 0 else delta
            return now + timedelta(days=delta)
    return None

async def show_time_slots_for_date(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_date) -> int:
    """Show available time slots for a given date without requiring a callback query."""
    context.user_data['appointment_date'] = selected_date
    time_slots = get_available_slots_from_db(selected_date)
    if not time_slots:
        await safe_send(update, context,
            "Lo siento, no hay horarios disponibles para la fecha seleccionada. Por favor, indícame otro día (por ejemplo: 'viernes' o 'mañana').")
        return SELECT_DATE
    keyboard = []
    row = []
    for i, slot in enumerate(time_slots, 1):
        time_str = slot['start'].strftime('%H:%M')
        row.append(InlineKeyboardButton(time_str, callback_data=f"time_{slot['start'].isoformat()}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Seleccionar otra fecha", callback_data="back_to_dates")])
    await safe_send(update, context,
        f"⏰ *Selecciona un horario para el {selected_date.strftime('%d/%m/%Y')}:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown')
    context.user_data['current_state'] = 'SELECT_TIME'
    return SELECT_TIME

async def confirm_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm the selected appointment time"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_dates":
        return await schedule_appointment(update, context)
    
    # Extract selected time from callback data
    selected_time = datetime.fromisoformat(query.data.split('_', 1)[1])
    context.user_data['appointment_time'] = selected_time
    
    # Format the date and time
    formatted_date = selected_time.strftime('%A, %d de %B de %Y')
    formatted_time = selected_time.strftime('%I:%M %p')
    
    # Create confirmation keyboard
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="confirm_appt"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_appt")
        ]
    ]
    
    await query.edit_message_text(
        f"📝 *Confirmación de cita*\n\n"
        f"*Fecha:* {formatted_date}\n"
        f"*Hora:* {formatted_time}\n\n"
        "¿Deseas confirmar esta cita?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    context.user_data['current_state'] = 'CONFIRM_APPOINTMENT'
    return CONFIRM_APPOINTMENT

async def save_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the appointment to the database"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_appt":
        await query.edit_message_text(
            "❌ *Cita cancelada*\n\n"
            "No se ha agendado ninguna cita. ¿En qué más puedo ayudarte?",
            parse_mode='Markdown'
        )
        return HANDLE_MENU
    
    # Get user data
    user_id = update.effective_user.id
    db = next(get_appt_db())
    user = db.query(User).filter(User.telegram_id == user_id).first()
    
    if not user:
        await query.edit_message_text(
            "❌ *Error*\n\n"
            "No se pudo encontrar tu información de usuario. Por favor, inicia el bot nuevamente con /start.",
            parse_mode='Markdown'
        )
        return HANDLE_MENU
    
    # Get appointment details
    appointment_date = context.user_data.get('appointment_date')
    appointment_time = context.user_data.get('appointment_time')
    
    if not all([appointment_date, appointment_time]):
        await query.edit_message_text(
            "❌ *Error*\n\n"
            "No se pudo obtener la información de la cita. Por favor, intenta nuevamente.",
            parse_mode='Markdown'
        )
        return HANDLE_MENU

    # If user doesn't have email, ask for it before saving the appointment
    if not user.email:
        context.user_data['await_email'] = True
        await query.edit_message_text(
            "✉️ *Antes de confirmar*, por favor escribe tu correo electrónico para enviarte la confirmación de la cita.",
            parse_mode='Markdown'
        )
        db.close()
        return COLLECT_EMAIL

    try:
        # Ensure the slot is still available
        if not is_slot_available(appointment_time, appointment_time + timedelta(minutes=30)):
            raise Exception("El horario seleccionado ya no está disponible.")

        # Save appointment to database
        appointment = Appointment(
            user_id=user.id,
            appointment_date=appointment_time,
            duration_minutes=30,
            status=AppointmentStatus.CONFIRMED
        )
        db.add(appointment)
        db.commit()

        # Format confirmation message
        formatted_date = appointment_time.strftime('%A, %d de %B de %Y')
        formatted_time = appointment_time.strftime('%I:%M %p')

        await query.edit_message_text(
            "✅ *¡Cita confirmada!*\n\n"
            f"*Fecha:* {formatted_date}\n"
            f"*Hora:* {formatted_time}\n\n"
            "Te enviaremos un recordatorio antes de tu cita.\n\n"
            "📍 *Ubicación:* Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n"
            "📞 *Teléfono:* 0412-3379711\n\n"
            "¿Necesitas ayuda con algo más?",
            parse_mode='Markdown'
        )

        # Send email confirmation via EmailJS
        try:
            body = (
                "Hola,\n\n"
                f"Tu cita ha sido confirmada para el {formatted_date} a las {formatted_time}.\n\n"
                "Ubicación: Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n"
                "Teléfono: 0412-3379711\n\n"
                "Si necesitas reprogramar, responde a este correo.\n\n"
                "Gracias."
            )
            html = build_confirmation_html(
                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                appointment_date=formatted_date,
                appointment_time=formatted_time,
                location='Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                support_phone='0412-3379711',
                support_email='contacto@authenology.com.ve',
            )
            send_email_emailjs(user.email, "Confirmación de cita - Authenology", body, {
                'appointment_date': formatted_date,
                'appointment_time': formatted_time,
                'user_name': f"{user.first_name} {user.last_name or ''}".strip(),
                'location': 'Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda',
                'support_phone': '0412-3379711',
                'support_email': 'contacto@authenology.com.ve',
                'email_type': 'appointment_confirmation',
                'html': html,
            })
            # Notificar a administradores
            notify_admin_appointment(
                ADMIN_NOTIFY_EMAILS,
                user_name=f"{user.first_name} {user.last_name or ''}".strip(),
                user_email=user.email or 'sin-email',
                formatted_date=formatted_date,
                formatted_time=formatted_time,
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error saving appointment: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\n"
            "No se pudo agendar la cita. Por favor, inténtalo de nuevo más tarde o contáctanos para asistencia.",
            parse_mode='Markdown'
        )
    finally:
        db.close()

    return HANDLE_MENU

async def show_faq_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show FAQ categories"""
    categories = [
        ("general", "📋 General"),
        ("legal", "⚖️ Legal"),
        ("tecnico", "💻 Técnico"),
        ("facturacion", "💰 Facturación"),
        ("uso", "🧭 Uso de la plataforma"),
        ("pagos", "💵 Pagos"),
    ]
    
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"faqcat_{cat}")]
        for cat, text in categories
    ]
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📚 *Preguntas Frecuentes*\n\n"
            "Selecciona una categoría para ver las preguntas más comunes:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "📚 *Preguntas Frecuentes*\n\n"
            "Selecciona una categoría para ver las preguntas más comunes:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    context.user_data['current_state'] = 'HANDLE_FAQ'
    return HANDLE_FAQ

async def show_faqs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show FAQs for the selected category"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_menu":
        return await start(update, context)
    elif query.data == "back_to_categories":
        return await show_faq_categories(update, context)
    
    # Get FAQs from questions database
    category = query.data.split('_', 1)[1]
    qdb = QuestionsSession()
    try:
        faqs = qdb.query(FAQ).filter(
            FAQ.category == category,
            FAQ.is_active == True
        ).all()
    finally:
        qdb.close()
    
    if not faqs:
        await query.edit_message_text(
            "No hay preguntas frecuentes disponibles en esta categoría.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Volver a categorías", callback_data="back_to_categories")]
            ])
        )
        return HANDLE_FAQ
    
    # Create FAQ buttons
    keyboard = [
        [InlineKeyboardButton(faq.question, callback_data=f"faq_{faq.id}")]
        for faq in faqs
    ]
    
    # Add back button
    keyboard.append([InlineKeyboardButton("🔙 Volver a categorías", callback_data="back_to_categories")])
    
    await query.edit_message_text(
        f"❓ *Preguntas frecuentes - {category.capitalize()}*\n\n"
        "Selecciona una pregunta para ver la respuesta:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return HANDLE_FAQ

async def show_faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the answer to the selected FAQ"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_faqs":
        category = context.user_data.get('faq_category', 'general')
        return await show_faqs(update, context)
    
    # Get FAQ from database
    faq_id = int(query.data.split('_', 1)[1])
    qdb = QuestionsSession()
    try:
        faq = qdb.query(FAQ).filter(FAQ.id == faq_id).first()
    finally:
        qdb.close()
    
    if not faq:
        await query.edit_message_text(
            "No se encontró la pregunta seleccionada.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Volver a preguntas", callback_data=f"back_to_faqs")]
            ])
        )
        return HANDLE_FAQ
    
    # Store category for back button
    context.user_data['faq_category'] = faq.category
    
    await query.edit_message_text(
        f"*{faq.question}*\n\n{faq.answer}\n\n"
        "¿Necesitas más ayuda?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔙 Volver a preguntas", callback_data="back_to_faqs"),
                InlineKeyboardButton("📞 Contactar soporte", callback_data="contact_support")
            ]
        ]),
        parse_mode='Markdown'
    )
    
    return HANDLE_FAQ

async def show_contact_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show contact information"""
    contact_text = (
        "📞 *Contacto*\n\n"
        "Estamos aquí para ayudarte. Puedes contactarnos a través de los siguientes medios:\n\n"
        "📍 *Oficina Principal:*\n"
        "Avenida Bolívar, Edificio Don David, Oficina 001, PB, Chacao, estado Miranda\n\n"
        "📱 *Teléfonos:*\n"
        "• 0412-3379711\n"
        "• 0414-1278081\n\n"
        "📧 *Correo:*\n"
        "contacto@authenology.com.ve\n\n"
        "🖥️ *App Web:*\n"
        "app.authenology.com.ve\n\n"
        "🌐 *Sitio Web:*\n"
        "www.authenology.com.ve\n\n"
        "⏱️ *Horario de Atención:*\n"
        "Lunes a Viernes: 8:00 AM - 5:00 PM"
    )
    
    keyboard = [
        [InlineKeyboardButton("📅 Agendar cita", callback_data="schedule_appt")],
        [
            InlineKeyboardButton("🖥️ Abrir App Web", url="https://app.authenology.com.ve"),
            InlineKeyboardButton("🌐 Sitio Web", url="https://www.authenology.com.ve")
        ],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            contact_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            contact_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    context.user_data['current_state'] = 'HANDLE_CONTACT'
    return HANDLE_CONTACT

async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show information about Authenology"""
    about_text = (
        "🌟 *Acerca de Authenology*\n\n"
        "*Authenology* es una plataforma venezolana que te permite firmar documentos de manera electrónica y legalmente válida desde cualquier lugar y dispositivo.\n\n"
        "Nuestro objetivo es simplificar tus trámites, ahorrarte tiempo y reducir el uso de papel.\n\n"
        "*Beneficios:*\n"
        "• Firma documentos desde cualquier lugar\n"
        "• Ahorra tiempo y papel\n"
        "• Procesos más rápidos y eficientes\n"
        "• Seguridad y validez legal garantizada\n\n"
        "*¿Listo para empezar?* Visita nuestra app web y registrate: app.authenology.com.ve"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📅 Agendar cita", callback_data="schedule_appt"),
            InlineKeyboardButton("📞 Contacto", callback_data="contact_info")
        ],
        [InlineKeyboardButton("🔙 Menú principal", callback_data="back_to_menu")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            about_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            about_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    
    return HANDLE_MENU

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    try:
        if update.message:
            await update.message.reply_text(
                '¡Hasta luego! Si necesitas ayuda, no dudes en escribirme.',
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await safe_send(update, context, '¡Hasta luego! Si necesitas ayuda, no dudes en escribirme.', reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass
    return ConversationHandler.END

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle incoming voice messages"""
    text = await voice_handler.handle_voice_message(update, context)
    if text:
        # Log question
        qdb = QuestionsSession()
        try:
            uid, uname, fname, lname = get_user_info(update)
            qdb.add(UserQuestion(
                telegram_id=uid,
                username=uname,
                first_name=fname,
                last_name=lname,
                question_text=text,
                source='voice'
            ))
            qdb.commit()
        finally:
            qdb.close()
        # Pricing intent
        pa = pricing_answer(text)
        if pa:
            await safe_send(update, context, pa)
            return HANDLE_MENU
        # Services intent
        sa = services_answer(text)
        if sa:
            await safe_send(update, context, sa, reply_markup=support_markup())
            return HANDLE_MENU
        # Renewal info intent
        ra = renewal_info_answer(text)
        if ra:
            await safe_send(update, context, ra, reply_markup=support_markup())
            return HANDLE_MENU
        # FAQ match
        faq = best_faq_answer(text)
        if faq:
            await safe_send(update, context, f"*{faq.question}*\n\n{faq.answer}")
            await safe_send(update, context, "¿Necesitas más ayuda?", reply_markup=feedback_markup())
        else:
            await safe_send(update, context, support_blurb(), reply_markup=support_markup())
            await safe_send(update, context, "También puedes elegir una opción:", reply_markup=suggestions_markup())
    return HANDLE_MENU

# (no standalone handle_text; text is handled in handle_menu)

def daterange_slots(date_obj) -> List[Dict[str, datetime]]:
    tz = pytz.timezone(TIMEZONE)
    start_dt = tz.localize(datetime.combine(date_obj, dtime(hour=BUSINESS_HOURS_START)))
    end_dt = tz.localize(datetime.combine(date_obj, dtime(hour=BUSINESS_HOURS_END)))
    slots = []
    cur = start_dt
    step = timedelta(minutes=30)
    while cur + step <= end_dt:
        slots.append({'start': cur, 'end': cur + step})
        cur += step
    return slots

def is_slot_available(start_dt: datetime, end_dt: datetime) -> bool:
    db = ApptSession()
    try:
        tz = pytz.timezone(TIMEZONE)
        start_dt = ensure_tz(start_dt)
        end_dt = ensure_tz(end_dt)
        day = start_dt.astimezone(tz).date()
        day_start = tz.localize(datetime.combine(day, dtime.min))
        day_end = tz.localize(datetime.combine(day, dtime.max))
        appts = db.query(Appointment).filter(
            Appointment.appointment_date >= day_start,
            Appointment.appointment_date <= day_end,
            Appointment.status != AppointmentStatus.CANCELLED
        ).all()
        for a in appts:
            a_start = ensure_tz(a.appointment_date)
            a_end = a_start + timedelta(minutes=a.duration_minutes)
            if start_dt < a_end and end_dt > a_start:
                return False
        return True
    finally:
        db.close()

def get_available_slots_from_db(date_obj) -> List[Dict[str, datetime]]:
    tz = pytz.timezone(TIMEZONE)
    all_slots = daterange_slots(date_obj)
    available = []
    db = ApptSession()
    try:
        day_start = tz.localize(datetime.combine(date_obj, dtime.min))
        day_end = tz.localize(datetime.combine(date_obj, dtime.max))
        appts = db.query(Appointment).filter(
            Appointment.appointment_date >= day_start,
            Appointment.appointment_date <= day_end,
            Appointment.status != AppointmentStatus.CANCELLED
        ).all()
        for slot in all_slots:
            overlap = False
            for a in appts:
                a_start = ensure_tz(a.appointment_date)
                a_end = a_start + timedelta(minutes=a.duration_minutes)
                if slot['start'] < a_end and slot['end'] > a_start:
                    overlap = True
                    break
            if not overlap:
                available.append(slot)
    finally:
        db.close()
    return available

def valid_email(email: str) -> bool:
    if not email:
        return False
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email.strip()) is not None

def build_signed_qr_url(user_email: str, payload: Dict[str, str] | None = None) -> str:
    """Genera una URL única con token HMAC. No requiere DB.
    token = base64url(hmac_sha256(secret, canonical_payload)) + '.' + base64url(nonce)
    canonical_payload incluye: email, ts, extras opcionales.
    """
    base = QR_BASE_URL.rstrip('/')
    # Si no hay secreto, retorna base directamente
    if not QR_SECRET:
        return base
    import hmac, hashlib, json, time, os, base64
    nonce = base64.urlsafe_b64encode(os.urandom(9)).decode('utf-8').rstrip('=')
    ts = int(time.time())
    payload = payload or {}
    data = {
        'e': (user_email or ''),
        'ts': ts,
        **{k: v for k, v in payload.items() if v is not None}
    }
    canonical = json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf-8')
    sig = hmac.new(QR_SECRET.encode('utf-8'), canonical, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('utf-8').rstrip('=')
    payload_b64 = base64.urlsafe_b64encode(canonical).decode('utf-8').rstrip('=')
    token = f"{sig_b64}.{payload_b64}.{nonce}"
    return f"{base}?t={token}"

def send_email_emailjs(to_email: str, subject: str, body: str, template_params: Dict[str, str] = None) -> bool:
    """Enviar correo vía microservicio Mailer (PHPMailer). Acepta HTML opcional en template_params['html']."""
    if not MAILER_URL:
        logger.warning("MAILER_URL no configurado; omitiendo envío de correo")
        return False
    import requests
    try:
        params = template_params or {}
        # Auto defaults for QR if not provided
        if 'qr_url' not in params or not params.get('qr_url'):
            # try to build signed URL using available context in params
            extras = {
                'user': params.get('user_name'),
                'appt_date': params.get('appointment_date'),
                'appt_time': params.get('appointment_time'),
            }
            params['qr_url'] = build_signed_qr_url(to_email, extras)
        if 'qr_seed' not in params or not params.get('qr_seed'):
            params['qr_seed'] = to_email
        if 'logo_url' not in params or not params.get('logo_url'):
            params['logo_url'] = 'https://app.authenology.com.ve/imagenes/logo01.png'
        html = params.get('html')
        if not html:
            # Generar HTML básico a partir de body y params comunes
            extra = []
            for k in ('appointment_date', 'appointment_time', 'user_name', 'location', 'support_phone', 'support_email'):
                if k in params and params[k]:
                    label = k.replace('_', ' ').title()
                    extra.append(f"<p><strong>{label}:</strong> {params[k]}</p>")
            body_html = '<br>'.join((body or '').split('\n'))
            html = f"""
            <div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#111'>
              <p>{body_html}</p>
              {''.join(extra)}
              <div><!--QR_BLOCK--></div>
            </div>
            """
        payload = {
            'to_email': to_email,
            'from_email': EMAILJS_FROM,
            'subject': subject,
            'message': body,
            'html': html,
        }
        if 'reply_to' in params:
            payload['reply_to'] = params['reply_to']
        # Optional QR parameters
        if 'qr_url' in params and params['qr_url']:
            payload['qr_url'] = params['qr_url']
        if 'qr_seed' in params and params['qr_seed']:
            payload['qr_seed'] = params['qr_seed']
        if 'qr_size' in params and params['qr_size']:
            try:
                payload['qr_size'] = int(params['qr_size'])
            except Exception:
                pass
        if 'logo_url' in params and params['logo_url']:
            payload['logo_url'] = params['logo_url']
        resp = requests.post(MAILER_URL.rstrip('/') + '/', json=payload, timeout=20)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict) and data.get('ok') is True:
                    return True
            except Exception:
                pass
            logger.error(f"Mailer error body: {resp.text}")
            return False
        logger.error(f"Mailer HTTP {resp.status_code}: {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Error calling Mailer: {e}")
        return False

def main() -> None:
    """Run the bot."""
    # Initialize databases
    init_appt_db()
    init_q_db()
    seed_faqs()
    
    # Create the Application and pass it your bot's token.
    application = (
        ApplicationBuilder()
        .token(os.getenv('TELEGRAM_BOT_TOKEN'))
        .rate_limiter(AIORateLimiter())
        .concurrent_updates(True)
        .build()
    )

    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            HANDLE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(schedule_appointment, pattern='^schedule_appt$'),
                CallbackQueryHandler(show_contact_info, pattern='^contact_info$'),
                CallbackQueryHandler(show_faq_categories, pattern='^back_to_categories$'),
                CallbackQueryHandler(back_prev, pattern='^back_prev$'),
                CallbackQueryHandler(handle_feedback_callback, pattern='^fb_up$'),
                CallbackQueryHandler(handle_feedback_callback, pattern='^fb_down$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            SCHEDULE_APPOINTMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(select_time, pattern='^date_'),
                CallbackQueryHandler(show_contact_info, pattern='^contact_info$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            SELECT_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(select_time, pattern='^date_'),
                CallbackQueryHandler(schedule_appointment, pattern='^back_to_dates$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            SELECT_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(confirm_appointment, pattern='^time_'),
                CallbackQueryHandler(schedule_appointment, pattern='^back_to_dates$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            CONFIRM_APPOINTMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(save_appointment, pattern='^(confirm_appt|cancel_appt)$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            HANDLE_FAQ: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(show_faq_categories, pattern='^back_to_categories$'),
                CallbackQueryHandler(show_faqs, pattern='^faqcat_'),
                CallbackQueryHandler(show_faq_answer, pattern='^back_to_faqs$'),
                CallbackQueryHandler(show_faq_answer, pattern='^faq_\\d+$'),
                CallbackQueryHandler(show_contact_info, pattern='^contact_support$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            HANDLE_CONTACT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu),
                MessageHandler(filters.VOICE, handle_voice_message),
                CallbackQueryHandler(schedule_appointment, pattern='^schedule_appt$'),
                CallbackQueryHandler(render_main_menu, pattern='^back_to_menu$'),
                CallbackQueryHandler(handle_unknown_callback),
            ],
            COLLECT_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_input),
                MessageHandler(filters.VOICE, handle_voice_message),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Global error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled exception while handling update: %s", context.error)
        try:
            if isinstance(update, Update) and update.effective_chat:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Ha ocurrido un error inesperado. Por favor, intenta nuevamente.")
        except Exception:
            pass

    application.add_error_handler(error_handler)

    # Command shortcuts
    application.add_handler(CommandHandler('menu', start))
    application.add_handler(CommandHandler('contacto', show_contact_info))
    application.add_handler(CommandHandler('faq', show_faq_categories))

    # Add conversation handler to the application
    application.add_handler(conv_handler)
    # Global catch-all for any stray callbacks to avoid stuck updates
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))
    
    # Ya se añadió en cada estado del ConversationHandler

    # Run the bot until the user presses Ctrl-C
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
