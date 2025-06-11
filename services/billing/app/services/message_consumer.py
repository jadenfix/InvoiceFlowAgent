import asyncio, json
from aio_pika import connect_robust, IncomingMessage, ExchangeType
from ..core.config import settings
from ..core.logging import get_logger
from ..models.database import get_db_session
from .billing_service import BillingService

logger = get_logger(__name__)

class BillingConsumer:
    def __init__(self):
        self._connection=None
        self._channel=None
        self._task=None

    async def connect(self):
        self._connection = await connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        queue = await self._channel.declare_queue(settings.billing_publish_queue, durable=True)
        await queue.consume(self.process_message, no_ack=False)
        logger.info("Billing consumer started")

    async def process_message(self, message: IncomingMessage):
        async with message.process(requeue=False):
            try:
                payload = json.loads(message.body)
                if payload.get("status")!="POSTED":
                    return
                invoice_id = payload.get("invoice_id")
                async with get_db_session() as session:
                    service = BillingService(session)
                    await service.report_usage(invoice_id)
            except Exception as e:
                logger.error("Billing message failed", error=str(e))

    async def start(self):
        await self.connect()
        self._task = asyncio.create_task(asyncio.Event().wait())

    async def stop(self):
        if self._connection:
            await self._connection.close()
        if self._task:
            self._task.cancel() 