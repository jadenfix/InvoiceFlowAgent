"""
Core configuration for InvoiceFlow Auth Service
Handles environment variables, validation, and secure defaults
"""
import os
import secrets
from typing import Optional
from pydantic import BaseSettings, validator
from pydantic import PostgresDsn, ValidationError


class Settings(BaseSettings):
    """Application settings with validation and secure defaults."""
    
    # Application
    app_name: str = "InvoiceFlow Auth Service"
    debug: bool = False
    environment: str = "development"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    
    # Database
    database_url: Optional[PostgresDsn] = None
    db_echo: bool = False
    
    # JWT Configuration
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 15
    
    # Rate Limiting
    rate_limit_attempts: int = 5
    rate_limit_window_minutes: int = 10
    
    # Security
    password_min_length: int = 8
    bcrypt_rounds: int = 12
    
    # Monitoring
    enable_metrics: bool = True
    log_level: str = "INFO"
    
    @validator("jwt_secret")
    def validate_jwt_secret(cls, v):
        """Ensure JWT secret is provided and secure."""
        if not v:
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError("JWT_SECRET is required in production")
            # Generate a random secret for development
            return secrets.token_urlsafe(32)
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v
    
    @validator("database_url")
    def validate_database_url(cls, v):
        """Ensure database URL is provided."""
        if not v:
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError("DATABASE_URL is required in production")
            # Default to local database for development
            return "postgresql://invoiceflow:password@localhost:5432/invoiceflow_auth"
        return v
    
    @validator("environment")
    def validate_environment(cls, v):
        """Validate environment value."""
        valid_envs = ["development", "staging", "production"]
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        # Map environment variables to settings
        fields = {
            "database_url": {"env": "DATABASE_URL"},
            "jwt_secret": {"env": "JWT_SECRET"},
            "environment": {"env": "ENVIRONMENT"},
            "debug": {"env": "DEBUG"},
            "log_level": {"env": "LOG_LEVEL"},
        }


def get_settings() -> Settings:
    """Get application settings with error handling."""
    try:
        return Settings()
    except ValidationError as e:
        print(f"Configuration validation error: {e}")
        raise SystemExit(1)


# Global settings instance
settings = get_settings() 