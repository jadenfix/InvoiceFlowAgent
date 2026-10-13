"""Actual HTTP/PostgreSQL/RabbitMQ pipeline with transactional outbox and replay."""

import asyncio
import contextlib
import json
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone, date
import logging
import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import aio_pika
import asyncpg
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .extraction import extract_fields, match_amount
from .storage import S3Mirror
from pamqp.commands import Basic

log = logging.getLogger(__name__)
SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_invoices (
 id UUID PRIMARY KEY, filename TEXT NOT NULL, pdf BYTEA NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','EXTRACTED','MATCHED','COMPLETED','FAILED')),
 fields JSONB, match_result JSONB, error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pipeline_purchase_orders (
 po_number TEXT PRIMARY KEY, amount NUMERIC(14,2) NOT NULL CHECK(amount>0),
 currency TEXT NOT NULL CHECK(length(currency)=3)
);
CREATE TABLE IF NOT EXISTS pipeline_users (
 id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE, full_name TEXT,
 password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pipeline_sessions (
 token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES pipeline_users(id), expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS pipeline_reviews (
 invoice_id UUID PRIMARY KEY REFERENCES pipeline_invoices(id), action TEXT NOT NULL CHECK(action IN ('approve','reject')),
 user_id BIGINT NOT NULL REFERENCES pipeline_users(id), reviewed_by TEXT NOT NULL, review_notes TEXT,
 reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pipeline_outbox (
 id UUID PRIMARY KEY, invoice_id UUID NOT NULL REFERENCES pipeline_invoices(id),
 stage TEXT NOT NULL CHECK(stage IN ('extract','match','complete')), sent BOOLEAN NOT NULL DEFAULT false,
 UNIQUE(invoice_id,stage)
);
ALTER TABLE pipeline_invoices DROP CONSTRAINT IF EXISTS pipeline_invoices_status_check;
ALTER TABLE pipeline_invoices ADD CONSTRAINT pipeline_invoices_status_check CHECK(status IN ('PENDING','EXTRACTED','MATCHED','COMPLETED','FAILED'));
ALTER TABLE pipeline_outbox DROP CONSTRAINT IF EXISTS pipeline_outbox_stage_check;
ALTER TABLE pipeline_outbox ADD CONSTRAINT pipeline_outbox_stage_check CHECK(stage IN ('extract','match','complete'));
"""


class PurchaseOrder(BaseModel):
    po_number: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Credentials(BaseModel):
    email: str = Field(
        min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )
    password: str = Field(min_length=12, max_length=128)


class Registration(Credentials):
    full_name: str | None = Field(default=None, max_length=200)


class ReviewInput(BaseModel):
    reviewed_by: str = Field(min_length=1, max_length=200)
    review_notes: str | None = Field(default=None, max_length=4000)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 600000
    ).hex()
    return salt + ":" + digest


class Pipeline:
    def __init__(self):
        self.storage = S3Mirror.from_env()
        self.pool = None
        self.connection = None
        self.channel = None
        self.tasks = []
        self.consumer_ready = False
        self.queue_lock = asyncio.Lock()

    async def connect_queue(self):
        async with self.queue_lock:
            if self.connection and not self.connection.is_closed:
                # A robust connection remains logically open during broker outages.
                # Wait for its real transport; do not replace it and strand consumers.
                await asyncio.wait_for(self.connection.connected.wait(), timeout=3)
                if self.channel:
                    await asyncio.wait_for(self.channel.ready(), timeout=3)
                    return
            else:
                self.connection = await aio_pika.connect_robust(
                    os.getenv(
                        "RABBITMQ_URL", "amqp://testuser:testpassword@127.0.0.1/"
                    ),
                    timeout=3,
                )
            self.channel = await self.connection.channel(
                publisher_confirms=True, on_return_raises=True
            )
            await self.channel.set_qos(prefetch_count=1)
            for stage in ("extract", "match", "complete"):
                await self.channel.declare_queue(f"pipeline_{stage}", durable=True)

    async def start(self, role):
        if os.getenv("EXTRACTION_MODE", "local_text") != "local_text":
            raise ValueError("Only explicit local_text PDF extraction is supported")
        if self.storage:
            await asyncio.to_thread(self.storage.check_ready)
        self.pool = await asyncpg.create_pool(
            os.getenv(
                "DATABASE_URL",
                "postgresql://testuser:testpassword@127.0.0.1/invoiceflow_test",
            ).replace("postgresql+asyncpg://", "postgresql://"),
            min_size=1,
            max_size=5,
        )
        # All roles may start concurrently; serialize first-time schema creation.
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(246613)")
                await conn.execute(SCHEMA)
        for attempt in range(30):
            try:
                await self.connect_queue()
                break
            except (OSError, aio_pika.exceptions.AMQPException, asyncio.TimeoutError):
                if attempt == 29:
                    await self.pool.close()
                    raise
                await asyncio.sleep(2)
        self.tasks.append(asyncio.create_task(self.dispatch_outbox()))
        if role in ("extract", "match"):
            self.tasks.append(asyncio.create_task(self.consume(role)))

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self.connection:
            await self.connection.close()
        if self.pool:
            await self.pool.close()

    async def dispatch_once(self):
        """One transactional batch; any unconfirmed publication rolls back sent/completed."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    "SELECT * FROM pipeline_outbox WHERE NOT sent ORDER BY id LIMIT 20 FOR UPDATE SKIP LOCKED"
                )
                for row in rows:
                    message = aio_pika.Message(
                        json.dumps(
                            {
                                "invoice_id": str(row["invoice_id"]),
                                "stage": row["stage"],
                            }
                        ).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        message_id=str(row["id"]),
                    )
                    confirmation = await self.channel.default_exchange.publish(
                        message,
                        routing_key=f"pipeline_{row['stage']}",
                        mandatory=True,
                    )
                    if not isinstance(confirmation, Basic.Ack):
                        raise RuntimeError("Broker did not confirm durable publication")
                    if row["stage"] == "complete":
                        await conn.execute(
                            "UPDATE pipeline_invoices SET status='COMPLETED',updated_at=now() WHERE id=$1 AND status='MATCHED'",
                            row["invoice_id"],
                        )
                    await conn.execute(
                        "UPDATE pipeline_outbox SET sent=true WHERE id=$1",
                        row["id"],
                    )

    async def dispatch_outbox(self):
        while True:
            try:
                await self.connect_queue()
                await self.dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Outbox dispatch failed; persisted work will retry")
            await asyncio.sleep(0.2)

    async def consume(self, stage):
        while True:
            try:
                await self.connect_queue()
                queue = await self.channel.declare_queue(
                    f"pipeline_{stage}", durable=True
                )
                async with queue.iterator() as iterator:
                    self.consumer_ready = True
                    async for message in iterator:
                        async with message.process(requeue=True):
                            try:
                                invoice_id = uuid.UUID(
                                    json.loads(message.body)["invoice_id"]
                                )
                            except (ValueError, KeyError, TypeError):
                                # Malformed queue messages must not poison the consumer indefinitely.
                                log.error("Discarding malformed pipeline message")
                                continue
                            await self.process(stage, invoice_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.consumer_ready = False
                log.exception("Consumer disconnected; retrying")
                await asyncio.sleep(1)

    async def process(self, stage, invoice_id):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT * FROM pipeline_invoices WHERE id=$1 FOR UPDATE", invoice_id
                )
                if row is None or row["status"] in ("COMPLETED", "FAILED"):
                    return
                if stage == "extract":
                    if row["status"] != "PENDING":
                        return  # redelivery after the extraction transaction committed
                    try:
                        fields = await asyncio.to_thread(
                            extract_fields, bytes(row["pdf"])
                        )
                    except ValueError as error:
                        await conn.execute(
                            "UPDATE pipeline_invoices SET status='FAILED',error=$2,updated_at=now() WHERE id=$1",
                            invoice_id,
                            str(error),
                        )
                        return
                    if self.storage:
                        await asyncio.to_thread(
                            self.storage.put_fields, invoice_id, fields
                        )
                    await conn.execute(
                        "UPDATE pipeline_invoices SET status='EXTRACTED',fields=$2::jsonb,updated_at=now() WHERE id=$1",
                        invoice_id,
                        json.dumps(fields),
                    )
                    await conn.execute(
                        "INSERT INTO pipeline_outbox(id,invoice_id,stage) VALUES($1,$2,'match') ON CONFLICT(invoice_id,stage) DO NOTHING",
                        uuid.uuid4(),
                        invoice_id,
                    )
                elif stage == "match" and row["status"] == "EXTRACTED":
                    fields = json.loads(row["fields"])
                    po = await conn.fetchrow(
                        "SELECT * FROM pipeline_purchase_orders WHERE po_number=$1",
                        fields.get("po_number"),
                    )
                    result = {
                        "matched_status": "NEEDS_REVIEW",
                        "reason": "Purchase order not found",
                        "po_number": fields.get("po_number"),
                    }
                    if po:
                        result = match_amount(
                            fields["total_amount"],
                            po["amount"],
                            fields["currency"],
                            po["currency"],
                        )
                        result["po_number"] = po["po_number"]
                    await conn.execute(
                        "UPDATE pipeline_invoices SET status='MATCHED',match_result=$2::jsonb,updated_at=now() WHERE id=$1",
                        invoice_id,
                        json.dumps(result),
                    )
                    await conn.execute(
                        "INSERT INTO pipeline_outbox(id,invoice_id,stage) VALUES($1,$2,'complete') ON CONFLICT(invoice_id,stage) DO NOTHING",
                        uuid.uuid4(),
                        invoice_id,
                    )


def create_app(role=None):
    role = role or os.getenv("PIPELINE_ROLE", "ingest")
    if role not in ("ingest", "extract", "match"):
        raise ValueError("PIPELINE_ROLE must be ingest, extract, or match")
    pipeline = Pipeline()

    @asynccontextmanager
    async def lifespan(app):
        await pipeline.start(role)
        try:
            yield
        finally:
            await pipeline.stop()

    app = FastAPI(title=f"InvoiceFlow {role} pipeline", lifespan=lifespan)
    app.state.pipeline = pipeline
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    def public_user(row):
        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "is_active": True,
            "is_verified": False,
            "created_at": row["created_at"],
            "updated_at": row["created_at"],
        }

    async def user(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Authentication required")
        hashed = hashlib.sha256(authorization[7:].encode()).hexdigest()
        row = await pipeline.pool.fetchrow(
            "SELECT u.* FROM pipeline_users u JOIN pipeline_sessions s ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires_at>now()",
            hashed,
        )
        if not row:
            raise HTTPException(401, "Invalid or expired session")
        return row

    @app.post("/auth/register", status_code=201)
    async def register(credentials: Registration):
        hashed = await asyncio.to_thread(password_hash, credentials.password)
        try:
            row = await pipeline.pool.fetchrow(
                "INSERT INTO pipeline_users(email,full_name,password_hash) VALUES($1,$2,$3) RETURNING *",
                credentials.email.lower(),
                credentials.full_name,
                hashed,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "Email already registered")
        return public_user(row)

    @app.post("/auth/login")
    async def login(credentials: Credentials):
        row = await pipeline.pool.fetchrow(
            "SELECT * FROM pipeline_users WHERE email=$1", credentials.email.lower()
        )
        # Perform comparable work on absent users to avoid a trivial timing oracle.
        expected = (
            row["password_hash"]
            if row
            else password_hash("dummy-missing-user-password", "00" * 16)
        )
        actual = await asyncio.to_thread(
            password_hash, credentials.password, expected.split(":")[0]
        )
        if not row or not hmac.compare_digest(actual, expected):
            raise HTTPException(401, "Invalid email or password")
        token = secrets.token_urlsafe(32)
        await pipeline.pool.execute(
            "INSERT INTO pipeline_sessions VALUES($1,$2,$3)",
            hashlib.sha256(token.encode()).hexdigest(),
            row["id"],
            datetime.now(timezone.utc) + timedelta(hours=1),
        )
        return {"access_token": token, "token_type": "bearer", "expires_in": 3600}

    @app.get("/auth/me")
    async def current_user(current=Depends(user)):
        return public_user(current)

    @app.post("/auth/logout")
    async def logout(current=Depends(user), authorization: str = Header()):
        await pipeline.pool.execute(
            "DELETE FROM pipeline_sessions WHERE token_hash=$1",
            hashlib.sha256(authorization[7:].encode()).hexdigest(),
        )
        return {"success": True}

    def review_item(row):
        fields = json.loads(row["fields"])
        match = json.loads(row["match_result"])
        return {
            "id": str(row["id"]),
            "vendor_name": fields["vendor_name"],
            "invoice_number": fields["invoice_number"],
            "invoice_date": fields.get("invoice_date"),
            "total_amount": float(fields["total_amount"]),
            "matched_status": match["matched_status"],
            "created_at": row["created_at"],
            "extraction_method": fields["extraction_method"],
        }

    @app.get("/api/v1/review/queue")
    async def review_queue(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        vendor_filter: str | None = Query(None, max_length=200),
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        current=Depends(user),
    ):
        sorts = {
            "created_at": "created_at",
            "vendor_name": "fields->>'vendor_name'",
            "invoice_number": "fields->>'invoice_number'",
            "invoice_date": "fields->>'invoice_date'",
            "total_amount": "(fields->>'total_amount')::numeric",
        }
        if sort_by not in sorts or sort_order not in ("asc", "desc"):
            raise HTTPException(400, "Invalid sort")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(400, "Invalid date range")
        clauses = [
            "status='COMPLETED'",
            "match_result->>'matched_status'='NEEDS_REVIEW'",
            "NOT EXISTS(SELECT 1 FROM pipeline_reviews r WHERE r.invoice_id=pipeline_invoices.id)",
        ]
        args = []
        for value, clause in [
            (vendor_filter, "fields->>'vendor_name' ILIKE '%' || ${n} || '%'"),
            (date_from, "(fields->>'invoice_date')::date>=${n}"),
            (date_to, "(fields->>'invoice_date')::date<=${n}"),
        ]:
            if value is not None:
                args.append(value)
                clauses.append(clause.replace("{n}", str(len(args))))
        where = " AND ".join(clauses)
        total = await pipeline.pool.fetchval(
            "SELECT count(*) FROM pipeline_invoices WHERE " + where, *args
        )
        rows = await pipeline.pool.fetch(
            "SELECT * FROM pipeline_invoices WHERE "
            + where
            + f" ORDER BY {sorts[sort_by]} {sort_order},id LIMIT ${len(args)+1} OFFSET ${len(args)+2}",
            *args,
            page_size,
            (page - 1) * page_size,
        )
        return {
            "items": [review_item(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        }

    @app.get("/api/v1/review/{invoice_id}")
    async def review_detail(invoice_id: uuid.UUID, current=Depends(user)):
        row = await pipeline.pool.fetchrow(
            "SELECT * FROM pipeline_invoices WHERE id=$1 AND status='COMPLETED'",
            invoice_id,
        )
        if not row:
            raise HTTPException(404, "Invoice not found")
        item = review_item(row)
        fields = json.loads(row["fields"])
        item.update(
            {
                "status": row["status"],
                "extracted_vendor": fields["vendor_name"],
                "extracted_amount": float(fields["total_amount"]),
                "extracted_invoice_number": fields["invoice_number"],
                "extracted_date": fields.get("invoice_date"),
                "file_path": f"/api/v1/review/{invoice_id}/document",
                "file_type": "pdf",
                "match_details": row["match_result"],
                "updated_at": row["updated_at"],
            }
        )
        review = await pipeline.pool.fetchrow(
            "SELECT * FROM pipeline_reviews WHERE invoice_id=$1", invoice_id
        )
        if review:
            item.update(
                {
                    "reviewed_by": review["reviewed_by"],
                    "review_notes": review["review_notes"],
                    "reviewed_at": review["reviewed_at"],
                    "matched_status": (
                        "APPROVED" if review["action"] == "approve" else "REJECTED"
                    ),
                }
            )
        return item

    @app.get("/api/v1/review/{invoice_id}/document")
    async def review_document(invoice_id: uuid.UUID, current=Depends(user)):
        pdf = await pipeline.pool.fetchval(
            "SELECT pdf FROM pipeline_invoices WHERE id=$1", invoice_id
        )
        if pdf is None:
            raise HTTPException(404, "Invoice not found")
        return Response(
            bytes(pdf),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=invoice.pdf",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/api/v1/review/{invoice_id}/{action}")
    async def review_action(
        invoice_id: uuid.UUID, action: str, review: ReviewInput, current=Depends(user)
    ):
        if action not in ("approve", "reject"):
            raise HTTPException(404, "Unknown review action")
        if action == "reject" and not (review.review_notes or "").strip():
            raise HTTPException(422, "Rejection requires review notes")
        async with pipeline.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT * FROM pipeline_invoices WHERE id=$1 FOR UPDATE", invoice_id
                )
                if not row or row["status"] != "COMPLETED":
                    raise HTTPException(404, "Invoice not found")
                if json.loads(row["match_result"])["matched_status"] != "NEEDS_REVIEW":
                    raise HTTPException(409, "Invoice does not require review")
                if await conn.fetchval(
                    "SELECT 1 FROM pipeline_reviews WHERE invoice_id=$1", invoice_id
                ):
                    raise HTTPException(409, "Invoice already reviewed")
                # Identity comes from the authenticated session, not client-supplied reviewer text.
                who = current["email"]
                saved = await conn.fetchrow(
                    "INSERT INTO pipeline_reviews(invoice_id,action,user_id,reviewed_by,review_notes) VALUES($1,$2,$3,$4,$5) RETURNING *",
                    invoice_id,
                    action,
                    current["id"],
                    who,
                    review.review_notes,
                )
        return {
            "invoice_id": str(invoice_id),
            "action": action,
            "reviewed_by": who,
            "reviewed_at": saved["reviewed_at"],
            "review_notes": saved["review_notes"],
        }

    @app.get("/health/live")
    async def health_live():
        return {"status": "alive", "role": role}

    @app.get("/healthz")
    @app.get("/health/ready")
    async def health_ready():
        try:
            await pipeline.pool.fetchval("SELECT 1")
            if (
                not pipeline.connection
                or not pipeline.connection.connected.is_set()
                or not pipeline.channel
                or (role != "ingest" and not pipeline.consumer_ready)
            ):
                raise RuntimeError("Queue not ready")
            await asyncio.wait_for(
                pipeline.channel.declare_queue(
                    "pipeline_extract", durable=True, passive=True
                ),
                timeout=2,
            )
            if pipeline.storage:
                await asyncio.to_thread(pipeline.storage.check_ready)
            return {
                "storage": "local_s3_verified" if pipeline.storage else "postgresql",
                "status": "ready",
                "database": "postgresql",
                "queue": "rabbitmq",
                "extraction": "local_text_pdf",
                "provider_used": False,
            }
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})

    @app.post("/api/v1/purchase-orders", status_code=201)
    async def create_po(po: PurchaseOrder):
        if role != "ingest":
            raise HTTPException(404)
        try:
            await pipeline.pool.execute(
                "INSERT INTO pipeline_purchase_orders VALUES($1,$2,$3)",
                po.po_number,
                po.amount,
                po.currency,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "Purchase order already exists")
        return {
            "po_number": po.po_number,
            "amount": str(po.amount),
            "currency": po.currency,
        }

    @app.post("/api/v1/ingest/upload", status_code=202)
    async def upload(file: UploadFile = File(...)):
        if role != "ingest":
            raise HTTPException(404)
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are supported")
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Maximum PDF size is 10MB")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(400, "Invalid PDF signature")
        invoice_id = uuid.uuid4()
        if pipeline.storage:
            try:
                await asyncio.to_thread(
                    pipeline.storage.put_source, invoice_id, content
                )
            except Exception:
                log.exception("S3 source storage failed; upload not accepted")
                raise HTTPException(503, "Source storage unavailable")
        async with pipeline.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO pipeline_invoices(id,filename,pdf,status) VALUES($1,$2,$3,'PENDING')",
                    invoice_id,
                    file.filename[:255],
                    content,
                )
                await conn.execute(
                    "INSERT INTO pipeline_outbox(id,invoice_id,stage) VALUES($1,$2,'extract')",
                    uuid.uuid4(),
                    invoice_id,
                )
        return {
            "request_id": str(invoice_id),
            "status": "PENDING",
            "extraction_method": "local_text_pdf",
        }

    @app.get("/api/v1/ingest/status/{request_id}")
    async def status(request_id: uuid.UUID):
        row = await pipeline.pool.fetchrow(
            "SELECT id,filename,status,fields,match_result,error,created_at,updated_at FROM pipeline_invoices WHERE id=$1",
            request_id,
        )
        if not row:
            raise HTTPException(404, "Invoice not found")
        record = dict(row)
        record["request_id"] = str(record.pop("id"))
        for key in ("fields", "match_result"):
            record[key] = json.loads(record[key]) if record[key] else None
        return record

    @app.get("/api/v1/ingest/stats")
    async def stats():
        rows = await pipeline.pool.fetch(
            "SELECT status,count(*) AS count FROM pipeline_invoices GROUP BY status"
        )
        counts = {row["status"].lower(): row["count"] for row in rows}
        return {
            **{
                key: counts.get(key, 0)
                for key in ("pending", "extracted", "matched", "completed", "failed")
            },
            "total": sum(counts.values()),
        }

    return app


app = create_app()
