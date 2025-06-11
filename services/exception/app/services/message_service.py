"""Message service for RabbitMQ integration."""

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import aio_pika
from aio_pika import connect_robust, Message, DeliveryMode

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class MessageServiceError(Exception):
    """Base exception for message service."""
    pass


class PublishError(MessageServiceError):
    """Error publishing message."""
    pass


class MessageService:
    """Service for handling RabbitMQ messages."""
    
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange_name = "invoice_events"
        self.queue_name = "invoice_reviewed"
    
    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        try:
            self.connection = await connect_robust(settings.rabbitmq_url)
            self.channel = await self.connection.channel()
            
            # Declare exchange
            self.exchange = await self.channel.declare_exchange(
                self.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            # Declare queue
            self.queue = await self.channel.declare_queue(
                self.queue_name,
                durable=True
            )
            
            # Bind queue to exchange
            await self.queue.bind(self.exchange, "invoice.reviewed.*")
            
            logger.info("Connected to RabbitMQ successfully")
            
        except Exception as e:
            logger.error("Failed to connect to RabbitMQ", error=str(e))
            raise MessageServiceError(f"Failed to connect to RabbitMQ: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            logger.error("Error disconnecting from RabbitMQ", error=str(e))
    
    async def publish_review_message(
        self,
        invoice_id: uuid.UUID,
        action: str,
        reviewed_by: str,
        review_notes: Optional[str] = None
    ) -> None:
        """Publish invoice review message."""
        
        if not self.channel or self.channel.is_closed:
            raise PublishError("Message service not connected")
        
        message_data = {
            "invoice_id": str(invoice_id),
            "action": action,
            "reviewed_by": reviewed_by,
            "review_notes": review_notes,
            "timestamp": datetime.utcnow().isoformat(),
            "service": "exception-review"
        }
        
        try:
            message = Message(
                json.dumps(message_data).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
                message_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow()
            )
            
            routing_key = f"invoice.reviewed.{action}"
            
            await self.exchange.publish(
                message,
                routing_key=routing_key
            )
            
            logger.info(
                "Published review message",
                invoice_id=str(invoice_id),
                action=action,
                routing_key=routing_key
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish review message",
                invoice_id=str(invoice_id),
                action=action,
                error=str(e)
            )
            raise PublishError(f"Failed to publish message: {e}")
    
    async def health_check(self) -> bool:
        """Check if RabbitMQ connection is healthy."""
        try:
            if not self.connection or self.connection.is_closed:
                return False
            if not self.channel or self.channel.is_closed:
                return False
            return True
        except Exception:
            return False


# Global message service instance
message_service = MessageService() 