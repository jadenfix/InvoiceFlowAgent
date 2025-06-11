# ERP Integration Service

This micro-service listens for **approved invoice** events, posts them to an external ERP (e.g., NetSuite) and records the outcome.

## Environment variables
| Var | Purpose | Default |
|-----|---------|---------|
| `DATABASE_URL` | Postgres connection string | ‑ |
| `RABBITMQ_URL` | RabbitMQ broker URL | ‑ |
| `ERP_API_BASE_URL` | Base URL for ERP REST API | ‑ |
| `ERP_API_TOKEN` | Bearer token for ERP | ‑ |
| `ERP_RETRY_MAX` | Max retries for ERP posting | `3` |
| `ERP_RETRY_BACKOFF_BASE` | Seconds for exponential back-off | `2` |

## Local dev
```
poetry install   # or create venv + pip install -r requirements.txt
export $(cat env.sample | xargs)  # adjust values
uvicorn app.main:app --reload --port 8008
```

### Manual push
```
curl -X POST http://localhost:8008/api/v1/erp/push/{invoice_id}
```

## Docker
```
docker build -t erp:local -f services/erp/Dockerfile .
docker run -p8008:8008 --env-file services/erp/env.sample erp:local
```

## Helm
```
helm install erp ./charts/erp \
  --set env.DATABASE_URL=postgresql://... \
  --set env.RABBITMQ_URL=amqp://... \
  --set env.ERP_API_BASE_URL=https://... \
  --set env.ERP_API_TOKEN=xxxxx
``` 