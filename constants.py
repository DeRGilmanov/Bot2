# constants.py

# Лимиты Telegram
MAX_MESSAGE_LENGTH = 4096
MAX_CAPTION_LENGTH = 1024

# Команды бота
COMMANDS = {
    'summary': 'Суммаризация последних сообщений',
    'themes': 'Тезисный анализ тем',
    'comment': 'Комментарий к текущей теме',
    'brief': 'Краткое изложение сообщения',
    'ask': 'Ответ на вопрос по истории чата',
    'gpt': 'Ответ на любой вопрос',
    'opinion': 'Анализ пользователя',
    'text': 'Извлечение текста из медиа',
    'help': 'Справка по командам'
}

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'summary_time': '21:00',
    'daily_summary_enabled': True,
    'pin_summary': True,
    'language': 'ru'
}