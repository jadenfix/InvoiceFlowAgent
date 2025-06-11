"""
Configuration management for Query Service
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "InvoiceFlow Query Service"
    version: str = "1.0.0"
    debug: bool = False
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8002
    
    # Redis Cache
    redis_url: str = "redis://localhost:6379/0"
    redis_password: Optional[str] = None
    cache_ttl: int = 86400  # 24 hours
    
    # OpenSearch
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_scheme: str = "http"
    opensearch_username: Optional[str] = None
    opensearch_password: Optional[str] = None
    opensearch_use_ssl: bool = False
    opensearch_verify_certs: bool = False
    
    # Query processing
    spacy_model: str = "en_core_web_sm"
    max_query_length: int = 500
    default_max_results: int = 10
    tier2_confidence_threshold: float = 0.7
    
    # Anthropic Configuration for Tier 2 NLU Fallback
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-2"
    anthropic_max_tokens: int = 500
    anthropic_temperature: float = 0.0
    anthropic_max_retries: int = 2
    anthropic_retry_delay: float = 1.0
    anthropic_retry_backoff: float = 2.0
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        env_prefix = ""


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings 