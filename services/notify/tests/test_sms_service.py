"""
Tests for SMS service
"""
import pytest
from unittest.mock import Mock, patch
from twilio.base.exceptions import TwilioException

from app.services.sms_service import SMSService, SMSServiceError


class TestSMSService:
    """Test SMS service functionality"""
    
    def test_is_valid_phone_number(self):
        """Test phone number validation"""
        service = SMSService()
        
        # Valid phone numbers
        assert service.is_valid_phone_number("+15551234567") is True
        assert service.is_valid_phone_number("+442071234567") is True
        assert service.is_valid_phone_number("+33123456789") is True
        
        # Invalid phone numbers
        assert service.is_valid_phone_number("5551234567") is False  # No +
        assert service.is_valid_phone_number("+0551234567") is False  # Starts with 0
        assert service.is_valid_phone_number("invalid") is False
        assert service.is_valid_phone_number("") is False
    
    def test_format_sms_content(self):
        """Test SMS content formatting"""
        service = SMSService()
        
        invoice_data = {
            'invoice_id': 'test-123',
            'vendor_name': 'Test Vendor',
            'total_amount': '$1,234.56'
        }
        
        message = service.format_sms_content(invoice_data)
        
        assert 'test-123' in message
        assert 'Test Vendor' in message
        assert '$1,234.56' in message
        assert 'http://localhost:3000/invoices/test-123' in message
        assert len(message) <= 160  # SMS length limit
    
    def test_format_sms_content_truncation(self):
        """Test SMS content truncation for long messages"""
        service = SMSService()
        
        invoice_data = {
            'invoice_id': 'test-123',
            'vendor_name': 'A' * 100,  # Very long vendor name
            'total_amount': '$1,234.56'
        }
        
        message = service.format_sms_content(invoice_data)
        
        assert len(message) <= 160
        assert message.endswith('...')  # Should be truncated
    
    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """Test successful SMS sending"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock successful response
            mock_message = Mock()
            mock_message.sid = "test_message_sid"
            mock_client = Mock()
            mock_client.messages.create.return_value = mock_message
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            invoice_data = {
                'invoice_id': 'test-123',
                'vendor_name': 'Test Vendor',
                'total_amount': '$100.00'
            }
            
            success, error = await service.send_notification("+15551234567", invoice_data)
            
            assert success is True
            assert error is None
            mock_client.messages.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_notification_no_client(self):
        """Test sending SMS when client is not configured"""
        service = SMSService()
        service.client = None
        
        invoice_data = {'invoice_id': 'test-123'}
        success, error = await service.send_notification("+15551234567", invoice_data)
        
        assert success is False
        assert "not configured" in error.lower()
    
    @pytest.mark.asyncio
    async def test_send_notification_invalid_phone(self):
        """Test sending to invalid phone number"""
        service = SMSService()
        service.client = Mock()  # Mock client to avoid None check
        
        invoice_data = {'invoice_id': 'test-123'}
        success, error = await service.send_notification("invalid-phone", invoice_data)
        
        assert success is False
        assert "Invalid phone number" in error
    
    @pytest.mark.asyncio
    async def test_send_notification_twilio_error(self):
        """Test handling Twilio API errors"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock Twilio error
            mock_client = Mock()
            mock_client.messages.create.side_effect = TwilioException("API error")
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            invoice_data = {'invoice_id': 'test-123'}
            success, error = await service.send_notification("+15551234567", invoice_data)
            
            assert success is False
            assert "Twilio error" in error
    
    @pytest.mark.asyncio
    async def test_send_notification_rate_limit(self):
        """Test handling rate limit errors"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock rate limit exception
            mock_client = Mock()
            rate_limit_error = TwilioException("Rate limit exceeded")
            rate_limit_error.status = 429
            mock_client.messages.create.side_effect = rate_limit_error
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            invoice_data = {'invoice_id': 'test-123'}
            success, error = await service.send_notification("+15551234567", invoice_data)
            
            assert success is False
            assert "rate limit" in error.lower()
    
    @pytest.mark.asyncio
    async def test_send_notification_unexpected_error(self):
        """Test handling unexpected errors"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock unexpected exception
            mock_client = Mock()
            mock_client.messages.create.side_effect = Exception("Unexpected error")
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            invoice_data = {'invoice_id': 'test-123'}
            success, error = await service.send_notification("+15551234567", invoice_data)
            
            assert success is False
            assert "Unexpected SMS error" in error
    
    def test_check_health_no_client(self):
        """Test health check when client is not configured"""
        service = SMSService()
        service.client = None
        
        assert service.check_health() is False
    
    def test_check_health_with_client(self):
        """Test health check with configured client"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock account fetch
            mock_account = Mock()
            mock_account.status = 'active'
            mock_client = Mock()
            mock_client.api.accounts.return_value.fetch.return_value = mock_account
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            assert service.check_health() is True
    
    def test_check_health_inactive_account(self):
        """Test health check with inactive account"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock inactive account
            mock_account = Mock()
            mock_account.status = 'inactive'
            mock_client = Mock()
            mock_client.api.accounts.return_value.fetch.return_value = mock_account
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            assert service.check_health() is False
    
    def test_check_health_error(self):
        """Test health check with error"""
        with patch('app.services.sms_service.Client') as mock_client_class:
            # Mock client that raises error
            mock_client = Mock()
            mock_client.api.accounts.return_value.fetch.side_effect = Exception("API error")
            mock_client_class.return_value = mock_client
            
            service = SMSService()
            service.client = mock_client
            
            assert service.check_health() is False 