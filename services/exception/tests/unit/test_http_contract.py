"""Real SQLite-backed HTTP contracts; broker faults are explicit local fixtures."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.main import app
from app.core.config import settings
from app.models import database
from app.models.database import Invoice
from app.services.message_service import message_service
from app.services.review_service import ReviewService


@pytest_asyncio.fixture
async def http_lane(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def sessions():
        async with factory() as session:
            yield session

    monkeypatch.setattr(database, "get_db_session", sessions)
    monkeypatch.setattr(settings, "environment", "production")
    publisher = AsyncMock()
    monkeypatch.setattr(message_service, "publish_review_message", publisher)
    monkeypatch.setattr(message_service, "health_check", AsyncMock(return_value=True))
    ids = []
    async with factory() as session:
        for vendor in ["Acme", "Acme", "Other"]:
            invoice = Invoice(
                vendor_name=vendor,
                invoice_number=str(uuid.uuid4()),
                total_amount=12,
                invoice_date=datetime(2026, 1, 1),
                created_at=datetime(2026, 1, 1, 12),
                status="PROCESSED",
                matched_status="NEEDS_REVIEW",
            )
            session.add(invoice)
            await session.flush()
            ids.append(str(invoice.id))
        await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, ids, publisher, factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_actual_filtered_queue_review_and_persistence(http_lane):
    client, ids, publisher, factory = http_lane
    response = await client.get(
        "/api/v1/review/queue",
        params={
            "vendor_filter": "Acme",
            "date_from": "2026-01-01",
            "date_to": "2026-01-01",
            "page_size": 1,
            "sort_order": "asc",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2 and response.json()["has_next"]
    second = await client.get("/api/v1/review/queue?page=2&page_size=1&vendor_filter=Acme")
    assert second.json()["has_prev"] and not second.json()["has_next"]
    detail = await client.get("/api/v1/review/" + ids[0])
    assert detail.json()["vendor_name"] == "Acme"
    for invoice_id, action in zip(ids[:2], ["approve", "reject"]):
        response = await client.post(
            f"/api/v1/review/{invoice_id}/{action}",
            json={"reviewed_by": "reviewer", "review_notes": "document checked"},
        )
        assert response.status_code == 200 and response.json()["action"] == action
        conflict = await client.post(
            f"/api/v1/review/{invoice_id}/{action}",
            json={"reviewed_by": "reviewer", "review_notes": "duplicate"},
        )
        assert conflict.status_code == 409
        async with factory() as session:
            saved = await session.get(Invoice, uuid.UUID(invoice_id))
            assert saved.reviewed_by == "reviewer" and saved.review_notes == "document checked"
    assert publisher.await_count == 2
    assert (await client.get("/api/v1/review/queue")).json()["total"] == 1


@pytest.mark.asyncio
async def test_validation_missing_and_readiness_contracts(http_lane, monkeypatch):
    client, ids, _, _ = http_lane
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/health/live")).json()["status"] == "healthy"
    assert (await client.get("/health/ready")).json()["status"] == "healthy"
    assert (await client.get("/api/v1/review/not-a-uuid")).status_code == 400
    assert (await client.get("/api/v1/review/queue?page=0")).status_code == 400
    missing = str(uuid.uuid4())
    for suffix in ["", "/approve", "/reject"]:
        if suffix:
            r = await client.post(
                "/api/v1/review/" + missing + suffix,
                json={"reviewed_by": "r", "review_notes": "why"},
            )
        else:
            r = await client.get("/api/v1/review/" + missing)
        assert r.status_code == 404
        assert r.json()["request_id"] == r.headers["x-request-id"]
    assert (
        await client.post("/api/v1/review/" + ids[0] + "/reject", json={"reviewed_by": "r"})
    ).status_code == 400
    monkeypatch.setattr(message_service, "health_check", AsyncMock(return_value=False))
    assert (await client.get("/health/ready")).status_code == 503
    monkeypatch.setattr(settings, "environment", "staging")
    assert (await client.get("/health/ready")).json()["status"] == "unhealthy"
    monkeypatch.setattr(
        message_service, "health_check", AsyncMock(side_effect=RuntimeError("broker fault fixture"))
    )
    assert (await client.get("/health/ready")).json()["checks"]["rabbitmq"].startswith("unhealthy")

    @asynccontextmanager
    async def broken_db():
        raise RuntimeError("database fault fixture")
        yield

    monkeypatch.setattr(database, "get_db_session", broken_db)
    assert (await client.get("/health/ready")).json()["checks"]["database"].startswith("unhealthy")


@pytest.mark.asyncio
@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", "/approve"), ("post", "/reject")])
@pytest.mark.parametrize(
    "error,expected",
    [(ImportError("dependency fixture"), 503), (RuntimeError("storage fixture"), 500)],
)
async def test_production_api_faults(http_lane, monkeypatch, method, suffix, error, expected):
    client, ids, _, _ = http_lane
    name = {"": "get_invoice_detail", "/approve": "approve_invoice", "/reject": "reject_invoice"}[
        suffix
    ]
    monkeypatch.setattr(ReviewService, name, AsyncMock(side_effect=error))
    kwargs = {"json": {"reviewed_by": "r", "review_notes": "reason"}} if method == "post" else {}
    response = await getattr(client, method)("/api/v1/review/" + ids[0] + suffix, **kwargs)
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_queue_fault_and_broker_publish_failures(http_lane, monkeypatch):
    client, ids, publisher, _ = http_lane
    publisher.side_effect = RuntimeError("publish fault fixture")
    for invoice_id, action in zip(ids[:2], ["approve", "reject"]):
        assert (
            await client.post(
                f"/api/v1/review/{invoice_id}/{action}",
                json={"reviewed_by": "r", "review_notes": "reason"},
            )
        ).status_code == 502
    monkeypatch.setattr(
        ReviewService, "get_review_queue", AsyncMock(side_effect=RuntimeError("storage fixture"))
    )
    assert (await client.get("/api/v1/review/queue")).status_code == 500


@pytest.mark.asyncio
async def test_development_routes_are_labeled_fixtures(http_lane, monkeypatch):
    client, _, _, _ = http_lane
    monkeypatch.setattr(settings, "environment", "development")
    known = "123e4567-e89b-12d3-a456-426614174000"
    assert (await client.get("/api/v1/review/queue")).json()["items"] == []
    assert (await client.get("/health/ready")).json()["checks"]["database"].startswith("skipped")
    assert (await client.get("/api/v1/review/" + known)).json()["vendor_name"] == "Acme Corp"
    for action in ["approve", "reject"]:
        assert (
            await client.post(
                f"/api/v1/review/{known}/{action}",
                json={"reviewed_by": "r", "review_notes": "fixture"},
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/review/{uuid.uuid4()}/{action}",
                json={"reviewed_by": "r", "review_notes": "fixture"},
            )
        ).status_code == 404
    assert (await client.get("/api/v1/review/" + str(uuid.uuid4()))).status_code == 404


@pytest.mark.asyncio
async def test_actual_service_query_and_review_contract(http_lane):
    """Exercise real SQL queries independently of the HTTP error wrappers."""
    from app.models.schemas import ApproveRequest, RejectRequest

    client, ids, publisher, factory = http_lane
    service = ReviewService(message_service)
    async with factory() as session:
        queue = await service.get_review_queue(
            session,
            vendor_filter="Acme",
            date_from=datetime(2026, 1, 1),
            date_to=datetime(2026, 1, 2),
            sort_order="asc",
        )
        assert queue.total == 2
        detail = await service.get_invoice_detail(session, uuid.UUID(ids[0]))
        assert detail.vendor_name == "Acme"
        approved = await service.approve_invoice(
            session, detail.id, ApproveRequest(reviewed_by="r")
        )
        rejected = await service.reject_invoice(
            session,
            uuid.UUID(ids[1]),
            RejectRequest(reviewed_by="r", review_notes="incorrect amount"),
        )
        assert approved.action == "approve" and rejected.action == "reject"
        assert publisher.await_count == 2
