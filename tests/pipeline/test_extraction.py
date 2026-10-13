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
