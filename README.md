# Invoice Processing System

A production-grade microservices architecture for automated invoice processing using FastAPI, PostgreSQL, OpenSearch, and RabbitMQ.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Services](#services)
- [Day 4: Ingestion Service](#day-4-ingestion-service)
- [Quick Start](#quick-start)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)

## Overview

This system provides a complete solution for ingesting, processing, and searching invoice documents. It supports multiple input sources (file upload, email, webhooks) and extracts structured data for downstream analytics and compliance workflows.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend UI   │    │   API Gateway   │    │  Load Balancer  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Ingestion       │    │ Query           │    │ Processing      │
│ Service         │    │ Service         │    │ Service         │
│ (Port 8003)     │    │ (Port 8002)     │    │ (Port 8004)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PostgreSQL    │    │   OpenSearch    │    │   RabbitMQ      │
│   Database      │    │   Search        │    │   Message Queue │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
┌─────────────────┐
│   AWS S3        │
│   File Storage  │
└─────────────────┘
```

## Services

### 1. Ingestion Service (Port 8003)
Handles file uploads, validation, S3 storage, and message queue integration.

### 2. Query Service (Port 8002)  
Provides search and retrieval APIs with advanced filtering capabilities.

### 3. Processing Service (Port 8004)
Processes uploaded files, extracts data, and updates search indices.

## Day 4: Ingestion Service

The ingestion service is a production-grade FastAPI application that handles file uploads with complete error handling, retry logic, and observability.

### Features

- **File Upload & Validation**: Supports PDF files up to 10MB
- **S3 Integration**: Stores raw files in AWS S3 with metadata
- **Database Persistence**: Tracks ingestion status in PostgreSQL
- **Message Queue**: Publishes events to RabbitMQ for downstream processing
- **Health Checks**: Comprehensive dependency health monitoring
- **Error Handling**: Robust error handling with automatic retries
- **Observability**: Structured logging and metrics

### API Endpoints

#### Upload Invoice
```http
POST /api/v1/ingest/upload
Content-Type: multipart/form-data

Parameters:
- file: PDF file (max 10MB)

Response: 202 Accepted
{
  "request_id": "uuid",
  "status": "PENDING", 
  "message": "File uploaded successfully, processing started"
}
```

#### Get Status
```http
GET /api/v1/ingest/status/{request_id}

Response: 200 OK
{
  "request_id": "uuid",
  "filename": "invoice.pdf",
  "status": "PENDING|PROCESSING|FAILED|COMPLETED",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z",
  "s3_key": "raw/uuid.pdf"
}
```

#### Get Statistics
```http
GET /api/v1/ingest/stats

Response: 200 OK
{
  "pending": 5,
  "processing": 3,
  "failed": 1,
  "completed": 23,
  "total": 32
}
```

#### Health Check
```http
GET /api/v1/ingest/health

Response: 200 OK / 503 Service Unavailable
{
  "service": "healthy|degraded|unhealthy",
  "dependencies": {
    "rabbitmq": "healthy|unhealthy",
    "s3": "healthy|unhealthy", 
    "database": "healthy|unhealthy"
  }
}
```

### Environment Variables

#### Required
```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/db

# AWS S3
S3_BUCKET=invoiceflow-raw-invoices
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# Message Queue
RABBITMQ_URL=amqp://user:password@host:5672/
```

#### Optional
```bash
# Service Configuration
SERVICE_NAME=ingest-service
VERSION=1.0.0
DEBUG=false
HOST=0.0.0.0
PORT=8003

# File Processing
MAX_FILE_SIZE_MB=10
UPLOAD_TIMEOUT_SECONDS=30

# Retry Configuration
MAX_RETRIES=3
RETRY_DELAY_SECONDS=1
RETRY_BACKOFF_FACTOR=2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Database Schema

The ingestion service uses the following database table:

```sql
CREATE TABLE ingestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    s3_key TEXT NOT NULL UNIQUE,
    status TEXT CHECK(status IN ('PENDING','PROCESSING','FAILED','COMPLETED')) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Trigger to update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ingestions_updated_at 
    BEFORE UPDATE ON ingestions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 13+
- RabbitMQ 3.8+
- AWS CLI (optional)
- Docker & Docker Compose (optional)

### Local Development

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd Invoice
   ```

2. **Start Ingestion Service**
   ```bash
   cd services/ingest
   pip install -r requirements.txt
   
   # Set environment variables
   export DATABASE_URL="postgresql://postgres:password@localhost:5432/invoiceflow_dev"
   export S3_BUCKET="invoiceflow-raw-invoices" 
   export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
   
   # Run database migrations
   alembic upgrade head
   
   # Start service
   uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
   ```

3. **Test Upload**
   ```bash
   # Create test PDF
   echo "test pdf content" > test.pdf
   
   # Upload file
   curl -X POST -F "file=@test.pdf" http://localhost:8003/api/v1/ingest/upload
   
   # Check status (use request_id from upload response)
   curl http://localhost:8003/api/v1/ingest/status/{request_id}
   
   # Check stats
   curl http://localhost:8003/api/v1/ingest/stats
   
   # Check health
   curl http://localhost:8003/api/v1/ingest/health
   ```

### Docker Development

1. **Build Image**
   ```bash
   cd services/ingest
   docker build -t invoiceflow/ingest:1.0.0 .
   ```

2. **Run Container**
   ```bash
   docker run -p 8003:8003 \
     -e DATABASE_URL="postgresql://postgres:password@host.docker.internal:5432/invoiceflow_dev" \
     -e S3_BUCKET="invoiceflow-raw-invoices" \
     -e RABBITMQ_URL="amqp://guest:guest@host.docker.internal:5672/" \
     invoiceflow/ingest:1.0.0
   ```

## Testing

### Unit Tests

```bash
cd services/ingest
python -m pytest tests/ -v
```

### Coverage Report

```bash
python -m pytest tests/ --cov=app --cov-report=html
```

### Integration Tests

```bash
# Start dependencies with Docker Compose
docker-compose up -d postgres rabbitmq

# Run integration tests
python -m pytest tests/test_integration.py -v
```

### Load Testing

```bash
# Install dependencies
pip install locust

# Run load tests
locust -f tests/load_test.py --host=http://localhost:8003
```

## Deployment

### Kubernetes with Helm

1. **Create Secrets**
   ```bash
   kubectl create secret generic ingest-db-secret \
     --from-literal=DATABASE_URL="postgresql://user:pass@host:5432/db"
   
   kubectl create secret generic aws-credentials \
     --from-literal=AWS_ACCESS_KEY_ID="your-key" \
     --from-literal=AWS_SECRET_ACCESS_KEY="your-secret"
   
   kubectl create secret generic s3-config \
     --from-literal=S3_BUCKET="your-bucket"
   
   kubectl create secret generic rabbitmq-secret \
     --from-literal=RABBITMQ_URL="amqp://user:pass@host:5672/"
   ```

2. **Deploy with Helm**
   ```bash
   helm install ingest charts/ingest/ \
     --set image.tag=1.0.0 \
     --set replicaCount=3
   ```

3. **Verify Deployment**
   ```bash
   kubectl get pods -l app.kubernetes.io/name=ingest
   kubectl port-forward svc/ingest 8003:8003
   curl http://localhost:8003/health
   ```

### AWS EKS with ALB

```bash
# Install ALB controller
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller eks/aws-load-balancer-controller

# Deploy with ALB ingress
helm install ingest charts/ingest/ \
  --set ingress.enabled=true \
  --set ingress.className=alb \
  --set ingress.annotations."alb\.ingress\.kubernetes\.io/scheme"=internet-facing
```

### Monitoring & Observability

The service includes comprehensive monitoring:

- **Structured Logging**: JSON formatted logs with correlation IDs
- **Health Checks**: Kubernetes liveness and readiness probes
- **Metrics**: Request latency, error rates, dependency health
- **Tracing**: Distributed tracing support (coming soon)

Example log output:
```json
{
  "timestamp": "2024-01-01T00:00:00.000Z",
  "level": "INFO", 
  "logger": "app.api.ingest",
  "message": "Processing upload request abc-123 for file invoice.pdf",
  "service": "ingest-service",
  "request_id": "abc-123",
  "filename": "invoice.pdf"
}
```

## Error Handling

The service implements comprehensive error handling:

### File Validation Errors (400 Bad Request)
- Non-PDF files
- Files exceeding 10MB limit
- Empty files
- Corrupted files

### Infrastructure Errors
- **502 Bad Gateway**: S3 upload failures, message queue unavailable
- **503 Service Unavailable**: Database unavailable, dependency health check failures
- **500 Internal Server Error**: Unexpected application errors

### Retry Logic
- Automatic retries for transient failures
- Exponential backoff with jitter
- Circuit breaker pattern for dependency failures

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Run the test suite
5. Submit a pull request

### Development Guidelines

- Follow PEP 8 style guidelines
- Write comprehensive tests (>95% coverage)
- Include docstrings for all functions
- Use structured logging
- Handle errors gracefully
- Add type hints

### Commit Messages

Use conventional commit format:
```
feat(ingest): add file validation for PDF uploads
fix(ingest): handle S3 connection timeouts
docs(ingest): update API documentation
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔒 Security

For security concerns, please email security@invoiceflow.com or see [SECURITY.md](SECURITY.md).

---

**Built with ❤️ for efficient invoice processing** 