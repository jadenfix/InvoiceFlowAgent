# Invoice Notification Service

A comprehensive notification service that proactively alerts AP teams when invoices require manual review. Built with FastAPI, Celery, SendGrid, and Twilio for reliable email and SMS notifications.

## Features

🔔 **Multi-Channel Notifications**
- Email notifications via SendGrid
- SMS notifications via Twilio
- Configurable recipient lists
- Rich HTML email templates

⏰ **Scheduled Processing**
- Periodic scanning for invoices needing review
- Configurable notification intervals
- Celery-based task scheduling with Redis

🛡️ **Reliability & Resilience**
- Duplicate notification prevention
- Retry logic with exponential backoff
- Rate limit handling
- Graceful error handling and logging

🏥 **Health Monitoring**
- Comprehensive health checks
- Component status monitoring
- Prometheus metrics ready
- Kubernetes-native health probes

## Architecture

```mermaid
graph TB
    subgraph "Notification Service"
        API[FastAPI API<br/>Port 8006]
        WORKER[Celery Worker]
        BEAT[Celery Beat<br/>Scheduler]
    end
    
    subgraph "External Services"
        SENDGRID[SendGrid API]
        TWILIO[Twilio API]
    end
    
    subgraph "Infrastructure"
        DB[(PostgreSQL)]
        REDIS[(Redis)]
    end
    
    BEAT -->|Schedule| WORKER
    WORKER -->|Query| DB
    WORKER -->|Send Email| SENDGRID
    WORKER -->|Send SMS| TWILIO
    WORKER -->|Store Results| DB
    API -->|Health Checks| DB
    API -->|Health Checks| REDIS
    WORKER -->|Task Queue| REDIS
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- SendGrid API key (for email)
- Twilio account (for SMS)

### Environment Variables

Create a `.env` file:

```bash
# Database
DATABASE_URL=postgresql://invoice_user:password@localhost:5432/invoice_db

# Celery/Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# SendGrid
SENDGRID_API_KEY=your_sendgrid_api_key_here

# Twilio
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_FROM_NUMBER=+15551234567

# Notification Settings
REVIEW_NOTIFICATION_INTERVAL=30
NOTIFICATION_RECIPIENTS=admin@example.com,finance@example.com,+15551234567
```

### Installation & Setup

1. **Install Dependencies**
   ```bash
   cd services/notify
   pip install -r requirements.txt
   ```

2. **Database Migration**
   ```bash
   alembic upgrade head
   ```

3. **Run Services**
   
   **API Server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8006 --reload
   ```
   
   **Celery Worker:**
   ```bash
   celery -A worker worker --loglevel=info
   ```
   
   **Celery Beat (Scheduler):**
   ```bash
   celery -A worker beat --loglevel=info
   ```

## API Endpoints

### Health Checks

- **GET `/health/live`** - Liveness probe
  ```bash
  curl http://localhost:8006/health/live
  ```

- **GET `/health/ready`** - Readiness probe (checks DB + Redis)
  ```bash
  curl http://localhost:8006/health/ready
  ```

- **GET `/health/status`** - Detailed component status
  ```bash
  curl http://localhost:8006/health/status
  ```

### Service Information

- **GET `/`** - Root endpoint with service info
- **GET `/info`** - Detailed service information and configuration

## Notification Process

### 1. Scheduled Scanning
- Celery Beat runs `scan_and_notify` task every `REVIEW_NOTIFICATION_INTERVAL` minutes
- Task queries database for invoices with `matched_status = 'NEEDS_REVIEW'`

### 2. Notification Logic
For each invoice requiring review:
1. Parse recipients from `NOTIFICATION_RECIPIENTS`
2. Check for existing notifications (prevent duplicates)
3. Send email/SMS via SendGrid/Twilio
4. Record notification status in database
5. Handle failures with retry logic

### 3. Duplicate Prevention
- Unique constraint on `(invoice_id, method, recipient)`
- Prevents multiple notifications for same invoice/recipient/method
- Safe for concurrent task execution

### 4. Error Handling
- **Rate Limits**: Exponential backoff and retry
- **Invalid Recipients**: Skip and log, continue with others
- **API Failures**: Record failure status and error message
- **Database Errors**: Task fails and restarts via Kubernetes

## Configuration

### Notification Templates

**Email Template Variables:**
- `{invoice_id}` - Invoice identifier
- `{vendor_name}` - Vendor name
- `{total_amount}` - Invoice amount
- `{invoice_link}` - Frontend URL for review

**SMS Template Variables:**
- Same as email, but content truncated to 160 characters

### Recipient Configuration

Recipients in `NOTIFICATION_RECIPIENTS` (comma-separated):
- **Email**: `admin@example.com`
- **SMS**: `+15551234567` (international format)
- **Mixed**: `admin@example.com,finance@example.com,+15551234567`

### Notification Intervals

- **Default**: 30 minutes
- **Range**: 5-1440 minutes (1 day max)
- **Configuration**: `REVIEW_NOTIFICATION_INTERVAL` environment variable

## Testing

