"""
Configuration settings for the extraction service
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    SERVICE_NAME: str = Field(default="extract-service", description="Service name")
    VERSION: str = Field(default="1.0.0", description="Service version")
    DEBUG: bool = Field(default=False, description="Debug mode")
    HOST: str = Field(default="0.0.0.0", description="Host to bind to")
    PORT: int = Field(default=8004, description="Port to bind to")
    WORKERS: int = Field(default=1, description="Number of worker processes")
    
    # Database configuration
    DATABASE_URL: str = Field(
        default="postgresql://postgres:password@localhost:5432/invoiceflow_dev",
        description="Database connection URL"
    )
    DB_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=20, description="Database connection pool max overflow")
    DB_ECHO: bool = Field(default=False, description="Echo SQL statements")
    
    # AWS S3 configuration
    S3_BUCKET: str = Field(default="invoiceflow-raw-invoices", description="S3 bucket for files")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="AWS secret access key")
    S3_ENDPOINT_URL: Optional[str] = Field(default=None, description="S3 endpoint URL (for LocalStack)")
    
    # Message Queue (RabbitMQ) configuration
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ connection URL"
    )
    RABBITMQ_INGEST_QUEUE: str = Field(default="invoice_ingest", description="Input queue name")
    RABBITMQ_EXTRACTED_QUEUE: str = Field(default="invoice_extracted", description="Output queue name")
    RABBITMQ_EXCHANGE_NAME: str = Field(default="invoices", description="RabbitMQ exchange name")
    RABBITMQ_ROUTING_KEY_EXTRACTED: str = Field(default="extracted", description="Routing key for extracted messages")
    
    # OpenAI configuration
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    OPENAI_MODEL: str = Field(default="gpt-4", description="OpenAI model to use")
    OPENAI_TEMPERATURE: float = Field(default=0.0, description="OpenAI temperature")
    OPENAI_MAX_TOKENS: int = Field(default=1000, description="OpenAI max tokens")
    OPENAI_TIMEOUT: int = Field(default=30, description="OpenAI API timeout in seconds")
    
    # AWS Textract configuration
    TEXTRACT_TIMEOUT: int = Field(default=30, description="Textract timeout in seconds")
    TEXTRACT_MAX_RETRIES: int = Field(default=2, description="Textract max retries")
    
    # OCR configuration
    OCR_FALLBACK_ENABLED: bool = Field(default=True, description="Enable Tesseract fallback")
    OCR_LANGUAGE: str = Field(default="eng", description="Tesseract language")
    OCR_PSM: int = Field(default=6, description="Tesseract Page Segmentation Mode")
    
    # Processing configuration
    MAX_FILE_SIZE_MB: int = Field(default=50, description="Maximum file size in MB")
    PROCESSING_TIMEOUT: int = Field(default=300, description="Processing timeout in seconds")
    PDF_DPI: int = Field(default=200, description="PDF to image DPI")
    
    # Retry configuration
    MAX_RETRIES: int = Field(default=3, description="Maximum number of retries")
    RETRY_DELAY_SECONDS: int = Field(default=1, description="Initial retry delay in seconds")
    RETRY_BACKOFF_FACTOR: int = Field(default=2, description="Retry backoff factor")
    
    # Logging configuration
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format (json/text)")
    
    # Health check configuration
    HEALTH_CHECK_TIMEOUT: int = Field(default=5, description="Health check timeout in seconds")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings instance
settings = Settings()


def get_database_url() -> str:
    """Get database URL with proper async driver"""
    db_url = settings.DATABASE_URL
    if db_url.startswith('postgresql://'):
        return db_url.replace('postgresql://', 'postgresql+asyncpg://')
    return db_url


def get_s3_config() -> dict:
    """Get S3 configuration"""
    config = {
        'region_name': settings.AWS_REGION,
    }
    
    if settings.AWS_ACCESS_KEY_ID:
        config['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
    
    if settings.AWS_SECRET_ACCESS_KEY:
        config['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
    
    if settings.S3_ENDPOINT_URL:
        config['endpoint_url'] = settings.S3_ENDPOINT_URL
    
    return config


def get_textract_config() -> dict:
    """Get Textract configuration"""
    config = {
        'region_name': settings.AWS_REGION,
    }
    
    if settings.AWS_ACCESS_KEY_ID:
        config['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
    
    if settings.AWS_SECRET_ACCESS_KEY:
        config['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
    
    return config 