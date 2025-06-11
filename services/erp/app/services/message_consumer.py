import asyncio
import json
from aio_pika import connect_robust, IncomingMessage, ExchangeType
from ..core.config import settings
from ..core.logging import get_logger
from ..models.database import get_db_session
from .erp_service import ERPService, ERPServiceError

logger = get_logger(__name__)


class InvoiceConsumer:
    def __init__(self):
        self._connection = None
        self._channel = None
        self._task: asyncio.Task | None = None

    async def connect(self):
        self._connection = await connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        queue = await self._channel.declare_queue(
            "invoice_reviewed", durable=True
        )
        await queue.consume(self.handle_message, no_ack=False)
        logger.info("Invoice consumer started")

    async def handle_message(self, message: IncomingMessage):
        async with message.process(requeue=False):
            try:
                data = json.loads(message.body)
                invoice_id = data.get("invoice_id")
                action = data.get("action")
                if action != "approve":
                    logger.info("Skipping non-approve action", action=action)
                    return

                async with get_db_session() as session:
                    async with ERPService(session) as svc:
                        try:
                            result = await svc.process_invoice(invoice_id)
                        except ERPServiceError:
                            logger.warning("Invoice missing", invoice_id=invoice_id)
                            return  # ack

                        # publish result
                        await self.publish_result(invoice_id, result)
            except Exception as e:
                logger.error("Message handling failed", error=str(e))

    async def publish_result(self, invoice_id, result):
        exchange = await self._channel.declare_exchange("", ExchangeType.DIRECT)
        await exchange.publish(
            message_body=json.dumps(
                {"invoice_id": invoice_id, "status": result["status"], "error": result.get("error")}
            ).encode(),
            routing_key="invoice_posted",
        )

    async def start(self):
        await self.connect()
        # keep running
        self._task = asyncio.create_task(asyncio.Event().wait())

    async def stop(self):
        if self._connection:
            await self._connection.close()
        if self._task:
            self._task.cancel() 