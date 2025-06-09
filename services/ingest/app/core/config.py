"""
Configuration settings for the ingestion service
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # Service configuration
    SERVICE_NAME: str = Field(default="ingest-service", description="Service name")
    VERSION: str = Field(default="1.0.0", description="Service version")
    DEBUG: bool = Field(default=False, description="Debug mode")
    HOST: str = Field(default="0.0.0.0", description="Host to bind to")
    PORT: int = Field(default=8003, description="Port to bind to")
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
    S3_BUCKET: str = Field(default="invoiceflow-raw-invoices", description="S3 bucket for raw files")
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="AWS secret access key")
    S3_ENDPOINT_URL: Optional[str] = Field(default=None, description="S3 endpoint URL (for LocalStack)")
    
    # Message Queue (RabbitMQ) configuration
    RABBITMQ_URL: str = Field(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ connection URL"
    )
    RABBITMQ_QUEUE_NAME: str = Field(default="invoice_ingest", description="RabbitMQ queue name")
    RABBITMQ_EXCHANGE_NAME: str = Field(default="invoices", description="RabbitMQ exchange name")
    RABBITMQ_ROUTING_KEY: str = Field(default="ingest", description="RabbitMQ routing key")
    
    # OpenSearch configuration
    OPENSEARCH_HOST: str = Field(default="localhost", description="OpenSearch host")
    OPENSEARCH_PORT: int = Field(default=9200, description="OpenSearch port")
    OPENSEARCH_USE_SSL: bool = Field(default=False, description="Use SSL for OpenSearch")
    OPENSEARCH_VERIFY_CERTS: bool = Field(default=False, description="Verify SSL certificates")
    OPENSEARCH_USERNAME: Optional[str] = Field(default=None, description="OpenSearch username")
    OPENSEARCH_PASSWORD: Optional[str] = Field(default=None, description="OpenSearch password")
    
    # File processing limits
    MAX_FILE_SIZE_MB: int = Field(default=10, description="Maximum file size in MB")
    ALLOWED_EXTENSIONS: List[str] = Field(default=["pdf"], description="Allowed file extensions")
    UPLOAD_TIMEOUT_SECONDS: int = Field(default=30, description="Upload timeout in seconds")
    
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


def get_opensearch_config() -> dict:
    """Get OpenSearch configuration dictionary"""
    config = {
        "hosts": [f"{settings.OPENSEARCH_HOST}:{settings.OPENSEARCH_PORT}"],
        "timeout": settings.HEALTH_CHECK_TIMEOUT,
    }
    
    if settings.OPENSEARCH_USERNAME and settings.OPENSEARCH_PASSWORD:
        config["http_auth"] = (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)
    
    return config


def is_testing() -> bool:
    """Check if running in test environment"""
    return os.getenv("TESTING", "false").lower() == "true" 