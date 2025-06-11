"""
Tests for notification service
"""
import pytest
import uuid
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.notification_service import NotificationService, NotificationServiceError
from app.models.notification import Invoice, Notification, NotificationMethod, NotificationStatus


class TestNotificationService:
    """Test notification service functionality"""
    
    def test_get_invoices_needing_review(self, notification_service, test_db, sample_invoices):
        """Test getting invoices that need review"""
        invoices = notification_service.get_invoices_needing_review(test_db)
        
        assert len(invoices) == 3
        assert all(invoice.matched_status == "NEEDS_REVIEW" for invoice in invoices)
    
    def test_get_invoices_needing_review_empty(self, notification_service, test_db):
        """Test getting invoices when none need review"""
        invoices = notification_service.get_invoices_needing_review(test_db)
        assert len(invoices) == 0
    
    def test_check_existing_notification(self, notification_service, test_db, sample_invoice):
        """Test checking for existing notifications"""
        # No existing notification
        existing = notification_service.check_existing_notification(
            test_db, sample_invoice.id, "email", "test@example.com"
        )
        assert existing is None
        
        # Create notification
        notification = Notification(
            invoice_id=sample_invoice.id,
            method="email",
            recipient="test@example.com",
            status="SENT"
        )
        test_db.add(notification)
        test_db.commit()
        
        # Check existing notification
        existing = notification_service.check_existing_notification(
            test_db, sample_invoice.id, "email", "test@example.com"
        )
        assert existing is not None
        assert existing.recipient == "test@example.com"
    
    def test_create_notification_record(self, notification_service, test_db, sample_invoice):
        """Test creating notification records"""
        notification = notification_service.create_notification_record(
            test_db,
            sample_invoice.id,
            NotificationMethod.EMAIL,
            "test@example.com",
            NotificationStatus.SENT
        )
        
        assert notification.id is not None
        assert notification.invoice_id == sample_invoice.id
        assert notification.method == "email"
        assert notification.recipient == "test@example.com"
        assert notification.status == "SENT"
        assert notification.error_message is None
    
    def test_create_notification_record_with_error(self, notification_service, test_db, sample_invoice):
        """Test creating notification record with error"""
        error_msg = "SendGrid API error"
        notification = notification_service.create_notification_record(
            test_db,
            sample_invoice.id,
            NotificationMethod.EMAIL,
            "test@example.com",
            NotificationStatus.FAILED,
            error_msg
        )
        
        assert notification.status == "FAILED"
        assert notification.error_message == error_msg
    
    @patch('app.services.notification_service.settings')
    def test_parse_recipients(self, mock_settings, notification_service):
        """Test parsing recipients into email and SMS lists"""
        mock_settings.recipients_list = [
            "test1@example.com",
            "test2@example.com", 
            "+15551234567",
            "+15559876543",
            "invalid-recipient",
            ""
        ]
        
        recipients = notification_service.parse_recipients()
        
        assert len(recipients['email']) == 2
        assert "test1@example.com" in recipients['email']
        assert "test2@example.com" in recipients['email']
        
        assert len(recipients['sms']) == 2
        assert "+15551234567" in recipients['sms']
        assert "+15559876543" in recipients['sms']
    
    @pytest.mark.asyncio
    async def test_send_notification_with_retry_success(self, notification_service):
        """Test successful notification sending"""
        invoice_data = {"invoice_id": "test-123", "vendor_name": "Test", "total_amount": "$100"}
        
        success, error = await notification_service.send_notification_with_retry(
            NotificationMethod.EMAIL, "test@example.com", invoice_data
        )
        
        assert success is True
        assert error is None
        notification_service.email_service.send_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_notification_with_retry_failure(self, notification_service):
        """Test notification sending failure"""
        notification_service.email_service.send_notification = AsyncMock(
            return_value=(False, "API error")
        )
        
        invoice_data = {"invoice_id": "test-123", "vendor_name": "Test", "total_amount": "$100"}
        
        success, error = await notification_service.send_notification_with_retry(
            NotificationMethod.EMAIL, "test@example.com", invoice_data, max_retries=1
        )
        
        assert success is False
        assert error == "API error"
    
    @pytest.mark.asyncio
    async def test_send_notification_with_rate_limit_retry(self, notification_service):
        """Test notification retry on rate limit"""
        # First call fails with rate limit, second succeeds
        notification_service.email_service.send_notification = AsyncMock(
            side_effect=[
                (False, "rate limit exceeded"),
                (True, None)
            ]
        )
        
        invoice_data = {"invoice_id": "test-123", "vendor_name": "Test", "total_amount": "$100"}
        
        success, error = await notification_service.send_notification_with_retry(
            NotificationMethod.EMAIL, "test@example.com", invoice_data, max_retries=1
        )
        
        assert success is True
        assert error is None
        assert notification_service.email_service.send_notification.call_count == 2
    
    @pytest.mark.asyncio
    @patch('app.services.notification_service.settings')
    async def test_process_invoice_notifications(
        self, mock_settings, notification_service, test_db, sample_invoice
    ):
        """Test processing notifications for a single invoice"""
        mock_settings.recipients_list = ["test@example.com", "+15551234567"]
        
        results = await notification_service.process_invoice_notifications(
            test_db, sample_invoice
        )
        
        assert results['invoice_id'] == str(sample_invoice.id)
        assert results['notifications_sent'] == 2  # email + SMS
        assert results['notifications_failed'] == 0
        assert len(results['errors']) == 0
        
        # Verify notifications were recorded in database
        notifications = test_db.query(Notification).filter(
            Notification.invoice_id == sample_invoice.id
        ).all()
        assert len(notifications) == 2
    
    @pytest.mark.asyncio
    @patch('app.services.notification_service.settings')
    async def test_process_invoice_notifications_with_existing(
        self, mock_settings, notification_service, test_db, sample_invoice
    ):
        """Test processing when notifications already exist"""
        mock_settings.recipients_list = ["test@example.com"]
        
        # Create existing notification
        existing = Notification(
            invoice_id=sample_invoice.id,
            method="email",
            recipient="test@example.com",
            status="SENT"
        )
        test_db.add(existing)
        test_db.commit()
        
        results = await notification_service.process_invoice_notifications(
            test_db, sample_invoice
        )
        
        assert results['notifications_sent'] == 0  # Already sent
        assert results['notifications_failed'] == 0
    
    @pytest.mark.asyncio
    @patch('app.services.notification_service.settings')
    async def test_scan_and_notify_no_invoices(self, mock_settings, notification_service, test_db):
        """Test scan when no invoices need review"""
        mock_settings.recipients_list = ["test@example.com"]
        
        results = await notification_service.scan_and_notify(test_db)
        
        assert results['status'] == 'completed'
        assert results['invoices_processed'] == 0
        assert results['total_notifications_sent'] == 0
        assert results['total_notifications_failed'] == 0
    
    @pytest.mark.asyncio
    @patch('app.services.notification_service.settings')
    async def test_scan_and_notify_with_invoices(
        self, mock_settings, notification_service, test_db, sample_invoices
    ):
        """Test scan and notify with multiple invoices"""
        mock_settings.recipients_list = ["test@example.com"]
        
        results = await notification_service.scan_and_notify(test_db)
        
        assert results['status'] == 'completed'
        assert results['invoices_processed'] == 3
        assert results['total_notifications_sent'] == 3  # 3 invoices × 1 recipient
        assert results['total_notifications_failed'] == 0
    
    def test_check_health(self, notification_service):
        """Test health check"""
        health = notification_service.check_health()
        
        assert 'email_service' in health
        assert 'sms_service' in health
        assert health['email_service'] is True
        assert health['sms_service'] is True


class TestNotificationServiceEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_invalid_recipients_skipped(self, notification_service):
        """Test that invalid recipients are skipped gracefully"""
        with patch('app.services.notification_service.settings') as mock_settings:
            mock_settings.recipients_list = [
                "invalid-email",
                "123-not-phone",
                "",
                "test@example.com"  # Only this one is valid
            ]
            
            recipients = notification_service.parse_recipients()
            assert len(recipients['email']) == 1
            assert len(recipients['sms']) == 0
    
    @pytest.mark.asyncio
    async def test_notification_service_failure(self, notification_service, test_db, sample_invoice):
        """Test handling of notification service failures"""
        notification_service.email_service.send_notification = AsyncMock(
            return_value=(False, "Service unavailable")
        )
        
        with patch('app.services.notification_service.settings') as mock_settings:
            mock_settings.recipients_list = ["test@example.com"]
            
            results = await notification_service.process_invoice_notifications(
                test_db, sample_invoice
            )
            
            assert results['notifications_sent'] == 0
            assert results['notifications_failed'] == 1
            assert "Service unavailable" in results['errors'][0]
    
    def test_database_error_handling(self, notification_service):
        """Test database error handling"""
        # Mock database session that raises an error
        mock_db = Mock()
        mock_db.query.side_effect = Exception("Database connection lost")
        
        with pytest.raises(NotificationServiceError):
            notification_service.get_invoices_needing_review(mock_db)
    
    @pytest.mark.asyncio
    async def test_concurrent_notifications(self, notification_service, test_db, sample_invoice):
        """Test handling of concurrent notification attempts"""
        with patch('app.services.notification_service.settings') as mock_settings:
            mock_settings.recipients_list = ["test@example.com"]
            
            # Simulate concurrent processing
            import asyncio
            tasks = [
                notification_service.process_invoice_notifications(test_db, sample_invoice)
                for _ in range(3)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Only one should succeed due to unique constraint
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) >= 1
            
            # Check that only one notification was actually created
            notifications = test_db.query(Notification).filter(
                Notification.invoice_id == sample_invoice.id
            ).all()
            assert len(notifications) == 1 