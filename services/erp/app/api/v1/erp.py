import uuid
from fastapi import APIRouter, HTTPException, status
from ....models.database import get_db_session
from ....services.erp_service import ERPService, ERPServiceError
from ....core.logging import get_logger
from ....models.schemas import ERPResult

router = APIRouter()
logger = get_logger(__name__)


@router.post("/push/{invoice_id}", status_code=status.HTTP_202_ACCEPTED, response_model=ERPResult)
async def push_invoice(invoice_id: uuid.UUID):
    async with get_db_session() as session:
        async with ERPService(session) as svc:
            try:
                result = await svc.process_invoice(invoice_id)
                return {
                    "invoice_id": invoice_id,
                    "status": result["status"],
                    "posted_at": result.get("posted_at"),
                    "error": result.get("error"),
                    "response": result.get("response"),
                }
            except ERPServiceError:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
            except ValueError as ve:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
            except Exception as e:
                logger.error("Manual push failed", error=str(e))
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Push failed") 