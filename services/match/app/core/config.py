"""Configuration settings for the matching service."""

import os
from decimal import Decimal
from typing import Optional
from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str
    
    # RabbitMQ
    rabbitmq_url: str
    
    # Matching configuration
    match_amount_tolerance: Decimal = Decimal("0.02")  # 2% default
    
    # Application
    port: int = 8005
    log_level: str = "INFO"
    
    # Service info
    service_name: str = "match-service"
    version: str = "1.0.0"
    
    @validator("match_amount_tolerance")
    def validate_tolerance(cls, v):
        """Validate amount tolerance is between 0 and 1."""
        if not (0 <= v <= 1):
            raise ValueError("Amount tolerance must be between 0 and 1")
        return v
    
    @validator("database_url")
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Database URL must be a PostgreSQL connection string")
        return v
    
    @validator("rabbitmq_url")
    def validate_rabbitmq_url(cls, v):
        """Validate RabbitMQ URL format."""
        if not v.startswith("amqp://"):
            raise ValueError("RabbitMQ URL must start with 'amqp://'")
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 