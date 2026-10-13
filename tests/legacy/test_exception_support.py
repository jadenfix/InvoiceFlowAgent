"""Local computation regressions; SQLite fixture is not Postgres/RabbitMQ E2E."""

import sys
from pathlib import Path
import uuid
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/exception"))
from app.models import database
from app.core.config import Settings, settings
from app.main import lifespan


@pytest.mark.asyncio
async def test_actual_session_context_persistence(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "invoice.db"))
    async with engine.begin() as connection:
        await connection.run_sync(database.Base.metadata.create_all)
    monkeypatch.setattr(
        database, "async_session_factory", async_sessionmaker(engine, expire_on_commit=False)
    )
    identifier = uuid.uuid4()
    try:
        async with database.get_db_session() as session:
            session.add(database.Invoice(id=identifier, vendor_name="Explicit SQLite fixture"))
            await session.commit()
        async with database.get_db_session() as session:
            invoice = await session.get(database.Invoice, identifier)
            assert invoice.vendor_name == "Explicit SQLite fixture"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_actual_context_rolls_back_failed_operation(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "rollback.db"))
    async with engine.begin() as connection:
        await connection.run_sync(database.Base.metadata.create_all)
    monkeypatch.setattr(database, "async_session_factory", async_sessionmaker(engine))
    try:
        with pytest.raises(ValueError, match="operation failed"):
            async with database.get_db_session() as session:
                session.add(database.Invoice(vendor_name="must roll back"))
                await session.flush()
                raise ValueError("operation failed")
        async with database.get_db_session() as session:
            assert (
                await session.execute(select(func.count()).select_from(database.Invoice))
            ).scalar() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lifespan_propagates_application_error_once(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "database_url", "sqlite:///:memory:")
    with pytest.raises(ValueError, match="actual application error"):
        async with lifespan(None):
            raise ValueError("actual application error")


def test_settings_environment_alias_and_constructor(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "testing")
    assert Settings(_env_file=None).environment == "testing"
    assert Settings(environment="development", _env_file=None).environment == "development"
