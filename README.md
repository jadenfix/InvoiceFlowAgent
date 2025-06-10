# Invoice Processing System

A production-grade microservices architecture for automated invoice processing using FastAPI, PostgreSQL, OpenSearch, and RabbitMQ.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [End-to-End Smoke Test](#end-to-end-smoke-test)
- [Services](#services)
- [Day 4: Ingestion Service](#day-4-ingestion-service)
- [Quick Start](#quick-start)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)

## End-to-End Smoke Test

The platform includes comprehensive end-to-end testing that validates the complete pipeline from PDF upload through matching results.

### Running the Demo Script

The quickest way to see the entire pipeline in action:

```bash
# Prerequisites: Docker, Docker Compose, curl, jq (optional)
./scripts/run_pipeline_demo.sh
```

This script will:
1. Build Docker images for all services (ingest, extract, match)
2. Start the complete infrastructure (PostgreSQL, RabbitMQ, S3, all services)
3. Upload a sample PDF invoice with PO data
4. Wait for processing to complete through all stages
5. Display the final matching results and approval status
6. Clean up all containers automatically

#### Demo Script Options

```bash
./scripts/run_pipeline_demo.sh --help          # Show help and prerequisites
./scripts/run_pipeline_demo.sh --build-only    # Only build images, don't run demo
./scripts/run_pipeline_demo.sh --no-build      # Skip building images (use existing)
./scripts/run_pipeline_demo.sh --cleanup-only  # Only cleanup existing containers
```

### Running E2E Tests

For automated testing of the complete pipeline:

```bash
# Install test dependencies
cd services/e2e
pip install -r requirements.txt

# Run the complete test suite
python -m pytest test_full_pipeline.py -v

# Run with detailed coverage reporting
python -m pytest test_full_pipeline.py -v --cov=test_full_pipeline --cov-report=html
```

The E2E tests validate:
- ✅ Complete PDF upload → ingestion → extraction → matching flow
- ✅ Database record creation and status updates
- ✅ S3 object storage and retrieval
- ✅ RabbitMQ message publishing and consumption
- ✅ Auto-approval vs needs-review decision logic
- ✅ Service health and readiness checks
- ✅ Error handling and timeout scenarios

### Docker Compose for Development

Start all services locally for development and testing:

```bash
# Start the complete stack
docker-compose -f docker-compose.e2e.yml up -d

# Check service health status
docker-compose -f docker-compose.e2e.yml ps

# View real-time logs
docker-compose -f docker-compose.e2e.yml logs -f

# Stop all services and cleanup
docker-compose -f docker-compose.e2e.yml down
```

**Services will be available at:**
- **Ingest API**: http://localhost:8003 (PDF upload, status tracking)
- **Extract API**: http://localhost:8004 (document processing)
- **Match API**: http://localhost:8005 (PO matching and approval)
- **PostgreSQL**: localhost:5432 (testuser/testpassword/invoiceflow_test)
- **RabbitMQ**: localhost:5672 (guest/guest) + Management UI at localhost:15672
- **S3 (LocalStack)**: http://localhost:4566 (local S3 emulator)

### CI Integration

The E2E pipeline tests run automatically on every commit via GitHub Actions:

[![E2E Pipeline](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml/badge.svg?event=e2e)](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml)

The CI pipeline:
1. Builds all service Docker images
2. Starts the complete infrastructure using docker-compose
3. Runs the full test suite with 90-second timeout
4. Reports test results and coverage
5. Cleans up all resources

Builds fail if the end-to-end tests don't pass, ensuring the complete pipeline works before any deployment.

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

# InvoiceFlow Agent Platform

[![CI/CD Pipeline](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml)
[![Terraform Security](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/terraform-security.yml/badge.svg)](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/terraform-security.yml)
[![E2E Pipeline](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml/badge.svg?event=e2e)](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml)

An AI-powered invoice processing platform built with modern cloud-native technologies. The platform automates the complete invoice lifecycle from ingestion to approval through extraction and purchase order matching.

## Architecture Overview

InvoiceFlow Agent is a microservices-based platform that processes invoices through multiple stages:

1. **Ingestion Service** (Port 8003) - PDF upload and initial validation
2. **Extraction Service** (Port 8004) - OCR and AI-powered field extraction  
3. **Matching Service** (Port 8005) - Purchase order matching and approval logic
4. **Auth Service** (Port 8000) - User authentication and authorization
5. **Frontend** (Port 3000) - React-based user interface

```mermaid
graph TB
    A[PDF Upload] --> B[Ingestion Service]
    B --> C[S3 Storage]
    B --> D[RabbitMQ]
    D --> E[Extraction Service]
    E --> F[AI/OCR Processing]
    F --> G[Extracted Data]
    G --> H[Matching Service]
    H --> I[Purchase Orders DB]
    H --> J[Auto-Approval/Review]
    J --> K[Final Results]
    
    L[Auth Service] --> M[User Management]
    N[Frontend] --> L
    N --> B
    N --> O[Real-time Updates]
```

## End-to-End Smoke Test

The platform includes comprehensive end-to-end testing that validates the complete pipeline from PDF upload through matching results.

### Running the Demo Script

The quickest way to see the entire pipeline in action:

```bash
# Prerequisites: Docker, Docker Compose, curl, jq (optional)
./scripts/run_pipeline_demo.sh
```

This script will:
1. Build Docker images for all services
2. Start the complete infrastructure (PostgreSQL, RabbitMQ, S3, all services)
3. Upload a sample PDF invoice
4. Wait for processing to complete
5. Display the final matching results
6. Clean up all containers

#### Demo Script Options

```bash
./scripts/run_pipeline_demo.sh --help          # Show help
./scripts/run_pipeline_demo.sh --build-only    # Only build images
./scripts/run_pipeline_demo.sh --no-build      # Skip building images
./scripts/run_pipeline_demo.sh --cleanup-only  # Only cleanup containers
```

### Running E2E Tests

For automated testing of the pipeline:

```bash
# Install dependencies
cd services/e2e
pip install -r requirements.txt

# Run the complete test suite
python -m pytest test_full_pipeline.py -v

# Run with coverage reporting
python -m pytest test_full_pipeline.py -v --cov=test_full_pipeline --cov-report=html
```

The E2E tests validate:
- Complete PDF upload to matching flow
- Database record creation and updates
- S3 object storage and retrieval
- RabbitMQ message publishing and consumption
- Auto-approval vs needs-review logic
- Service health and readiness checks

### Docker Compose for Development

Start all services locally for development:

```bash
# Start all services
docker-compose -f docker-compose.e2e.yml up -d

# Check service health
docker-compose -f docker-compose.e2e.yml ps

# View logs
docker-compose -f docker-compose.e2e.yml logs -f

# Stop all services
docker-compose -f docker-compose.e2e.yml down
```

Services will be available at:
- **Ingest API**: http://localhost:8003
- **Extract API**: http://localhost:8004  
- **Match API**: http://localhost:8005
- **PostgreSQL**: localhost:5432 (testuser/testpassword/invoiceflow_test)
- **RabbitMQ**: localhost:5672 (guest/guest) + Management at localhost:15672
- **S3 (LocalStack)**: http://localhost:4566

## Quick Start

### Prerequisites

- Docker & Docker Compose
- AWS CLI (configured)
- Terraform >= 1.6.0
- kubectl
- Helm 3.x
- Node.js 18+ (for frontend development)
- Python 3.11+ (for backend development)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/jadenfix/InvoiceFlowAgent.git
   cd InvoiceFlowAgent
   ```

2. **Set up infrastructure**
   ```bash
   cd infra/environments/dev
   terraform init
   terraform plan
   terraform apply
   ```

3. **Deploy services**
   ```bash
   # Deploy auth service
   helm install invoiceflow-auth ./charts/auth \
     --set image.tag=latest \
     --set environment=development

   # Deploy other services
   helm install invoiceflow-ingest ./charts/ingest
   helm install invoiceflow-extract ./charts/extract  
   helm install invoiceflow-match ./charts/match
   ```

4. **Run the demo**
   ```bash
   ./scripts/run_pipeline_demo.sh
   ```

### Infrastructure

The platform deploys on AWS using:

- **EKS** - Kubernetes cluster for microservices
- **RDS Aurora** - PostgreSQL for data persistence
- **S3** - Document storage and processing artifacts
- **VPC** - Secure networking with public/private subnets
- **IAM** - Service-specific roles and policies

#### Environments

- **Development** (`infra/environments/dev`) - Single AZ, minimal resources
- **Staging** (`infra/environments/staging`) - Production-like, multi-AZ
- **Production** (`infra/environments/prod`) - High availability, auto-scaling

#### Deploying Infrastructure

```bash
cd infra/environments/{env}
terraform init
terraform plan -var="image_tag=latest"
terraform apply -var="image_tag=latest"
```

## Services

### Authentication Service (Port 8000)

FastAPI-based authentication with JWT tokens, rate limiting, and comprehensive security.

**Features:**
- User registration and login
- JWT token management
- Password strength validation
- Rate limiting (5 attempts/10min)
- Input sanitization
- Structured logging

**Endpoints:**
- `POST /register` - User registration
- `POST /login` - User authentication  
- `GET /healthz` - Health check

[More details](services/auth/README.md)

### Ingestion Service (Port 8003)

Handles PDF upload, validation, and initial processing coordination.

**Features:**
- Multi-format file upload
- File validation and virus scanning
- S3 integration
- RabbitMQ message publishing
- Processing status tracking

**Endpoints:**
- `POST /api/v1/ingest/upload` - File upload
- `GET /api/v1/ingest/status/{id}` - Processing status
- `GET /healthz` - Health check

[More details](services/ingest/README.md)

### Extraction Service (Port 8004)

AI-powered document processing with OCR and field extraction.

**Features:**
- OCR text extraction
- AI-powered field identification
- Structured data output
- Error handling and retries
- Performance monitoring

**Endpoints:**
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe

[More details](services/extract/README.md)

### Matching Service (Port 8005)

Intelligent invoice matching against purchase orders with configurable approval logic.

**Features:**
- Purchase order matching
- Amount tolerance validation
- Auto-approval logic
- Comprehensive audit trail
- Configurable matching rules

**Endpoints:**
- `GET /health/live` - Liveness probe  
- `GET /health/ready` - Readiness probe
- `GET /info` - Service information

[More details](services/match/README.md)

### Frontend (Port 3000)

Modern React application with TypeScript, Tailwind CSS, and real-time features.

**Features:**
- User authentication
- File upload interface
- Processing status tracking
- Interactive map visualization
- Responsive design
- Real-time updates

[More details](frontend/README.md)

## Development

### Code Structure

```
InvoiceFlowAgent/
├── infra/                 # Terraform infrastructure
│   ├── modules/          # Reusable Terraform modules
│   └── environments/     # Environment-specific configs
├── services/             # Microservices
│   ├── auth/            # Authentication service
│   ├── ingest/          # File ingestion service
│   ├── extract/         # Document extraction service
│   ├── match/           # Invoice matching service
│   └── e2e/             # End-to-end tests
├── frontend/             # React frontend application
├── charts/               # Helm charts for deployment
├── scripts/              # Utility scripts
└── docs/                 # Documentation
```

### Testing Strategy

1. **Unit Tests** - Service-specific functionality
2. **Integration Tests** - Database and external service interactions  
3. **End-to-End Tests** - Complete pipeline validation
4. **Load Tests** - Performance and scalability validation

#### Running Tests

```bash
# Run all service tests
make test-all

# Run specific service tests  
cd services/auth && python -m pytest
cd services/match && python -m pytest

# Run E2E tests
cd services/e2e && python -m pytest

# Run frontend tests
cd frontend && npm test

# Run with coverage
cd services/auth && python -m pytest --cov=app --cov-report=html
```

### Contributing

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Write tests** for your changes
4. **Ensure all tests pass** (`make test-all`)
5. **Commit your changes** (`git commit -m 'Add amazing feature'`)
6. **Push to the branch** (`git push origin feature/amazing-feature`)
7. **Open a Pull Request**

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Development Standards

- **Code Coverage**: Minimum 95% for all services
- **Code Quality**: Automated linting (flake8, black, eslint)
- **Security**: Automated security scanning (Trivy, Checkov)
- **Documentation**: Comprehensive README for each service
- **Testing**: Unit, integration, and E2E tests required

## CI/CD Pipeline

Automated pipeline using GitHub Actions:

1. **Code Quality** - Linting, formatting, type checking
2. **Security Scanning** - Vulnerability assessment  
3. **Unit Testing** - Service-specific test suites
4. **Integration Testing** - Database and message queue tests
5. **End-to-End Testing** - Complete pipeline validation
6. **Infrastructure Validation** - Terraform plan and security scan
7. **Image Building** - Docker image creation and pushing
8. **Deployment** - Automated deployment to dev/staging/prod

### Pipeline Status

[![CI/CD Pipeline](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/jadenfix/InvoiceFlowAgent/actions/workflows/ci-cd.yml)

### Branch Strategy

- **main** - Production deployments
- **develop** - Development environment deployments  
- **feature/** - Feature development branches

## Monitoring & Observability

### Health Checks

All services implement comprehensive health checks:

- **Liveness Probes** - Basic service health
- **Readiness Probes** - Dependency health (DB, RabbitMQ, etc.)
- **Startup Probes** - Service initialization

### Logging

Structured JSON logging with:

- Request tracing IDs
- Service context
- Performance metrics
- Error details and stack traces

### Metrics

Key metrics collected:

- Request rate and latency
- Error rates and types
- Resource utilization
- Processing pipeline metrics
- Business metrics (invoices processed, approval rates)

## Security

### Security Features

- **Authentication** - JWT-based user authentication
- **Authorization** - Role-based access control
- **Input Validation** - Comprehensive data sanitization
- **Rate Limiting** - API abuse prevention
- **Encryption** - Data encryption at rest and in transit
- **Vulnerability Scanning** - Automated security assessments

### Security Scanning

Automated security scanning includes:

- **Container Scanning** - Trivy vulnerability assessment
- **Infrastructure Scanning** - Checkov and TFSec
- **Dependency Scanning** - Known vulnerability detection
- **SAST** - Static application security testing

## Performance

### Scalability

- **Horizontal Scaling** - Auto-scaling based on metrics
- **Resource Optimization** - Right-sized containers
- **Caching** - Redis for frequently accessed data
- **Connection Pooling** - Efficient database connections

### Performance Targets

- **API Response Time** - <200ms for 95th percentile
- **Document Processing** - <30s for standard invoices
- **Throughput** - 1000+ invoices/hour per service instance
- **Availability** - 99.9% uptime SLA

## Troubleshooting

### Common Issues

1. **Services Not Starting**
   ```bash
   # Check logs
   kubectl logs -f deployment/service-name
   
   # Check health endpoints
   curl http://localhost:8003/healthz
   ```

2. **Database Connection Issues**
   ```bash
   # Verify database connectivity
   psql postgresql://user:pass@host:port/db -c "SELECT 1;"
   ```

3. **Message Queue Issues**
   ```bash
   # Check RabbitMQ status
   curl http://localhost:15672/api/overview
   ```

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
kubectl set env deployment/service-name LOG_LEVEL=DEBUG
```

### Getting Help

- **Issues** - GitHub Issues for bug reports
- **Discussions** - GitHub Discussions for questions
- **Documentation** - Comprehensive service documentation
- **Examples** - Working examples in `examples/` directory

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- FastAPI for the excellent web framework
- React and the React ecosystem
- Terraform for infrastructure as code
- Kubernetes and the cloud-native ecosystem
- The open-source community

---

Built with ❤️ by the InvoiceFlow team 