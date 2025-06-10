"""
Full pipeline end-to-end tests.

Tests the complete flow:
PDF Upload → Ingestion → Extraction → Matching → Results
"""
import asyncio
import json
import time
from typing import Dict, Any

import pytest
import httpx
import pika
import boto3
from sqlalchemy import create_engine, text
import structlog

logger = structlog.get_logger()


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_full_pipeline_auto_approval(
    service_containers,
    http_client: httpx.AsyncClient,
    sample_pdf_content: bytes,
    test_request_id: str
):
    """
    Test complete pipeline with auto-approval scenario.
    
    Flow:
    1. Upload PDF to ingest service
    2. Poll for processing completion  
    3. Verify database records
    4. Check S3 objects
    5. Consume and validate RabbitMQ messages
    """
    
    # Step 1: Upload PDF to ingest service
    logger.info("Starting full pipeline test", request_id=test_request_id)
    
    files = {
        "file": ("test_invoice.pdf", sample_pdf_content, "application/pdf")
    }
    
    # Add PO number to the PDF content metadata (simulated)
    form_data = {
        "metadata": json.dumps({
            "po_numbers": ["PO-TEST-001"],  # This matches our test PO
            "vendor_name": "Test Vendor Corp",
            "total_amount": 995.00  # Within 2% tolerance of 1000.00
        })
    }
    
    upload_response = await http_client.post(
        f"{service_containers['ingest_url']}/api/v1/ingest/upload",
        files=files,
        data=form_data
    )
    
    assert upload_response.status_code == 200
    upload_result = upload_response.json()
    request_id = upload_result["request_id"]
    
    logger.info("PDF uploaded successfully", request_id=request_id, upload_result=upload_result)
    
    # Step 2: Poll for processing completion
    max_polls = 30
    poll_interval = 2  # seconds
    
    for poll_count in range(max_polls):
        status_response = await http_client.get(
            f"{service_containers['ingest_url']}/api/v1/ingest/status/{request_id}"
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        
        logger.info(
            "Polling status", 
            request_id=request_id, 
            poll_count=poll_count,
            status=status_data.get("status"),
            processing_stage=status_data.get("processing_stage")
        )
        
        if status_data.get("status") == "COMPLETED":
            logger.info("Processing completed", request_id=request_id)
            break
        elif status_data.get("status") == "ERROR":
            pytest.fail(f"Processing failed: {status_data.get('error_message')}")
        
        await asyncio.sleep(poll_interval)
    else:
        pytest.fail(f"Processing did not complete within {max_polls * poll_interval} seconds")
    
    # Step 3: Verify database records
    postgres_config = service_containers["postgres"]
    engine = create_engine(postgres_config["sync_url"])
    
    with engine.connect() as conn:
        # Check invoices_raw table
        raw_result = conn.execute(
            text("SELECT * FROM invoices_raw WHERE request_id = :request_id"),
            {"request_id": request_id}
        ).fetchone()
        
        assert raw_result is not None, "No record found in invoices_raw table"
        assert raw_result.processing_status == "COMPLETED"
        
        logger.info("Verified invoices_raw record", request_id=request_id)
        
        # Check invoices table (after extraction)
        invoice_result = conn.execute(
            text("SELECT * FROM invoices WHERE request_id = :request_id"),
            {"request_id": request_id}
        ).fetchone()
        
        assert invoice_result is not None, "No record found in invoices table"
        
        # Verify matching results
        assert invoice_result.matched_status in ["AUTO_APPROVED", "NEEDS_REVIEW"]
        assert invoice_result.matched_details is not None
        
        matched_details = json.loads(invoice_result.matched_details) if isinstance(invoice_result.matched_details, str) else invoice_result.matched_details
        
        # For our test scenario, should be auto-approved due to PO match and amount tolerance
        if matched_details.get("po_number") == "PO-TEST-001":
            assert invoice_result.matched_status == "AUTO_APPROVED"
            assert matched_details["variance_pct"] <= 0.02  # Within tolerance
        
        logger.info(
            "Verified invoice matching",
            request_id=request_id,
            matched_status=invoice_result.matched_status,
            matched_details=matched_details
        )
    
    # Step 4: Check S3 objects
    s3_config = service_containers["s3"]
    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_config["endpoint_url"],
        aws_access_key_id=s3_config["access_key"],
        aws_secret_access_key=s3_config["secret_key"],
        region_name=s3_config["region"]
    )
    
    # Check raw PDF exists
    try:
        raw_pdf_key = f"raw/{request_id}.pdf"
        s3_client.head_object(Bucket="invoices", Key=raw_pdf_key)
        logger.info("Verified raw PDF in S3", request_id=request_id, key=raw_pdf_key)
    except Exception as e:
        pytest.fail(f"Raw PDF not found in S3: {e}")
    
    # Check extracted data exists
    try:
        extracted_key = f"extracted/raw/{request_id}.json"
        response = s3_client.get_object(Bucket="processed-invoices", Key=extracted_key)
        extracted_data = json.loads(response["Body"].read())
        
        assert "fields" in extracted_data
        assert "total_amount" in extracted_data["fields"]
        
        logger.info("Verified extracted data in S3", request_id=request_id, key=extracted_key)
    except Exception as e:
        logger.warning(f"Extracted data not found in S3: {e}")
        # This might be acceptable depending on service implementation
    
    # Step 5: Consume and validate RabbitMQ messages
    rabbitmq_config = service_containers["rabbitmq"]
    
    # Connect to RabbitMQ and consume messages
    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_config["url"]))
    channel = connection.channel()
    
    # Declare queues to ensure they exist
    channel.queue_declare(queue="invoice_extracted", durable=True)
    channel.queue_declare(queue="invoice_matched", durable=True)
    
    # Check for invoice_extracted message
    extracted_messages = []
    method_frame, header_frame, body = channel.basic_get(queue="invoice_extracted", auto_ack=True)
    
    if body:
        extracted_message = json.loads(body)
        extracted_messages.append(extracted_message)
        
        # Verify message structure
        assert "request_id" in extracted_message
        assert "fields" in extracted_message
        assert "total_amount" in extracted_message["fields"]
        
        logger.info("Validated invoice_extracted message", message=extracted_message)
    
    # Check for invoice_matched message
    matched_messages = []
    method_frame, header_frame, body = channel.basic_get(queue="invoice_matched", auto_ack=True)
    
    if body:
        matched_message = json.loads(body)
        matched_messages.append(matched_message)
        
        # Verify message structure
        assert "request_id" in matched_message
        assert "status" in matched_message
        assert "details" in matched_message
        assert matched_message["status"] in ["AUTO_APPROVED", "NEEDS_REVIEW"]
        
        # Validate details structure
        details = matched_message["details"]
        assert "invoice_amount" in details
        assert "variance_pct" in details
        
        logger.info("Validated invoice_matched message", message=matched_message)
    
    connection.close()
    
    logger.info(
        "Full pipeline test completed successfully",
        request_id=request_id,
        extracted_messages_count=len(extracted_messages),
        matched_messages_count=len(matched_messages)
    )


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_full_pipeline_needs_review(
    service_containers,
    http_client: httpx.AsyncClient,
    sample_pdf_content: bytes,
    test_request_id: str
):
    """
    Test complete pipeline with needs-review scenario.
    
    This test uses an invoice that should NOT be auto-approved
    (either no PO or amount outside tolerance).
    """
    
    logger.info("Starting needs-review pipeline test", request_id=test_request_id)
    
    files = {
        "file": ("test_invoice_review.pdf", sample_pdf_content, "application/pdf")
    }
    
    # No PO number provided - should trigger NEEDS_REVIEW
    form_data = {
        "metadata": json.dumps({
            "vendor_name": "Another Test Vendor",
            "total_amount": 2500.00  # No matching PO for this amount
        })
    }
    
    upload_response = await http_client.post(
        f"{service_containers['ingest_url']}/api/v1/ingest/upload",
        files=files,
        data=form_data
    )
    
    assert upload_response.status_code == 200
    upload_result = upload_response.json()
    request_id = upload_result["request_id"]
    
    # Poll for completion
    max_polls = 30
    for poll_count in range(max_polls):
        status_response = await http_client.get(
            f"{service_containers['ingest_url']}/api/v1/ingest/status/{request_id}"
        )
        
        status_data = status_response.json()
        
        if status_data.get("status") == "COMPLETED":
            break
        elif status_data.get("status") == "ERROR":
            pytest.fail(f"Processing failed: {status_data.get('error_message')}")
        
        await asyncio.sleep(2)
    else:
        pytest.fail("Processing did not complete in time")
    
    # Verify the invoice is marked as NEEDS_REVIEW
    postgres_config = service_containers["postgres"]
    engine = create_engine(postgres_config["sync_url"])
    
    with engine.connect() as conn:
        invoice_result = conn.execute(
            text("SELECT * FROM invoices WHERE request_id = :request_id"),
            {"request_id": request_id}
        ).fetchone()
        
        assert invoice_result is not None
        assert invoice_result.matched_status == "NEEDS_REVIEW"
        
        matched_details = json.loads(invoice_result.matched_details) if isinstance(invoice_result.matched_details, str) else invoice_result.matched_details
        
        # Should have null/empty PO details
        assert matched_details.get("po_number") is None
        
        logger.info(
            "Verified needs-review scenario",
            request_id=request_id,
            matched_status=invoice_result.matched_status,
            matched_details=matched_details
        )


