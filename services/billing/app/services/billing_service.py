import asyncio, time, stripe
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.config import settings
from ..core.logging import get_logger
from ..models.usage import UsageRecord

logger = get_logger(__name__)
stripe.api_key = settings.stripe_api_key

class BillingServiceError(Exception):
    pass

class BillingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def report_usage(self, invoice_id):
        # upsert usage record
        result = await self.session.execute(select(UsageRecord).where(UsageRecord.invoice_id == invoice_id))
        record: UsageRecord | None = result.scalars().first()
        if record and record.status == "REPORTED":
            logger.info("Usage already reported", invoice_id=invoice_id)
            return record
        if not record:
            record = UsageRecord(invoice_id=invoice_id)
            self.session.add(record)
            await self.session.commit()
            await self.session.refresh(record)

        retries = 0
        backoff = 2
        while retries <=3:
            try:
                resp = stripe.SubscriptionItem.create_usage_record(
                    subscription_item=settings.stripe_subscription_item_id,
                    quantity=1,
                    timestamp=int(time.time()),
                    action="increment",
                )
                record.status = "REPORTED"
                record.reported_at = datetime.utcnow()
                record.stripe_usage_record = resp.get("id")
                await self.session.commit()
                return record
            except stripe.error.RateLimitError as e:
                retries += 1
                if retries>3:
                    record.status = "FAILED"
                    record.error_message = str(e)
                    await self.session.commit()
                    return record
                await asyncio.sleep(backoff)
                backoff*=2
            except stripe.error.StripeError as e:
                record.status = "FAILED"
                record.error_message = str(e)
                await self.session.commit()
                return record 