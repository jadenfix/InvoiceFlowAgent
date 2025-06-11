from pydantic_settings import BaseSettings, Field
from typing import List


class Settings(BaseSettings):
    # Service info
    service_name: str = "erp-integration"
    service_version: str = "1.0.0"
    service_host: str = "0.0.0.0"
    service_port: int = 8008

    # Environment
    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(True, env="DEBUG")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # RabbitMQ
    rabbitmq_url: str = Field(..., env="RABBITMQ_URL")

    # ERP API
    erp_api_base_url: str = Field(..., env="ERP_API_BASE_URL")
    erp_api_token: str = Field(..., env="ERP_API_TOKEN")
    erp_retry_max: int = Field(3, env="ERP_RETRY_MAX")
    erp_retry_backoff_base: int = Field(2, env="ERP_RETRY_BACKOFF_BASE")

    # CORS
    allow_origins: List[str] = Field(["*"], env="ALLOW_ORIGINS")

    class Config:
        env_file = "env.sample"
        case_sensitive = False


settings = Settings() 