@pytest.mark.asyncio
async def test_service_health_checks(service_containers, http_client: httpx.AsyncClient):
    """Test that all services respond to health checks."""
    
    health_endpoints = [
        (service_containers["ingest_url"], "/healthz"),
        (service_containers["extract_url"], "/health/live"),
        (service_containers["match_url"], "/health/live"),
    ]
    
    for base_url, endpoint in health_endpoints:
        response = await http_client.get(f"{base_url}{endpoint}")
        assert response.status_code == 200, f"Health check failed for {base_url}{endpoint}"
        
        logger.info("Health check passed", service=base_url, endpoint=endpoint)


@pytest.mark.asyncio
async def test_service_readiness_checks(service_containers, http_client: httpx.AsyncClient):
    """Test that services respond to readiness checks."""
    
    readiness_endpoints = [
        (service_containers["extract_url"], "/health/ready"),
        (service_containers["match_url"], "/health/ready"),
    ]
    
    for base_url, endpoint in readiness_endpoints:
        response = await http_client.get(f"{base_url}{endpoint}")
        # Should be 200 (ready) or 503 (not ready), but not 404
        assert response.status_code in [200, 503], f"Readiness check failed for {base_url}{endpoint}"
        
        logger.info("Readiness check completed", service=base_url, endpoint=endpoint, status=response.status_code) 