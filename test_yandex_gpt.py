import asyncio
import aiohttp
import os
from config import config

async def test_yandex_gpt():
    """Тестирование подключения к Yandex GPT API"""
    
    # Данные из конфигурации
    api_key = config.YANDEX_API_KEY
    folder_id = config.YANDEX_FOLDER_ID
    
    print(f"🔑 API Key: {api_key[:10]}...{api_key[-4:] if api_key else 'None'}")
    print(f"📁 Folder ID: {folder_id}")
    
    if not api_key or not folder_id:
        print("❌ Отсутствуют API ключ или Folder ID в конфигурации")
        return False
    
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.6,
            "maxTokens": 100
        },
        "messages": [
            {
                "role": "user",
                "text": "Привет! Ответь коротко: работаешь?"
            }
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as response:
                print(f"📡 Status Code: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    answer = result['result']['alternatives'][0]['message']['text']
                    print(f"✅ Успех! Ответ: {answer}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Ошибка API: {error_text}")
                    return False
                    
    except aiohttp.ClientConnectorError as e:
        print(f"❌ Ошибка подключения: {e}")
    except asyncio.TimeoutError:
        print("❌ Таймаут подключения")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
    
    return False

if __name__ == "__main__":
    asyncio.run(test_yandex_gpt())