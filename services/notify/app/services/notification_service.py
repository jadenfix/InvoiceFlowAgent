"""
Main notification service that orchestrates email and SMS notifications
"""
import logging
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.notification import (
    Notification, 
    Invoice, 
    NotificationMethod, 
    NotificationStatus
)
from app.services.email_service import EmailService
from app.services.sms_service import SMSService
from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationServiceError(Exception):
    """Notification service specific errors"""
    pass


class NotificationService:
    """Main notification service"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.sms_service = SMSService()
    
    def get_invoices_needing_review(self, db: Session) -> List[Invoice]:
        """Get all invoices with matched_status = 'NEEDS_REVIEW'"""
        try:
            invoices = db.query(Invoice).filter(
                Invoice.matched_status == 'NEEDS_REVIEW'
            ).all()
            
            logger.info(f"Found {len(invoices)} invoices needing review")
            return invoices
            
        except Exception as e:
            logger.error(f"Error querying invoices: {e}")
            raise NotificationServiceError(f"Database query failed: {e}")
    
    def check_existing_notification(
        self, 
        db: Session, 
        invoice_id: uuid.UUID, 
        method: str, 
        recipient: str
    ) -> Optional[Notification]:
        """Check if notification already exists for this invoice/method/recipient"""
        try:
            notification = db.query(Notification).filter(
                and_(
                    Notification.invoice_id == invoice_id,
                    Notification.method == method,
                    Notification.recipient == recipient
                )
            ).first()
            
            return notification
            
        except Exception as e:
            logger.error(f"Error checking existing notification: {e}")
            return None
    
    def create_notification_record(
        self,
        db: Session,
        invoice_id: uuid.UUID,
        method: NotificationMethod,
        recipient: str,
        status: NotificationStatus,
        error_message: Optional[str] = None
    ) -> Notification:
        """Create a notification record in the database"""
        try:
            notification = Notification(
                invoice_id=invoice_id,
                method=method.value,
                recipient=recipient,
                status=status.value,
                error_message=error_message
            )
            
            db.add(notification)
            db.commit()
            db.refresh(notification)
            
            logger.info(f"Notification record created: {notification.id}")
            return notification
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating notification record: {e}")
            raise NotificationServiceError(f"Failed to create notification record: {e}")
    
    def parse_recipients(self) -> Dict[str, List[str]]:
        """Parse recipients into email and SMS lists"""
        recipients = {
            'email': [],
            'sms': []
        }
        
        for recipient in settings.recipients_list:
            recipient = recipient.strip()
            if not recipient:
                continue
                
            if '@' in recipient:
                # Email address
                if self.email_service.is_valid_email(recipient):
                    recipients['email'].append(recipient)
                else:
                    logger.warning(f"Invalid email address skipped: {recipient}")
            elif recipient.startswith('+'):
                # Phone number
                if self.sms_service.is_valid_phone_number(recipient):
                    recipients['sms'].append(recipient)
                else:
                    logger.warning(f"Invalid phone number skipped: {recipient}")
            else:
                logger.warning(f"Unrecognized recipient format skipped: {recipient}")
        
        return recipients
    
    async def send_notification_with_retry(
        self, 
        method: NotificationMethod,
        recipient: str,
        invoice_data: Dict[str, Any],
        max_retries: int = 2
    ) -> Tuple[bool, Optional[str]]:
        """Send notification with retry logic"""
        service = self.email_service if method == NotificationMethod.EMAIL else self.sms_service
        
        for attempt in range(max_retries + 1):
            success, error_message = await service.send_notification(recipient, invoice_data)
            
            if success:
                return True, None
            
            # Handle rate limiting with exponential backoff
            if error_message and "rate limit" in error_message.lower():
                if attempt < max_retries:
                    import asyncio
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.info(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}")
                    await asyncio.sleep(wait_time)
                    continue
            
            # For other errors, don't retry
            if attempt < max_retries:
                logger.warning(f"Notification failed, attempt {attempt + 1}: {error_message}")
            
        return False, error_message
    
    async def process_invoice_notifications(
        self, 
        db: Session, 
        invoice: Invoice
    ) -> Dict[str, Any]:
        """Process notifications for a single invoice"""
        results = {
            'invoice_id': str(invoice.id),
            'notifications_sent': 0,
            'notifications_failed': 0,
            'errors': []
        }
        
        # Prepare invoice data for templates
        invoice_data = {
            'invoice_id': str(invoice.id),
            'vendor_name': invoice.vendor_name or 'Unknown',
            'total_amount': invoice.total_amount or 'Unknown'
        }
        
        # Parse recipients
        recipients = self.parse_recipients()
        
        # Send email notifications
        for email in recipients['email']:
            # Check if notification already sent
            existing = self.check_existing_notification(
                db, invoice.id, NotificationMethod.EMAIL.value, email
            )
            
            if existing:
                logger.info(f"Email notification already sent to {email} for invoice {invoice.id}")
                continue
            
            # Send notification
            success, error_message = await self.send_notification_with_retry(
                NotificationMethod.EMAIL, email, invoice_data
            )
            
            # Record result
            status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            try:
                self.create_notification_record(
                    db, invoice.id, NotificationMethod.EMAIL, email, status, error_message
                )
                
                if success:
                    results['notifications_sent'] += 1
                else:
                    results['notifications_failed'] += 1
                    results['errors'].append(f"Email to {email}: {error_message}")
                    
            except Exception as e:
                logger.error(f"Failed to record email notification: {e}")
                results['errors'].append(f"Database error for email {email}: {str(e)}")
        
        # Send SMS notifications
        for phone in recipients['sms']:
            # Check if notification already sent
            existing = self.check_existing_notification(
                db, invoice.id, NotificationMethod.SMS.value, phone
            )
            
            if existing:
                logger.info(f"SMS notification already sent to {phone} for invoice {invoice.id}")
                continue
            
            # Send notification
            success, error_message = await self.send_notification_with_retry(
                NotificationMethod.SMS, phone, invoice_data
            )
            
            # Record result
            status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            try:
                self.create_notification_record(
                    db, invoice.id, NotificationMethod.SMS, phone, status, error_message
                )
                
                if success:
                    results['notifications_sent'] += 1
                else:
                    results['notifications_failed'] += 1
                    results['errors'].append(f"SMS to {phone}: {error_message}")
                    
            except Exception as e:
                logger.error(f"Failed to record SMS notification: {e}")
                results['errors'].append(f"Database error for SMS {phone}: {str(e)}")
        
        return results
    
    async def scan_and_notify(self, db: Session) -> Dict[str, Any]:
        """Main function to scan for invoices and send notifications"""
        logger.info("Starting notification scan")
        
        # Get invoices needing review
        invoices = self.get_invoices_needing_review(db)
        
        if not invoices:
            logger.info("No invoices found needing review")
            return {
                'status': 'completed',
                'invoices_processed': 0,
                'total_notifications_sent': 0,
                'total_notifications_failed': 0,
                'errors': []
            }
        
        # Process each invoice
        total_sent = 0
        total_failed = 0
        all_errors = []
        
        for invoice in invoices:
            try:
                results = await self.process_invoice_notifications(db, invoice)
                total_sent += results['notifications_sent']
                total_failed += results['notifications_failed']
                all_errors.extend(results['errors'])
                
            except Exception as e:
                error_msg = f"Failed to process invoice {invoice.id}: {str(e)}"
                logger.error(error_msg)
                all_errors.append(error_msg)
                total_failed += 1
        
        logger.info(f"Notification scan completed: {total_sent} sent, {total_failed} failed")
        
        return {
            'status': 'completed',
            'invoices_processed': len(invoices),
            'total_notifications_sent': total_sent,
            'total_notifications_failed': total_failed,
            'errors': all_errors
        }
    
    def check_health(self) -> Dict[str, bool]:
        """Check health of notification services"""
        return {
            'email_service': self.email_service.check_health(),
            'sms_service': self.sms_service.check_health()
        } 