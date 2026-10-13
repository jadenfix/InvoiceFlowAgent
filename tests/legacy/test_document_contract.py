"""Real PDF bytes through the shared parser; no OCR/AI or provider mocks."""

import io
from decimal import Decimal

import pytest
from pypdf import PdfReader, PdfWriter

from scripts.check_pipeline_http import make_pdf
from services.pipeline.extraction import extract_fields, match_amount


def invoice_lines(total="995.00", po="PO-REAL"):
    lines = [
        "Vendor: Document Vendor",
        "Invoice #: INV-DOCUMENT",
        f"Total: {total}",
        "Currency: USD",
        "Date: 2026-10-13",
    ]
    if po:
        lines.append(f"PO: {po}")
    return lines


@pytest.mark.parametrize(
    "total,expected", [("995.00", "AUTO_APPROVED"), ("2500.00", "NEEDS_REVIEW")]
)
def test_decision_is_derived_from_actual_pdf_not_upload_metadata(total, expected):
    # Embedded PDF metadata deliberately contradicts its document content.
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(make_pdf(invoice_lines(total)))))
    writer.add_metadata({"/total_amount": "1.00", "/po_number": "PO-FORGED"})
    output = io.BytesIO()
    writer.write(output)
    fields = extract_fields(output.getvalue())
    assert fields["total_amount"] == total
    assert fields["po_number"] == "PO-REAL"
    assert fields["vendor_name"] == "Document Vendor"
    assert fields["invoice_date"] == "2026-10-13"
    assert fields["extraction_method"] == "local_text_pdf"
    assert fields["provider_used"] is False
    result = match_amount(fields["total_amount"], "1000.00", fields["currency"], "USD")
    assert result["matched_status"] == expected
    assert Decimal(result["invoice_amount"]) == Decimal(total)


def test_document_without_po_does_not_invent_one():
    assert extract_fields(make_pdf(invoice_lines(po=None)))["po_number"] is None


@pytest.mark.parametrize(
    "total",
    ["9,9,5.00", "1,,000.00", "1000,00", "0.00", "-5.00", "NaN", "Infinity", "12.345"],
)
def test_invalid_document_totals_fail_closed(total):
    with pytest.raises(ValueError):
        extract_fields(make_pdf(invoice_lines(total)))


def test_valid_grouped_total_preserves_exact_cents():
    fields = extract_fields(make_pdf(invoice_lines("1,000.01")))
    assert fields["total_amount"] == "1000.01"


@pytest.mark.parametrize(
    "extra",
    [
        "Vendor: Other Vendor",
        "Invoice #: OTHER",
        "Total: 1.00",
        "Currency: EUR",
        "PO: OTHER",
    ],
)
def test_conflicting_document_fields_are_rejected(extra):
    with pytest.raises(ValueError, match="Ambiguous"):
        extract_fields(make_pdf(invoice_lines() + [extra]))


@pytest.mark.parametrize("missing", ["Vendor:", "Invoice #:", "Total:", "Currency:"])
def test_required_document_field_cannot_be_supplied_by_metadata(missing):
    with pytest.raises(ValueError):
        extract_fields(
            make_pdf([line for line in invoice_lines() if not line.startswith(missing)])
        )


def test_blank_pdf_requires_unimplemented_ocr_instead_of_reporting_success():
    with pytest.raises(ValueError, match="No embedded PDF text"):
        extract_fields(make_pdf([]))


def test_encrypted_and_excessive_page_documents_are_rejected():
    for encrypted in (False, True):
        writer = PdfWriter()
        for _ in range(1 if encrypted else 21):
            writer.add_blank_page(width=612, height=792)
        if encrypted:
            writer.encrypt("private")
        output = io.BytesIO()
        writer.write(output)
        with pytest.raises(ValueError):
            extract_fields(output.getvalue())


@pytest.mark.parametrize("role", ["ingest", "extract"])
def test_documented_service_directory_cli_uses_canonical_pipeline(role):
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ, EXTRACTION_MODE="local_text")
    code = (
        "from app.main import app; "
        f"assert app.title == 'InvoiceFlow {role} pipeline'; "
        "assert app.state.pipeline.pool is None; "
        "assert '/health/ready' in [route.path for route in app.routes]"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root / "services" / role,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    environment["EXTRACTION_MODE"] = "textract"
    unsupported = subprocess.run(
        [sys.executable, "-c", "from app.main import app"],
        cwd=root / "services" / role,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert unsupported.returncode != 0
    assert "Only EXTRACTION_MODE=local_text is supported" in unsupported.stderr


def test_legacy_router_is_the_real_application_router():
    from services.ingest.app.main import app
    from services.ingest.app.api.ingest import router

    assert router is app.router
    paths = {route.path for route in router.routes}
    assert {
        "/api/v1/ingest/upload",
        "/api/v1/ingest/status/{request_id}",
        "/api/v1/ingest/stats",
    } <= paths


@pytest.mark.parametrize(
    "malformed", ["9,9,5.00", "1,,000.00", "1000,00", "not-an-amount"]
)
def test_malformed_second_total_cannot_be_ignored(malformed):
    with pytest.raises(ValueError):
        extract_fields(make_pdf(invoice_lines() + [f"Total Amount: {malformed}"]))
