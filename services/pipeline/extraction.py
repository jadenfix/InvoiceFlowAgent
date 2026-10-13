"""Local text-PDF extraction. This parser never pretends to call an AI provider."""

import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from pypdf import PdfReader


def extract_fields(content: bytes) -> dict:
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are unsupported")
        if not 1 <= len(reader.pages) <= 20:
            raise ValueError("PDF must have between 1 and 20 pages")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise ValueError("Cannot read text from this PDF") from error
    if not text.strip():
        raise ValueError(
            "No embedded PDF text; scanned PDFs require a configured OCR provider"
        )

    def field(pattern: str, required: bool = False):
        matches = re.findall(pattern, text, flags=re.I | re.M)
        values = list(dict.fromkeys(value.strip() for value in matches))
        if len(values) > 1:
            raise ValueError("Ambiguous invoice field: multiple different values")
        if not values:
            if required:
                raise ValueError("Missing required invoice field")
            return None
        return values[0]

    total = field(r"^\s*Total(?: Amount)?\s*:\s*\$?([\d,]+(?:\.\d{1,2})?)\s*$", True)
    try:
        amount = Decimal(total.replace(",", ""))
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Total must be positive")
    except InvalidOperation as error:
        raise ValueError("Invalid total amount") from error
    currency = field(r"^\s*Currency\s*:\s*([A-Z]{3})\s*$", True).upper()
    invoice_date = field(r"^\s*(?:Invoice Date|Date)\s*:\s*(\S+)\s*$")
    if invoice_date:
        try:
            invoice_date = date.fromisoformat(invoice_date).isoformat()
        except ValueError as error:
            raise ValueError("Invoice date must be ISO YYYY-MM-DD") from error
    return {
        "invoice_date": invoice_date,
        "vendor_name": field(r"^\s*Vendor\s*:\s*(.+)$", True),
        "invoice_number": field(r"^\s*Invoice(?: Number| #|#)?\s*:\s*(\S+)\s*$", True),
        "total_amount": str(amount),
        "currency": currency,
        "po_number": field(r"^\s*PO(?: Number)?\s*:\s*(\S+)\s*$"),
        "extraction_method": "local_text_pdf",
        "provider_used": False,
    }


def match_amount(
    invoice_amount, po_amount, currency, po_currency, tolerance=Decimal("0.02")
):
    """Use the project's 2% PO variance rule with decimal arithmetic."""
    amount, expected = Decimal(str(invoice_amount)), Decimal(str(po_amount))
    if (
        not expected.is_finite()
        or not amount.is_finite()
        or expected <= 0
        or amount <= 0
    ):
        raise ValueError("Amounts must be finite and positive")
    variance = abs(amount - expected) / expected
    return {
        "matched_status": (
            "AUTO_APPROVED"
            if currency == po_currency and variance <= tolerance
            else "NEEDS_REVIEW"
        ),
        "variance_pct": str(variance),
        "po_amount": str(expected),
        "invoice_amount": str(amount),
        "currency_match": currency == po_currency,
    }
