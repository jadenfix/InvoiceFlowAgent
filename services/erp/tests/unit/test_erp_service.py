import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from services.erp.app.services.erp_service import ERPService
from services.erp.app.models.invoice import Invoice
from services.erp.app.core.config import settings
from services.erp.app.models.database import Base

DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@pytest.mark.asyncio
async def test_push_success():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        inv = Invoice(invoice_number="TEST", vendor_name="ACME", total_amount=100)
        session.add(inv)
        await session.commit()

        with patch("services.erp.app.services.erp_service.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 201
            mock_post.return_value.json.return_value = {"ok": True}
            async with ERPService(session) as svc:
                res = await svc.process_invoice(inv.id)
                assert res["status"] == "POSTED" 