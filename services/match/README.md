# InvoiceFlow Matching Service

## Day 6 → Matching Service

The Matching Service is responsible for consuming invoice extraction results and matching them against purchase orders to determine approval status.

## Overview

This service:
1. Consumes `invoice_extracted` messages from RabbitMQ
2. Matches invoices against purchase orders based on PO number and amount tolerance
3. Updates invoice status as `AUTO_APPROVED` or `NEEDS_REVIEW`
4. Publishes `invoice_matched` messages for downstream processing

## Architecture

```
RabbitMQ (invoice_extracted) → Matching Service → PostgreSQL
                                      ↓
                              RabbitMQ (invoice_matched)
```

## Required Environment Variables

Create a `.env` file from `.env.sample`:

```bash
cp env.sample .env
```

Required variables:
- `DATABASE_URL`: PostgreSQL connection string
- `RABBITMQ_URL`: RabbitMQ connection URL
- `MATCH_AMOUNT_TOLERANCE`: Amount variance tolerance (default: 0.02 = 2%)
- `LOG_LEVEL`: Logging level (INFO, DEBUG, WARNING, ERROR)
- `PORT`: Service port (default: 8005)

## Database Setup

### Migration

Run Alembic migrations to set up database tables:

```bash
# Initialize if needed
alembic upgrade head
```

### Tables Created

1. **purchase_orders**: Master data for PO matching
   - `id`: UUID primary key
   - `po_number`: Unique PO identifier
   - `order_date`: PO creation date
   - `total_amount`: Expected amount
   - `created_at`: Record creation timestamp

2. **invoices**: Updated with matching fields
   - `matched_status`: `AUTO_APPROVED` | `NEEDS_REVIEW`
   - `matched_at`: Matching timestamp
   - `matched_details`: JSON with matching results

## Matching Logic

### Auto-Approval Criteria
An invoice is marked as `AUTO_APPROVED` if:
1. Invoice contains a valid PO number in `fields.po_numbers`
2. PO exists in `purchase_orders` table
3. Amount variance is within tolerance: `ABS(po_amount - invoice_amount) / po_amount ≤ MATCH_AMOUNT_TOLERANCE`

### Needs Review
An invoice is marked as `NEEDS_REVIEW` if:
- No PO number provided
- PO number not found
- Amount variance exceeds tolerance
- Any processing errors occur

## API Endpoints

### Health Checks
- `GET /health/live` → 200 (liveness probe)
- `GET /health/ready` → 200 if DB & RabbitMQ accessible, 503 otherwise

### Service Info
- `GET /` → Service status
- `GET /info` → Detailed service information

## Message Processing

### Input: `invoice_extracted` Queue
```json
{
  "request_id": "uuid-string",
  "raw_key": "s3-object-key",
  "fields": {
    "total_amount": 1000.00,
    "po_numbers": ["PO12345"],
    "vendor_name": "Example Corp",
    "invoice_number": "INV-001"
  }
}
```

### Output: `invoice_matched` Queue
```json
{
  "request_id": "uuid-string",
  "status": "AUTO_APPROVED",
  "details": {
    "po_number": "PO12345",
    "po_amount": 1000.00,
    "invoice_amount": 990.00,
    "variance_pct": 0.01
  }
}
```

## Running Locally

### Prerequisites
- Python 3.11+
- PostgreSQL
- RabbitMQ

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp env.sample .env
# Edit .env with your configuration

# Run migrations
alembic upgrade head

# Start the service
python -m app.main
```

### Development
```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run linting
flake8 app/
black app/
```

## Docker Deployment

### Build Image
```bash
docker build -t invoiceflow/match:latest .
```

### Run Container
```bash
docker run -d \
  --name match-service \
  -p 8005:8005 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e RABBITMQ_URL="amqp://..." \
  invoiceflow/match:latest
```

## Kubernetes Deployment

### Using Helm

```bash
# Install chart
helm install match ./charts/match \
  --set env.DATABASE_URL="postgresql+asyncpg://..." \
  --set env.RABBITMQ_URL="amqp://..." \
  --set image.repository="your-ecr/match"

# Upgrade
helm upgrade match ./charts/match

# Check status
kubectl get pods -l app.kubernetes.io/name=match
```

### Configuration Values

Key Helm values:
- `env.DATABASE_URL`: Database connection
- `env.RABBITMQ_URL`: Message queue connection
- `env.MATCH_AMOUNT_TOLERANCE`: Matching tolerance
- `image.repository`: Container image
- `replicaCount`: Number of replicas
- `resources`: CPU/memory limits

## Monitoring

### Health Endpoints
- Liveness: `curl http://localhost:8005/health/live`
- Readiness: `curl http://localhost:8005/health/ready`

### Logs
Structured JSON logging with request IDs for tracing:
```json
{
  "timestamp": "2024-01-20T10:00:00Z",
  "level": "INFO",
  "message": "Invoice matched successfully",
  "request_id": "uuid-string",
  "service": "match",
  "matched_status": "AUTO_APPROVED"
}
```

## Testing

### Unit Tests
- Matching logic validation
- Database operations
- Message queue handling
- Error scenarios

### Integration Tests
- End-to-end message processing
- Database connectivity
- RabbitMQ connectivity
- Health check validation

### Coverage Target
≥ 95% test coverage required

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run specific test categories
pytest tests/test_matching_logic.py
pytest tests/test_integration.py
```

## Error Handling

### Database Errors
- Retry up to 3 times with exponential backoff
- Mark as `NEEDS_REVIEW` if retries exhausted
- Log detailed error information

### RabbitMQ Errors
- Connection failures cause service restart
- Invalid messages are logged and acknowledged (dropped)
- Processing errors trigger retry mechanism

### Message Processing
1. Parse and validate message format
2. Execute matching logic with error handling
3. Update database with transaction safety
4. Publish result message
5. Acknowledge original message only on success

## Performance

### Scaling
- Stateless service supports horizontal scaling
- Database connection pooling for efficiency
- Async I/O for concurrent message processing

### Monitoring Metrics
- Message processing rate
- Matching accuracy
- Error rates
- Database query performance

## Troubleshooting

### Common Issues

1. **Service not starting**
   - Check database connectivity
   - Verify RabbitMQ access
   - Validate environment variables

2. **Messages not processing**
   - Check queue configuration
   - Verify message format
   - Review error logs

3. **Incorrect matching**
   - Verify PO data in database
   - Check tolerance configuration
   - Review matching logic

### Debug Mode
Set `LOG_LEVEL=DEBUG` for detailed logging:
```bash
export LOG_LEVEL=DEBUG
python -m app.main
``` 