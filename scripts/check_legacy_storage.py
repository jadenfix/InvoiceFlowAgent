"""Mandatory shared LocalStack/Postgres/RabbitMQ document-derived integration proof."""

import asyncio
import json
import os
import sys
import subprocess
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aio_pika
import asyncpg
import boto3
import httpx
from types import SimpleNamespace
from services.pipeline.runtime import Pipeline
from scripts.check_pipeline_http import make_pdf, wait_status

BASE = "http://127.0.0.1:8003"
DB = "postgresql://testuser:testpassword@127.0.0.1/invoiceflow_test"
MQ = "amqp://testuser:testpassword@127.0.0.1/"


def client():
    return boto3.client(
        "s3",
        endpoint_url="http://127.0.0.1:4566",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )


def bootstrap():
    s3 = client()
    for bucket in ("invoices", "processed-invoices"):
        s3.create_bucket(Bucket=bucket)
        s3.head_bucket(Bucket=bucket)
    print("Actual local S3 buckets ready", flush=True)


async def proof():
    s3 = client()
    mq = await aio_pika.connect_robust(MQ)
    channel = await mq.channel()
    complete = await channel.declare_queue("pipeline_complete", durable=True)
    db = await asyncpg.connect(DB)
    try:
        with httpx.Client(timeout=15) as http:
            suffix = uuid.uuid4().hex[:12]
            po = "PO-" + suffix
            response = http.post(
                BASE + "/api/v1/purchase-orders",
                json={"po_number": po, "amount": "1000.00", "currency": "USD"},
            )
            response.raise_for_status()
            cases = [("995.00", po, "AUTO_APPROVED"), ("2500.00", None, "NEEDS_REVIEW")]
            ids = []
            for index, (amount, number, decision) in enumerate(cases):
                lines = [
                    "Vendor: Storage Contract",
                    f"Invoice: S3-{suffix}-{index}",
                    f"Total: {amount}",
                    "Currency: USD",
                ]
                if number:
                    lines.append("PO: " + number)
                pdf = make_pdf(lines)
                response = http.post(
                    BASE + "/api/v1/ingest/upload",
                    files={"file": ("invoice.pdf", pdf, "application/pdf")},
                    data={
                        "total_amount": "1.00",
                        "po_number": "CONTRADICTORY-METADATA",
                    },
                )
                assert response.status_code == 202, response.text
                invoice_id = response.json()["request_id"]
                ids.append(invoice_id)
                # Let workers run while waiting for real final state.
                status = await asyncio.to_thread(wait_status, http, invoice_id)
                assert status["fields"]["total_amount"] == amount, status
                assert status["match_result"]["matched_status"] == decision, status
                body = s3.get_object(
                    Bucket="invoices", Key=f"invoices/{invoice_id}/source.pdf"
                )["Body"]
                assert body.read() == pdf
                body.close()
                fields = json.loads(
                    s3.get_object(
                        Bucket="processed-invoices",
                        Key=f"invoices/{invoice_id}/fields.json",
                    )["Body"].read()
                )
                assert fields == status["fields"]
                persisted = await db.fetchrow(
                    "SELECT status, pdf,fields FROM pipeline_invoices WHERE id=$1",
                    uuid.UUID(invoice_id),
                )
                assert (
                    persisted["status"] == "COMPLETED"
                    and bytes(persisted["pdf"]) == pdf
                )
            found = set()
            deadline = time.monotonic() + 15
            while not set(ids).issubset(found) and time.monotonic() < deadline:
                message = await complete.get(timeout=2, fail=False)
                if message:
                    event = json.loads(message.body)
                    if event["invoice_id"] in ids:
                        assert event["stage"] == "complete"
                        found.add(event["invoice_id"])
                    await message.ack()
            assert set(ids).issubset(
                found
            ), "Missing mandatory correlated final broker event"
            bad = make_pdf(
                ["Vendor: Bad", "Invoice: Bad", "Total: 9,9,5.00", "Currency: USD"]
            )
            response = http.post(
                BASE + "/api/v1/ingest/upload",
                files={"file": ("bad.pdf", bad, "application/pdf")},
            )
            assert response.status_code == 202
            failed = await asyncio.to_thread(
                wait_status, http, response.json()["request_id"], "FAILED"
            )
            assert failed["match_result"] is None
            assert (
                http.get(
                    BASE + "/api/v1/ingest/status/" + str(uuid.uuid4())
                ).status_code
                == 404
            )
            # Real missing-bucket SDK error must reject upload without any invoice/outbox row.
            before = await db.fetchval("SELECT count(*) FROM pipeline_invoices")
            for entry in s3.list_objects_v2(Bucket="invoices").get("Contents", []):
                s3.delete_object(Bucket="invoices", Key=entry["Key"])
            s3.delete_bucket(Bucket="invoices")
            rejected = http.post(
                BASE + "/api/v1/ingest/upload",
                files={
                    "file": (
                        "unavailable.pdf",
                        make_pdf(
                            [
                                "Vendor: No Storage",
                                "Invoice: X",
                                "Total: 100.00",
                                "Currency: USD",
                            ]
                        ),
                        "application/pdf",
                    )
                },
            )
            assert rejected.status_code == 503, rejected.text
            assert await db.fetchval("SELECT count(*) FROM pipeline_invoices") == before
            assert http.get(BASE + "/health/ready").status_code == 503
            s3.create_bucket(Bucket="invoices")
        # Stop application dispatchers, then exercise real PostgreSQL rollback for
        # an explicitly injected broker rejection, followed by a real confirmed publish.
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.e2e.yml",
                "stop",
                "ingest",
                "extract",
                "match",
            ],
            check=True,
        )
        test_id, outbox_id = uuid.uuid4(), uuid.uuid4()
        await db.execute(
            "INSERT INTO pipeline_invoices(id,filename,pdf,status) VALUES($1,'publication-failure.pdf',$2,'MATCHED')",
            test_id,
            b"%PDF-contract",
        )
        await db.execute(
            "INSERT INTO pipeline_outbox(id,invoice_id,stage) VALUES($1,$2,'complete')",
            outbox_id,
            test_id,
        )
        worker = Pipeline()
        worker.pool = await asyncpg.create_pool(DB, min_size=1, max_size=2)

        async def rejected(*args, **kwargs):
            return False

        worker.channel = SimpleNamespace(
            default_exchange=SimpleNamespace(publish=rejected)
        )
        try:
            try:
                await worker.dispatch_once()
            except RuntimeError as error:
                assert "did not confirm" in str(error)
            else:
                raise AssertionError("Unconfirmed publication was accepted")
            assert (
                await db.fetchval(
                    "SELECT status FROM pipeline_invoices WHERE id=$1", test_id
                )
                == "MATCHED"
            )
            assert (
                await db.fetchval(
                    "SELECT sent FROM pipeline_outbox WHERE id=$1", outbox_id
                )
                is False
            )
            await worker.connect_queue()
            await worker.dispatch_once()
            assert (
                await db.fetchval(
                    "SELECT status FROM pipeline_invoices WHERE id=$1", test_id
                )
                == "COMPLETED"
            )
            assert (
                await db.fetchval(
                    "SELECT sent FROM pipeline_outbox WHERE id=$1", outbox_id
                )
                is True
            )
            observed = False
            for _ in range(30):
                message = await complete.get(timeout=2, fail=False)
                if message:
                    observed = json.loads(message.body)["invoice_id"] == str(test_id)
                    await message.ack()
                    if observed:
                        break
            assert observed, "Confirmed publication missing actual final event"
        finally:
            await worker.stop()
        print(
            "PASS real S3 byte roundtrip, shared DB, document-derived decisions, mandatory final events, malformed PDF and actual storage failure",
            flush=True,
        )
    finally:
        await db.close()
        await mq.close()


if __name__ == "__main__":
    if "--bootstrap" in sys.argv:
        bootstrap()
    else:
        asyncio.run(proof())
