"""Configuration settings for the Exception Review Service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # Service info
    service_name: str = "exception-review"
    service_version: str = "1.0.0"
    service_port: int = 8007
    service_host: str = "0.0.0.0"

    # Environment
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/invoice_flow",
    )

    # RabbitMQ
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")

    # API Configuration
    api_title: str = "Exception Review Service"
    api_description: str = "Service for managing invoice exception reviews"
    api_version: str = "1.0.0"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    # CORS
    allow_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:5173"])
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]

    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100

    # Logging
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")

    # Health Check
    health_check_timeout: int = 5

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, populate_by_name=True)


# Global settings instance
settings = Settings()
