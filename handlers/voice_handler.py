# handlers/voice_handler.py
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

# Используем абсолютный импорт
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_client import ai_client

logger = logging.getLogger(__name__)

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает голосовые сообщения."""
    try:
        voice = update.message.voice
        user = update.effective_user

        # Создаем временную директорию
        os.makedirs("temp_files", exist_ok=True)
        local_filename = os.path.join("temp_files", f"temp_voice_{user.id}.ogg")

        # Скачиваем голосовое сообщение
        voice_file = await voice.get_file()
        await voice_file.download_to_drive(local_filename)

        # Конвертируем в текст
        recognized_text = await ai_client.speech_to_text(local_filename)
        
        if recognized_text:
            await update.message.reply_text(f"🎤 Вы сказали: \"{recognized_text}\"")
        else:
            await update.message.reply_text("❌ Не удалось распознать речь.")

    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке голосового сообщения.")
    finally:
        # Удаляем временный файл
        if os.path.exists(local_filename):
            os.unlink(local_filename)

def setup_voice_handler(application):
    """Регистрация обработчика голосовых сообщений"""
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))