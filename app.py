import os
import logging
from typing import Optional

# Определяем среду выполнения
IS_RAILWAY = os.getenv('RAILWAY', False)
IS_PRODUCTION = IS_RAILWAY

# Настройка логирования для Railway
if IS_PRODUCTION:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[logging.StreamHandler()]  # Только консоль для Railway
    )
else:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot_debug.log', encoding='utf-8')
        ]
    )

logger = logging.getLogger(__name__)

# Проверка обязательных переменных
def check_environment():
    required_vars = ['TELEGRAM_TOKEN', 'YANDEX_API_KEY', 'YANDEX_FOLDER_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        if IS_PRODUCTION:
            raise ValueError(error_msg)
        else:
            logger.warning("Running in development mode with missing variables")
import os
import logging
from typing import Optional
from dotenv import load_dotenv
import requests
import json
import asyncio
import tempfile
import subprocess

# Импорты для обработки медиа
import speech_recognition as sr
import easyocr
from pydub import AudioSegment

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Инициализация EasyOCR для русского и английского языков
try:
    reader = easyocr.Reader(['ru', 'en'])
    logger.info("EasyOCR успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации EasyOCR: {e}")
    reader = None

class MediaProcessor:
    """Класс для обработки медиа-контента (голосовые, изображения)"""
    
    @staticmethod
    def extract_text_from_image(image_path: str) -> str:
        """Извлекает текст с изображения с помощью EasyOCR"""
        try:
            if reader is None:
                return "Ошибка: OCR не инициализирован"
                
            logger.info("Начало распознавания текста с изображения")
            
            # Распознаем текст
            results = reader.readtext(image_path)
            
            if not results:
                return "Текст на изображении не обнаружен"
            
            # Объединяем все распознанные тексты
            text = '\n'.join([result[1] for result in results])
            logger.info(f"Распознанный текст: {text[:100]}...")
            
            return text
            
        except Exception as e:
            logger.error(f"Ошибка при распознавании текста: {e}")
            return f"Ошибка при распознавании текста: {str(e)}"
    
    @staticmethod
    def convert_audio_ogg_to_wav(ogg_path: str, wav_path: str) -> bool:
        """Конвертирует OGG в WAV используя pydub"""
        try:
            audio = AudioSegment.from_ogg(ogg_path)
            audio.export(wav_path, format="wav")
            return True
        except Exception as e:
            logger.error(f"Ошибка конвертации аудио через pydub: {e}")
            return MediaProcessor.convert_audio_ffmpeg(ogg_path, wav_path)
    
    @staticmethod
    def convert_audio_ffmpeg(ogg_path: str, wav_path: str) -> bool:
        """Альтернативный способ конвертации через ffmpeg"""
        try:
            ffmpeg_paths = [
                'ffmpeg', 'ffmpeg.exe', './ffmpeg', 
                './ffmpeg.exe', 'C:\\ffmpeg\\bin\\ffmpeg.exe'
            ]
            
            for ffmpeg_path in ffmpeg_paths:
                try:
                    result = subprocess.run(
                        [ffmpeg_path, '-y', '-i', ogg_path, wav_path], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.PIPE,
                        timeout=30
                    )
                    if result.returncode == 0:
                        logger.info(f"Аудио сконвертировано с помощью: {ffmpeg_path}")
                        return True
                except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                    continue
                    
            logger.error("Не удалось найти рабочий ffmpeg")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка конвертации через ffmpeg: {e}")
            return False
    
    @staticmethod
    def transcribe_audio(audio_path: str) -> str:
        """Транскрибирует аудио в текст"""
        try:
            r = sr.Recognizer()
            with sr.AudioFile(audio_path) as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.record(source)
            
            text = r.recognize_google(audio, language="ru-RU")
            logger.info(f"Распознанная речь: {text}")
            return text
            
        except sr.UnknownValueError:
            logger.error("Не удалось распознать речь")
            return "Не удалось распознать речь. Попробуйте говорить четче и громче."
        except sr.RequestError as e:
            logger.error(f"Ошибка сервиса распознавания речи: {e}")
            return "Ошибка сервиса распознавания речи. Проверьте подключение к интернету."
        except Exception as e:
            logger.error(f"Ошибка транскрибации аудио: {e}")
            return f"Ошибка обработки аудио: {str(e)}"

class YandexGPT:
    def __init__(self, api_key: str, folder_id: str):
        self.api_key = api_key
        self.folder_id = folder_id
        self.url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        
    def generate_response(self, prompt: str) -> str:
        """Генерация ответа через Yandex GPT API"""
        try:
            headers = {
                "Authorization": f"Api-Key {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "modelUri": f"gpt://{self.folder_id}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.6,
                    "maxTokens": 2000
                },
                "messages": [
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }
            
            response = requests.post(self.url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            return result['result']['alternatives'][0]['message']['text']
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            return "⚠️ Произошла ошибка сети. Попробуйте позже."
        except KeyError as e:
            logger.error(f"API response format error: {e}")
            return "⚠️ Ошибка в формате ответа от API."
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return "❌ Произошла непредвиденная ошибка."

class DatabaseManager:
    """Упрощенный менеджер базы данных для демонстрации"""
    
    def __init__(self):
        self.messages = []
        
    async def get_recent_messages(self, chat_id: int, limit: int = 100):
        """Получение последних сообщений из чата (заглушка)"""
        try:
            # В реальной реализации здесь был бы запрос к БД
            # Для демонстрации возвращаем сохраненные сообщения
            recent_messages = self.messages[-limit:] if len(self.messages) > limit else self.messages
            return recent_messages
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    async def save_message(self, chat_id: int, user_id: int, username: str, text: str, message_type: str = 'text'):
        """Сохранение сообщения (заглушка)"""
        try:
            message_data = {
                'chat_id': chat_id,
                'user_id': user_id,
                'username': username,
                'text': text,
                'type': message_type,
                'timestamp': asyncio.get_event_loop().time()
            }
            self.messages.append(message_data)
            logger.info(f"Message saved: {username}: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return False

class EnhancedAIAssistant:
    def __init__(self):
        # Конфигурация (замените на ваши реальные токены)
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'your_telegram_token')
        self.YANDEX_API_KEY = os.getenv('YANDEX_API_KEY', 'your_yandex_api_key')
        self.YANDEX_FOLDER_ID = os.getenv('YANDEX_FOLDER_ID', 'your_yandex_folder_id')
        
        # Инициализация компонентов
        self.application = Application.builder().token(self.TELEGRAM_TOKEN).build()
        self.db = DatabaseManager()
        self.media_processor = MediaProcessor()
        self.yandex_gpt = YandexGPT(
            api_key=self.YANDEX_API_KEY,
            folder_id=self.YANDEX_FOLDER_ID
        )
        
        self.setup_handlers()
        self.setup_error_handler()
    
    def setup_handlers(self):
        """Настройка всех обработчиков команд"""
        
        # Основные функции
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CommandHandler("about", self.handle_about))
        
        # Решение споров
        self.application.add_handler(CommandHandler("dispute", self.handle_dispute))
        
        # Работа с вопросами
        self.application.add_handler(CommandHandler("yagpt", self.handle_yagpt))
        
        # Утилиты
        self.application.add_handler(CommandHandler("text", self.handle_text))
        
        # Обработка текстовых сообщений
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND, 
                self.handle_text_message
            )
        )
        
        # Обработка голосовых сообщений
        self.application.add_handler(
            MessageHandler(
                filters.VOICE, 
                self.handle_voice_message
            )
        )
        
        # Обработка изображений
        self.application.add_handler(
            MessageHandler(
                filters.PHOTO, 
                self.handle_photo_message
            )
        )
    
    def setup_error_handler(self):
        """Настройка обработчика ошибок"""
        self.application.add_error_handler(self.error_handler)

    async def save_text_to_db(self, chat_id: int, user_id: int, username: str, text: str, 
                            is_voice: bool = False, is_photo: bool = False):
        """Сохранение текста в базу данных"""
        try:
            message_type = 'voice' if is_voice else 'photo_text' if is_photo else 'text'
            success = await self.db.save_message(chat_id, user_id, username, text, message_type)
            return success
        except Exception as e:
            logger.error(f"Error saving text to DB: {e}")
            return False

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка голосовых сообщений с сохранением в историю"""
        try:
            voice = update.message.voice
            user = update.effective_user
            chat = update.effective_chat
            
            logger.info(f"Получено голосовое сообщение от пользователя {user.id}")
            
            # Показываем статус обработки
            await update.message.chat.send_action(action="typing")
            
            # Скачиваем голосовое сообщение
            voice_file = await voice.get_file()
            ogg_path = ""
            wav_path = ""
            
            try:
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as ogg_file:
                    await voice_file.download_to_drive(ogg_file.name)
                    ogg_path = ogg_file.name
                
                logger.info(f"OGG файл сохранен: {ogg_path}")
                
                # Конвертируем в WAV
                wav_path = ogg_path.replace('.ogg', '.wav')
                if not self.media_processor.convert_audio_ogg_to_wav(ogg_path, wav_path):
                    await update.message.reply_text("❌ Ошибка конвертации аудио формата")
                    return
                
                # Транскрибируем аудио
                transcribed_text = self.media_processor.transcribe_audio(wav_path)
                
                if transcribed_text and "Не удалось распознать речь" not in transcribed_text and "Ошибка" not in transcribed_text:
                    # Сохраняем распознанный текст в базу
                    success = await self.save_text_to_db(
                        chat.id, user.id, user.first_name, transcribed_text, is_voice=True
                    )
                    
                    if success:
                        # Отправляем распознанный текст пользователю
                        await update.message.reply_text(
                            f"🎤 Распознанная речь:\n\n{transcribed_text}",
                            reply_to_message_id=update.message.message_id
                        )
                        
                        logger.info(f"Голосовое сообщение сохранено как текст: {transcribed_text[:100]}...")
                    else:
                        await update.message.reply_text(
                            "❌ Ошибка сохранения текста в базу данных",
                            reply_to_message_id=update.message.message_id
                        )
                else:
                    await update.message.reply_text(
                        "❌ Не удалось распознать речь. Попробуйте говорить четче.",
                        reply_to_message_id=update.message.message_id
                    )
                    
            finally:
                # Очистка временных файлов
                for path in [ogg_path, wav_path]:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                            logger.info(f"Удален временный файл: {path}")
                        except Exception as e:
                            logger.error(f"Ошибка удаления файла {path}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки голосового сообщения: {e}")
            await update.message.reply_text(
                "⚠️ Произошла ошибка при обработке голосового сообщения.",
                reply_to_message_id=update.message.message_id
            )

    async def handle_photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка изображений с извлечением текста и сохранением в историю"""
        try:
            photo = update.message.photo[-1]  # Берем самое качественное изображение
            user = update.effective_user
            chat = update.effective_chat
            
            logger.info(f"Получено изображение от пользователя {user.id}")
            
            # Показываем статус обработки
            await update.message.chat.send_action(action="typing")
            
            # Скачиваем изображение
            photo_file = await photo.get_file()
            image_path = ""
            
            try:
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as img_file:
                    await photo_file.download_to_drive(img_file.name)
                    image_path = img_file.name
                
                logger.info(f"Изображение сохранено: {image_path}")
                
                # Извлекаем текст с изображения
                extracted_text = self.media_processor.extract_text_from_image(image_path)
                
                if extracted_text and "не обнаружен" not in extracted_text and "Ошибка" not in extracted_text:
                    # Сохраняем извлеченный текст в базу
                    success = await self.save_text_to_db(
                        chat.id, user.id, user.first_name, extracted_text, is_photo=True
                    )
                    
                    if success:
                        # Обрезаем длинный текст для отображения
                        display_text = extracted_text[:2000] + "..." if len(extracted_text) > 2000 else extracted_text
                        
                        # Отправляем распознанный текст пользователю
                        await update.message.reply_text(
                            f"📖 Распознанный текст с изображения:\n\n{display_text}",
                            reply_to_message_id=update.message.message_id
                        )
                        
                        logger.info(f"Текст с изображения сохранен: {extracted_text[:100]}...")
                    else:
                        await update.message.reply_text(
                            "❌ Ошибка сохранения текста в базу данных",
                            reply_to_message_id=update.message.message_id
                        )
                else:
                    await update.message.reply_text(
                        "❌ Не удалось распознать текст на изображении. Попробуйте отправить более четкое изображение.",
                        reply_to_message_id=update.message.message_id
                    )
                    
            finally:
                # Очистка временного файла
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        logger.info(f"Удален временный файл: {image_path}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления файла {image_path}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки изображения: {e}")
            await update.message.reply_text(
                "⚠️ Произошла ошибка при обработке изображения.",
                reply_to_message_id=update.message.message_id
            )

    async def handle_dispute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /dispute - сбалансированная версия с четкой позицией"""
        try:
            chat_id = update.effective_chat.id

            await update.message.chat.send_action(action="typing")

            messages = await self.db.get_recent_messages(chat_id, limit=100)

            if not messages:
                await update.message.reply_text("❌ Недостаточно сообщений для анализа.")
                return

            chat_history = "\n".join([f"{msg['username']}: {msg['text']}" for msg in messages])

            prompt = f"""
            Анализируй этот чат как опытный медиатор:

            {chat_history}

            Дай ответ в таком формате:

            🎯 **СУТЬ КОНФЛИКТА:** 
            [Опиши основную проблему]

            👥 **АНАЛИЗ СТОРОН:**
            - Сторона А: [имя] - [позиция] - [сильные аргументы]
            - Сторона Б: [имя] - [позиция] - [сильные аргументы]

            ⚖️ **МОЁ РЕШЕНИЕ:**
            🏆 **ПРАВ:** [конкретное имя]
            📉 **НЕ ПРАВ:** [конкретное имя] 
            ❤️ **НА ЧЬЕЙ СТОРОНЕ Я:** [имя] - [четкое обоснование]

            💡 **ПОЧЕМУ ИМЕННО ТАК:**
            [Развернутое объяснение твоей позиции]

            🤝 **КАК ИСПРАВИТЬ:**
            [Конкретные шаги]

            Будь честным и прямым. Не бойся занимать четкую позицию.
            """

            response = await asyncio.get_event_loop().run_in_executor(
                None, self.yandex_gpt.generate_response, prompt
            )

            result = (
                f"⚖️ **ЭКСПЕРТНОЕ ЗАКЛЮЧЕНИЕ**\n\n"
                f"На основе {len(messages)} сообщений:\n\n"
                f"{response}\n\n"
                f"📊 _Анализ проведен на основе последних сообщений чата_"
            )

            await update.message.reply_text(result)

        except Exception as e:
            logger.error(f"Error in dispute handler: {e}")
            await update.message.reply_text("❌ Ошибка при анализе чата.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Улучшенная команда /text для извлечения текста из медиа"""
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "❌ Пожалуйста, ответьте этой командой на голосовое сообщение или изображение, чтобы извлечь текст."
            )
            return
        
        replied_message = update.message.reply_to_message
        
        if replied_message.voice:
            # Обрабатываем голосовое сообщение
            await self.handle_voice_message(update, context)
        elif replied_message.photo:
            # Обрабатываем изображение
            await self.handle_photo_message(update, context)
        else:
            await update.message.reply_text(
                "❌ Ответьте на голосовое сообщение или изображение для извлечения текста."
            )

    async def handle_yagpt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /yagpt - Яндекс GPT"""
        if not context.args:
            await update.message.reply_text("❌ Пожалуйста, напишите вопрос после команды /yagpt")
            return
        
        question = " ".join(context.args)
        
        if len(question) > 4000:
            await update.message.reply_text("❌ Сообщение слишком длинное. Максимум 4000 символов.")
            return
        
        await update.message.chat.send_action(action="typing")
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, self.yandex_gpt.generate_response, question
            )
            await update.message.reply_text(response)
            logger.info(f"Yandex GPT request from user {update.effective_user.id}: {question[:50]}...")
            
        except Exception as e:
            logger.error(f"Error in Yandex GPT handler: {e}")
            await update.message.reply_text("🚫 Произошла ошибка при обработке вашего запроса через Яндекс GPT.")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений для сохранения в историю"""
        try:
            user = update.effective_user
            chat = update.effective_chat
            text = update.message.text
            
            # Сохраняем текстовое сообщение в базу
            success = await self.save_text_to_db(
                chat.id, user.id, user.first_name, text, is_voice=False, is_photo=False
            )
            
            if success:
                logger.info(f"Text message saved from {user.first_name}: {text[:50]}...")
            else:
                logger.error(f"Failed to save text message from {user.first_name}")
                
        except Exception as e:
            logger.error(f"Error saving text message: {e}")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start с информацией о новых функциях"""
        welcome_text = """
