"""
Celery worker for notification service
"""
import logging
import asyncio
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.database import get_sync_db, check_database_connection
from app.services.notification_service import NotificationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "notification_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        'scan-and-notify': {
            'task': 'worker.scan_and_notify',
            'schedule': crontab(minute=f'*/{settings.review_notification_interval}'),
        },
    },
)


@celery_app.task(bind=True)
def scan_and_notify(self):
    """
    Periodic task to scan for invoices needing review and send notifications
    """
    logger.info(f"Starting scan_and_notify task (task_id: {self.request.id})")
    
    # Check database connectivity
    if not check_database_connection():
        error_msg = "Database connection failed"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    try:
        # Get database session
        db_gen = get_sync_db()
        db = next(db_gen)
        
        # Create notification service
        notification_service = NotificationService()
        
        # Run async notification process in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                notification_service.scan_and_notify(db)
            )
            
            logger.info(f"Task completed successfully: {result}")
            return result
            
        finally:
            loop.close()
            
    except Exception as e:
        error_msg = f"Task failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise
    
    finally:
        # Ensure database session is closed
        try:
            db.close()
        except:
            pass


@celery_app.task
def health_check():
    """Health check task for monitoring"""
    try:
        # Check database
        db_healthy = check_database_connection()
        
        # Check notification services
        notification_service = NotificationService()
        service_health = notification_service.check_health()
        
        return {
            'status': 'healthy' if db_healthy else 'unhealthy',
            'database': db_healthy,
            'email_service': service_health.get('email_service', False),
            'sms_service': service_health.get('sms_service', False),
            'timestamp': str(asyncio.get_event_loop().time())
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': str(asyncio.get_event_loop().time())
        }


if __name__ == '__main__':
    # Run the worker
    celery_app.start() 