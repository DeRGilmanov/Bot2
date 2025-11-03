import logging
from telegram import Update
from telegram.ext import ContextTypes, ChatMemberHandler
from database import get_chat_settings

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """
👋 **Добро пожаловать в чат с Чатикусом!**

*Мануал по работе с ботом-суммаризатором*

**Что такое Чатикус?**
Это бот, который создаёт краткую выжимку (саммари) из большого количества сообщений...

// ... весь текст мануала ...

[Подробная инструкция и документация](https://your-link-here.com)
"""

async def send_welcome_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение в чат"""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=WELCOME_MESSAGE,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info(f"Приветственное сообщение отправлено в чат {chat_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки приветственного сообщения в чат {chat_id}: {e}")
        # Пробуем отправить без разметки
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=WELCOME_MESSAGE,
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"Не удалось отправить сообщение даже без разметки: {e2}")

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает добавление бота в чат"""
    try:
        chat_member = update.chat_member
        new_status = chat_member.new_chat_member.status
        old_status = chat_member.old_chat_member.status
        
        # Проверяем, что бота добавили в группу
        if (old_status == 'left' and new_status in ['member', 'administrator'] 
            and chat_member.new_chat_member.user.id == context.bot.id):
            
            chat = update.effective_chat
            logger.info(f"Бота добавили в чат: {chat.title} (ID: {chat.id})")
            
            # Отправляем приветственное сообщение
            await send_welcome_message(chat.id, context)
            
    except Exception as e:
        logger.error(f"Ошибка в chat_member_handler: {e}")

async def welcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная отправка приветственного сообщения (только для админов)"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Проверяем права администратора
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        await update.message.reply_text("❌ Не удалось проверить права!")
        return
    
    # Отправляем сообщение
    await send_welcome_message(chat.id, context)
    await update.message.reply_text("✅ Приветственное сообщение отправлено!")