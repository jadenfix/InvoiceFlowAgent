"""Dependency lifecycle and message-envelope contracts with labeled fault fixtures."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import Request
from app import main
from app.core.config import settings
from app.models import database
from app.services import message_service as broker
from app.services.message_service import MessageService, MessageServiceError, PublishError
from app.services.review_service import ReviewService
from app.models.schemas import ApproveRequest, RejectRequest
from app.models.database import Invoice


@pytest.mark.asyncio
async def test_message_envelope_and_local_broker_faults(monkeypatch):
    service = MessageService()
    assert not await service.health_check()
    with pytest.raises(PublishError, match="not connected"):
        await service.publish_review_message(uuid.uuid4(), "approve", "reviewer")
    connection, channel, exchange, queue = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    connection.is_closed = channel.is_closed = False
    connection.channel = AsyncMock(return_value=channel)
    connection.close = AsyncMock()
    channel.declare_exchange = AsyncMock(return_value=exchange)
    channel.declare_queue = AsyncMock(return_value=queue)
    queue.bind = AsyncMock()
    exchange.publish = AsyncMock()
    monkeypatch.setattr(broker, "connect_robust", AsyncMock(return_value=connection))
    await service.connect()
    assert await service.health_check()
    invoice_id = uuid.uuid4()
    await service.publish_review_message(invoice_id, "reject", "reviewer", "amount mismatch")
    message = exchange.publish.await_args.args[0]
    body = json.loads(message.body)
    assert body["invoice_id"] == str(invoice_id) and body["review_notes"] == "amount mismatch"
    assert message.delivery_mode.value == 2 and message.content_type == "application/json"
    assert exchange.publish.await_args.kwargs["routing_key"] == "invoice.reviewed.reject"
    queue.bind.assert_awaited_once_with(exchange, "invoice.reviewed.*")
    exchange.publish.side_effect = RuntimeError("broker publish fault fixture")
    with pytest.raises(PublishError, match="broker publish fault"):
        await service.publish_review_message(invoice_id, "approve", "reviewer")
    channel.is_closed = True
    assert not await service.health_check()
    service.channel = None
    assert not await service.health_check()
    await service.disconnect()
    connection.close.assert_awaited_once()
    connection.close.side_effect = RuntimeError("close fault fixture")
    await service.disconnect()
    service.connection = MagicMock(spec=["is_closed"])
    type(service.connection).is_closed = property(
        lambda _: (_ for _ in ()).throw(RuntimeError("health fault"))
    )
    assert not await service.health_check()
    monkeypatch.setattr(
        broker, "connect_robust", AsyncMock(side_effect=RuntimeError("connect fault fixture"))
    )
    with pytest.raises(MessageServiceError, match="connect fault"):
        await MessageService().connect()


@pytest.mark.asyncio
async def test_startup_shutdown_failures_do_not_leak_resources(monkeypatch):
    init, close, connect, disconnect = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(database, "init_db", init)
    monkeypatch.setattr(database, "close_db", close)
    monkeypatch.setattr(broker.message_service, "connect", connect)
    monkeypatch.setattr(broker.message_service, "disconnect", disconnect)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "database_url", "sqlite:///:memory:")
    await main.initialize_dependencies()
    await main.close_dependencies()
    assert not init.called and not disconnect.called
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://explicit-fixture")
    init.side_effect = RuntimeError("database startup fault")
    await main.initialize_dependencies()
    connect.assert_awaited_once()
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError, match="startup fault"):
        async with main.lifespan(main.app):
            pytest.fail("failed production startup must not serve requests")
    close.assert_awaited_once()
    init.side_effect = None
    disconnect.side_effect = RuntimeError("disconnect fault")
    async with main.lifespan(main.app):
        pass
    assert close.await_count == 2
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(
        main, "initialize_dependencies", AsyncMock(side_effect=RuntimeError("limited mode fixture"))
    )
    async with main.lifespan(main.app):
        pass


@pytest.mark.asyncio
async def test_request_failure_has_safe_error_envelope():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/fault",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": None,
            "scheme": "http",
        }
    )

    async def failure(_):
        raise RuntimeError("internal secret fixture")

    with pytest.raises(RuntimeError):
        await main.logging_middleware(request, failure)
    response = await main.general_exception_handler(
        request, RuntimeError("internal secret fixture")
    )
    assert response.status_code == 500
    body = json.loads(response.body)
    assert "internal secret" not in body["message"]
    assert body["request_id"] == request.state.request_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,request_type", [("approve", ApproveRequest), ("reject", RejectRequest)]
)
async def test_commit_failure_never_publishes_notification(action, request_type):
    invoice = Invoice(id=uuid.uuid4(), reviewed_by=None)
    result = MagicMock()
    result.scalar_one_or_none.return_value = invoice
    session = AsyncMock()
    session.execute.return_value = result
    session.commit.side_effect = RuntimeError("commit fault fixture")
    publisher = AsyncMock()
    service = ReviewService(publisher)
    with pytest.raises(RuntimeError, match="commit fault"):
        await getattr(service, action + "_invoice")(
            session, invoice.id, request_type(reviewed_by="reviewer", review_notes="reason")
        )
    session.rollback.assert_awaited_once()
    publisher.publish_review_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_database_initializer_and_session_cleanup(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import inspect, select

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(database, "async_engine", engine)
    monkeypatch.setattr(database, "async_session_factory", async_sessionmaker(engine))
    await database.init_db()
    async with engine.connect() as conn:
        assert "invoices" in await conn.run_sync(lambda c: inspect(c).get_table_names())
    async with database.get_db_session() as session:
        session.add(Invoice(vendor_name="persistent fixture"))
        await session.commit()
    with pytest.raises(RuntimeError, match="transaction fault"):
        async with database.get_db_session() as session:
            session.add(Invoice(vendor_name="rolled back fixture"))
            await session.flush()
            raise RuntimeError("transaction fault")
    async with database.get_db_session() as session:
        assert (await session.scalars(select(Invoice.vendor_name))).all() == ["persistent fixture"]
    await database.close_db()
