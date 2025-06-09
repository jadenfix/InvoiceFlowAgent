"""
Rate limiting for InvoiceFlow Auth Service
Prevents brute force attacks with in-memory and database tracking
"""
import time
from typing import Dict, Optional
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger, log_auth_event
from app.models.user import User

logger = get_logger("auth.rate_limiter")


class RateLimiter:
    """In-memory rate limiter for quick blocking."""
    
    def __init__(self):
        # Track attempts by IP address
        self.ip_attempts: Dict[str, list] = defaultdict(list)
        # Track attempts by email
        self.email_attempts: Dict[str, list] = defaultdict(list)
        self.window_seconds = settings.rate_limit_window_minutes * 60
        self.max_attempts = settings.rate_limit_attempts
    
    def _clean_old_attempts(self, attempts: list) -> list:
        """Remove attempts outside the time window."""
        cutoff_time = time.time() - self.window_seconds
        return [timestamp for timestamp in attempts if timestamp > cutoff_time]
    
    def check_ip_limit(self, ip_address: str) -> bool:
        """Check if IP address has exceeded rate limit."""
        if not ip_address:
            return True  # Allow if we can't get IP
        
        self.ip_attempts[ip_address] = self._clean_old_attempts(
            self.ip_attempts[ip_address]
        )
        
        return len(self.ip_attempts[ip_address]) < self.max_attempts
    
    def check_email_limit(self, email: str) -> bool:
        """Check if email has exceeded rate limit."""
        if not email:
            return True
        
        email = email.lower()
        self.email_attempts[email] = self._clean_old_attempts(
            self.email_attempts[email]
        )
        
        return len(self.email_attempts[email]) < self.max_attempts
    
    def record_attempt(self, ip_address: str, email: str = None):
        """Record a failed attempt."""
        current_time = time.time()
        
        if ip_address:
            self.ip_attempts[ip_address].append(current_time)
        
        if email:
            email = email.lower()
            self.email_attempts[email].append(current_time)
    
    def reset_email_attempts(self, email: str):
        """Reset attempts for a specific email (on successful login)."""
        if email:
            email = email.lower()
            if email in self.email_attempts:
                del self.email_attempts[email]
    
    def get_remaining_attempts(self, ip_address: str = None, email: str = None) -> int:
        """Get remaining attempts for IP or email."""
        remaining_ip = self.max_attempts
        remaining_email = self.max_attempts
        
        if ip_address:
            self.ip_attempts[ip_address] = self._clean_old_attempts(
                self.ip_attempts[ip_address]
            )
            remaining_ip = self.max_attempts - len(self.ip_attempts[ip_address])
        
        if email:
            email = email.lower()
            self.email_attempts[email] = self._clean_old_attempts(
                self.email_attempts[email]
            )
            remaining_email = self.max_attempts - len(self.email_attempts[email])
        
        return min(remaining_ip, remaining_email)
    
    def get_lockout_time_remaining(self, ip_address: str = None, email: str = None) -> int:
        """Get remaining lockout time in seconds."""
        oldest_attempt_time = 0
        
        if ip_address and self.ip_attempts[ip_address]:
            oldest_attempt_time = max(oldest_attempt_time, min(self.ip_attempts[ip_address]))
        
        if email:
            email = email.lower()
            if self.email_attempts[email]:
                oldest_attempt_time = max(oldest_attempt_time, min(self.email_attempts[email]))
        
        if oldest_attempt_time > 0:
            time_elapsed = time.time() - oldest_attempt_time
            remaining = self.window_seconds - time_elapsed
            return max(0, int(remaining))
        
        return 0


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request."""
    # Check for forwarded IP first (behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For can contain multiple IPs, use the first one
        return forwarded.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    
    return "unknown"


def check_rate_limit(request: Request, email: str = None) -> None:
    """Check rate limits and raise HTTPException if exceeded."""
    client_ip = get_client_ip(request)
    
    # Check IP-based rate limit
    if not rate_limiter.check_ip_limit(client_ip):
        remaining_time = rate_limiter.get_lockout_time_remaining(ip_address=client_ip)
        
        log_auth_event(
            "rate_limit_exceeded_ip",
            success=False,
            client_ip=client_ip,
            lockout_remaining_seconds=remaining_time
        )
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Too many requests",
                "message": f"Rate limit exceeded for IP address. Try again in {remaining_time} seconds.",
                "retry_after": remaining_time,
                "type": "ip_rate_limit"
            },
            headers={"Retry-After": str(remaining_time)}
        )
    
    # Check email-based rate limit if email provided
    if email and not rate_limiter.check_email_limit(email):
        remaining_time = rate_limiter.get_lockout_time_remaining(email=email)
        
        log_auth_event(
            "rate_limit_exceeded_email",
            user_email=email,
            success=False,
            client_ip=client_ip,
            lockout_remaining_seconds=remaining_time
        )
        
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Too many requests",
                "message": f"Too many failed attempts for this email. Try again in {remaining_time} seconds.",
                "retry_after": remaining_time,
                "type": "email_rate_limit"
            },
            headers={"Retry-After": str(remaining_time)}
        )


def record_failed_attempt(request: Request, email: str = None):
    """Record a failed login attempt."""
    client_ip = get_client_ip(request)
    rate_limiter.record_attempt(client_ip, email)
    
    remaining = rate_limiter.get_remaining_attempts(client_ip, email)
    
    log_auth_event(
        "failed_login_attempt",
        user_email=email,
        success=False,
        client_ip=client_ip,
        remaining_attempts=remaining
    )


def record_successful_login(request: Request, email: str):
    """Record a successful login and reset counters."""
    client_ip = get_client_ip(request)
    rate_limiter.reset_email_attempts(email)
    
    log_auth_event(
        "successful_login",
        user_email=email,
        success=True,
        client_ip=client_ip
    )


def check_user_account_lockout(user: User) -> None:
    """Check if user account is locked due to failed attempts."""
    if user.is_account_locked():
        remaining_time = settings.rate_limit_window_minutes * 60
        if user.last_failed_login:
            elapsed = (datetime.utcnow() - user.last_failed_login).total_seconds()
            remaining_time = max(0, int(remaining_time - elapsed))
        
        log_auth_event(
            "account_locked",
            user_email=user.email,
            success=False,
            lockout_remaining_seconds=remaining_time
        )
        
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={
                "error": "Account locked",
                "message": f"Account is temporarily locked due to too many failed attempts. Try again in {remaining_time} seconds.",
                "retry_after": remaining_time,
                "type": "account_lockout"
            },
            headers={"Retry-After": str(remaining_time)}
        ) 