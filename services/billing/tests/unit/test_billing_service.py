import pytest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.billing.app.models.database import Base
from services.billing.app.services.billing_service import BillingService
from services.billing.app.models.usage import UsageRecord

DATABASE_URL="sqlite+aiosqlite:///:memory:"
engine=create_async_engine(DATABASE_URL)
Session=async_sessionmaker(engine, expire_on_commit=False)

@pytest.mark.asyncio
async def test_report_usage_success():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with Session() as session:
        invoice_id=uuid4()
        with patch("services.billing.app.services.billing_service.stripe.SubscriptionItem.create_usage_record", new_callable=AsyncMock) as mock_stripe:
            mock_stripe.return_value={"id":"ur_123"}
            svc=BillingService(session)
            record=await svc.report_usage(invoice_id)
            assert record.status=="REPORTED" 