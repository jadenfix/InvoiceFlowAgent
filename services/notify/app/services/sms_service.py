"""
SMS service using Twilio
"""
import logging
from typing import Optional, Dict, Any
from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from app.core.config import settings

logger = logging.getLogger(__name__)


class SMSServiceError(Exception):
    """SMS service specific errors"""
    pass


class SMSService:
    """Twilio SMS service implementation"""
    
    def __init__(self):
        if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_from_number]):
            logger.warning("Twilio credentials not fully configured")
            self.client = None
        else:
            self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    
    def is_valid_phone_number(self, phone: str) -> bool:
        """Basic phone number validation"""
        import re
        # Simple regex for international phone numbers starting with +
        pattern = r'^\+[1-9]\d{1,14}$'
        return bool(re.match(pattern, phone.strip()))
    
    def format_sms_content(self, invoice_data: Dict[str, Any]) -> str:
        """Format SMS content with invoice data"""
        # Create invoice link
        invoice_link = f"{settings.frontend_base_url}/invoices/{invoice_data.get('invoice_id', '')}"
        
        message = settings.sms_template.format(
            invoice_id=invoice_data.get('invoice_id', 'Unknown'),
            vendor_name=invoice_data.get('vendor_name', 'Unknown'),
            total_amount=invoice_data.get('total_amount', 'Unknown'),
            invoice_link=invoice_link
        )
        
        # Ensure message is within SMS length limits (160 chars for single SMS)
        if len(message) > 160:
            # Truncate and add ellipsis
            message = message[:157] + "..."
        
        return message
    
    async def send_notification(
        self, 
        recipient: str, 
        invoice_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Send SMS notification
        
        Returns:
            tuple: (success: bool, error_message: Optional[str])
        """
        if not self.client:
            error_msg = "Twilio client not configured"
            logger.error(error_msg)
            return False, error_msg
        
        if not self.is_valid_phone_number(recipient):
            error_msg = f"Invalid phone number: {recipient}"
            logger.error(error_msg)
            return False, error_msg
        
        try:
            message_body = self.format_sms_content(invoice_data)
            
            # Send SMS
            message = self.client.messages.create(
                body=message_body,
                from_=settings.twilio_from_number,
                to=recipient
            )
            
            logger.info(f"SMS sent successfully to {recipient}, SID: {message.sid}")
            return True, None
            
        except TwilioException as e:
            if hasattr(e, 'status') and e.status == 429:
                error_msg = "Twilio rate limit exceeded"
                logger.warning(error_msg)
                return False, error_msg
            else:
                error_msg = f"Twilio error: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Unexpected SMS error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def check_health(self) -> bool:
        """Check if Twilio service is available"""
        if not self.client:
            return False
        
        try:
            # Simple API health check by fetching account info
            account = self.client.api.accounts(settings.twilio_account_sid).fetch()
            return account.status == 'active'
        except Exception as e:
            logger.error(f"Twilio health check failed: {e}")
            return False 