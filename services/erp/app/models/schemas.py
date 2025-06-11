from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

class ERPResult(BaseModel):
    invoice_id: UUID
    status: str
    posted_at: Optional[datetime] = None
    error: Optional[str] = None
    response: Optional[Dict[str, Any]] = None

class PushResponse(BaseModel):
    detail: str = Field(..., example="Invoice push accepted")
    task_id: Optional[str] = None 