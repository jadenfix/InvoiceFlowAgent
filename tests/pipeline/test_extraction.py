from decimal import Decimal
import pytest
from services.pipeline.extraction import extract_fields, match_amount


def test_variance_boundary_and_currency_mismatch():
    assert match_amount("102", "100", "USD", "USD")["matched_status"] == "AUTO_APPROVED"
    assert (
        match_amount("102.01", "100", "USD", "USD")["matched_status"] == "NEEDS_REVIEW"
    )
    assert match_amount("100", "100", "EUR", "USD")["matched_status"] == "NEEDS_REVIEW"
    assert match_amount("98", "100", "USD", "USD")["variance_pct"] == "0.02"


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity"])
def test_invalid_amount_rejected(amount):
    with pytest.raises(ValueError):
        match_amount(amount, "100", "USD", "USD")


def test_invalid_pdf_never_returns_success():
    with pytest.raises(ValueError, match="Cannot read"):
        extract_fields(b"%PDF-broken")


def test_real_pdf_roundtrip_and_optional_calendar_date():
    from scripts.check_pipeline_http import make_pdf

    fields = extract_fields(
        make_pdf(
            [
                "Vendor: Real PDF Vendor",
                "Invoice #: INV-2026",
                "Total Amount: $123.45",
                "Currency: USD",
                "PO Number: PO-2026",
                "Date: 2026-10-13",
            ]
        )
    )
    assert fields["total_amount"] == "123.45"
    assert fields["invoice_date"] == "2026-10-13"
    assert fields["po_number"] == "PO-2026"
    assert fields["provider_used"] is False


@pytest.mark.parametrize("extra", ["Total Amount: $999.00", "Date: tomorrow"])
def test_ambiguous_total_or_invalid_date_fails(extra):
    from scripts.check_pipeline_http import make_pdf

    with pytest.raises(ValueError):
        extract_fields(
            make_pdf(
                [
                    "Vendor: Test",
                    "Invoice #: INV-1",
                    "Total Amount: $100.00",
                    "Currency: USD",
                    extra,
                ]
            )
        )
