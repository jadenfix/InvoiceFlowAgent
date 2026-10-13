"""
User model for InvoiceFlow Auth Service
Handles user data with proper validation and security
"""
import re
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Integer, String, DateTime, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr, validator, Field
import bcrypt
from app.core.config import settings

class Base(DeclarativeBase):
    pass



class User(Base):
    """User database model."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=True)
    last_failed_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        try:
            encoded = password.encode("utf-8")
            return len(encoded) <= 72 and bcrypt.checkpw(encoded, self.hashed_password.encode("ascii"))
        except (ValueError, TypeError):
            return False

    def set_password(self, password: str) -> None:
        """Set password hash from plain password."""
        encoded = password.encode("utf-8")
        if len(encoded) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        self.hashed_password = bcrypt.hashpw(
            encoded, bcrypt.gensalt(rounds=settings.bcrypt_rounds)
        ).decode("ascii")

    def is_account_locked(self) -> bool:
        """Check if account is locked due to failed login attempts."""
        if self.failed_login_attempts < settings.rate_limit_attempts:
            return False
        
        if not self.last_failed_login:
            return False
        
        # Check if lockout period has expired
        lockout_minutes = settings.rate_limit_window_minutes
        last = self.last_failed_login
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        time_diff = datetime.now(timezone.utc) - last
        return time_diff.total_seconds() < (lockout_minutes * 60)

    def reset_failed_attempts(self) -> None:
        """Reset failed login attempts counter."""
        self.failed_login_attempts = 0
        self.last_failed_login = None

    def increment_failed_attempts(self) -> None:
        """Increment failed login attempts counter."""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.now(timezone.utc)


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
        
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        
        # Check for common weak passwords
        common_passwords = [
            "password", "123456", "123456789", "qwerty", "abc123",
            "password123", "admin", "letmein", "welcome", "monkey"
        ]
        if v.lower() in common_passwords:
            raise ValueError("Password is too common and easily guessable")
        

        # Check for required character types
        has_upper = bool(re.search(r'[A-Z]', v))
        has_lower = bool(re.search(r'[a-z]', v))
        has_digit = bool(re.search(r'\d', v))
        
        if not (has_upper and has_lower and has_digit):
            raise ValueError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit"
            )
        
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
