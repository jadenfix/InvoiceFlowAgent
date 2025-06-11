import asyncio
import json
from datetime import datetime
from typing import Any, Dict
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.logging import get_logger
from ..models.invoice import Invoice

logger = get_logger(__name__)


class ERPServiceError(Exception):
    pass


class ERPService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type, excValue, traceback):
        if self._client:
            await self._client.aclose()

    async def push_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        url = f"{settings.erp_api_base_url}/invoices"
        payload = {
            "id": str(invoice.id),
            "vendor": invoice.vendor_name,
            "invoice_number": invoice.invoice_number,
            "amount": str(invoice.total_amount),
        }

        retries = 0
        backoff = settings.erp_retry_backoff_base
        while retries <= settings.erp_retry_max:
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.erp_api_token}"},
                    timeout=30,
                )
                if 200 <= response.status_code < 300:
                    logger.info("ERP push success", invoice_id=str(invoice.id))
                    return {"status": "POSTED", "response": response.json()}
                elif response.status_code in (429, 500, 502, 503, 504):
                    # retryable
                    retries += 1
                    if retries > settings.erp_retry_max:
                        break
                    logger.warning(
                        "ERP push retryable error", status=response.status_code, retry=retries
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                else:
                    # non-retryable
                    logger.error("ERP push failed", status=response.status_code)
                    return {
                        "status": "FAILED",
                        "error": f"ERP returned {response.status_code}",
                        "response": response.text,
                    }
            except httpx.RequestError as exc:
                retries += 1
                if retries > settings.erp_retry_max:
                    break
                logger.warning("Network error, retrying", error=str(exc), retry=retries)
                await asyncio.sleep(backoff)
                backoff *= 2
        return {
            "status": "FAILED",
            "error": "Max retries exceeded",
            "response": None,
        }

    async def process_invoice(self, invoice_id):
        invoice = await self.session.get(Invoice, invoice_id)
        if not invoice:
            raise ERPServiceError("invoice_not_found")
        if invoice.posted_status == "POSTED":
            logger.info("Invoice already posted", invoice_id=str(invoice_id))
            return "ALREADY_POSTED"

        result = await self.push_invoice(invoice)
        invoice.posted_status = result["status"]
        invoice.posted_at = datetime.utcnow()
        invoice.posted_response = result.get("response") or result.get("error")
        await self.session.commit()
        return result 