🤖 **Добро пожаловать в Enhanced AI Assistant Bot!**

Я помогу вам анализировать групповые чаты, суммаризировать обсуждения, решать споры и отвечать на вопросы.

**⚖️ Новые возможности:**
• /dispute - Анализ последних сообщений чата на наличие конфликтов и споров

**🎤 Медиа-функции:**
• Распознавание голосовых сообщений и сохранение в историю
• Чтение текста с изображений и сохранение в историю

**📊 Основные команды:**
• /dispute - Анализ споров в чате (последние 100 сообщений)
• /yagpt [вопрос] - Ответ через Яндекс GPT
• /text - Извлечение текста из голосовых и изображений

**🛠️ Утилиты:**
• Просто отправьте голосовое сообщение - я распознаю и сохраню его
• Отправьте изображение с текстом - я прочитаю и сохраню текст
• /text - Извлечение текста из голосовых и изображений (ответьте на сообщение)

Напишите /help для полного списка команд!
        """
        await update.message.reply_text(welcome_text) 
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help с информацией о медиа-функциях"""
        help_text = """
📚 **Полный список команд Enhanced Bot:**

**🎤 Медиа-функции:**
• Отправьте голосовое сообщение - автоматическое распознавание и сохранение
• Отправьте изображение с текстом - автоматическое чтение и сохранение текста
• /text - Принудительное извлечение текста (ответьте на медиа-сообщение)

**⚖️ Решение споров:**
• /dispute - Анализ последних 100 сообщений чата на наличие конфликтов и споров

**❓ Работа с вопросами:**
• /yagpt [вопрос] - Ответ через Яндекс GPT

**ℹ️ Примечания:**
- Голосовые сообщения автоматически распознаются и сохраняются
- Текст с изображений автоматически извлекается и сохраняется
- Вся история (текст + распознанный контент) используется для анализа
        """
        await update.message.reply_text(help_text)

    async def handle_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /about"""
        about_text = """
