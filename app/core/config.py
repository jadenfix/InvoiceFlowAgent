"""
Configuration settings for notification service
"""
import os
from typing import List
from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Database
    database_url: str = "postgresql://invoice_user:password@localhost:5432/invoice_db"
    
    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    
    # SendGrid
    sendgrid_api_key: str = ""
    
    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    
    # Notification settings
    review_notification_interval: int = 30  # minutes
    notification_recipients: str = ""
    
    # Service
    host: str = "0.0.0.0"
    port: int = 8006
    
    # Email templates
    email_template_subject: str = "Invoice {invoice_id} Requires Review"
    email_template_body: str = """
    <html>
    <body>
        <h2>Invoice Review Required</h2>
        <p>An invoice requires your attention for manual review.</p>
        
        <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 10px 0;">
            <strong>Invoice Details:</strong><br/>
            Invoice ID: {invoice_id}<br/>
            Vendor: {vendor_name}<br/>
            Amount: {total_amount}<br/>
            Status: Needs Review
        </div>
        
        <p>
            <a href="{invoice_link}" 
               style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                Review Invoice
            </a>
        </p>
        
        <p>Please review this invoice at your earliest convenience.</p>
        
        <hr/>
        <small>This is an automated notification from Invoice Flow Agent</small>
    </body>
    </html>
    """
    
    # SMS template
    sms_template: str = "Invoice {invoice_id} requires review. Vendor: {vendor_name}, Amount: {total_amount}. Review: {invoice_link}"
    
    # Frontend URL for links
    frontend_base_url: str = "http://localhost:3000"
    
    @property
    def recipients_list(self) -> List[str]:
        """Parse notification recipients into a list"""
        if not self.notification_recipients:
            return []
        return [r.strip() for r in self.notification_recipients.split(",") if r.strip()]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 