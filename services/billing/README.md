# Billing Service

Consumes `invoice_posted` events and reports metered usage to Stripe.

## Env vars
Refer to `env.sample`.

## Local run
```
pip install -r requirements.txt
export $(cat env.sample | xargs)
uvicorn app.main:app --reload --port 8010
```

## API
- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/billing/usage?start=2024-01-01&end=2024-01-31` 