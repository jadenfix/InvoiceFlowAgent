"""
Normalizer service for parsing PDFs and JSON into structured invoice data
"""
import json
import re
import time
from typing import Optional, Dict, Any, List
from decimal import Decimal, InvalidOperation
from datetime import datetime
from io import BytesIO
from pathlib import Path

import PyPDF2
import pdfplumber
import pytesseract
from PIL import Image

from ..core.config import settings
from ..core.logging import get_logger, log_function_call, log_function_result, log_error
from ..models.invoice import InvoiceData, InvoiceLineItem, ProcessingResult


logger = get_logger(__name__)


class PDFParser:
    """PDF parser with OCR fallback support"""
    
    def __init__(self):
        self.ocr_enabled = settings.OCR_ENABLED
    
    async def parse_pdf(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Parse PDF content and extract text"""
        log_function_call("PDFParser.parse_pdf", filename=filename, size=len(content))
        start_time = time.time()
        
        extracted_text = ""
        ocr_used = False
        
        try:
            # First try with pdfplumber for better text extraction
            extracted_text = await self._extract_with_pdfplumber(content)
            
            # If no text found and OCR is enabled, try OCR
            if not extracted_text.strip() and self.ocr_enabled:
                logger.info(f"No text found in {filename}, attempting OCR")
                extracted_text = await self._extract_with_ocr(content)
                ocr_used = True
            
            # Fallback to PyPDF2 if still no text
            if not extracted_text.strip():
                extracted_text = await self._extract_with_pypdf2(content)
            
            result = {
                "text": extracted_text,
                "ocr_used": ocr_used,
                "word_count": len(extracted_text.split()),
                "char_count": len(extracted_text)
            }
            
            return result
            
        except Exception as e:
            log_error(e, {"filename": filename, "size": len(content)})
            raise
        finally:
            log_function_result("PDFParser.parse_pdf", 
                              len(extracted_text), time.time() - start_time)
    
    async def _extract_with_pdfplumber(self, content: bytes) -> str:
        """Extract text using pdfplumber"""
        try:
            text_parts = []
            with pdfplumber.open(BytesIO(content)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"pdfplumber extraction failed: {e}")
            return ""
    
    async def _extract_with_pypdf2(self, content: bytes) -> str:
        """Extract text using PyPDF2"""
        try:
            text_parts = []
            pdf_reader = PyPDF2.PdfReader(BytesIO(content))
            
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"PyPDF2 extraction failed: {e}")
            return ""
    
    async def _extract_with_ocr(self, content: bytes) -> str:
        """Extract text using OCR"""
        try:
            # Convert PDF to images and run OCR
            # This is a simplified implementation
            # In production, you'd want to use pdf2image
            # For now, we'll return a placeholder
            logger.warning("OCR extraction not fully implemented")
            return ""
        except Exception as e:
            logger.debug(f"OCR extraction failed: {e}")
            return ""


class JSONParser:
    """JSON parser for structured invoice data"""
    
    async def parse_json(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Parse JSON content"""
        log_function_call("JSONParser.parse_json", filename=filename, size=len(content))
        start_time = time.time()
        
        try:
            # Decode and parse JSON
            text_content = content.decode('utf-8')
            data = json.loads(text_content)
            
            # Validate it's a dictionary
            if not isinstance(data, dict):
                raise ValueError("JSON must contain an object, not an array or primitive")
            
            result = {
                "data": data,
                "keys": list(data.keys()),
                "nested_keys": self._get_nested_keys(data),
                "size": len(text_content)
            }
            
            return result
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid text encoding: {e}")
        except Exception as e:
            log_error(e, {"filename": filename})
            raise
        finally:
            log_function_result("JSONParser.parse_json", 
                              len(data) if 'data' in locals() else 0, 
                              time.time() - start_time)
    
    def _get_nested_keys(self, data: Dict[str, Any], prefix: str = "") -> List[str]:
        """Get all nested keys from dictionary"""
        keys = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.append(full_key)
            
            if isinstance(value, dict):
                keys.extend(self._get_nested_keys(value, full_key))
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                keys.extend(self._get_nested_keys(value[0], f"{full_key}[0]"))
        
        return keys


class InvoiceExtractor:
    """Extract structured invoice data from text or JSON"""
    
    def __init__(self):
        self.patterns = {
            'invoice_id': [
                r'invoice\s*(?:number|#|id)[:]\s*([A-Z0-9-]+)',
                r'inv\s*(?:number|#|id)[:]\s*([A-Z0-9-]+)',
                r'bill\s*(?:number|#|id)[:]\s*([A-Z0-9-]+)',
            ],
            'amount': [
                r'total[:]\s*\$?([0-9,]+\.?[0-9]*)',
                r'amount[:]\s*\$?([0-9,]+\.?[0-9]*)',
                r'due[:]\s*\$?([0-9,]+\.?[0-9]*)',
                r'\$([0-9,]+\.?[0-9]*)',
            ],
            'date': [
                r'date[:]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})',
                r'date[:]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})',
                r'invoice\s*date[:]\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})',
            ],
            'vendor': [
                r'from[:]\s*([A-Za-z\s]+)',
                r'vendor[:]\s*([A-Za-z\s]+)',
                r'billed\s*by[:]\s*([A-Za-z\s]+)',
            ]
        }
    
    async def extract_from_text(self, text: str, metadata: Dict[str, Any]) -> InvoiceData:
        """Extract invoice data from text"""
        log_function_call("InvoiceExtractor.extract_from_text", 
                         text_length=len(text))
        
        try:
            # Extract basic fields using regex patterns
            invoice_id = self._extract_field(text, 'invoice_id') or f"unknown_{int(time.time())}"
            vendor = self._extract_field(text, 'vendor') or "Unknown Vendor"
            
            # Extract and parse amount
            amount_str = self._extract_field(text, 'amount')
            if amount_str:
                amount = Decimal(amount_str.replace(',', ''))
            else:
                raise ValueError("Could not extract invoice amount")
            
            # Extract and parse date
            date_str = self._extract_field(text, 'date')
            if date_str:
                invoice_date = self._parse_date(date_str)
            else:
                # Use current date as fallback
                invoice_date = datetime.now()
                logger.warning("Could not extract invoice date, using current date")
            
            # Extract line items (simplified)
            line_items = self._extract_line_items(text)
            
            invoice_data = InvoiceData(
                invoice_id=invoice_id,
                vendor=vendor.strip(),
                date=invoice_date,
                amount=amount,
                line_items=line_items
            )
            
            return invoice_data
            
        except Exception as e:
            log_error(e, {"text_length": len(text)})
            raise
    
    async def extract_from_json(self, data: Dict[str, Any], metadata: Dict[str, Any]) -> InvoiceData:
        """Extract invoice data from JSON"""
        log_function_call("InvoiceExtractor.extract_from_json", 
                         keys=list(data.keys()))
        
        try:
            # Map common JSON field names to our schema
            field_mappings = {
                'invoice_id': ['invoice_id', 'invoiceId', 'invoice_number', 'number', 'id'],
                'vendor': ['vendor', 'company', 'supplier', 'from', 'seller'],
                'amount': ['amount', 'total', 'total_amount', 'grand_total'],
                'date': ['date', 'invoice_date', 'created_date', 'issued_date'],
                'line_items': ['line_items', 'items', 'details', 'products']
            }
            
            # Extract required fields
            invoice_id = self._get_json_field(data, field_mappings['invoice_id'])
            if not invoice_id:
                raise ValueError("Missing required field: invoice_id")
            
            vendor = self._get_json_field(data, field_mappings['vendor'])
            if not vendor:
                raise ValueError("Missing required field: vendor")
            
            amount = self._get_json_field(data, field_mappings['amount'])
            if amount is None:
                raise ValueError("Missing required field: amount")
            amount = Decimal(str(amount))
            
            date_value = self._get_json_field(data, field_mappings['date'])
            if date_value:
                if isinstance(date_value, str):
                    invoice_date = self._parse_date(date_value)
                else:
                    invoice_date = datetime.fromtimestamp(date_value)
            else:
                invoice_date = datetime.now()
                logger.warning("Missing invoice date in JSON, using current date")
            
            # Extract line items
            line_items_data = self._get_json_field(data, field_mappings['line_items']) or []
            line_items = []
            
            for item_data in line_items_data:
                if isinstance(item_data, dict):
                    try:
                        line_item = InvoiceLineItem(
                            description=item_data.get('description', 'Unknown item'),
                            quantity=Decimal(str(item_data.get('quantity', 1))),
                            unit_price=Decimal(str(item_data.get('unit_price', 0))),
                            total_price=Decimal(str(item_data.get('total_price', 0)))
                        )
                        line_items.append(line_item)
                    except (ValueError, InvalidOperation) as e:
                        logger.warning(f"Invalid line item data: {e}")
                        continue
            
            invoice_data = InvoiceData(
                invoice_id=str(invoice_id),
                vendor=str(vendor),
                date=invoice_date,
                amount=amount,
                line_items=line_items
            )
            
            return invoice_data
            
        except Exception as e:
            log_error(e, {"json_keys": list(data.keys())})
            raise
    
    def _extract_field(self, text: str, field_type: str) -> Optional[str]:
        """Extract field using regex patterns"""
        patterns = self.patterns.get(field_type, [])
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_line_items(self, text: str) -> List[InvoiceLineItem]:
        """Extract line items from text (simplified implementation)"""
        # This is a simplified implementation
        # In production, you'd want more sophisticated parsing
        line_items = []
        
        # Look for patterns like "Description $amount"
        item_pattern = r'([A-Za-z\s]+)\s+\$([0-9,]+\.?[0-9]*)'
        matches = re.findall(item_pattern, text)
        
        for description, price_str in matches:
            try:
                price = Decimal(price_str.replace(',', ''))
                line_item = InvoiceLineItem(
                    description=description.strip(),
                    quantity=Decimal('1'),
                    unit_price=price,
                    total_price=price
                )
                line_items.append(line_item)
            except (ValueError, InvalidOperation):
                continue
        
        return line_items
    
    def _get_json_field(self, data: Dict[str, Any], field_names: List[str]) -> Any:
        """Get field from JSON data using multiple possible field names"""
        for field_name in field_names:
            if field_name in data:
                return data[field_name]
        return None
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        date_formats = [
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%B %d, %Y',
            '%d %B %Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}")


class InvoiceNormalizer:
    """Main normalizer service that coordinates parsing and extraction"""
    
    def __init__(self):
        self.pdf_parser = PDFParser()
        self.json_parser = JSONParser()
        self.extractor = InvoiceExtractor()
    
    async def normalize_file(self, content: bytes, filename: str, 
                           metadata: Dict[str, Any]) -> ProcessingResult:
        """Normalize a file into structured invoice data"""
        log_function_call("InvoiceNormalizer.normalize_file", 
                         filename=filename, size=len(content))
        start_time = time.time()
        
        errors = []
        warnings = []
        invoice_data = None
        ocr_used = False
        
        try:
            file_extension = Path(filename).suffix.lower()
            
            if file_extension == '.json':
                # Parse JSON file
                parsed_data = await self.json_parser.parse_json(content, filename)
                invoice_data = await self.extractor.extract_from_json(
                    parsed_data['data'], metadata
                )
                
            elif file_extension == '.pdf':
                # Parse PDF file
                parsed_data = await self.pdf_parser.parse_pdf(content, filename)
                ocr_used = parsed_data['ocr_used']
                
                if not parsed_data['text'].strip():
                    raise ValueError("No text could be extracted from PDF")
                
                invoice_data = await self.extractor.extract_from_text(
                    parsed_data['text'], metadata
                )
                
            else:
                raise ValueError(f"Unsupported file type: {file_extension}")
            
            # Validate the extracted data
            validation_errors = self._validate_invoice_data(invoice_data)
            if validation_errors:
                errors.extend(validation_errors)
                invoice_data = None
            
            success = invoice_data is not None and not errors
            
            result = ProcessingResult(
                success=success,
                invoice_data=invoice_data,
                errors=errors,
                warnings=warnings,
                processing_time=time.time() - start_time,
                file_size=len(content),
                ocr_used=ocr_used
            )
            
            return result
            
        except Exception as e:
            errors.append(str(e))
            log_error(e, {"filename": filename})
            
            return ProcessingResult(
                success=False,
                invoice_data=None,
                errors=errors,
                warnings=warnings,
                processing_time=time.time() - start_time,
                file_size=len(content),
                ocr_used=ocr_used
            )
        finally:
            log_function_result("InvoiceNormalizer.normalize_file", 
                              success if 'success' in locals() else False, 
                              time.time() - start_time)
    
    def _validate_invoice_data(self, invoice_data: InvoiceData) -> List[str]:
        """Validate invoice data for required fields and constraints"""
        errors = []
        
        # Check required fields
        if not invoice_data.invoice_id or invoice_data.invoice_id.strip() == "":
            errors.append("Missing or empty invoice_id")
        
        if not invoice_data.vendor or invoice_data.vendor.strip() == "":
            errors.append("Missing or empty vendor")
        
        if invoice_data.amount <= 0:
            errors.append("Invoice amount must be greater than 0")
        
        # Validate date is not too far in the future
        future_limit = datetime.now().replace(year=datetime.now().year + 1)
        if invoice_data.date > future_limit:
            errors.append("Invoice date is too far in the future")
        
        # Validate line items if present
        if invoice_data.line_items:
            for i, item in enumerate(invoice_data.line_items):
                if item.quantity <= 0:
                    errors.append(f"Line item {i+1}: quantity must be greater than 0")
                if item.unit_price < 0:
                    errors.append(f"Line item {i+1}: unit_price cannot be negative")
                if item.total_price < 0:
                    errors.append(f"Line item {i+1}: total_price cannot be negative")
        
        return errors


# Global normalizer instance
normalizer = InvoiceNormalizer() 