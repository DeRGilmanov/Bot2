import logging
from typing import List, Dict, Optional
from telegram import Update, Message
from telegram.ext import ContextTypes
from config import config
from database import DatabaseManager
from ai_client import AIClient  # Добавляем импорт универсального клиента

logger = logging.getLogger(__name__)

class SummaryHandler:
    """Обработчик команд суммаризации и анализа тем"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.ai_client = AIClient()  # Заменяем OpenAI клиент на универсальный
    
    async def handle_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /summary [n]"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            # Получаем количество сообщений для анализа
            n_messages = self._parse_message_count(context.args, default=50)
            
            # Проверяем лимит сообщений
            if n_messages > config.MAX_MESSAGES_FOR_ANALYSIS:
                await message.reply_text(
                    f"⚠️ Максимальное количество сообщений для анализа: {config.MAX_MESSAGES_FOR_ANALYSIS}\n"
                    f"Использую {config.MAX_MESSAGES_FOR_ANALYSIS} сообщений."
                )
                n_messages = config.MAX_MESSAGES_FOR_ANALYSIS
            
            # Получаем сообщения из базы данных
            messages = self.db.get_recent_messages(chat_id, n_messages)
            
            if not messages:
                await message.reply_text("📭 Нет сообщений для суммаризации.")
                return
            
            # Отправляем сообщение о начале обработки
            processing_msg = await message.reply_text(
                f"🔄 Анализирую последние {len(messages)} сообщений..."
            )
            
            # Получаем личность бота для контекста
            personality = self._get_bot_personality(chat_id)
            
            # Создаем суммаризацию
            summary = await self._create_summary(messages, personality)
            
            # Удаляем сообщение о обработке
            await processing_msg.delete()
            
            # Отправляем результат
            response_text = f"📋 **Суммаризация последних {len(messages)} сообщений:**\n\n{summary}"
            
            # Если включен закреп, закрепляем сообщение
            if self._should_pin_summary(chat_id):
                sent_message = await message.reply_text(response_text)
                try:
                    await sent_message.pin(disable_notification=True)
                except Exception as e:
                    logger.warning(f"Could not pin message: {e}")
            else:
                await message.reply_text(response_text)
                
        except Exception as e:
            logger.error(f"Error in handle_summary: {e}")
            await self._send_error_message(update, "при создании суммаризации")
    
    async def handle_themes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /themes [n]"""
        try:
            chat_id = update.effective_chat.id
            message = update.effective_message
            
            # Получаем количество сообщений для анализа
            n_messages = self._parse_message_count(context.args, default=50)
            
            if n_messages > config.MAX_MESSAGES_FOR_ANALYSIS:
                await message.reply_text(
                    f"⚠️ Максимальное количество сообщений для анализа: {config.MAX_MESSAGES_FOR_ANALYSIS}"
                )
                n_messages = config.MAX_MESSAGES_FOR_ANALYSIS
            
            # Получаем сообщения
            messages = self.db.get_recent_messages(chat_id, n_messages)
            
            if not messages:
                await message.reply_text("📭 Нет сообщений для анализа тем.")
                return
            
            # Сообщение о обработке
            processing_msg = await message.reply_text(
                f"🎯 Анализирую темы из {len(messages)} сообщений..."
            )
            
            # Получаем личность бота
            personality = self._get_bot_personality(chat_id)
            
            # Анализируем темы
            themes = await self._analyze_themes(messages, personality)
            
            # Удаляем сообщение о обработке
            await processing_msg.delete()
            
            # Отправляем результат
            response_text = f"🎯 **Основные темы из {len(messages)} сообщений:**\n\n{themes}"
            await message.reply_text(response_text)
            
        except Exception as e:
            logger.error(f"Error in handle_themes: {e}")
            await self._send_error_message(update, "при анализе тем")
    
    async def handle_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /brief - краткое изложение длинного сообщения"""
        try:
            message = update.effective_message
            
            # Проверяем, является ли сообщение ответом на другое сообщение
            if not message.reply_to_message:
                await message.reply_text(
                    "📝 **Как использовать /brief:**\n\n"
                    "Ответьте этой командой на длинное сообщение, которое нужно сократить."
                )
                return
            
            # Получаем текст сообщения, на которое ответили
            target_message = message.reply_to_message
            text_to_summarize = self._extract_text_from_message(target_message)
            
            if not text_to_summarize:
                await message.reply_text("❌ Не удалось извлечь текст из сообщения.")
                return
            
            # Проверяем длину текста
            if len(text_to_summarize) < config.BRIEF_MIN_LENGTH:
                await message.reply_text(
                    f"📏 Сообщение слишком короткое для сокращения (минимум {config.BRIEF_MIN_LENGTH} символов). "
                    "Команда /brief предназначена для длинных сообщений."
                )
                return
            
            # Сообщение о обработке
            processing_msg = await message.reply_text("🔄 Сокращаю сообщение...")
            
            # Создаем краткое изложение
            brief = await self._create_brief_summary(text_to_summarize)
            
            # Удаляем сообщение о обработке
            await processing_msg.delete()
            
            # Отправляем результат
            preview = text_to_summarize[:200] + "..." if len(text_to_summarize) > 200 else text_to_summarize
            response_text = (
                f"📄 **Оригинал:** {preview}\n\n"
                f"📝 **Краткое изложение:**\n{brief}"
            )
            
            await message.reply_text(response_text)
            
        except Exception as e:
            logger.error(f"Error in handle_brief: {e}")
            await self._send_error_message(update, "при создании краткого изложения")
    
    async def _create_summary(self, messages: List[Dict], personality: str = "") -> str:
        """Создание суммаризации сообщений с помощью Yandex GPT"""
        conversation_text = self._format_messages_for_ai(messages)
        
        system_message = self._build_system_message(
            base_role="Ты - помощник для суммаризации групповых чатов. "
                     "Создай краткое, но информативное содержание обсуждения.",
            personality=personality
        )
        
        prompt = f"""Проанализируй следующие сообщения из группового чата и создай краткое содержание:

