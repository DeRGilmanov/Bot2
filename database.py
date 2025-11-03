import sqlite3
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных для хранения сообщений и настроек чатов"""
    
    def __init__(self, db_path: str = "chat_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    message_text TEXT,
                    message_type TEXT DEFAULT 'text',
                    media_file_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    reply_to_message_id INTEGER,
                    is_forwarded BOOLEAN DEFAULT 0
                )
            ''')
            
            # Таблица настроек чата
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id INTEGER PRIMARY KEY,
                    daily_summary_enabled BOOLEAN DEFAULT 1,
                    summary_time TEXT DEFAULT '21:00',
                    pin_summary BOOLEAN DEFAULT 1,
                    bot_personality TEXT,
                    language TEXT DEFAULT 'ru',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для хранения извлеченного текста из медиа
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS extracted_texts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_message_id INTEGER,
                    chat_id INTEGER NOT NULL,
                    extracted_text TEXT NOT NULL,
                    extraction_type TEXT NOT NULL,  -- 'voice', 'image', 'document'
                    confidence_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (original_message_id) REFERENCES messages (id)
                )
            ''')
            
            # Таблица для статистики использования команд
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT 1
                )
            ''')
            
            # Индексы для оптимизации запросов
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_chat_timestamp 
                ON messages(chat_id, timestamp DESC)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_user 
                ON messages(chat_id, user_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
                ON messages(timestamp)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_command_stats_timestamp 
                ON command_stats(timestamp)
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def save_message(self, chat_id: int, user_id: int, user_name: str, 
                    message_text: str, message_type: str = 'text', 
                    media_file_id: str = None, reply_to_message_id: int = None,
                    is_forwarded: bool = False) -> bool:
        """Сохранение сообщения в базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO messages 
                (chat_id, user_id, user_name, message_text, message_type, 
                 media_file_id, reply_to_message_id, is_forwarded)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, user_id, user_name, message_text, message_type, 
                  media_file_id, reply_to_message_id, is_forwarded))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            return False
    
    def get_recent_messages(self, chat_id: int, limit: int = 50, 
                           offset: int = 0) -> List[Dict]:
        """Получение последних сообщений чата"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_name, message_text, timestamp, message_type, user_id
                FROM messages 
                WHERE chat_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
            ''', (chat_id, limit, offset))
            
            messages = []
            for row in cursor.fetchall():
                messages.append({
                    'user': row[0],
                    'text': row[1],
                    'timestamp': row[2],
                    'type': row[3],
                    'user_id': row[4]
                })
            
            conn.close()
            return list(reversed(messages))  # Возвращаем в хронологическом порядке
            
        except Exception as e:
            logger.error(f"Error getting recent messages: {e}")
            return []
    
    def get_user_messages(self, chat_id: int, user_name: str, 
                         limit: int = 100) -> List[Dict]:
        """Получение сообщений конкретного пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT message_text, timestamp, message_type
                FROM messages 
                WHERE chat_id = ? AND user_name = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (chat_id, user_name, limit))
            
            messages = [
                {
                    'text': row[0],
                    'timestamp': row[1],
                    'type': row[2]
                } 
                for row in cursor.fetchall()
            ]
            
            conn.close()
            return messages
            
        except Exception as e:
            logger.error(f"Error getting user messages: {e}")
            return []
    
    def get_messages_by_time_range(self, chat_id: int, 
                                 start_time: datetime, 
                                 end_time: datetime) -> List[Dict]:
        """Получение сообщений за определенный период времени"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_name, message_text, timestamp, message_type
                FROM messages 
                WHERE chat_id = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (chat_id, start_time, end_time))
            
            messages = [
                {
                    'user': row[0],
                    'text': row[1],
                    'timestamp': row[2],
                    'type': row[3]
                }
                for row in cursor.fetchall()
            ]
            
            conn.close()
            return messages
            
        except Exception as e:
            logger.error(f"Error getting messages by time range: {e}")
            return []
    
    def get_chat_statistics(self, chat_id: int, days: int = 7) -> Dict:
        """Получение статистики чата"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            start_date = datetime.now() - timedelta(days=days)
            
            # Общее количество сообщений
            cursor.execute('''
                SELECT COUNT(*) FROM messages 
                WHERE chat_id = ? AND timestamp > ?
            ''', (chat_id, start_date))
            total_messages = cursor.fetchone()[0]
            
            # Количество активных пользователей
            cursor.execute('''
                SELECT COUNT(DISTINCT user_id) FROM messages 
                WHERE chat_id = ? AND timestamp > ?
            ''', (chat_id, start_date))
            active_users = cursor.fetchone()[0]
            
            # Самые активные пользователи
            cursor.execute('''
                SELECT user_name, COUNT(*) as message_count 
                FROM messages 
                WHERE chat_id = ? AND timestamp > ?
                GROUP BY user_name 
                ORDER BY message_count DESC 
                LIMIT 10
            ''', (chat_id, start_date))
            
            top_users = [
                {'user': row[0], 'count': row[1]}
                for row in cursor.fetchall()
            ]
            
            # Распределение по типам сообщений
            cursor.execute('''
                SELECT message_type, COUNT(*) 
                FROM messages 
                WHERE chat_id = ? AND timestamp > ?
                GROUP BY message_type
            ''', (chat_id, start_date))
            
            message_types = {
                row[0]: row[1] for row in cursor.fetchall()
            }
            
            conn.close()
            
            return {
                'total_messages': total_messages,
                'active_users': active_users,
                'top_users': top_users,
                'message_types': message_types,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Error getting chat statistics: {e}")
            return {}
    
    def save_extracted_text(self, original_message_id: int, chat_id: int, 
                          extracted_text: str, extraction_type: str,
                          confidence_score: float = None) -> bool:
        """Сохранение извлеченного текста из медиа"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO extracted_texts 
                (original_message_id, chat_id, extracted_text, extraction_type, confidence_score)
                VALUES (?, ?, ?, ?, ?)
            ''', (original_message_id, chat_id, extracted_text, extraction_type, confidence_score))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error saving extracted text: {e}")
            return False
    
    def log_command_usage(self, chat_id: int, user_id: int, 
                         command: str, success: bool = True) -> bool:
        """Логирование использования команд"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO command_stats 
                (chat_id, user_id, command, success)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, user_id, command, success))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error logging command usage: {e}")
            return False
    
    def get_command_stats(self, chat_id: int = None, days: int = 30) -> Dict:
        """Получение статистики использования команд"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            start_date = datetime.now() - timedelta(days=days)
            
            if chat_id:
                cursor.execute('''
                    SELECT command, COUNT(*) as usage_count 
                    FROM command_stats 
                    WHERE chat_id = ? AND timestamp > ?
                    GROUP BY command 
                    ORDER BY usage_count DESC
                ''', (chat_id, start_date))
            else:
                cursor.execute('''
                    SELECT command, COUNT(*) as usage_count 
                    FROM command_stats 
                    WHERE timestamp > ?
                    GROUP BY command 
                    ORDER BY usage_count DESC
                ''', (start_date,))
            
            command_stats = {
                row[0]: row[1] for row in cursor.fetchall()
            }
            
            # Общее количество команд
            total_commands = sum(command_stats.values())
            
            conn.close()
            
            return {
                'total_commands': total_commands,
                'command_usage': command_stats,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Error getting command stats: {e}")
            return {}
    
    def cleanup_old_messages(self, days: int = 90) -> int:
        """Очистка старых сообщений (для экономии места)"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM messages 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            
            # Также очищаем связанные извлеченные тексты
            cursor.execute('''
                DELETE FROM extracted_texts 
                WHERE created_at < ?
            ''', (cutoff_date,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} messages older than {days} days")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old messages: {e}")
            return 0
    
    def get_database_size(self) -> int:
        """Получение размера базы данных в байтах"""
        try:
            import os
            return os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return 0
    
    def backup_database(self, backup_path: str = None) -> bool:
        """Создание резервной копии базы данных"""
        try:
            import shutil
            import datetime
            
            if backup_path is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"chat_data_backup_{timestamp}.db"
            
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backed up to: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error backing up database: {e}")
            return False
    
    # Методы для работы с настройками чата
    
    def get_chat_settings(self, chat_id: int) -> Dict:
        """Получение настроек чата"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT daily_summary_enabled, summary_time, pin_summary, 
                       bot_personality, language, created_at, updated_at
                FROM chat_settings 
                WHERE chat_id = ?
            ''', (chat_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'daily_summary_enabled': bool(result[0]),
                    'summary_time': result[1],
                    'pin_summary': bool(result[2]),
                    'bot_personality': result[3],
                    'language': result[4],
                    'created_at': result[5],
                    'updated_at': result[6]
                }
            else:
                # Возвращаем настройки по умолчанию
                return {
                    'daily_summary_enabled': True,
                    'summary_time': '21:00',
                    'pin_summary': True,
                    'bot_personality': None,
                    'language': 'ru',
                    'created_at': None,
                    'updated_at': None
                }
            
        except Exception as e:
            logger.error(f"Error getting chat settings: {e}")
            return {}
    
    def update_chat_settings(self, chat_id: int, **kwargs) -> bool:
        """Обновление настроек чата"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            allowed_fields = {
                'daily_summary_enabled', 'summary_time', 'pin_summary',
                'bot_personality', 'language'
            }
            
            update_fields = []
            update_values = []
            
            for field, value in kwargs.items():
                if field in allowed_fields:
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)
            
            if not update_fields:
                return False
            
            update_values.append(chat_id)
            
            query = f'''
                INSERT OR REPLACE INTO chat_settings 
                (chat_id, {', '.join(kwargs.keys())}, updated_at)
                VALUES (?, {', '.join(['?' for _ in kwargs])}, CURRENT_TIMESTAMP)
            '''
            
            cursor.execute(query, [chat_id] + list(kwargs.values()))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error updating chat settings: {e}")
            return False
        

        