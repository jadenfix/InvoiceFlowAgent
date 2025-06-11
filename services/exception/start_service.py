#!/usr/bin/env python3
"""Simple startup script for the exception service."""

import os
import sys

# Set environment variables
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEBUG"] = "true"

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import uvicorn
    from app.main import app
    
    print("Starting Exception Review Service...")
    print(f"Environment: {os.environ.get('ENVIRONMENT')}")
    print(f"Database URL: {os.environ.get('DATABASE_URL')}")
    print(f"Available routes: {[route.path for route in app.routes]}")
    
    # Start the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8007,
        log_level="info"
    )
    
except Exception as e:
    print(f"Error starting service: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1) 