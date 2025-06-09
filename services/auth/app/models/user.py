"""
User model for InvoiceFlow Auth Service
Handles user data with proper validation and security
"""
import re
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr, validator, Field
from passlib.context import CryptContext
from app.core.config import settings

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    """User database model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    last_failed_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return pwd_context.verify(password, self.hashed_password)

    def set_password(self, password: str) -> None:
        """Set password hash from plain password."""
        self.hashed_password = pwd_context.hash(password)

    def is_account_locked(self) -> bool:
        """Check if account is locked due to failed login attempts."""
        if self.failed_login_attempts < settings.rate_limit_attempts:
            return False
        
        if not self.last_failed_login:
            return False
        
        # Check if lockout period has expired
        lockout_minutes = settings.rate_limit_window_minutes
        time_diff = datetime.utcnow() - self.last_failed_login
        return time_diff.total_seconds() < (lockout_minutes * 60)

    def reset_failed_attempts(self) -> None:
        """Reset failed login attempts counter."""
        self.failed_login_attempts = 0
        self.last_failed_login = None

    def increment_failed_attempts(self) -> None:
        """Increment failed login attempts counter."""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()


# Pydantic Models for API

class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None

    @validator("email")
    def validate_email_format(cls, v):
        """Additional email validation."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Email cannot be empty")
        if len(v) > 255:
            raise ValueError("Email must be less than 255 characters")
        return v.lower().strip()

    @validator("full_name")
    def validate_full_name(cls, v):
        """Validate full name."""
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None
            if len(v) > 255:
                raise ValueError("Full name must be less than 255 characters")
            # Basic XSS prevention
            if re.search(r'[<>"\']', v):
                raise ValueError("Full name contains invalid characters")
        return v


class UserCreate(UserBase):
    """Schema for user creation."""
    password: str = Field(..., min_length=settings.password_min_length)

    @validator("password")
    def validate_password_strength(cls, v):
        """Validate password meets security requirements."""
        if len(v) < settings.password_min_length:
            raise ValueError(f"Password must be at least {settings.password_min_length} characters long")
        
        if len(v) > 128:
            raise ValueError("Password must be less than 128 characters")
        
        # Check for required character types
        has_upper = bool(re.search(r'[A-Z]', v))
        has_lower = bool(re.search(r'[a-z]', v))
        has_digit = bool(re.search(r'\d', v))
        
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit"
            )
        
        # Check for common weak passwords
        common_passwords = [
            "password", "123456", "123456789", "qwerty", "abc123",
            "password123", "admin", "letmein", "welcome", "monkey"
        ]
        if v.lower() in common_passwords:
            raise ValueError("Password is too common and easily guessable")
        
        return v


class UserLogin(BaseModel):
    """Schema for user login."""
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @validator("email")
    def validate_email_format(cls, v):
        """Validate email format."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Email cannot be empty")
        return v.lower().strip()

    @validator("password")
    def validate_password_not_empty(cls, v):
        """Ensure password is not empty."""
        if not v or len(v.strip()) == 0:
            raise ValueError("Password cannot be empty")
        return v


class UserResponse(UserBase):
    """Schema for user response (excludes password)."""
    id: int
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until expiration


class TokenData(BaseModel):
    """Schema for token payload data."""
    email: Optional[str] = None
    user_id: Optional[int] = None 