ℹ️ **О Enhanced AI Assistant Bot:**

Этот бот использует несколько AI-моделей и технологий для работы:

**Технологии:**
• Yandex GPT API - для ответов на вопросы и решения споров
• SpeechRecognition - для распознавания голосовых сообщений
• EasyOCR - для чтения текста с изображений
• AI-анализ сообщений

**Функциональность:**
- Анализ групповых чатов
- Решение споров и конфликтных ситуаций
- Ответы на вопросы
- Распознавание текста из голосовых и изображений
- Автоматическое сохранение медиа-контента в историю

Бот разработан для удобного взаимодействия с AI в Telegram.
        """
        await update.message.reply_text(about_text)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ошибок"""
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
        
        try:
            error_message = "⚠️ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            if update and update.effective_message:
                await update.effective_message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск Enhanced AI Assistant Bot с медиа-функциями и решением споров...")
        self.application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )

def main():
    """Основная функция запуска"""
    try:
        # Проверяем переменные окружения
        check_environment()
        
        bot = EnhancedAIAssistant()
        
        if IS_PRODUCTION:
            logger.info("🚀 Starting bot in PRODUCTION mode on Railway")
        else:
            logger.info("🔧 Starting bot in DEVELOPMENT mode")
            
        bot.run()
            
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        if IS_PRODUCTION:
            # В продакшене выходим с ошибкой
            raise
        else:
            # В разработке продолжаем
            logger.info("Bot stopped")

if __name__ == "__main__":
    main()