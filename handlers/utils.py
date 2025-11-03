import logging
import os
import tempfile
import asyncio
from typing import List, Dict, Optional, Tuple
from datetime import datetime, time
import sqlite3

from telegram import Update, Message
from telegram.ext import ContextTypes, filters
import openai
from PIL import Image
import requests
from pydub import AudioSegment

from config import config
from database import DatabaseManager


logger = logging.getLogger(__name__)

class UtilsHandler:
    """Обработчик вспомогательных функций и утилит"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.openai_client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    
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
    
    async def handle_settings_daily_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /settings_daily_summary - вкл/выкл ежедневной суммаризации"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            current_setting = self._get_daily_summary_setting(chat_id)
            
            if not context.args:
                status = "включена" if current_setting else "выключена"
                await message.reply_text(
                    f"📊 **Ежедневная суммаризация:** {status}\n\n"
                    "Чтобы изменить настройку, используйте:\n"
                    "`/settings_daily_summary on` - включить\n"
                    "`/settings_daily_summary off` - выключить"
                )
                return
            
            action = context.args[0].lower()
            
            if action in ['on', 'вкл', 'enable', 'true', '1']:
                new_setting = True
                status_text = "включена"
            elif action in ['off', 'выкл', 'disable', 'false', '0']:
                new_setting = False
                status_text = "выключена"
            else:
                await message.reply_text(
                    "❌ Неверный аргумент.\n"
                    "Используйте:\n"
                    "`/settings_daily_summary on` - включить\n"
                    "`/settings_daily_summary off` - выключить"
                )
                return
            
            if self._set_daily_summary_setting(chat_id, new_setting):
                await message.reply_text(
                    f"✅ Ежедневная суммаризация **{status_text}**\n\n"
                    f"Суммаризация будет {'отправляться' if new_setting else 'отключена'} "
                    f"в {self._get_summary_time(chat_id)} каждый день."
                )
            else:
                await message.reply_text("❌ Не удалось сохранить настройки.")
                
        except Exception as e:
            logger.error(f"Error in handle_settings_daily_summary: {e}")
            await self._send_error_message(update, "при настройке ежедневной суммаризации")
    
    async def handle_settings_pin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /settings_pin - вкл/выкл закрепления суммаризации"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            current_setting = self._get_pin_setting(chat_id)
            
            if not context.args:
                status = "включено" if current_setting else "выключено"
                await message.reply_text(
                    f"📌 **Закрепление суммаризации:** {status}\n\n"
                    "Чтобы изменить настройку, используйте:\n"
                    "`/settings_pin on` - включить\n"
                    "`/settings_pin off` - выключить"
                )
                return
            
            action = context.args[0].lower()
            
            if action in ['on', 'вкл', 'enable', 'true', '1']:
                new_setting = True
                status_text = "включено"
            elif action in ['off', 'выкл', 'disable', 'false', '0']:
                new_setting = False
                status_text = "выключено"
            else:
                await message.reply_text(
                    "❌ Неверный аргумент.\n"
                    "Используйте:\n"
                    "`/settings_pin on` - включить\n"
                    "`/settings_pin off` - выключить"
                )
                return
            
            if self._set_pin_setting(chat_id, new_setting):
                await message.reply_text(
                    f"✅ Закрепление суммаризации **{status_text}**\n\n"
                    f"Суммаризации будут {'закрепляться' if new_setting else 'отправляться без закрепления'}."
                )
            else:
                await message.reply_text("❌ Не удалось сохранить настройки.")
                
        except Exception as e:
            logger.error(f"Error in handle_settings_pin: {e}")
            await self._send_error_message(update, "при настройке закрепления")
    
    async def handle_set_personality(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /set_personality - установка личности бота"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            if not context.args:
                current_personality = self._get_bot_personality(chat_id)
                if current_personality:
                    await message.reply_text(
                        f"🎭 **Текущая личность бота:**\n{current_personality}\n\n"
                        "Чтобы изменить личность, используйте:\n"
                        "`/set_personality [описание личности]`\n\n"
                        "Примеры:\n"
                        "`/set_personality профессиональный бизнес-аналитик`\n"
                        "`/set_personality веселый и дружелюбный помощник`\n"
                        "`/set_personality эксперт по технологиям с чувством юмора`"
                    )
                else:
                    await message.reply_text(
                        "🎭 **Личность бота не установлена**\n\n"
                        "Чтобы установить личность, используйте:\n"
                        "`/set_personality [описание личности]`\n\n"
                        "Личность влияет на:\n"
                        "• Стиль суммаризации\n"
                        "• Ответы на вопросы /ask\n"
                        "• Анализ пользователей /opinion\n"
                        "• Комментарии /comment"
                    )
                return
            
            personality = " ".join(context.args)
            
            # Проверяем длину описания
            if len(personality) > 500:
                await message.reply_text(
                    "❌ Описание личности слишком длинное.\n"
                    "Максимальная длина - 500 символов."
                )
                return
            
            if self._set_bot_personality(chat_id, personality):
                await message.reply_text(
                    f"✅ **Личность бота установлена:**\n\n{personality}\n\n"
                    "Теперь бот будет использовать эту личность при:\n"
                    "• Создании суммаризации\n"
                    "• Ответах на вопросы /ask\n"
                    "• Анализе пользователей /opinion\n"
                    "• Комментариях к обсуждениям\n\n"
                    "Чтобы очистить личность, используйте /clear_personality"
                )
            else:
                await message.reply_text("❌ Не удалось сохранить личность бота.")
                
        except Exception as e:
            logger.error(f"Error in handle_set_personality: {e}")
            await self._send_error_message(update, "при установке личности")
    
    async def handle_clear_personality(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /clear_personality - очистка личности бота"""
        try:
            chat_id = update.effective_chat.id
            
            if self._clear_bot_personality(chat_id):
                await update.effective_message.reply_text(
                    "✅ **Личность бота очищена**\n\n"
                    "Бот вернулся к стандартному стилю общения."
                )
            else:
                await update.effective_message.reply_text(
                    "❌ Не удалось очистить личность бота.\n"
                    "Возможно, личность не была установлена."
                )
                
        except Exception as e:
            logger.error(f"Error in handle_clear_personality: {e}")
            await self._send_error_message(update, "при очистке личности")
    
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
                # Можно добавить автоматическое распознавание голоса
                
            elif message.photo:
                media_type = 'photo'
                file_id = message.photo[-1].file_id  # Берем самое качественное фото
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
    
    async def _extract_text_from_media(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из различных типов медиа"""
        try:
            # Голосовые сообщения
            if message.voice:
                return await self._transcribe_voice_message(message, context)
            
            # Изображения с текстом
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
        """Транскрибация голосового сообщения"""
        try:
            # Скачиваем голосовое сообщение
            voice_file = await message.voice.get_file()
            
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                await voice_file.download_to_drive(temp_file.name)
                
                # Конвертируем в формат, подходящий для OpenAI
                audio = AudioSegment.from_ogg(temp_file.name)
                wav_path = temp_file.name.replace('.ogg', '.wav')
                audio.export(wav_path, format='wav')
                
                # Отправляем в OpenAI Whisper для транскрибации
                with open(wav_path, 'rb') as audio_file:
                    transcription = await self.openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ru"  # Можно определить автоматически
                    )
                
                # Очистка временных файлов
                os.unlink(temp_file.name)
                os.unlink(wav_path)
                
                return transcription.text
                
        except Exception as e:
            logger.error(f"Error transcribing voice message: {e}")
            return None
    
    async def _extract_text_from_image(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из изображения с помощью OCR"""
        try:
            # Скачиваем изображение
            photo = message.photo[-1]  # Берем самое качественное
            photo_file = await photo.get_file()
            
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                await photo_file.download_to_drive(temp_file.name)
                
                # Используем GPT-4 Vision для распознавания текста
                with open(temp_file.name, 'rb') as image_file:
                    response = await self.openai_client.chat.completions.create(
                        model="gpt-4-vision-preview",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text", 
                                        "text": "Прочитай и верни весь текст, который видишь на этом изображении. Сохрани форматирование и структуру текста. Если текст на русском - верни на русском, если на английском - на английском."
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{self._image_to_base64(temp_file.name)}"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=1000
                    )
                
                # Очистка временного файла
                os.unlink(temp_file.name)
                
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Error extracting text from image: {e}")
            return None
    
    async def _extract_text_from_document(self, message: Message, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Извлечение текста из документа"""
        # Базовая реализация - можно расширить для разных форматов
        if message.caption:
            return f"Документ: {message.caption}"
        else:
            return "Прикреплен документ (текст недоступен для автоматического извлечения)"
    
    def _image_to_base64(self, image_path: str) -> str:
        """Конвертация изображения в base64"""
        import base64
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def _save_extracted_text(self, update: Update, original_message: Message, extracted_text: str):
        """Сохранение извлеченного текста в базу"""
        try:
            user = update.effective_user
            chat_id = update.effective_chat.id
            
            self.db.save_message(
                chat_id=chat_id,
                user_id=user.id,
                user_name=user.username or user.first_name,
                message_text=f"[Извлеченный текст] {extracted_text}",
                message_type='extracted_text'
            )
        except Exception as e:
            logger.error(f"Error saving extracted text: {e}")
    
    def _format_extracted_text_response(self, extracted_text: str, original_message: Message) -> str:
        """Форматирование ответа с извлеченным текстом"""
        media_type = "голосовое сообщение" if original_message.voice else "изображение"
        
        return f"""📝 **Текст из {media_type}:**

{extracted_text}

---
*Текст извлечен автоматически. Точность может варьироваться.*"""
    
    def _is_valid_time_format(self, time_str: str) -> bool:
        """Проверка корректности формата времени"""
        try:
            datetime.strptime(time_str, '%H:%M')
            return True
        except ValueError:
            return False
    
    # Методы работы с настройками в базе данных
    
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
    
    def _get_daily_summary_setting(self, chat_id: int) -> bool:
        """Получение настройки ежедневной суммаризации"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT daily_summary_enabled FROM chat_settings WHERE chat_id = ?',
                (chat_id,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            return bool(result[0]) if result else config.DEFAULT_SUMMARY_ENABLED
            
        except Exception as e:
            logger.error(f"Error getting daily summary setting: {e}")
            return config.DEFAULT_SUMMARY_ENABLED
    
    def _set_daily_summary_setting(self, chat_id: int, enabled: bool) -> bool:
        """Установка настройки ежедневной суммаризации"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO chat_settings 
                (chat_id, daily_summary_enabled, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, enabled))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error setting daily summary: {e}")
            return False
    
    def _get_pin_setting(self, chat_id: int) -> bool:
        """Получение настройки закрепления"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT pin_summary FROM chat_settings WHERE chat_id = ?',
                (chat_id,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            return bool(result[0]) if result else config.DEFAULT_PIN_SUMMARY
            
        except Exception as e:
            logger.error(f"Error getting pin setting: {e}")
            return config.DEFAULT_PIN_SUMMARY
    
    def _set_pin_setting(self, chat_id: int, enabled: bool) -> bool:
        """Установка настройки закрепления"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO chat_settings 
                (chat_id, pin_summary, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, enabled))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error setting pin: {e}")
            return False
    
    def _get_bot_personality(self, chat_id: int) -> Optional[str]:
        """Получение личности бота"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute(
                'SELECT bot_personality FROM chat_settings WHERE chat_id = ?',
                (chat_id,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error getting bot personality: {e}")
            return None
    
    def _set_bot_personality(self, chat_id: int, personality: str) -> bool:
        """Установка личности бота"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO chat_settings 
                (chat_id, bot_personality, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, personality))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error setting bot personality: {e}")
            return False
    
    def _clear_bot_personality(self, chat_id: int) -> bool:
        """Очистка личности бота"""
        try:
            conn = sqlite3.connect('chat_data.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE chat_settings 
                SET bot_personality = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            ''', (chat_id,))
            
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error clearing bot personality: {e}")
            return False
    
    async def _send_error_message(self, update: Update, action: str):
        """Отправка сообщения об ошибке"""
        try:
            await update.effective_message.reply_text(
                f"❌ Произошла ошибка {action}. "
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}") 
async def save_text_to_db(self, chat_id: int, user_id: int, username: str, text: str, 
                         is_voice: bool = False, is_photo: bool = False):
    """Сохранение текста в базу данных"""
    try:
        # Используем существующий метод save_message из DatabaseManager
        await self.db.save_message(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            text=text,
            message_type='voice' if is_voice else 'photo_text' if is_photo else 'text'
        )
        logger.info(f"Текст сохранен в БД: {text[:100]}... (тип: {'voice' if is_voice else 'photo' if is_photo else 'text'})")
        return True
    except Exception as e:
        logger.error(f"Error saving text to DB: {e}")
        return False