{conversation_text}

**Требования к суммаризации:**
- Будь кратким, но информативным
- Выдели основные темы обсуждения
- Отметь ключевые выводы или решения
- Укажи основных участников обсуждения
- Используй маркированные списки для лучшей читаемости
- Пиши на русском языке

**Формат ответа:**
Основные темы:
• Тема 1: краткое описание
• Тема 2: краткое описание

Ключевые выводы:
• Вывод 1
• Вывод 2

Участники: [список основных участников]"""
        
        # Подготавливаем сообщения для AI
        ai_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        summary = await self.ai_client.chat_completion(
            ai_messages, 
            max_tokens=config.AI_MAX_TOKENS,
            temperature=config.AI_TEMPERATURE
        )
        
        if not summary:
            return "❌ Не удалось создать суммаризацию. Пожалуйста, попробуйте позже."
        
        return summary
    
    async def _analyze_themes(self, messages: List[Dict], personality: str = "") -> str:
        """Анализ основных тем в сообщениях с помощью Yandex GPT"""
        conversation_text = self._format_messages_for_ai(messages)
        
        system_message = self._build_system_message(
            base_role="Ты анализируешь групповые чаты и выделяешь основные темы обсуждения. "
                     "Будь точным и структурированным.",
            personality=personality
        )
        
        prompt = f"""Проанализируй следующие сообщения и выдели основные темы обсуждения в виде структурированного списка:

{conversation_text}

**Требования:**
- Выдели 3-5 основных тем
- Для каждой темы укажи:
  • Название темы
  • Краткое описание
  • Уровень активности обсуждения (высокий/средний/низкий)
  • Ключевых участников
