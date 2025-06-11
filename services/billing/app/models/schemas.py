from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class UsageRecordSchema(BaseModel):
    id: UUID
    invoice_id: UUID
    quantity: int = 1
    status: str
    stripe_usage_record: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    reported_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class UsageSummary(BaseModel):
    total: int
    pending: int
    reported: int
    failed: int
    records: List[UsageRecordSchema]

class CSVExport(BaseModel):
    content: str = Field(..., description="CSV data encoded as string") 