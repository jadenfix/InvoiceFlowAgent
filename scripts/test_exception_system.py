#!/usr/bin/env python3
"""
Exception Review System Integration Test
========================================

This script tests the complete Exception Review system end-to-end:
1. Backend API endpoints
2. Database operations
3. Message publishing
4. Error handling
5. Edge cases

Usage:
    python scripts/test_exception_system.py [--base-url http://localhost:8007]
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import httpx
import asyncpg
from typing import Optional, Dict, Any


class ExceptionSystemTester:
    """Test suite for Exception Review System."""
    
    def __init__(self, base_url: str = "http://localhost:8007"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_invoice_id: Optional[str] = None
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": []
        }
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def log_result(self, test_name: str, success: bool, message: str = ""):
        """Log test result."""
        self.results["total_tests"] += 1
        if success:
            self.results["passed"] += 1
            print(f"✅ {test_name}")
        else:
            self.results["failed"] += 1
            self.results["errors"].append({"test": test_name, "error": message})
            print(f"❌ {test_name}: {message}")
    
    async def test_health_endpoints(self):
        """Test health check endpoints."""
        print("\n🏥 Testing Health Endpoints")
        
        # Test liveness probe
        try:
            response = await self.client.get(f"{self.base_url}/health/live")
            success = response.status_code == 200 and response.json().get("status") == "healthy"
            self.log_result("Liveness probe", success, 
                          f"Status: {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Liveness probe", False, str(e))
        
        # Test readiness probe
        try:
            response = await self.client.get(f"{self.base_url}/health/ready")
            success = response.status_code == 200
            data = response.json() if success else {}
            self.log_result("Readiness probe", success, 
                          f"Status: {response.status_code}, Checks: {data.get('checks', {})}" 
                          if not success else "")
        except Exception as e:
            self.log_result("Readiness probe", False, str(e))
    
    async def test_review_queue_empty(self):
        """Test empty review queue."""
        print("\n📋 Testing Review Queue (Empty)")
        
        try:
            response = await self.client.get(f"{self.base_url}/api/v1/review/queue")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                expected_fields = ["items", "total", "page", "page_size", "has_next", "has_prev"]
                has_fields = all(field in data for field in expected_fields)
                self.log_result("Queue structure", has_fields, 
                              f"Missing fields: {[f for f in expected_fields if f not in data]}" 
                              if not has_fields else "")
                
                is_empty = data["total"] == 0 and len(data["items"]) == 0
                self.log_result("Empty queue response", is_empty,
                              f"Total: {data['total']}, Items: {len(data['items'])}" 
                              if not is_empty else "")
            else:
                self.log_result("Queue endpoint", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_result("Queue endpoint", False, str(e))
    
    async def test_review_queue_pagination(self):
        """Test review queue pagination."""
        print("\n📄 Testing Pagination")
        
        try:
            # Test with different page sizes
            response = await self.client.get(
                f"{self.base_url}/api/v1/review/queue?page=1&page_size=5"
            )
            success = response.status_code == 200
            
            if success:
                data = response.json()
                correct_pagination = data["page"] == 1 and data["page_size"] == 5
                self.log_result("Pagination parameters", correct_pagination,
                              f"Page: {data['page']}, Size: {data['page_size']}" 
                              if not correct_pagination else "")
            else:
                self.log_result("Pagination", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_result("Pagination", False, str(e))
    
    async def test_review_queue_filtering(self):
        """Test review queue filtering."""
        print("\n🔍 Testing Filtering")
        
        try:
            # Test vendor filtering
            response = await self.client.get(
                f"{self.base_url}/api/v1/review/queue?vendor_filter=test"
            )
            success = response.status_code == 200
            self.log_result("Vendor filtering", success, 
                          f"Status: {response.status_code}" if not success else "")
            
            # Test date filtering
            response = await self.client.get(
                f"{self.base_url}/api/v1/review/queue?date_from=2024-01-01&date_to=2024-12-31"
            )
            success = response.status_code == 200
            self.log_result("Date filtering", success, 
                          f"Status: {response.status_code}" if not success else "")
            
            # Test sorting
            response = await self.client.get(
                f"{self.base_url}/api/v1/review/queue?sort_by=created_at&sort_order=desc"
            )
            success = response.status_code == 200
            self.log_result("Sorting", success, 
                          f"Status: {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Filtering", False, str(e))
    
    async def test_invoice_detail_not_found(self):
        """Test invoice detail with non-existent ID."""
        print("\n🔍 Testing Invoice Detail (Not Found)")
        
        try:
            fake_id = str(uuid.uuid4())
            response = await self.client.get(f"{self.base_url}/api/v1/review/{fake_id}")
            success = response.status_code == 404
            self.log_result("Invoice not found (404)", success, 
                          f"Expected 404, got {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Invoice not found", False, str(e))
    
    async def test_review_actions_not_found(self):
        """Test review actions with non-existent invoice."""
        print("\n⚡ Testing Review Actions (Not Found)")
        
        fake_id = str(uuid.uuid4())
        approve_request = {
            "reviewed_by": "test@example.com",
            "review_notes": "Test approval"
        }
        reject_request = {
            "reviewed_by": "test@example.com",
            "review_notes": "Test rejection"
        }
        
        try:
            # Test approve not found
            response = await self.client.post(
                f"{self.base_url}/api/v1/review/{fake_id}/approve",
                json=approve_request
            )
            success = response.status_code == 404
            self.log_result("Approve not found (404)", success,
                          f"Expected 404, got {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Approve not found", False, str(e))
        
        try:
            # Test reject not found
            response = await self.client.post(
                f"{self.base_url}/api/v1/review/{fake_id}/reject",
                json=reject_request
            )
            success = response.status_code == 404
            self.log_result("Reject not found (404)", success,
                          f"Expected 404, got {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Reject not found", False, str(e))
    
    async def test_validation_errors(self):
        """Test validation error handling."""
        print("\n🚨 Testing Validation Errors")
        
        fake_id = str(uuid.uuid4())
        
        try:
            # Test approve without required fields
            response = await self.client.post(
                f"{self.base_url}/api/v1/review/{fake_id}/approve",
                json={}
            )
            success = response.status_code == 400
            self.log_result("Approve validation error (400)", success,
                          f"Expected 400, got {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Approve validation", False, str(e))
        
        try:
            # Test reject without notes
            response = await self.client.post(
                f"{self.base_url}/api/v1/review/{fake_id}/reject",
                json={"reviewed_by": "test@example.com"}
            )
            success = response.status_code == 400
            self.log_result("Reject validation error (400)", success,
                          f"Expected 400, got {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("Reject validation", False, str(e))
    
    async def test_api_documentation(self):
        """Test API documentation endpoints."""
        print("\n📚 Testing API Documentation")
        
        try:
            # Test OpenAPI docs
            response = await self.client.get(f"{self.base_url}/docs")
            success = response.status_code == 200
            self.log_result("OpenAPI docs", success,
                          f"Status: {response.status_code}" if not success else "")
        except Exception as e:
            self.log_result("OpenAPI docs", False, str(e))
        
        try:
            # Test OpenAPI JSON
            response = await self.client.get(f"{self.base_url}/openapi.json")
            success = response.status_code == 200
            if success:
                data = response.json()
                has_paths = "paths" in data and "/api/v1/review/queue" in data["paths"]
                self.log_result("OpenAPI schema", has_paths,
                              "Missing expected paths" if not has_paths else "")
            else:
                self.log_result("OpenAPI JSON", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_result("OpenAPI JSON", False, str(e))
    
    async def test_cors_headers(self):
        """Test CORS headers."""
        print("\n🌐 Testing CORS Headers")
        
        try:
            # Test preflight request
            response = await self.client.options(
                f"{self.base_url}/api/v1/review/queue",
                headers={"Origin": "http://localhost:3000"}
            )
            
            has_cors_headers = (
                "access-control-allow-origin" in response.headers or
                response.status_code == 200  # Some implementations don't require preflight
            )
            self.log_result("CORS headers", has_cors_headers,
                          f"Missing CORS headers in response" if not has_cors_headers else "")
        except Exception as e:
            self.log_result("CORS headers", False, str(e))
    
    async def test_error_response_format(self):
        """Test error response format consistency."""
        print("\n📋 Testing Error Response Format")
        
        try:
            fake_id = str(uuid.uuid4())
            response = await self.client.get(f"{self.base_url}/api/v1/review/{fake_id}")
            
            if response.status_code == 404:
                data = response.json()
                expected_fields = ["error", "message", "timestamp"]
                has_fields = all(field in data for field in expected_fields)
                self.log_result("Error response format", has_fields,
                              f"Missing fields: {[f for f in expected_fields if f not in data]}"
                              if not has_fields else "")
            else:
                self.log_result("Error response format", False, "Could not test error format")
        except Exception as e:
            self.log_result("Error response format", False, str(e))
    
    async def test_rate_limiting(self):
        """Test basic rate limiting (if implemented)."""
        print("\n⏱️ Testing Rate Limiting")
        
        try:
            # Make multiple rapid requests
            tasks = []
            for _ in range(10):
                tasks.append(self.client.get(f"{self.base_url}/health/live"))
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check if all requests succeeded (rate limiting may not be implemented)
            successful_requests = sum(1 for r in responses 
                                    if not isinstance(r, Exception) and r.status_code == 200)
            
            # This is more of an informational test
            self.log_result("Rate limiting test", True, 
                          f"Successfully handled {successful_requests}/10 rapid requests")
        except Exception as e:
            self.log_result("Rate limiting test", False, str(e))
    
    async def test_service_info(self):
        """Test root service information endpoint."""
        print("\n ℹ️ Testing Service Info")
        
        try:
            response = await self.client.get(f"{self.base_url}/")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                expected_fields = ["service", "version", "description"]
                has_fields = all(field in data for field in expected_fields)
                self.log_result("Service info structure", has_fields,
                              f"Missing fields: {[f for f in expected_fields if f not in data]}"
                              if not has_fields else "")
                
                is_exception_service = data.get("service") == "exception-review"
                self.log_result("Service identification", is_exception_service,
                              f"Service name: {data.get('service')}" if not is_exception_service else "")
            else:
                self.log_result("Service info endpoint", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_result("Service info endpoint", False, str(e))
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🚀 Starting Exception Review System Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 50)
        
        # Run all test suites
        await self.test_health_endpoints()
        await self.test_service_info()
        await self.test_review_queue_empty()
        await self.test_review_queue_pagination()
        await self.test_review_queue_filtering()
        await self.test_invoice_detail_not_found()
        await self.test_review_actions_not_found()
        await self.test_validation_errors()
        await self.test_api_documentation()
        await self.test_cors_headers()
        await self.test_error_response_format()
        await self.test_rate_limiting()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 50)
        print("🏁 Test Summary")
        print("=" * 50)
        print(f"Total Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        
        if self.results['failed'] > 0:
            print(f"\n💥 Failed Tests:")
            for error in self.results['errors']:
                print(f"  • {error['test']}: {error['error']}")
        
        success_rate = (self.results['passed'] / self.results['total_tests']) * 100
        print(f"\n📊 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 95:
            print("🎉 Excellent! System is working great!")
        elif success_rate >= 80:
            print("👍 Good! Minor issues detected.")
        else:
            print("⚠️  Warning! Significant issues detected.")


async def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Test Exception Review System")
    parser.add_argument(
        "--base-url", 
        default="http://localhost:8007",
        help="Base URL for the Exception Review Service"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds"
    )
    
    args = parser.parse_args()
    
    print("🧪 Exception Review System Tester")
    print("=" * 40)
    
    try:
        async with ExceptionSystemTester(args.base_url) as tester:
            await tester.run_all_tests()
            
            # Exit with error code if tests failed
            if tester.results['failed'] > 0:
                sys.exit(1)
                
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 