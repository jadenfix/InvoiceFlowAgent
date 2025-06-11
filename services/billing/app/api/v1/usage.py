from datetime import date, datetime
from uuid import UUID
from fastapi import APIRouter, Query, HTTPException, status
from sqlalchemy import select, func
from ...models.database import get_db_session
from ...models.usage import UsageRecord
from ...models.schemas import UsageRecordSchema, UsageSummary

router = APIRouter()

@router.get("/usage", response_model=UsageSummary)
async def usage_summary(start: date = Query(...), end: date = Query(...), status_filter: str | None = Query(None)):
    if start> end:
        raise HTTPException(status_code=400, detail="start must be <= end")
    async with get_db_session() as session:
        query = select(UsageRecord).where(UsageRecord.created_at>=datetime.combine(start, datetime.min.time()), UsageRecord.created_at<=datetime.combine(end, datetime.max.time()))
        if status_filter:
            query = query.where(UsageRecord.status==status_filter)
        result = await session.execute(query)
        records = result.scalars().all()
        total=len(records)
        pending=len([r for r in records if r.status=='PENDING'])
        reported=len([r for r in records if r.status=='REPORTED'])
        failed=len([r for r in records if r.status=='FAILED'])
        return UsageSummary(total=total,pending=pending,reported=reported,failed=failed,records=[UsageRecordSchema.model_validate(r) for r in records]) 