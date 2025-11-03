# test_config.py
from config import config

print("=== ПРОВЕРКА КОНФИГУРАЦИИ ===")
print(f"AI Provider: {config.AI_PROVIDER}")
print(f"Telegram Token: {'✅' if config.TELEGRAM_TOKEN else '❌'}")
print(f"Yandex GPT: {'✅' if config.YANDEX_API_KEY else '❌'}")
print(f"SpeechKit: {'✅' if config.is_speechkit_available() else '❌'}")
print(f"Vision API: {'✅' if config.is_vision_available() else '❌'}")

if not config.is_speechkit_available():
    print("\n🔍 Проблемы с SpeechKit:")
    if not config.YANDEX_SPEECHKIT_API_KEY:
        print("   - Отсутствует YANDEX_SPEECHKIT_API_KEY в .env файле")
    if not config.YANDEX_FOLDER_ID:
        print("   - Отсутствует YANDEX_FOLDER_ID в .env файле")