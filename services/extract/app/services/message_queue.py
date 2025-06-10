"""
Message queue service for RabbitMQ operations
"""
import json
import asyncio
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import aio_pika
from aio_pika import Message, ExchangeType
from aio_pika.exceptions import AMQPConnectionError, AMQPChannelError
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings
from ..core.logging import get_logger, log_processing_step, log_error
from ..models.invoice import IngestMessage, ExtractedMessage


logger = get_logger(__name__)


class MessageQueueService:
    """Message queue service for RabbitMQ operations"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.exchange = None
        self.ingest_queue = None
        self.extracted_queue = None
        self.is_consuming = False
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, max=60)
    )
    async def connect(self):
        """Connect to RabbitMQ with retry logic"""
        try:
            if self.connection and not self.connection.is_closed:
                logger.info("Already connected to RabbitMQ")
                return
            
            logger.info(f"Connecting to RabbitMQ at {settings.RABBITMQ_URL}")
            
            self.connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                heartbeat=600,
                blocked_connection_timeout=300,
            )
            
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=1)
            
            # Declare exchange
            self.exchange = await self.channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE_NAME,
                ExchangeType.TOPIC,
                durable=True
            )
            
            # Declare queues
            self.ingest_queue = await self.channel.declare_queue(
                settings.RABBITMQ_INGEST_QUEUE,
                durable=True
            )
            
            self.extracted_queue = await self.channel.declare_queue(
                settings.RABBITMQ_EXTRACTED_QUEUE,
                durable=True
            )
            
            # Bind queues
            await self.ingest_queue.bind(self.exchange, "ingest")
            await self.extracted_queue.bind(
                self.exchange, 
                settings.RABBITMQ_ROUTING_KEY_EXTRACTED
            )
            
            logger.info("Connected to RabbitMQ successfully")
            
        except AMQPConnectionError as e:
            log_error(e, {"operation": "rabbitmq_connect"})
            raise
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_connect"})
            raise
    
    async def disconnect(self):
        """Disconnect from RabbitMQ"""
        try:
            self.is_consuming = False
            
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
                logger.info("Disconnected from RabbitMQ")
                
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_disconnect"})
    
    async def publish_extracted_message(
        self, 
        extracted_message: ExtractedMessage,
        request_id: str
    ) -> bool:
        """
        Publish extracted message to queue
        
        Args:
            extracted_message: Extracted message data
            request_id: Request ID for logging
            
        Returns:
            True if successful, False otherwise
        """
        log_processing_step("publish_extracted", request_id)
        
        try:
            if not self.exchange:
                await self.connect()
            
            message_body = json.dumps(
                extracted_message.model_dump(),
                default=str
            ).encode('utf-8')
            
            message = Message(
                message_body,
                content_type='application/json',
                delivery_mode=2,  # Persistent
                headers={
                    'request_id': request_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'service': 'extract-service'
                }
            )
            
            await self.exchange.publish(
                message,
                routing_key=settings.RABBITMQ_ROUTING_KEY_EXTRACTED
            )
            
            logger.info(f"Published extracted message for request {request_id}")
            return True
            
        except Exception as e:
            log_error(e, {"operation": "publish_extracted", "request_id": request_id})
            return False
    
    async def start_consuming(self, message_handler: Callable):
        """
        Start consuming messages from ingest queue
        
        Args:
            message_handler: Async function to handle messages
        """
        if self.is_consuming:
            logger.warning("Already consuming messages")
            return
        
        try:
            if not self.ingest_queue:
                await self.connect()
            
            self.is_consuming = True
            logger.info("Starting to consume messages from ingest queue")
            
            await self.ingest_queue.consume(
                self._wrap_message_handler(message_handler),
                no_ack=False
            )
            
        except Exception as e:
            log_error(e, {"operation": "start_consuming"})
            self.is_consuming = False
            raise
    
    def _wrap_message_handler(self, handler: Callable):
        """Wrap message handler with error handling and logging"""
        async def wrapper(message: aio_pika.IncomingMessage):
            request_id = None
            
            try:
                # Extract request ID from headers or body for logging
                headers = message.headers or {}
                request_id = headers.get('request_id')
                
                if not request_id:
                    # Try to extract from message body
                    try:
                        body = json.loads(message.body.decode('utf-8'))
                        request_id = body.get('request_id', 'unknown')
                    except:
                        request_id = 'unknown'
                
                log_processing_step("message_received", request_id)
                
                # Parse message
                message_data = json.loads(message.body.decode('utf-8'))
                ingest_message = IngestMessage(**message_data)
                
                # Call the actual handler
                success = await handler(ingest_message)
                
                if success:
                    await message.ack()
                    logger.info(f"Message processed successfully for request {request_id}")
                else:
                    await message.nack(requeue=False)
                    logger.error(f"Message processing failed for request {request_id}")
                    
            except json.JSONDecodeError as e:
                log_error(e, {"operation": "message_decode", "request_id": request_id})
                await message.nack(requeue=False)
                
            except Exception as e:
                log_error(e, {"operation": "message_processing", "request_id": request_id})
                await message.nack(requeue=False)
        
        return wrapper
    
    async def health_check(self) -> bool:
        """Health check for message queue service"""
        try:
            if not self.connection or self.connection.is_closed:
                await self.connect()
            
            # Simple check - try to declare a temporary queue
            temp_queue = await self.channel.declare_queue(
                exclusive=True,
                auto_delete=True
            )
            await temp_queue.delete()
            
            return True
            
        except Exception as e:
            log_error(e, {"operation": "rabbitmq_health_check"})
            return False


# Create service instance
message_queue_service = MessageQueueService() 