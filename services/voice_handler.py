import os
import tempfile
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update
from telegram.ext import ContextTypes
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class VoiceHandler:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.supported_formats = ['.ogg', '.wav', '.mp3', '.m4a']
        self.lang = os.getenv('VOICE_LANG', 'es-VE')  # idioma por defecto Venezuela
    
    async def process_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Process voice message and return transcribed text"""
        try:
            # Get voice message file
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            
            # Create a temporary file to store the voice message
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            
            # Download the voice message
            await voice_file.download_to_drive(custom_path=temp_path)
            
            # Convert to WAV format if needed
            audio_path = self._convert_to_wav(temp_path)
            
            # Transcribe the audio
            text = self._transcribe_audio(audio_path)
            logger.info(f"Voice transcript: {text}")
            
            # Clean up temporary files
            temp_path.unlink(missing_ok=True)
            if audio_path != temp_path:
                audio_path.unlink(missing_ok=True)
            
            return text
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            return ""
    
    def _convert_to_wav(self, audio_path: Path) -> Path:
        """Convert audio file to WAV format if needed"""
        if audio_path.suffix.lower() == '.wav':
            return audio_path
        
        try:
            # Convert to WAV using pydub
            sound = AudioSegment.from_file(audio_path)
            wav_path = audio_path.with_suffix('.wav')
            sound.export(wav_path, format='wav')
            return wav_path
        except Exception as e:
            logger.error(f"Error converting audio to WAV: {e}")
            return audio_path  # Try with original file if conversion fails
    
    def _transcribe_audio(self, audio_path: Path) -> str:
        """Transcribe audio file to text using Google Speech Recognition"""
        try:
            with sr.AudioFile(str(audio_path)) as source:
                # Listen for the data (load audio to memory)
                # Ajuste de ruido ambiente para mejorar precisión
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio_data = self.recognizer.record(source)
                # Recognize (convert from speech to text)
                text = self.recognizer.recognize_google(audio_data, language=self.lang)
                return text
        except sr.UnknownValueError:
            logger.warning("Speech Recognition could not understand audio")
            return ""
        except sr.RequestError as e:
            logger.error(f"Could not request results from Google Speech Recognition service; {e}")
            return ""
        except Exception as e:
            logger.error(f"Error in speech recognition: {e}")
            return ""
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming voice messages"""
        if not update.message.voice:
            return
        
        # Send a typing action to indicate processing
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action='typing'
        )
        
        # Process the voice message
        transcribed_text = await self.process_voice_message(update, context)
        
        if not transcribed_text:
            await update.message.reply_text(
                "Lo siento, no pude transcribir tu mensaje de voz. "
                "¿Podrías intentarlo de nuevo o escribir tu consulta?"
            )
            return ""
        
        # Do not echo transcription here; let bot.py decide the final answer
        return transcribed_text
