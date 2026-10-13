"""Actual HTTP→PDF→RabbitMQ→Postgres proof; no mocks or paid providers.

Requires docker-compose.pipeline.yml to be running. Includes broker/worker outages,
idempotent redelivery, invalid PDF failures, currency/variance review, and restart.
"""

import argparse
import asyncio
import io
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import aio_pika
import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("PIPELINE_URL", "http://127.0.0.1:8003")
DB = os.getenv(
    "DATABASE_URL", "postgresql://testuser:testpassword@127.0.0.1/invoiceflow_test"
)
MQ = os.getenv("RABBITMQ_URL", "amqp://testuser:testpassword@127.0.0.1/")


def make_pdf(lines):
    """Generate a valid text PDF with actual font, offsets and byte lengths."""
    escaped = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    stream = (
        "BT /F1 12 Tf 50 740 Td "
        + " 0 -24 Td ".join(f"({line}) Tj" for line in escaped)
        + " ET"
    ).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, data in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{i} 0 obj\n".encode() + data + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    content.extend(
        b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    )
    content.extend(
        f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(content)


def compose(*args):
    subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.pipeline.yml"), *args],
        cwd=ROOT,
        check=True,
    )


def wait_ready(client):
    for _ in range(120):
        try:
            if client.get(BASE + "/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise AssertionError("Ingestion service did not become ready")


def wait_status(client, invoice_id, expected="COMPLETED"):
    for _ in range(120):
        response = client.get(BASE + f"/api/v1/ingest/status/{invoice_id}")
        response.raise_for_status()
        data = response.json()
        if data["status"] == expected:
            return data
        if data["status"] == "FAILED" and expected != "FAILED":
            raise AssertionError(data)
        time.sleep(0.25)
    raise AssertionError(f"Pipeline did not reach {expected}: {data}")


async def verify_database(ids, approved_id):
    conn = await asyncpg.connect(DB)
    try:
        rows = await conn.fetch(
            "SELECT id,status,fields,match_result,pdf FROM pipeline_invoices WHERE id=ANY($1::uuid[])",
            [uuid.UUID(x) for x in ids],
        )
        assert len(rows) == len(ids)
        assert all(bytes(r["pdf"]).startswith(b"%PDF-") for r in rows)
        row = next(r for r in rows if str(r["id"]) == approved_id)
        assert json.loads(row["fields"])["invoice_number"].startswith("INV-")
        assert json.loads(row["match_result"])["matched_status"] == "AUTO_APPROVED"
    finally:
        await conn.close()


async def replay(invoice_id):
    connection = await aio_pika.connect_robust(MQ)
    try:
        channel = await connection.channel(publisher_confirms=True)
        for stage in ["extract", "match"]:
            await channel.default_exchange.publish(
                aio_pika.Message(
                    json.dumps({"invoice_id": invoice_id}).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="pipeline_" + stage,
                mandatory=True,
            )
    finally:
        await connection.close()


def run(with_restart=True):
    run_id = uuid.uuid4().hex[:8]
    po = "PO-" + run_id
    ids = []
    with httpx.Client(timeout=10, trust_env=False) as client:
        wait_ready(client)
        assert (
            client.get(BASE + "/api/v1/ingest/status/" + str(uuid.uuid4())).status_code
            == 404
        )
        assert client.get(BASE + "/api/v1/review/queue").status_code == 401
        credentials = {
            "email": f"reviewer-{run_id}@example.com",
            "password": "Proof-Pipeline-Password-123",
        }
        assert (
            client.post(
                BASE + "/auth/register",
                json={**credentials, "full_name": "Pipeline Reviewer"},
            ).status_code
            == 201
        )
        assert client.post(BASE + "/auth/register", json=credentials).status_code == 409
        assert (
            client.post(
                BASE + "/auth/login",
                json={**credentials, "password": "Wrong-Password-123"},
            ).status_code
            == 401
        )
        token = client.post(BASE + "/auth/login", json=credentials)
        assert token.status_code == 200, token.text
        client.headers["Authorization"] = "Bearer " + token.json()["access_token"]
        assert client.get(BASE + "/auth/me").json()["email"] == credentials["email"]
        assert (
            client.get(
                BASE + "/auth/me", headers={"Authorization": "Bearer tampered"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                BASE + "/api/v1/ingest/upload",
                files={"file": ("bad.pdf", b"garbage", "application/pdf")},
            ).status_code
            == 400
        )
        assert (
            client.post(
                BASE + "/api/v1/purchase-orders",
                json={"po_number": po, "amount": "100", "currency": "USD"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                BASE + "/api/v1/purchase-orders",
                json={"po_number": po, "amount": "100", "currency": "USD"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                BASE + "/api/v1/purchase-orders",
                json={"po_number": "bad", "amount": "-1", "currency": "USD"},
            ).status_code
            == 422
        )

        def upload(amount="101.50", currency="USD", po_number=po):
            pdf = make_pdf(
                [
                    "Vendor: Test Vendor",
                    "Invoice #: INV-" + uuid.uuid4().hex[:8],
                    f"PO Number: {po_number}",
                    f"Total Amount: ${amount}",
                    f"Currency: {currency}",
                ]
            )
            r = client.post(
                BASE + "/api/v1/ingest/upload",
                files={"file": ("invoice.pdf", pdf, "application/pdf")},
            )
            assert r.status_code == 202, r.text
            invoice_id = r.json()["request_id"]
            ids.append(invoice_id)
            return invoice_id

        approved = upload()
        record = wait_status(client, approved)
        assert record["fields"]["total_amount"] == "101.50", record
        assert record["fields"]["extraction_method"] == "local_text_pdf"
        assert record["match_result"]["matched_status"] == "AUTO_APPROVED"
        review_id = upload("120")
        assert (
            wait_status(client, review_id)["match_result"]["matched_status"]
            == "NEEDS_REVIEW"
        )
        reject_id = upload("100", "EUR")
        assert (
            wait_status(client, reject_id)["match_result"]["matched_status"]
            == "NEEDS_REVIEW"
        )
        assert (
            wait_status(client, upload(po_number="PO-MISSING"))["match_result"][
                "matched_status"
            ]
            == "NEEDS_REVIEW"
        )
        r = client.post(
            BASE + "/api/v1/ingest/upload",
            files={"file": ("broken.pdf", b"%PDF-1.4\nbroken", "application/pdf")},
        )
        assert r.status_code == 202
        broken = r.json()["request_id"]
        assert wait_status(client, broken, "FAILED")["error"]
        asyncio.run(replay(approved))
        time.sleep(1)
        assert wait_status(client, approved)["match_result"] == record["match_result"]
        asyncio.run(verify_database(ids, approved))
        queue = client.get(BASE + "/api/v1/review/queue?page=1&page_size=1")
        assert queue.status_code == 200, queue.text
        assert queue.json()["total"] >= 3 and len(queue.json()["items"]) == 1
        assert (
            client.get(BASE + "/api/v1/review/queue?sort_by=sql_injection").status_code
            == 400
        )
        assert (
            client.get(BASE + "/api/v1/review/" + review_id).json()["matched_status"]
            == "NEEDS_REVIEW"
        )
        pdf = client.get(BASE + "/api/v1/review/" + review_id + "/document")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
        assert (
            client.post(
                BASE + "/api/v1/review/" + reject_id + "/reject",
                json={"reviewed_by": "forged", "review_notes": ""},
            ).status_code
            == 422
        )
        approved_review = client.post(
            BASE + "/api/v1/review/" + review_id + "/approve",
            json={"reviewed_by": "forged", "review_notes": "Verified purchase order"},
        )
        assert approved_review.status_code == 200, approved_review.text
        assert approved_review.json()["reviewed_by"] == credentials["email"]
        assert (
            client.post(
                BASE + "/api/v1/review/" + review_id + "/approve",
                json={"reviewed_by": "forged"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                BASE + "/api/v1/review/" + reject_id + "/reject",
                json={"reviewed_by": "forged", "review_notes": "Currency mismatch"},
            ).status_code
            == 200
        )
        assert (
            client.get(BASE + "/api/v1/review/" + review_id).json()["matched_status"]
            == "APPROVED"
        )
        assert (
            client.get(BASE + "/api/v1/review/" + reject_id).json()["matched_status"]
            == "REJECTED"
        )
        if with_restart:
            # Stop workers: ingestion persists accepted work and the durable broker holds it.
            compose("stop", "extract", "match")
            queued = upload()
            time.sleep(1)
            assert (
                client.get(BASE + "/api/v1/ingest/status/" + queued).json()["status"]
                == "PENDING"
            )
            compose("start", "extract", "match")
            assert (
                wait_status(client, queued)["match_result"]["matched_status"]
                == "AUTO_APPROVED"
            )
            # Stop broker: HTTP upload still atomically persists invoice plus outbox.
            compose("stop", "rabbitmq")
            queued = upload()
            time.sleep(1)
            assert client.get(BASE + "/health/ready").status_code == 503
            assert (
                client.get(BASE + "/api/v1/ingest/status/" + queued).json()["status"]
                == "PENDING"
            )
            compose("start", "rabbitmq")
            assert (
                wait_status(client, queued)["match_result"]["matched_status"]
                == "AUTO_APPROVED"
            )
            # Restart all application roles and the DB: committed invoice remains queryable.
            compose("stop", "ingest", "extract", "match")
            compose("restart", "postgres")
            compose("up", "-d", "--wait", "--wait-timeout", "120")
            wait_ready(client)
            persisted = wait_status(client, approved)
            assert (
                persisted["fields"] == record["fields"]
                and persisted["match_result"] == record["match_result"]
            )
            asyncio.run(verify_database(ids, approved))
            assert client.get(BASE + "/auth/me").json()["email"] == credentials["email"]
            assert (
                client.get(BASE + "/api/v1/review/" + review_id).json()[
                    "matched_status"
                ]
                == "APPROVED"
            )
        assert client.post(BASE + "/auth/logout", json={}).status_code == 200
        assert client.get(BASE + "/auth/me").status_code == 401
        print(
            "PASS: actual PDF text → durable RabbitMQ → decimal PO match → PostgreSQL; failure paths, redelivery and outage/restart persistence"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()
    run(not args.no_restart)
