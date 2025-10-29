from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Engine and session for questions DB
QUESTIONS_DB_URL = os.getenv('QUESTIONS_DB_URL', 'sqlite:///questions.db')
engine = create_engine(QUESTIONS_DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class FAQ(Base):
    __tablename__ = 'faqs'

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserQuestion(Base):
    __tablename__ = 'user_questions'

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, index=True)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=True)
    source = Column(String(20), default='text')  # 'text' | 'voice'
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, index=True)
    value = Column(String(10), nullable=False)  # 'up' | 'down'
    question_text = Column(Text, nullable=True)
    message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_faqs():
    """Seed or update FAQs idempotently.

    If a FAQ with the same question exists, update its answer/category and set active.
    Otherwise, insert it. This lets text edits in the code propagate to DB on startup.
    """
    db = SessionLocal()
    try:
        faqs = [
            FAQ(
                question="¿Qué es Authenology?",
                answer=(
                    "Authenology es una plataforma venezolana que te permite firmar documentos de manera "
                    "electrónica y legalmente válida desde cualquier lugar y dispositivo. Nuestro objetivo es "
                    "simplificar tus trámites, ahorrarte tiempo y reducir el uso de papel."
                ),
                category="general",
            ),
            FAQ(
                question="¿Cómo puedo empezar a usar Authenology?",
                answer=(
                    "Visita nuestro app web regístrate y podrás empezar a firmar en minutos. "
                    "Ingresa a app.authenology.com.ve desde tu Laptop o PC e incluso desde tu dispositivo movil."
                ),
                category="general",
            ),
            FAQ(
                question="¿Las firmas electrónicas de Authenology son legales en Venezuela?",
                answer=(
                    "Sí. Cumplen con la Ley de Mensajes de Datos y Firmas Electrónicas de Venezuela. "
                    "Tienen la misma validez legal que una firma manuscrita."
                ),
                category="legal",
            ),
            FAQ(
                question="¿Qué tan segura es la plataforma?",
                answer=(
                    "Usamos cifrado SSL y múltiples capas de seguridad. Cada firma genera un hash unico que no es capaz alterarse ni rompese "
                    "y que garantiza la integridad del documento."
                ),
                category="tecnico",
            ),
            FAQ(
                question="¿Cuánto cuesta la firma electrónica?",
                answer=(
                    "Persona Natural: $30/año. Profesional Titulado: $36/año. Persona Jurídica: $48/año. "
                    "Precios más 16% de IVA y sujetos a tasa BCV del día."
                ),
                category="facturacion",
            ),
            FAQ(
                question="¿Cómo firmo un documento desde el aplicativo?",
                answer=(
                    "1) Entra a app.authenology.com.ve. 2) Inicia sesión. 3) Ve a 'Firmar'. 4) Carga el PDF. "
                    "5) Selecciona tu certificado .p12 y coloca tu contraseña. 6) Elige 'QR + Información'. "
                    "7) Posiciona la firma y presiona 'Firmar'."
                ),
                category="uso",
            ),
            FAQ(
                question="¿Dónde y cómo puedo pagar?",
                answer=(
                    "Banco de Venezuela: 0102-0105-54-0000616575, AUTHENTICSING C.A., RIF J503240237, Tel 04123379711.\n"
                    "Banco Nacional de Crédito (BNC): 0191-0098-74-2198344333, AUTHENTICSING, C.A., RIF J503240237, Tel 04141278081."
                ),
                category="pagos",
            ),
            FAQ(
                question="Horario de atención",
                answer=(
                    "Lunes a Viernes: 8:00 AM a 5:00 PM."
                ),
                category="general",
            ),
        ]

        # Upsert by question
        for f in faqs:
            existing = db.query(FAQ).filter(FAQ.question == f.question).first()
            if existing:
                changed = False
                if existing.answer != f.answer:
                    existing.answer = f.answer
                    changed = True
                if existing.category != f.category:
                    existing.category = f.category
                    changed = True
                if existing.is_active is False:
                    existing.is_active = True
                    changed = True
                if changed:
                    existing.updated_at = datetime.utcnow()
            else:
                db.add(f)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    seed_faqs()
