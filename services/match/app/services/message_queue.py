"""Message queue service for RabbitMQ operations."""

import asyncio
import json
from typing import Callable, Optional, Dict, Any
from datetime import datetime

import aio_pika
from aio_pika import ExchangeType, Message, DeliveryMode
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractQueue
import structlog

from ..core.config import settings
from ..core.logging import log_error, log_matching_event

logger = structlog.get_logger(__name__)


class MessageQueueService:
    """Service for RabbitMQ message operations."""
    
    def __init__(self):
        """Initialize message queue service."""
        self.connection: Optional[AbstractConnection] = None
        self.channel: Optional[AbstractChannel] = None
        self.queues: Dict[str, AbstractQueue] = {}
        self._is_healthy = False
    
    async def initialize(self) -> None:
        """Initialize RabbitMQ connection."""
        try:
            self.connection = await aio_pika.connect_robust(
                settings.rabbitmq_url,
                heartbeat=600,
                client_properties={
                    "connection_name": "match-service",
                    "version": settings.version
                }
            )
            
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=10)
            
            # Declare exchanges and queues
            await self._declare_infrastructure()
            
            self._is_healthy = True
            logger.info("Message queue service initialized", service="match-service")
            
        except Exception as e:
            self._is_healthy = False
            log_error(logger, e, "system", {"operation": "mq_init"})
            raise
    
    async def close(self) -> None:
        """Close message queue connections."""
        try:
            if self.channel:
                await self.channel.close()
            if self.connection:
                await self.connection.close()
            logger.info("Message queue connections closed", service="match-service")
        except Exception as e:
            log_error(logger, e, "system", {"operation": "mq_close"})
    
    async def health_check(self) -> bool:
        """Check message queue health."""
        try:
            if not self.connection or self.connection.is_closed:
                self._is_healthy = False
                return False
            
            # Try to declare a temporary queue to test connection
            temp_queue = await self.channel.declare_queue(
                exclusive=True,
                auto_delete=True
            )
            await temp_queue.delete()
            
            self._is_healthy = True
            return True
            
        except Exception as e:
            self._is_healthy = False
            log_error(logger, e, "system", {"operation": "mq_health_check"})
            return False
    
    @property
    def is_healthy(self) -> bool:
        """Get current health status."""
        return self._is_healthy
    
    async def _declare_infrastructure(self) -> None:
        """Declare exchanges and queues."""
        # Declare exchanges
        default_exchange = await self.channel.declare_exchange(
            "", 
            ExchangeType.DIRECT,
            durable=True
        )
        
        # Declare durable queues
        self.queues["invoice_extracted"] = await self.channel.declare_queue(
            "invoice_extracted",
            durable=True,
            arguments={
                "x-message-ttl": 86400000,  # 24 hours
                "x-max-length": 10000
            }
        )
        
        self.queues["invoice_matched"] = await self.channel.declare_queue(
            "invoice_matched",
            durable=True,
            arguments={
                "x-message-ttl": 86400000,  # 24 hours
                "x-max-length": 10000
            }
        )
        
        # Declare dead letter queue for failed messages
        self.queues["invoice_extracted_dlq"] = await self.channel.declare_queue(
            "invoice_extracted_dlq",
            durable=True
        )
    
    async def consume_invoice_extracted(
        self,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Start consuming invoice_extracted messages."""
        try:
            queue = self.queues["invoice_extracted"]
            
            async def message_handler(message: aio_pika.abc.AbstractIncomingMessage):
                request_id = "unknown"
                try:
                    async with message.process():
                        # Parse message
                        body = json.loads(message.body.decode())
                        request_id = body.get("request_id", "unknown")
                        
                        log_matching_event(
                            logger,
                            "Received invoice_extracted message",
                            request_id,
                            queue="invoice_extracted"
                        )
                        
                        # Process message
                        await callback(body)
                        
                        log_matching_event(
                            logger,
                            "Successfully processed invoice_extracted message",
                            request_id
                        )
                        
                except json.JSONDecodeError as e:
                    log_error(
                        logger,
                        e,
                        request_id,
                        {"operation": "parse_message", "queue": "invoice_extracted"}
                    )
                    # Acknowledge invalid messages to remove them
                    
                except Exception as e:
                    log_error(
                        logger,
                        e,
                        request_id,
                        {"operation": "process_message", "queue": "invoice_extracted"}
                    )
                    # Let the message be requeued for retry
                    raise
            
            await queue.consume(message_handler)
            logger.info("Started consuming invoice_extracted messages", service="match-service")
            
        except Exception as e:
            log_error(logger, e, "system", {"operation": "start_consumer"})
            raise
    
    async def publish_invoice_matched(
        self,
        message_data: Dict[str, Any],
        request_id: str
    ) -> None:
        """Publish invoice_matched message."""
        try:
            # Add timestamp if not present
            if "timestamp" not in message_data:
                message_data["timestamp"] = datetime.utcnow().isoformat()
            
            message_body = json.dumps(message_data, default=str)
            
            message = Message(
                message_body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                headers={
                    "request_id": request_id,
                    "service": "match-service",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            await self.channel.default_exchange.publish(
                message,
                routing_key="invoice_matched"
            )
            
            log_matching_event(
                logger,
                "Published invoice_matched message",
                request_id,
                status=message_data.get("status"),
                queue="invoice_matched"
            )
            
        except Exception as e:
            log_error(
                logger,
                e,
                request_id,
                {"operation": "publish_message", "queue": "invoice_matched"}
            )
            raise
    
    async def retry_with_backoff(
        self,
        operation,
        *args,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs
    ):
        """Retry message queue operation with exponential backoff."""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "Message queue operation failed, retrying",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Message queue operation failed after all retries",
                        attempts=max_retries + 1,
                        error=str(e)
                    )
                    raise last_exception


# Global message queue service instance
mq_service = MessageQueueService() 