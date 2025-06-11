from pydantic_settings import BaseSettings, Field
from typing import List

class Settings(BaseSettings):
    service_name: str = "billing"
    service_version: str = "1.0.0"
    service_host: str = "0.0.0.0"
    service_port: int = 8010

    environment: str = Field("development", env="ENVIRONMENT")
    debug: bool = Field(True, env="DEBUG")

    database_url: str = Field(..., env="DATABASE_URL")
    rabbitmq_url: str = Field(..., env="RABBITMQ_URL")

    stripe_api_key: str = Field(..., env="STRIPE_API_KEY")
    stripe_subscription_item_id: str = Field(..., env="STRIPE_SUBSCRIPTION_ITEM_ID")

    billing_publish_queue: str = Field("invoice_posted", env="BILLING_PUBLISH_QUEUE")

    allow_origins: List[str] = Field(["*"], env="ALLOW_ORIGINS")

    class Config:
        env_file = "env.sample"
        case_sensitive = False

settings = Settings() 