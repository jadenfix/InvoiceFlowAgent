"""
End-to-end test fixtures and configuration.
"""
import asyncio
import os
import time
import uuid
from typing import AsyncGenerator, Dict, Any

import pytest
import httpx
import psycopg2
from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer
from testcontainers.rabbitmq import RabbitMqContainer
from testcontainers.localstack import LocalStackContainer
from testcontainers.compose import DockerCompose
import structlog

logger = structlog.get_logger()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def postgres_container():
    """Start PostgreSQL container for testing."""
    with PostgresContainer("postgres:15") as postgres:
        # Wait for container to be ready
        postgres.get_connection_url()
        
        # Run migrations for all services
        connection_url = postgres.get_connection_url()
        engine = create_engine(connection_url)
        
        # Apply migrations (simplified - in real scenario would use alembic)
        with engine.connect() as conn:
            # Create basic schema for testing
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS invoices_raw (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    request_id VARCHAR(255) UNIQUE NOT NULL,
                    file_name VARCHAR(255) NOT NULL,
                    file_size BIGINT NOT NULL,
                    content_type VARCHAR(100) NOT NULL,
                    s3_key VARCHAR(500) NOT NULL,
                    upload_timestamp TIMESTAMPTZ DEFAULT NOW(),
                    processing_status VARCHAR(50) DEFAULT 'PENDING',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS invoices (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    request_id VARCHAR(255) UNIQUE NOT NULL,
                    vendor_name TEXT,
                    invoice_number VARCHAR(255),
                    invoice_date TIMESTAMPTZ,
                    due_date TIMESTAMPTZ,
                    total_amount NUMERIC(12,2),
                    tax_amount NUMERIC(12,2),
                    line_items JSON,
                    po_numbers JSON,
                    matched_status VARCHAR(20) DEFAULT 'NEEDS_REVIEW',
                    matched_at TIMESTAMPTZ,
                    matched_details JSON,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE TABLE IF NOT EXISTS purchase_orders (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    po_number TEXT UNIQUE NOT NULL,
                    order_date TIMESTAMPTZ,
                    total_amount NUMERIC(12,2) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                -- Insert test PO for matching
                INSERT INTO purchase_orders (po_number, total_amount) 
                VALUES ('PO-TEST-001', 1000.00) 
                ON CONFLICT (po_number) DO NOTHING;
            """))
            conn.commit()
        
        yield {
            "url": connection_url.replace("postgresql://", "postgresql+asyncpg://"),
            "sync_url": connection_url,
            "host": postgres.get_container_host_ip(),
            "port": postgres.get_exposed_port(5432),
            "username": postgres.username,
            "password": postgres.password,
            "database": postgres.dbname
        }


@pytest.fixture(scope="session")
async def rabbitmq_container():
    """Start RabbitMQ container for testing."""
    with RabbitMqContainer() as rabbitmq:
        rabbitmq_url = rabbitmq.get_connection_url()
        
        # Wait for RabbitMQ to be ready
        import pika
        max_retries = 30
        for attempt in range(max_retries):
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                connection.close()
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(1)
        
        yield {
            "url": rabbitmq_url,
            "host": rabbitmq.get_container_host_ip(),
            "port": rabbitmq.get_exposed_port(5672),
            "management_port": rabbitmq.get_exposed_port(15672)
        }


@pytest.fixture(scope="session")
async def s3_container():
    """Start LocalStack S3 container for testing."""
    with LocalStackContainer() as localstack:
        # Configure boto3 to use localstack
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        
        endpoint_url = localstack.get_url()
        
        # Create test buckets
        import boto3
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            region_name="us-east-1"
        )
        
        # Create buckets that our services expect
        buckets = ["invoices", "processed-invoices", "logs", "backups"]
        for bucket in buckets:
            try:
                s3_client.create_bucket(Bucket=bucket)
            except Exception as e:
                logger.warning(f"Could not create bucket {bucket}: {e}")
        
        yield {
            "endpoint_url": endpoint_url,
            "access_key": "testing",
            "secret_key": "testing",
            "region": "us-east-1",
            "buckets": buckets
        }


@pytest.fixture(scope="session")
async def service_containers(postgres_container, rabbitmq_container, s3_container):
    """Start all microservice containers using docker-compose."""
    
    # Set environment variables for services
    env_vars = {
        "DATABASE_URL": postgres_container["url"],
        "RABBITMQ_URL": rabbitmq_container["url"],
        "S3_ENDPOINT_URL": s3_container["endpoint_url"],
        "AWS_ACCESS_KEY_ID": s3_container["access_key"],
        "AWS_SECRET_ACCESS_KEY": s3_container["secret_key"],
        "AWS_DEFAULT_REGION": s3_container["region"],
        "S3_BUCKET_INVOICES": "invoices",
        "S3_BUCKET_PROCESSED": "processed-invoices",
        "MATCH_AMOUNT_TOLERANCE": "0.02",
        "LOG_LEVEL": "DEBUG"
    }
    
    # Update environment
    for key, value in env_vars.items():
        os.environ[key] = value
    
    # Start services using docker-compose
    compose_file_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.e2e.yml")
    
    with DockerCompose(
        filepath=os.path.dirname(compose_file_path),
        compose_file_name="docker-compose.e2e.yml",
        env_file=None
    ) as compose:
        
        # Wait for services to be ready
        await asyncio.sleep(10)
        
        # Health check all services
        services = {
            "ingest": "http://localhost:8003/healthz",
            "extract": "http://localhost:8004/health/live", 
            "match": "http://localhost:8005/health/live"
        }
        
        async with httpx.AsyncClient() as client:
            for service_name, health_url in services.items():
                max_retries = 30
                for attempt in range(max_retries):
                    try:
                        response = await client.get(health_url, timeout=5.0)
                        if response.status_code == 200:
                            logger.info(f"{service_name} service is ready")
                            break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise Exception(f"{service_name} service failed to start: {e}")
                        await asyncio.sleep(2)
        
        yield {
            "ingest_url": "http://localhost:8003",
            "extract_url": "http://localhost:8004", 
            "match_url": "http://localhost:8005",
            "postgres": postgres_container,
            "rabbitmq": rabbitmq_container,
            "s3": s3_container
        }


@pytest.fixture
async def http_client():
    """Provide an async HTTP client for testing."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture
def sample_pdf_content():
    """Provide sample PDF content for testing."""
    # Simple PDF content for testing
    # In a real scenario, you'd use a proper test PDF file
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"


@pytest.fixture
def test_request_id():
    """Generate a unique request ID for each test."""
    return str(uuid.uuid4()) 