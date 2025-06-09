"""
RabbitMQ message queue service
"""
import asyncio
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
import aio_pika
from aio_pika import Message, DeliveryMode
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..core.logging import get_logger, log_function_call, log_function_result, log_error


logger = get_logger(__name__)


class MessageQueueService:
    """RabbitMQ service for publishing messages"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None
        self.queue = None
    
    async def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            self.connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            self.channel = await self.connection.channel()
            
            # Declare exchange
            self.exchange = await self.channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE_NAME,
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )
            
            # Declare queue
            self.queue = await self.channel.declare_queue(
                settings.RABBITMQ_QUEUE_NAME,
                durable=True
            )
            
            # Bind queue to exchange
            await self.queue.bind(self.exchange, settings.RABBITMQ_ROUTING_KEY)
            
            logger.info("Connected to RabbitMQ")
            
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_connect"})
            raise
    
    async def disconnect(self):
        """Close RabbitMQ connection"""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
                logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_disconnect"})
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(
            multiplier=settings.RETRY_DELAY_SECONDS,
            max=60
        )
    )
    async def publish_message(self, payload: Dict[str, Any]) -> bool:
        """
        Publish message to RabbitMQ
        
        Args:
            payload: Message payload
            
        Returns:
            bool: Success status
        """
        log_function_call("MessageQueueService.publish_message", 
                         request_id=payload.get('request_id'))
        start_time = time.time()
        
        try:
            # Ensure connection
            if not self.connection or self.connection.is_closed:
                await self.connect()
            
            # Create message
            message_body = json.dumps(payload, default=str)
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                headers={
                    'timestamp': datetime.utcnow().isoformat(),
                    'request_id': payload.get('request_id')
                }
            )
            
            # Publish message
            await self.exchange.publish(
                message,
                routing_key=settings.RABBITMQ_ROUTING_KEY
            )
            
            logger.info(f"Published message for request_id: {payload.get('request_id')}")
            return True
            
        except Exception as e:
            log_error(e, {
                "operation": "rabbitmq_publish",
                "request_id": payload.get('request_id')
            })
            raise
            
        finally:
            log_function_result("MessageQueueService.publish_message", 
                              True if 'message' in locals() else False,
                              time.time() - start_time)
    
    async def health_check(self) -> bool:
        """Health check for RabbitMQ connectivity"""
        try:
            if not self.connection or self.connection.is_closed:
                await self.connect()
            return True
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_health_check"})
            return False


# Create service instance
message_queue_service = MessageQueueService() 