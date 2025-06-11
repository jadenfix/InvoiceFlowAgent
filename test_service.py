#!/usr/bin/env python3
"""
Simple test script for notification service
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, '.')

# Set environment variables
os.environ['NOTIFICATION_RECIPIENTS'] = 'admin@example.com,+15551234567'
os.environ['SENDGRID_API_KEY'] = 'test_key'
os.environ['DATABASE_URL'] = 'postgresql://test:test@localhost:5432/test'

try:
    print("🔍 Testing notification service imports...")
    
    # Test core imports
    from app.core.config import settings
    print(f"✅ Settings loaded: {len(settings.recipients_list)} recipients configured")
    
    # Test service imports
    from app.services.email_service import EmailService
    from app.services.sms_service import SMSService
    print("✅ Services imported successfully")
    
    # Test main app
    from app.main import app
    print("✅ FastAPI app imported successfully")
    
    # Test basic functionality
    email_service = EmailService()
    sms_service = SMSService()
    print(f"✅ Services instantiated - Email: {email_service.check_health()}, SMS: {sms_service.check_health()}")
    
    print("\n🎉 All tests passed! Starting server...")
    
    # Start the server
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006, log_level="info")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1) 