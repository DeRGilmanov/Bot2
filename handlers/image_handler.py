# handlers/image_handler.py
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

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает изображения."""
    try:
        photo = update.message.photo[-1]
        user = update.effective_user

        # Создаем временную директорию
        os.makedirs("temp_files", exist_ok=True)
        local_filename = os.path.join("temp_files", f"temp_photo_{user.id}.jpg")

        # Скачиваем изображение
        photo_file = await photo.get_file()
        await photo_file.download_to_drive(local_filename)

        # Анализируем изображение
        analysis_result = await ai_client.analyze_image(local_filename)
        
        if analysis_result:
            await update.message.reply_text(f"📷 Результат анализа изображения:\n{analysis_result}")
        else:
            await update.message.reply_text("❌ Не удалось проанализировать изображение.")

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке изображения.")
    finally:
        # Удаляем временный файл
        if os.path.exists(local_filename):
            os.unlink(local_filename)

def setup_image_handler(application):
    """Регистрация обработчика изображений"""
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))