- Используй понятные эмодзи для визуального разделения
- Будь объективным и точным
- Пиши на русском языке

**Формат ответа:**
🎯 **Тема 1: [Название]**
• Описание: [краткое описание]
• Активность: [уровень]
• Участники: [список]

🎯 **Тема 2: [Название]**
• Описание: [краткое описание]
• Активность: [уровень]
• Участники: [список]"""
        
        # Подготавливаем сообщения для AI
        ai_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        themes = await self.ai_client.chat_completion(
            ai_messages,
            max_tokens=800,
            temperature=0.5  # Более низкая температура для большей консистентности
        )
        
        if not themes:
            return "❌ Не удалось проанализировать темы. Пожалуйста, попробуйте позже."
        
        return themes
    
    async def _create_brief_summary(self, text: str) -> str:
        """Создание краткого изложения длинного текста с помощью Yandex GPT"""
        system_message = (
            "Ты - эксперт по созданию кратких изложений. "
            "Сокращай длинные тексты, сохраняя ключевые идеи и смысл."
        )
        
        prompt = f"""Создай краткое изложение следующего текста:

{text}

**Требования:**
- Сохрани основные идеи и ключевые моменты
- Будь максимально кратким, но информативным
- Используй ясный и понятный язык
- Выдели главную мысль текста
- Объем: 20-30% от оригинала
- Пиши на русском языке

**Краткое изложение:**"""
        
        # Подготавливаем сообщения для AI
        ai_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        brief = await self.ai_client.chat_completion(
            ai_messages,
            max_tokens=500,
            temperature=0.3  # Низкая температура для большей точности
        )
        
        if not brief:
            return "❌ Не удалось создать краткое изложение. Пожалуйста, попробуйте позже."
        
        return brief
    
    def _parse_message_count(self, args: List[str], default: int = 50) -> int:
        """Парсинг количества сообщений из аргументов"""
        if not args:
            return default
        
        try:
            count = int(args[0])
            return max(1, min(count, config.MAX_MESSAGES_FOR_ANALYSIS))
        except (ValueError, TypeError):
            return default
    
    def _format_messages_for_ai(self, messages: List[Dict]) -> str:
        """Форматирование сообщений для передачи в AI"""
        formatted = []
        for msg in messages:
            user = msg.get('user', 'Unknown')
            text = msg.get('text', '')
            if text and len(text.strip()) > 0:  # Игнорируем пустые сообщения
                # Обрезаем слишком длинные сообщения
                if len(text) > 300:
                    text = text[:297] + "..."
                formatted.append(f"{user}: {text}")
        
        return "\n".join(formatted)
    
    def _extract_text_from_message(self, message: Message) -> str:
        """Извлечение текста из сообщения Telegram"""
        if message.text:
            return message.text
        elif message.caption:
            return message.caption
        else:
            return ""
    
    def _get_bot_personality(self, chat_id: int) -> str:
        """Получение личности бота для чата"""
        # Временная реализация - позже интегрируем с базой данных
        try:
            settings = self.db.get_chat_settings(chat_id)
            return settings.get('bot_personality', '')
        except:
            return ""
    
    def _build_system_message(self, base_role: str, personality: str = "") -> str:
        """Построение системного сообщения с учетом личности"""
        if personality:
            return f"{base_role}\n\nТвоя личность: {personality}"
        return base_role
    
    def _should_pin_summary(self, chat_id: int) -> bool:
        """Проверка, нужно ли закреплять суммаризацию"""
        try:
            settings = self.db.get_chat_settings(chat_id)
            return settings.get('pin_summary', config.DEFAULT_PIN_SUMMARY)
        except:
            return config.DEFAULT_PIN_SUMMARY
    
    async def _send_error_message(self, update: Update, action: str):
        """Отправка сообщения об ошибке"""
        try:
            await update.effective_message.reply_text(
                f"❌ Произошла ошибка {action}. "
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")