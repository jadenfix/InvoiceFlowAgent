"""Prove real Alembic upgrades, persistence and reversible review migrations.

Run from services/exception. PostgreSQL uses an isolated temporary database;
SQLite uses a temporary file. No existing application database is modified.
"""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from sqlalchemy.engine import make_url


def migrate(url, revision, direction="upgrade"):
    env = {**os.environ, "DATABASE_URL": url, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "alembic", direction, revision], env=env, check=True)


async def exercise(url, execute, rows):
    migrate(url, "head")
    columns = await rows("SELECT * FROM invoices LIMIT 0")
    assert {"id", "vendor_name", "confidence_score", "reviewed_by", "review_notes"} <= columns
    invoice_id = str(uuid.uuid4())
    # A real row must survive a repeated upgrade and review-column rollback.
    await execute(
        "INSERT INTO invoices (id, vendor_name, matched_status) VALUES "
        f"('{invoice_id}', 'Migration receipt', 'REVIEW')"
    )
    migrate(url, "head")
    assert await rows("SELECT vendor_name FROM invoices") == {"Migration receipt"}
    migrate(url, "0000", "downgrade")
    assert "reviewed_by" not in await rows("SELECT * FROM invoices LIMIT 0")
    assert await rows("SELECT vendor_name FROM invoices") == {"Migration receipt"}
    migrate(url, "head")
    assert "reviewed_by" in await rows("SELECT * FROM invoices LIMIT 0")
    migrate(url, "base", "downgrade")
    migrate(url, "head")
    assert await rows("SELECT vendor_name FROM invoices") == set()


async def main():
    supplied = make_url(os.environ.get("DATABASE_URL", "sqlite+aiosqlite://"))
    if supplied.get_backend_name() == "postgresql":
        import asyncpg

        database = "invoice_migration_" + uuid.uuid4().hex
        admin_url = supplied.set(drivername="postgresql").render_as_string(hide_password=False)
        admin = await asyncpg.connect(admin_url)
        connection = None
        try:
            await admin.execute(f'CREATE DATABASE "{database}"')
            target = supplied.set(database=database)
            url = target.render_as_string(hide_password=False)
            connection = await asyncpg.connect(
                target.set(drivername="postgresql").render_as_string(hide_password=False)
            )

            async def rows(sql):
                statement = await connection.prepare(sql)
                if "LIMIT 0" in sql:
                    return {attribute.name for attribute in statement.get_attributes()}
                return {row[0] for row in await statement.fetch()}

            await exercise(url, connection.execute, rows)
        finally:
            if connection:
                await connection.close()
            await admin.execute(f'DROP DATABASE IF EXISTS "{database}"')
            await admin.close()
    elif supplied.get_backend_name() == "sqlite":
        import aiosqlite

        with tempfile.TemporaryDirectory(prefix="invoice-migration-") as directory:
            path = Path(directory) / "proof.sqlite3"
            url = "sqlite+aiosqlite:///" + str(path)
            async with aiosqlite.connect(path) as connection:

                async def execute(sql):
                    await connection.execute(sql)
                    await connection.commit()

                async def rows(sql):
                    async with connection.execute(sql) as cursor:
                        if "LIMIT 0" in sql:
                            return {column[0] for column in cursor.description}
                        return {row[0] for row in await cursor.fetchall()}

                await exercise(url, execute, rows)
    else:
        raise ValueError("Only PostgreSQL and SQLite migration proof are supported")
    print("Actual migration upgrade/repeat/persistence/downgrade/reupgrade PASS")


if __name__ == "__main__":
    asyncio.run(main())
