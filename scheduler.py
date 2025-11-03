import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from database import DatabaseManager
from handlers.summary import SummaryHandler

logger = logging.getLogger(__name__)

class TaskScheduler:
    def __init__(self, db: DatabaseManager, application):
        self.db = db
        self.application = application
        self.scheduler = BackgroundScheduler()
        self.summary_handler = SummaryHandler(db)
        
    async def send_daily_summary(self, chat_id: str):
        """Отправка ежедневной суммаризации"""
        try:
            # Получаем настройки чата
            settings = self.db.get_chat_settings(int(chat_id))
            if not settings.get('daily_summary_enabled', True):
                return
                
            # Получаем сообщения за последние 24 часа
            from datetime import datetime, timedelta
            start_time = datetime.now() - timedelta(hours=24)
            messages = self.db.get_messages_by_time_range(
                int(chat_id), start_time, datetime.now()
            )
            
            if not messages:
                return
                
            # Создаем суммаризацию
            # Здесь нужно адаптировать вызов для планировщика
            # Это упрощенная версия - в реальности нужно больше логики
            
        except Exception as e:
            logger.error(f"Error sending daily summary for chat {chat_id}: {e}")
    
    def setup_daily_summaries(self):
        """Настройка ежедневных суммаризаций для всех чатов"""
        try:
            # Здесь будет логика получения всех чатов и их настроек времени
            # Пока просто пример для 21:00
            self.scheduler.add_job(
                self.send_daily_summaries,
                trigger=CronTrigger(hour=21, minute=0),
                id='daily_summaries'
            )
        except Exception as e:
            logger.error(f"Error setting up daily summaries: {e}")
    
    async def send_daily_summaries(self):
        """Отправка суммаризаций всем активным чатам"""
        # Логика получения всех чатов с включенными ежедневными суммаризациями
        pass
    
    def start(self):
        """Запуск планировщика"""
        self.scheduler.start()
        logger.info("Task scheduler started")
    
    def shutdown(self):
        """Остановка планировщика"""
        self.scheduler.shutdown()
        logger.info("Task scheduler stopped")