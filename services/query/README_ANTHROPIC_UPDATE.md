# Query Service - Anthropic Migration (Day 8)

## Overview

The Query Service has been migrated from OpenAI to Anthropic's Claude API for Tier 2 NLU fallback processing. This change provides better accuracy and reliability for low-confidence natural language queries.

## Configuration

### Environment Variables

```bash
# Anthropic Configuration for Tier 2 NLU Fallback
ANTHROPIC_API_KEY=your-anthropic-api-key-here
ANTHROPIC_MODEL=claude-2
ANTHROPIC_MAX_TOKENS=500
ANTHROPIC_TEMPERATURE=0.0
ANTHROPIC_MAX_RETRIES=2
ANTHROPIC_RETRY_DELAY=1.0
ANTHROPIC_RETRY_BACKOFF=2.0
TIER2_CONFIDENCE_THRESHOLD=0.7
```

### Required API Key

To enable Tier 2 fallback functionality, you must obtain an API key from Anthropic:

1. Sign up at [https://console.anthropic.com/](https://console.anthropic.com/)
2. Generate an API key
3. Set the `ANTHROPIC_API_KEY` environment variable

**Note:** If no API key is provided, the service will run in Tier 1 only mode (spaCy + regex).

## How It Works

### Two-Tier Processing

1. **Tier 1 (spaCy + Regex)**: Fast local processing using spaCy NER and regex patterns
2. **Tier 2 (Anthropic Claude)**: Advanced LLM fallback for low-confidence queries

### Fallback Logic

```python
if confidence < TIER2_CONFIDENCE_THRESHOLD and anthropic_client:
    tier2_result = anthropic_parse(query)
    if tier2_result:
        return merge_results(tier1_result, tier2_result)
    else:
        return tier1_result  # Fallback to Tier 1
```

### Example Queries

| Query | Tier 1 Confidence | Tier 2 Triggered | Final Result |
|-------|------------------|-------------------|--------------|
| "3 bed 2 bath Denver under 700k" | 1.0 | No | Tier 1 only |
| "cozy loft near beach" | 0.4 | Yes | Merged result |
| "family home downtown" | 0.5 | Yes | Merged result |

## API Usage

### Parse Endpoint

```bash
curl "http://localhost:8002/parse?q=cozy+loft+near+beach"
```

**Response with Tier 2 fallback:**

```json
{
  "beds": 1,
  "baths": 1,
  "city": "Santa Monica",
  "max_price": 800000.0,
  "confidence": 0.8,
  "cache_hit": false
}
```

## Helm Deployment

### values.yaml Configuration

```yaml
env:
  ANTHROPIC_API_KEY: ""  # Set from secret
  ANTHROPIC_MODEL: "claude-2"
  TIER2_CONFIDENCE_THRESHOLD: "0.7"

secrets:
  anthropic:
    name: "query-secrets"
    key: "anthropic-api-key"
```

### Deploy with API Key Secret

```bash
# Create secret
kubectl create secret generic query-secrets \
  --from-literal=anthropic-api-key="your-api-key-here"

# Deploy chart
helm upgrade --install query ./charts/query
```

## Testing

### Unit Tests

```bash
cd services/query
pytest tests/test_parse_fallback.py -v
```

### Integration Test

```bash
# With real Anthropic API key
export ANTHROPIC_API_KEY="your-api-key"
pytest tests/test_integration.py -v
```

### Coverage

The service maintains ≥95% test coverage including:
- Tier 2 fallback success/failure scenarios
- API error handling and retries
- Result merging logic
- Configuration validation

## Monitoring

### Health Checks

- **Liveness**: `/health/live` - Basic service health
- **Readiness**: `/health/ready` - Dependencies check

### Metrics

The service logs Tier 2 usage and performance:

```json
{
  "level": "INFO",
  "message": "Tier 2 fallback successful",
  "confidence_tier1": 0.4,
  "confidence_final": 0.8,
  "anthropic_latency_ms": 250,
  "tier2_used": true
}
```

## Migration from OpenAI

### Removed

- All OpenAI dependencies and imports
- `OPENAI_API_KEY` environment variable
- OpenAI-specific prompt templates
- OpenAI error handling

### Added

- Anthropic Claude client integration
- New prompt templates optimized for Claude
- Anthropic-specific error handling and retries
- Enhanced configuration options

### Backwards Compatibility

The API interface remains unchanged. Existing clients will continue to work without modification.

## Troubleshooting

### Common Issues

1. **Tier 2 not working**: Check `ANTHROPIC_API_KEY` is set correctly
2. **High latency**: Adjust `ANTHROPIC_MAX_TOKENS` or `TIER2_CONFIDENCE_THRESHOLD`
3. **Rate limits**: Configure `ANTHROPIC_MAX_RETRIES` and `ANTHROPIC_RETRY_DELAY`

### Debug Logs

Enable debug logging to see Tier 2 decision making:

```bash
export LOG_LEVEL=DEBUG
```

### Performance Tuning

- **Lower threshold**: More Tier 2 usage, higher accuracy, slower response
- **Higher threshold**: Less Tier 2 usage, faster response, lower accuracy

Recommended: `TIER2_CONFIDENCE_THRESHOLD=0.7` for balanced performance. 