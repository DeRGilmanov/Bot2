import logging
import aiohttp
import json
import asyncio
from typing import List, Optional
from config import config

logger = logging.getLogger(__name__)

class AIClient:
    """Универсальный клиент для работы с AI провайдерами"""
    
    def __init__(self):
        self.provider = config.AI_PROVIDER
        logger.info(f"Инициализирован AI клиент с провайдером: {self.provider}")
    
    async def chat_completion(self, messages: List[dict], max_tokens: int = None, temperature: float = None) -> Optional[str]:
        """Основной метод для получения ответов от AI"""
        try:
            logger.info(f"🔧 AI клиент: запрос к {self.provider}, сообщений: {len(messages)}")
            
            if self.provider == "yandex":
                return await self._yandex_chat(messages, max_tokens, temperature)
            elif self.provider == "openai":
                return await self._openai_chat(messages, max_tokens, temperature)
            else:
                logger.warning("🔧 AI клиент: использование локального fallback")
                return await self._local_fallback(messages)
                
        except Exception as e:
            logger.error(f"❌ Ошибка AI клиента ({self.provider}): {e}")
            return None

    async def _yandex_chat(self, messages: List[dict], max_tokens: int = None, temperature: float = None) -> str:
        """Yandex GPT API - реализация с обработкой system messages и fallback'ами"""
        logger.info(f"🔧 Yandex GPT: начало обработки запроса")
        
        # Проверяем конфигурацию
        if not getattr(config, "YANDEX_API_KEY", None):
            logger.error("❌ Yandex GPT: отсутствует API_KEY в конфиге")
            raise Exception("YANDEX_API_KEY не настроен")
        
        if not getattr(config, "YANDEX_FOLDER_ID", None):
            logger.error("❌ Yandex GPT: отсутствует FOLDER_ID в конфиге")
            raise Exception("YANDEX_FOLDER_ID не настроен")
        
        headers = {
            "Authorization": f"Api-Key {config.YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Преобразуем сообщения в формат для Yandex (text вместо content)
        yandex_messages = []
        system_content = ""
        for msg in messages:
            role = msg.get("role") or msg.get("role", "user")
            content = msg.get("content") or msg.get("text") or ""
            if role == "system":
                system_content = content
            else:
                yandex_messages.append({
                    "role": role,
                    "text": content
                })
        
        # Включаем system content в начало первого user сообщения если есть
        if system_content:
            if yandex_messages:
                yandex_messages[0]["text"] = f"{system_content}\n\n{yandex_messages[0]['text']}"
            else:
                yandex_messages.append({"role": "user", "text": system_content})
        
        data = {
            "modelUri": f"gpt://{config.YANDEX_FOLDER_ID}/{getattr(config, 'YANDEX_MODEL', 'yandexgpt')}",  # Используем yandexgpt по умолчанию
            "completionOptions": {
                "stream": False,
                "temperature": temperature or getattr(config, "AI_TEMPERATURE", 0.7),
                "maxTokens": max_tokens or getattr(config, "AI_MAX_TOKENS", 800)
            },
            "messages": yandex_messages
        }
        
        logger.debug(f"🔧 Yandex GPT запрос: {json.dumps(data, ensure_ascii=False)}")
        
        try:
            async with aiohttp.ClientSession() as session:
                logger.info(f"🔧 Yandex GPT: отправка запроса на {getattr(config, 'YANDEX_URL', 'YANDEX_URL_NOT_SET')}")
                timeout = aiohttp.ClientTimeout(total=30)
                async with session.post(getattr(config, "YANDEX_URL"), headers=headers, json=data, timeout=timeout) as response:
                    logger.info(f"🔧 Yandex GPT: статус ответа {response.status}")
                    
                    if response.status == 200:
                        result = await response.json()
                        answer = result['result']['alternatives'][0]['message']['text']
                        logger.info(f"✅ Yandex GPT: успешный ответ: {answer[:100]}...")
                        return answer
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Yandex GPT API ошибка: {response.status} - {error_text}")
                        
                        if response.status == 500:
                            # Попробуем упрощённый запрос
                            return await self._retry_with_simple_prompt(messages)
                        
                        raise Exception(f"Yandex GPT API error: {response.status} - {error_text}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"❌ Yandex GPT: ошибка сети: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error("❌ Yandex GPT: таймаут запроса")
            raise
        except Exception as e:
            logger.error(f"❌ Yandex GPT: неожиданная ошибка: {e}")
            raise

    async def _try_different_model(self, message: str) -> str:
        """Пробуем разные модели (вспомогательный метод)"""
        models_to_try = ["yandexgpt-lite", "yandexgpt"]
        
        for model in models_to_try:
            logger.info(f"🔄 Пробуем модель: {model}")
            
            data = {
                "modelUri": f"gpt://{config.YANDEX_FOLDER_ID}/{model}",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": 50
                },
                "messages": [{"role": "user", "text": message}]
            }
            
            headers = {
                "Authorization": f"Api-Key {config.YANDEX_API_KEY}",
                "Content-Type": "application/json"
            }
            
            try:
                async with aiohttp.ClientSession() as session:
                    timeout = aiohttp.ClientTimeout(total=30)
                    async with session.post(
                        getattr(config, "YANDEX_URL"), headers=headers, json=data, timeout=timeout
                    ) as response:
                        
                        if response.status == 200:
                            result = await response.json()
                            answer = result['result']['alternatives'][0]['message']['text']
                            logger.info(f"✅ Модель {model} РАБОТАЕТ! Ответ: {answer}")
                            return answer
                        else:
                            logger.warning(f"❌ Модель {model} тоже не работает: {response.status}")
                            continue
                            
            except Exception as e:
                logger.warning(f"❌ Модель {model} ошибка: {e}")
                continue
        
        # Если все модели не работают
        raise Exception("Все модели Yandex GPT возвращают ошибку")

    async def _retry_with_simple_prompt(self, messages: List[dict]) -> str:
        """Альтернативный метод для обхода 500 ошибки"""
        logger.info("🔄 Yandex GPT: пробуем упрощенный запрос...")
        
        # Находим последнее пользовательское сообщение
        last_user_message = ""
        for msg in reversed(messages):
            role = msg.get("role") or "user"
            if role == "user":
                last_user_message = msg.get("content") or msg.get("text") or ""
                break
        
        if not last_user_message:
            last_user_message = "Привет"
        
        simple_messages = [{"role": "user", "text": last_user_message}]
        
        headers = {
            "Authorization": f"Api-Key {config.YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "modelUri": f"gpt://{config.YANDEX_FOLDER_ID}/{getattr(config, 'YANDEX_MODEL', 'yandexgpt')}",  # Используем yandexgpt по умолчанию
            "completionOptions": {
                "stream": False,
                "temperature": 0.7,
                "maxTokens": 200
            },
            "messages": simple_messages
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=30)
                async with session.post(getattr(config, "YANDEX_URL"), headers=headers, json=data, timeout=timeout) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['result']['alternatives'][0]['message']['text']
                    else:
                        raise Exception(f"Retry failed: {response.status}")
        except Exception as e:
            logger.error(f"❌ Yandex GPT retry failed: {e}")
            raise

    async def _openai_chat(self, messages: List[dict], max_tokens: int = None, temperature: float = None) -> Optional[str]:
        """OpenAI GPT (резервный вариант) — заглушка"""
        logger.info("🔧 OpenAI: вызывается заглушка (не реализовано)")
        # Реализация для OpenAI может быть добавлена здесь при необходимости.
        return None

    async def _local_fallback(self, messages: List[dict]) -> str:
        """Локальная заглушка когда API недоступны"""
        # Простая логика: вернем ответ на основе последнего user сообщения
        last = ""
        for msg in reversed(messages):
            role = msg.get("role") or "user"
            if role == "user":
                last = msg.get("content") or msg.get("text") or ""
                break
        if not last:
            return "🤖 Локальный fallback: нет входных сообщений."
        return f"🤖 Локальный fallback ответ на: '{last[:200]}'"