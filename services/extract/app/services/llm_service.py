"""
LLM service for structured field extraction using OpenAI GPT-4
"""
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException
from tenacity import retry, stop_after_attempt, wait_exponential
import openai

from ..core.config import settings
from ..core.logging import get_logger, log_processing_step, log_error
from ..models.invoice import InvoiceFields, LineItem


logger = get_logger(__name__)


class LLMService:
    """LLM service for structured invoice field extraction"""
    
    def __init__(self):
        self.llm = None
        self.parser = JsonOutputParser()
        self._setup_llm()
    
    def _setup_llm(self):
        """Setup LangChain LLM"""
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI API key not configured")
            return
        
        try:
            self.llm = ChatOpenAI(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
                temperature=settings.OPENAI_TEMPERATURE,
                max_tokens=settings.OPENAI_MAX_TOKENS,
                timeout=settings.OPENAI_TIMEOUT
            )
            logger.info(f"LLM initialized with model: {settings.OPENAI_MODEL}")
            
        except Exception as e:
            log_error(e, {"operation": "llm_setup"})
            self.llm = None
    
    def _get_extraction_prompt(self) -> PromptTemplate:
        """Get the prompt template for invoice field extraction"""
        
        template = """
You are an expert invoice data extraction system. Extract structured information from the following invoice text.

IMPORTANT INSTRUCTIONS:
1. Return ONLY valid JSON, no additional text or explanation
2. Use null for missing values, not empty strings
3. Dates should be in ISO format (YYYY-MM-DD) or null
4. Numbers should be numeric types, not strings
5. Line items should be an array of objects with consistent structure

INVOICE TEXT:
{invoice_text}

Extract the following fields and return as JSON:

{{
    "vendor_name": "Company name that issued the invoice",
    "invoice_number": "Invoice or reference number",
    "invoice_date": "Invoice date in YYYY-MM-DD format",
    "due_date": "Payment due date in YYYY-MM-DD format",
    "total_amount": "Total amount as number",
    "currency": "Currency code (e.g., USD, EUR)",
    "subtotal": "Subtotal before tax as number", 
    "tax_amount": "Tax amount as number",
    "po_number": "Purchase order number if present",
    "line_items": [
        {{
            "description": "Item description",
            "quantity": "Quantity as number",
            "unit_price": "Unit price as number", 
            "total_price": "Total price for this line as number",
            "sku": "SKU or item code if present"
        }}
    ]
}}

JSON:
"""
        
        return PromptTemplate(
            template=template,
            input_variables=["invoice_text"]
        )
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_DELAY_SECONDS, max=60)
    )
    async def extract_fields(self, invoice_text: str, request_id: str) -> InvoiceFields:
        """
        Extract structured fields from invoice text using LLM
        
        Args:
            invoice_text: Raw text extracted from invoice
            request_id: Request ID for logging
            
        Returns:
            InvoiceFields with extracted data
        """
        log_processing_step("llm_extraction", request_id, text_length=len(invoice_text))
        
        if not self.llm:
            logger.error(f"LLM not available for request {request_id}")
            return InvoiceFields()
        
        if not invoice_text.strip():
            logger.warning(f"Empty invoice text for request {request_id}")
            return InvoiceFields()
        
        start_time = time.time()
        
        try:
            # Create prompt
            prompt = self._get_extraction_prompt()
            
            # Create chain
            chain = prompt | self.llm | self.parser
            
            # Truncate text if too long to avoid token limits
            max_chars = 8000  # Conservative estimate for token limits
            if len(invoice_text) > max_chars:
                logger.warning(f"Truncating invoice text from {len(invoice_text)} to {max_chars} chars for request {request_id}")
                invoice_text = invoice_text[:max_chars] + "...[truncated]"
            
            # Extract fields
            result = await chain.ainvoke({"invoice_text": invoice_text})
            
            # Validate and clean the result
            cleaned_result = self._clean_extraction_result(result, request_id)
            
            # Convert to InvoiceFields
            invoice_fields = InvoiceFields(**cleaned_result)
            
            duration = time.time() - start_time
            logger.info(f"LLM extraction completed in {duration:.2f}s for request {request_id}")
            
            return invoice_fields
            
        except OutputParserException as e:
            log_error(e, {"operation": "llm_parsing", "request_id": request_id})
            logger.warning(f"Failed to parse LLM output for request {request_id}, trying manual extraction")
            
            # Try to extract JSON from the response manually
            try:
                # This is a fallback for when the LLM returns extra text
                response_text = str(e).split("Could not parse LLM output: `")[1].split("`")[0]
                if response_text.startswith('{') and response_text.endswith('}'):
                    result = json.loads(response_text)
                    cleaned_result = self._clean_extraction_result(result, request_id)
                    return InvoiceFields(**cleaned_result)
            except Exception:
                pass
            
            return InvoiceFields()
            
        except openai.RateLimitError as e:
            log_error(e, {"operation": "llm_rate_limit", "request_id": request_id})
            logger.warning(f"OpenAI rate limit exceeded for request {request_id}")
            # Re-raise for retry
            raise
            
        except openai.APIError as e:
            log_error(e, {"operation": "llm_api_error", "request_id": request_id})
            logger.error(f"OpenAI API error for request {request_id}: {e}")
            # Re-raise for retry
            raise
            
        except Exception as e:
            log_error(e, {"operation": "llm_extraction", "request_id": request_id})
            logger.error(f"Unexpected error in LLM extraction for request {request_id}")
            return InvoiceFields()
    
    def _clean_extraction_result(self, result: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Clean and validate extraction result"""
        try:
            cleaned = {}
            
            # String fields
            for field in ['vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'currency', 'po_number']:
                value = result.get(field)
                if value and isinstance(value, str) and value.strip():
                    cleaned[field] = value.strip()
                else:
                    cleaned[field] = None
            
            # Numeric fields
            for field in ['total_amount', 'subtotal', 'tax_amount']:
                value = result.get(field)
                if value is not None:
                    try:
                        cleaned[field] = float(value) if value else None
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid numeric value for {field}: {value} in request {request_id}")
                        cleaned[field] = None
                else:
                    cleaned[field] = None
            
            # Line items
            line_items = result.get('line_items', [])
            cleaned_line_items = []
            
            if isinstance(line_items, list):
                for item in line_items:
                    if isinstance(item, dict):
                        cleaned_item = {}
                        
                        # String fields
                        for field in ['description', 'sku']:
                            value = item.get(field)
                            if value and isinstance(value, str) and value.strip():
                                cleaned_item[field] = value.strip()
                            else:
                                cleaned_item[field] = None
                        
                        # Numeric fields
                        for field in ['quantity', 'unit_price', 'total_price']:
                            value = item.get(field)
                            if value is not None:
                                try:
                                    cleaned_item[field] = float(value) if value else None
                                except (ValueError, TypeError):
                                    cleaned_item[field] = None
                            else:
                                cleaned_item[field] = None
                        
                        # Only add item if it has some useful data
                        if any(v is not None for v in cleaned_item.values()):
                            cleaned_line_items.append(cleaned_item)
            
            cleaned['line_items'] = cleaned_line_items
            
            return cleaned
            
        except Exception as e:
            log_error(e, {"operation": "result_cleaning", "request_id": request_id})
            return {}
    
    async def health_check(self) -> bool:
        """Health check for LLM service"""
        if not self.llm:
            return False
        
        try:
            # Simple test call
            test_prompt = "Respond with: OK"
            response = await self.llm.ainvoke(test_prompt)
            return "OK" in str(response)
            
        except Exception as e:
            log_error(e, {"operation": "llm_health_check"})
            return False


# Create service instance
llm_service = LLMService() 