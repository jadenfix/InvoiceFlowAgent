import pytest
import asyncio
import os
import time
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from redis import Redis
from opensearchpy import OpenSearch
import docker
import uuid

from app.main import app
from app.core.config import settings
from app.services.cache import CacheService
from app.services.search import SearchService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_spacy_doc():
    """Mock spaCy document for testing."""
    mock_doc = Mock()
    mock_doc.ents = []
    return mock_doc


@pytest.fixture
def mock_nlp():
    """Mock spaCy NLP pipeline."""
    mock = Mock()
    mock.return_value = Mock()
    mock.return_value.ents = []
    return mock


@pytest.fixture
def sample_properties():
    """Sample property data for testing."""
    return [
        {
            "_id": "prop1",
            "_source": {
                "address": "123 Main St",
                "city": "Denver",
                "state": "CO",
                "price": 650000.0,
                "beds": 3,
                "baths": 2,
                "square_feet": 1800,
                "location": {"lat": 39.7392, "lon": -104.9903}
            }
        },
        {
            "_id": "prop2", 
            "_source": {
                "address": "456 Oak Ave",
                "city": "Seattle",
                "state": "WA", 
                "price": 750000.0,
                "beds": 2,
                "baths": 1,
                "square_feet": 1200,
                "location": {"lat": 47.6062, "lon": -122.3321}
            }
        }
    ]


@pytest.fixture(scope="session")
def docker_client():
    """Docker client for container management."""
    try:
        return docker.from_env()
    except Exception:
        pytest.skip("Docker not available")


@pytest.fixture(scope="session")
def redis_container(docker_client):
    """Start Redis container for integration tests."""
    container_name = f"test-redis-{uuid.uuid4().hex[:8]}"
    
    try:
        # Remove any existing container with same name
        try:
            old_container = docker_client.containers.get(container_name)
            old_container.remove(force=True)
        except docker.errors.NotFound:
            pass
        
        container = docker_client.containers.run(
            "redis:7-alpine",
            name=container_name,
            ports={"6379/tcp": None},
            detach=True,
            remove=True
        )
        
        # Wait for Redis to be ready
        port = container.ports["6379/tcp"][0]["HostPort"]
        redis_url = f"redis://localhost:{port}"
        
        for _ in range(30):  # 30 second timeout
            try:
                redis_client = Redis.from_url(redis_url)
                redis_client.ping()
                break
            except Exception:
                time.sleep(1)
        else:
            raise Exception("Redis container failed to start")
        
        yield redis_url
        
    finally:
        try:
            container.stop()
        except Exception:
            pass


@pytest.fixture(scope="session") 
def opensearch_container(docker_client):
    """Start OpenSearch container for integration tests."""
    container_name = f"test-opensearch-{uuid.uuid4().hex[:8]}"
    
    try:
        # Remove any existing container
        try:
            old_container = docker_client.containers.get(container_name)
            old_container.remove(force=True)
        except docker.errors.NotFound:
            pass
        
        container = docker_client.containers.run(
            "opensearchproject/opensearch:2.11.0",
            name=container_name,
            ports={"9200/tcp": None},
            environment={
                "discovery.type": "single-node",
                "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "admin123!",
                "DISABLE_SECURITY_PLUGIN": "true"
            },
            detach=True,
            remove=True
        )
        
        # Wait for OpenSearch to be ready
        port = container.ports["9200/tcp"][0]["HostPort"]
        opensearch_url = f"http://localhost:{port}"
        
        for _ in range(60):  # 60 second timeout
            try:
                client = OpenSearch([opensearch_url])
                client.cluster.health()
                break
            except Exception:
                time.sleep(2)
        else:
            raise Exception("OpenSearch container failed to start")
        
        yield opensearch_url
        
    finally:
        try:
            container.stop()
        except Exception:
            pass


@pytest.fixture
def mock_cache_service():
    """Mock cache service for unit tests."""
    mock = Mock(spec=CacheService)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.is_healthy = AsyncMock(return_value=True)
    return mock


@pytest.fixture  
def mock_search_service():
    """Mock search service for unit tests."""
    mock = Mock(spec=SearchService)
    mock.search = AsyncMock(return_value=[])
    mock.is_healthy = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def large_query_payload():
    """Generate large query payload for testing size limits."""
    return "x" * 15000  # 15KB payload


@pytest.fixture
def non_ascii_query():
    """Non-ASCII and multi-language query for testing."""
    return "3 спальни 2 ванные комнаты Denver 価格 under 700k"


@pytest.fixture
def sql_injection_payload():
    """SQL injection attempt for security testing."""
    return "'; DROP TABLE users; --"


@pytest.fixture
def malformed_geo_data():
    """Invalid geo coordinates for testing."""
    return {
        "lat": 999.999,  # Invalid latitude
        "lon": -999.999  # Invalid longitude  
    }


@pytest.fixture
def sample_parse_data():
    """Sample parse data for testing"""
    return {
        'beds': 3,
        'baths': 2,
        'city': 'Denver',
        'max_price': 700000.0,
        'confidence': 0.8
    } 