### Unit Tests
```bash
cd services/notify
python -m pytest tests/ -v --cov=app --cov-report=html
```

### Integration Tests
```bash
# With testcontainers (requires Docker)
python -m pytest tests/test_integration.py -v
```

### Coverage Report
```bash
python -m pytest --cov=app --cov-report=html --cov-fail-under=95
open htmlcov/index.html
```

## Deployment

### Docker

**Build Image:**
```bash
docker build -t invoice-notify:latest .
```

**Run Container:**
```bash
docker run -d \
  --name notify-api \
  -p 8006:8006 \
  -e DATABASE_URL="postgresql://..." \
  -e CELERY_BROKER_URL="redis://..." \
  invoice-notify:latest \
  uvicorn app.main:app --host 0.0.0.0 --port 8006
```

**Run Worker:**
```bash
docker run -d \
  --name notify-worker \
  -e DATABASE_URL="postgresql://..." \
  -e CELERY_BROKER_URL="redis://..." \
  invoice-notify:latest \
  celery -A worker worker --loglevel=info
```

### Kubernetes with Helm

**Install Chart:**
```bash
helm install notify charts/notify/ \
  --set image.tag="1.0.0" \
  --namespace invoice-system \
  --create-namespace
```

**Configure Secrets:**
```bash
kubectl create secret generic notify-secrets \
  --from-literal=sendgrid-api-key="your_key" \
  --from-literal=twilio-account-sid="your_sid" \
  --from-literal=twilio-auth-token="your_token" \
  --namespace invoice-system
```

**Check Status:**
```bash
kubectl get pods -l app.kubernetes.io/name=notify -n invoice-system
kubectl logs -f deployment/notify-worker -n invoice-system
```

## Monitoring & Observability

### Health Checks
- **Liveness**: Basic service health
- **Readiness**: Database + Redis connectivity
- **Status**: Detailed component health

### Logging
Structured JSON logging with:
- Request IDs for tracing
- Service context
- Performance metrics
- Error details

### Metrics (Prometheus Ready)
- Notification success/failure rates
- Processing latency
- Queue length
- Component health status

### Alerts
Monitor these key metrics:
- Health check failures
- High notification failure rate
- Worker process crashes
- Queue backlog growth

## Security

### Authentication
- No direct user authentication (internal service)
- Service-to-service communication within cluster

### Data Protection
- Sensitive configuration via Kubernetes secrets
- No PII in logs
- Encrypted data at rest and in transit

### Network Security
- Internal cluster communication only
- Firewall rules for external API access (SendGrid/Twilio)

## Performance

### Scalability
- **API**: Auto-scaling based on CPU/memory
- **Workers**: Horizontal scaling with multiple replicas
- **Throughput**: 1000+ notifications/hour per worker

### Optimization
- Connection pooling for database
- Redis connection reuse
- Batch processing capabilities
- Efficient recipient parsing

### Resource Requirements

**Production Recommendations:**

| Component | CPU | Memory | Replicas |
|-----------|-----|--------|----------|
| API | 200m | 256Mi | 2-5 |
| Worker | 100m | 128Mi | 2-10 |
| Beat | 50m | 64Mi | 1 |

## Troubleshooting

### Common Issues

**1. Notifications Not Sending**
```bash
# Check worker logs
kubectl logs -f deployment/notify-worker

# Verify external API credentials
curl -X POST "https://api.sendgrid.v3/mail/send" \
  -H "Authorization: Bearer $SENDGRID_API_KEY"
```

**2. Database Connection Issues**
```bash
# Test database connectivity
psql postgresql://user:pass@host:port/db -c "SELECT 1;"

# Check secret configuration
kubectl get secret notify-secrets -o yaml
```

**3. Redis/Celery Issues**
```bash
# Check Redis connectivity
redis-cli ping

# Monitor Celery tasks
celery -A worker inspect active
celery -A worker inspect stats
```

**4. High Failure Rate**
```bash
# Check notification records
SELECT status, COUNT(*) FROM notifications 
GROUP BY status ORDER BY COUNT(*) DESC;

# Review error messages
SELECT error_message, COUNT(*) FROM notifications 
WHERE status = 'FAILED' 
GROUP BY error_message;
```

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload --log-level debug
```

### Performance Analysis

Monitor key metrics:
```bash
# API response times
curl -w "@curl-format.txt" http://localhost:8006/health/ready

# Worker task processing
celery -A worker inspect stats
```

## Contributing

1. **Fork and Clone**
2. **Create Feature Branch**
3. **Write Tests** (maintain 95%+ coverage)
4. **Update Documentation**
5. **Submit Pull Request**

### Development Standards
- Type hints for all functions
- Docstrings for public methods
- Error handling for all external calls
- Comprehensive test coverage
- Security-first design

## License

MIT License - see [LICENSE](../../LICENSE) file for details.

## Support

- **Documentation**: [Invoice Flow Agent Docs](../../docs/)
- **Issues**: [GitHub Issues](https://github.com/jadenfix/InvoiceFlowAgent/issues)
- **Community**: [Discussions](https://github.com/jadenfix/InvoiceFlowAgent/discussions) 