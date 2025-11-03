#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации бота
Запустите этот скрипт перед запуском бота для проверки настроек
"""

import sys
import os
from dotenv import load_dotenv

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import config

def main():
    """Проверка конфигурации"""
    print("🔧 Проверка конфигурации AI Assistant Bot...")
    print("=" * 50)
    
    try:
        # Проверяем обязательные переменные
        config.validate_config()
        print("✅ Конфигурация успешно проверена")
        
        # Выводим основные настройки
        print("\n📋 Основные настройки:")
        print(f"   AI Model: {config.AI_MODEL}")
        print(f"   Max messages for analysis: {config.MAX_MESSAGES_FOR_ANALYSIS}")
        print(f"   Default summary time: {config.DEFAULT_SUMMARY_TIME}")
        
        # Выводим информацию о лимитах
        print("\n📊 Лимиты системы:")
        print(config.get_limits_info())
        
        print("\n🎯 Бот готов к запуску!")
        
    except ValueError as e:
        print(f"❌ Ошибка конфигурации: {e}")
        print("\n💡 Убедитесь, что:")
        print("   - Файл .env существует и заполнен")
        print("   - TELEGRAM_TOKEN установлен")
        print("   - OPENAI_API_KEY установлен")
        sys.exit(1)

if __name__ == "__main__":
    main()