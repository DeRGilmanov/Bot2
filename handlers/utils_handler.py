import logging
import os
import tempfile
import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, time
import sqlite3

from telegram import Update, Message
from telegram.ext import ContextTypes, filters

# ИСПРАВЛЕННЫЕ ИМПОРТЫ
from ai_client import ai_client
from database import DatabaseManager
from config import config

logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)

class UtilsHandler:
    """Обработчик вспомогательных функций и утилит"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        # Убираем OpenAI клиент, используем наш универсальный AI клиент
    
    async def handle_text_extraction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /text - извлечение текста из голосовых и изображений"""
        try:
            message = update.effective_message
            
            # Проверяем, является ли сообщение ответом на медиа-сообщение
            if not message.reply_to_message:
                await message.reply_text(
                    "📝 **Как использовать /text:**\n\n"
                    "Ответьте этой командой на:\n"
                    "• 🎤 Голосовое сообщение - для преобразования в текст\n"
                    "• 🖼️ Изображение с текстом - для распознавания текста\n"
                    "• 📄 Документ с текстом - для извлечения текста\n\n"
                    "💡 *Бот поддерживает русский и английский языки*"
                )
                return
            
            target_message = message.reply_to_message
            
            # Проверяем доступность функций
            if target_message.voice and not config.is_speechkit_available():
                await message.reply_text(
                    "❌ Распознавание голоса временно недоступно.\n"
                    "Функция требует настройки Yandex SpeechKit API."
                )
                return
                
            if target_message.photo and not config.is_vision_available():
                await message.reply_text(
                    "❌ Анализ изображений временно недоступен.\n"
                    "Функция требует настройки Yandex Vision API."
                )
                return
            
            processing_msg = await message.reply_text("🔍 Извлекаю текст...")
            
            extracted_text = await self._extract_text_from_media(target_message, context)
            
            await processing_msg.delete()
            
            if extracted_text:
                # Сохраняем извлеченный текст в базу
                self._save_extracted_text(update, target_message, extracted_text)
                
                response_text = self._format_extracted_text_response(extracted_text, target_message)
                await message.reply_text(response_text, parse_mode='Markdown')
            else:
                await message.reply_text(
                    "❌ Не удалось извлечь текст из сообщения.\n"
                    "Убедитесь, что:\n"
                    "• Голосовое сообщение четко записано\n"
                    "• На изображении есть читаемый текст\n"
                    "• Формат файла поддерживается"
                )
                
        except Exception as e:
            logger.error(f"Error in handle_text_extraction: {e}")
            await self._send_error_message(update, "при извлечении текста")

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Автоматическая обработка голосовых сообщений"""
        try:
            if not config.is_speechkit_available():
                return  # Просто игнорируем, если сервис недоступен
            
            message = update.effective_message
            if not message.voice:
                return
            
            # Проверяем длительность голосового сообщения
            if message.voice.duration > config.MAX_VOICE_DURATION:
                await message.reply_text(
                    f"❌ Голосовое сообщение слишком длинное.\n"
                    f"Максимальная длительность: {config.MAX_VOICE_DURATION // 60} минут."
                )
                return
            
            # Скачиваем и обрабатываем голосовое сообщение
            processing_msg = await message.reply_text("🎤 Обрабатываю голосовое сообщение...")
            
            voice_file = await message.voice.get_file()
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                await voice_file.download_to_drive(temp_path)
                recognized_text = await ai_client.speech_to_text(temp_path)
                
                await processing_msg.delete()
                
                if recognized_text:
                    # Сохраняем распознанный текст
                    self._save_recognized_voice_text(message, recognized_text)
                    
                    # Отправляем распознанный текст
                    response = config.VOICE_RECOGNITION_TEMPLATE.format(text=recognized_text)
                    await message.reply_text(response, parse_mode='Markdown')
                    
                    # Автоматически отправляем в GPT для ответа (опционально)
                    # await self._process_voice_with_gpt(update, context, recognized_text)
                else:
                    await message.reply_text(config.VOICE_RECOGNITION_ERROR_TEMPLATE)
                    
            finally:
                # Очищаем временный файл
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except Exception as e:
            logger.error(f"Error in handle_voice_message: {e}")
            # Не отправляем сообщение об ошибке, чтобы не спамить

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Автоматическая обработка изображений"""
        try:
            if not config.is_vision_available():
                return  # Просто игнорируем, если сервис недоступен
            
            message = update.effective_message
            if not message.photo:
                return
            
            # Проверяем размер изображения
            photo = message.photo[-1]  # Берем самое качественное
            if photo.file_size and photo.file_size > config.MAX_IMAGE_SIZE:
                await message.reply_text(
                    f"❌ Изображение слишком большое.\n"
                    f"Максимальный размер: {config.MAX_IMAGE_SIZE // (1024*1024)}MB."
                )
                return
            
            # Скачиваем и обрабатываем изображение
            processing_msg = await message.reply_text("🖼️ Анализирую изображение...")
            
            photo_file = await photo.get_file()
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                await photo_file.download_to_drive(temp_path)
                analysis_result = await ai_client.analyze_image(temp_path)
                
                await processing_msg.delete()
                
                if analysis_result:
                    # Сохраняем результат анализа
                    self._save_image_analysis(message, analysis_result)
                    
                    # Отправляем результат анализа
                    response = config.IMAGE_ANALYSIS_TEMPLATE.format(analysis=analysis_result)
                    await message.reply_text(response, parse_mode='Markdown')
                else:
                    await message.reply_text(config.IMAGE_ANALYSIS_ERROR_TEMPLATE)
                    
            finally:
                # Очищаем временный файл
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except Exception as e:
            logger.error(f"Error in handle_photo_message: {e}")
            # Не отправляем сообщение об ошибке, чтобы не спамить

    async def handle_capabilities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать возможности бота"""
        try:
            capabilities = ai_client.get_capabilities_info()
            
            message = (
                "🤖 **Доступные возможности бота:**\n\n"
                f"{capabilities}\n\n"
                "---\n"
                "💡 *Для настройки дополнительных функций обратитесь к администратору*"
            )
            
            await update.effective_message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in handle_capabilities: {e}")
            await self._send_error_message(update, "при получении информации о возможностях")

    # Существующие методы настроек (оставляем без изменений)
    async def handle_settings_summary_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /settings_summary_time - настройка времени ежедневной суммаризации"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            if not context.args:
                current_time = self._get_summary_time(chat_id)
                await message.reply_text(
                    f"⏰ **Текущее время ежедневной суммаризации:** {current_time}\n\n"
                    "Чтобы изменить время, используйте:\n"
                    "`/settings_summary_time 21:00`\n"
                    "`/settings_summary_time 09:30`\n\n"
                    "💡 *Время указывается в 24-часовом формате*"
                )
                return
            
            time_str = context.args[0]
            
            # Валидация формата времени
            if not self._is_valid_time_format(time_str):
                await message.reply_text(
                    "❌ Неверный формат времени.\n"
                    "Используйте формат ЧЧ:MM (24 часа):\n"
                    "`/settings_summary_time 21:00`\n"
                    "`/settings_summary_time 09:30`"
                )
                return
            
            # Сохраняем настройку
            if self._set_summary_time(chat_id, time_str):
                await message.reply_text(
                    f"✅ Время ежедневной суммаризации установлено на **{time_str}**\n\n"
                    f"Бот будет отправлять суммаризацию каждый день в {time_str}"
                )
            else:
                await message.reply_text("❌ Не удалось сохранить настройки времени.")
                
        except Exception as e:
            logger.error(f"Error in handle_settings_summary_time: {e}")
            await self._send_error_message(update, "при настройке времени")

    # ... остальные методы handle_settings_* остаются без изменений ...

    async def _extract_text_from_media(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из различных типов медиа с использованием Yandex API"""
        try:
            # Голосовые сообщения - используем SpeechKit
            if message.voice:
                return await self._transcribe_voice_message(message, context)
            
            # Изображения с текстом - используем Vision API
            elif message.photo:
                return await self._extract_text_from_image(message, context)
            
            # Документы
            elif message.document:
                return await self._extract_text_from_document(message, context)
            
            # Текстовые сообщения (просто возвращаем текст)
            elif message.text:
                return message.text
            
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error extracting text from media: {e}")
            return None

    async def _transcribe_voice_message(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Транскрибация голосового сообщения с помощью Yandex SpeechKit"""
        try:
            if not config.is_speechkit_available():
                return None
            
            # Скачиваем голосовое сообщение
            voice_file = await message.voice.get_file()
            
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                temp_path = temp_file.name
                await voice_file.download_to_drive(temp_path)
                
                try:
                    # Используем наш AI клиент для распознавания
                    recognized_text = await ai_client.speech_to_text(temp_path)
                    return recognized_text
                finally:
                    # Очистка временного файла
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                
        except Exception as e:
            logger.error(f"Error transcribing voice message with SpeechKit: {e}")
            return None

    async def _extract_text_from_image(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из изображения с помощью Yandex Vision API"""
        try:
            if not config.is_vision_available():
                return None
            
            # Скачиваем изображение
            photo = message.photo[-1]  # Берем самое качественное
            photo_file = await photo.get_file()
            
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
                await photo_file.download_to_drive(temp_path)
                
                try:
                    # Используем наш AI клиент для анализа изображения
                    analysis_result = await ai_client.analyze_image(temp_path)
                    
                    # Извлекаем только текст из анализа
                    if analysis_result and "Текст на изображении:" in analysis_result:
                        # Парсим текст из ответа Vision API
                        lines = analysis_result.split('\n')
                        for line in lines:
                            if line.startswith("📝 **Текст на изображении:**"):
                                return line.replace("📝 **Текст на изображении:**", "").strip()
                    
                    return analysis_result  # Возвращаем весь анализ, если не удалось извлечь только текст
                finally:
                    # Очистка временного файла
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                
        except Exception as e:
            logger.error(f"Error extracting text from image with Vision API: {e}")
            return None

    async def _extract_text_from_document(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из документа"""
        # Базовая реализация - можно расширить для разных форматов
        if message.caption:
            return f"Документ: {message.caption}"
        else:
            return "Прикреплен документ (текст недоступен для автоматического извлечения)"

    def _save_recognized_voice_text(self, message: Message, recognized_text: str):
        """Сохранение распознанного текста из голосового сообщения"""
        try:
            user = message.from_user
            chat_id = message.chat_id
            
            self.db.save_message(
                chat_id=chat_id,
                user_id=user.id,
                user_name=user.username or user.first_name,
                message_text=f"[Распознанный голос] {recognized_text}",
                message_type='voice_text'
            )
        except Exception as e:
            logger.error(f"Error saving recognized voice text: {e}")

    def _save_image_analysis(self, message: Message, analysis_result: str):
        """Сохранение результата анализа изображения"""
        try:
            user = message.from_user
            chat_id = message.chat_id
            
            self.db.save_message(
                chat_id=chat_id,
                user_id=user.id,
                user_name=user.username or user.first_name,
                message_text=f"[Анализ изображения] {analysis_result}",
                message_type='image_analysis'
            )
        except Exception as e:
            logger.error(f"Error saving image analysis: {e}")

    def _format_extracted_text_response(self, extracted_text: str, original_message: Message) -> str:
        """Форматирование ответа с извлеченным текстом"""
        if original_message.voice:
            media_type = "голосового сообщения"
            template = config.VOICE_RECOGNITION_TEMPLATE
        elif original_message.photo:
            media_type = "изображения"
            template = config.IMAGE_ANALYSIS_TEMPLATE
        else:
            media_type = "медиа"
            template = config.EXTRACTED_TEXT_TEMPLATE
        
        return template.format(
            media_type=media_type,
            text=extracted_text
        )

    def _is_valid_time_format(self, time_str: str) -> bool:
        """Проверка корректности формата времени"""
        try:
            datetime.strptime(time_str, '%H:%M')
            return True
        except ValueError:
            return False

    # Методы работы с настройками в базе данных (оставляем без изменений)
    
    def _get_summary_time(self, chat_id: int) -> str:
        """Получение времени суммаризации для чата"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT summary_time FROM chat_settings WHERE chat_id = ?',
                (chat_id,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else config.DEFAULT_SUMMARY_TIME
            
        except Exception as e:
            logger.error(f"Error getting summary time: {e}")
            return config.DEFAULT_SUMMARY_TIME

    def _set_summary_time(self, chat_id: int, time_str: str) -> bool:
        """Установка времени суммаризации для чата"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO chat_settings 
                (chat_id, summary_time, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, time_str))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error setting summary time: {e}")
            return False

    # ... остальные методы работы с базой данных остаются без изменений ...

    async def _send_error_message(self, update: Update, action: str):
        """Отправка сообщения об ошибке"""
        try:
            await update.effective_message.reply_text(
                f"❌ Произошла ошибка {action}. "
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

    # Методы сохранения сообщений (оставляем без изменений)
    async def save_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение текстовых сообщений в базу данных"""
        try:
            message = update.effective_message
            if not message:
                return
            
            user = message.from_user
            chat_id = message.chat_id
            
            success = self.db.save_message(
                chat_id=chat_id,
                user_id=user.id,
                user_name=user.username or user.first_name,
                message_text=message.text,
                message_type='text'
            )
            
            if not success:
                logger.warning(f"Failed to save message from user {user.id} in chat {chat_id}")
                
        except Exception as e:
            logger.error(f"Error saving text message: {e}")

    async def save_media_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение медиа-сообщений в базу данных"""
        try:
            message = update.effective_message
            if not message:
                return
            
            user = message.from_user
            chat_id = message.chat_id
            
            # Определяем тип медиа и извлекаем текст если возможно
            media_type = 'unknown'
            media_text = ''
            file_id = ''
            
            if message.voice:
                media_type = 'voice'
                file_id = message.voice.file_id
                
            elif message.photo:
                media_type = 'photo'
                file_id = message.photo[-1].file_id
                if message.caption:
                    media_text = message.caption
                    
            elif message.document:
                media_type = 'document'
                file_id = message.document.file_id
                if message.caption:
                    media_text = message.caption
            
            success = self.db.save_message(
                chat_id=chat_id,
                user_id=user.id,
                user_name=user.username or user.first_name,
                message_text=media_text,
                message_type=media_type,
                media_file_id=file_id
            )
            
            if not success:
                logger.warning(f"Failed to save media message from user {user.id} in chat {chat_id}")
                
        except Exception as e:
            logger.error(f"Error saving media message: {e}")