"""
Email service using SendGrid
"""
import logging
from typing import Optional, Dict, Any
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from python_http_client.exceptions import HTTPError

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Email service specific errors"""
    pass


class EmailService:
    """SendGrid email service implementation"""
    
    def __init__(self):
        if not settings.sendgrid_api_key:
            logger.warning("SendGrid API key not configured")
            self.client = None
        else:
            self.client = SendGridAPIClient(api_key=settings.sendgrid_api_key)
    
    def is_valid_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def format_email_content(self, invoice_data: Dict[str, Any]) -> tuple[str, str]:
        """Format email subject and body with invoice data"""
        subject = settings.email_template_subject.format(
            invoice_id=invoice_data.get('invoice_id', 'Unknown')
        )
        
        # Create invoice link
        invoice_link = f"{settings.frontend_base_url}/invoices/{invoice_data.get('invoice_id', '')}"
        
        body = settings.email_template_body.format(
            invoice_id=invoice_data.get('invoice_id', 'Unknown'),
            vendor_name=invoice_data.get('vendor_name', 'Unknown'),
            total_amount=invoice_data.get('total_amount', 'Unknown'),
            invoice_link=invoice_link
        )
        
        return subject, body
    
    async def send_notification(
        self, 
        recipient: str, 
        invoice_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Send email notification
        
        Returns:
            tuple: (success: bool, error_message: Optional[str])
        """
        if not self.client:
            error_msg = "SendGrid client not configured"
            logger.error(error_msg)
            return False, error_msg
        
        if not self.is_valid_email(recipient):
            error_msg = f"Invalid email address: {recipient}"
            logger.error(error_msg)
            return False, error_msg
        
        try:
            subject, body = self.format_email_content(invoice_data)
            
            # Create email
            from_email = Email("noreply@invoiceflow.com")  # Configure your from email
            to_email = To(recipient)
            content = Content("text/html", body)
            
            mail = Mail(from_email, to_email, subject, content)
            
            # Send email
            response = self.client.send(mail)
            
            if response.status_code in [200, 202]:
                logger.info(f"Email sent successfully to {recipient}")
                return True, None
            else:
                error_msg = f"SendGrid API error: {response.status_code} - {response.body}"
                logger.error(error_msg)
                return False, error_msg
                
        except HTTPError as e:
            if hasattr(e, 'status_code') and e.status_code == 429:
                error_msg = "SendGrid rate limit exceeded"
                logger.warning(error_msg)
                return False, error_msg
            else:
                error_msg = f"SendGrid HTTP error: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Unexpected email error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def check_health(self) -> bool:
        """Check if SendGrid service is available"""
        if not self.client:
            return False
        
        try:
            # Simple API health check
            # Note: SendGrid doesn't have a dedicated health endpoint
            # This is a minimal check that the client is configured
            return bool(self.client.api_key)
        except Exception as e:
            logger.error(f"SendGrid health check failed: {e}")
            return False 