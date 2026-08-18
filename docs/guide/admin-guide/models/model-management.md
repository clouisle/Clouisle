# Model Management

This guide covers how to manage LLM models as an administrator.

## Overview

As an administrator, you can:

- **View all models**: Access all configured LLM models
- **Add models**: Configure new LLM providers and models
- **Update models**: Modify model settings and credentials
- **Test models**: Verify model connectivity
- **Set defaults**: Control the default model and team grants
- **Discover models**: List remote models before saving

## Accessing Model Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Models**
3. View model management interface

### Model List View

The model list shows:

- **Model name**
- **Provider** (OpenAI, Anthropic, Azure OpenAI, etc.)
- **Model ID** (gpt-4-turbo, claude-3-5-sonnet, etc.)
- **Type** (chat, embedding, rerank, tts, stt, image/video generation, etc.)
- **Status** (Enabled / Disabled)
- **Default** (whether it is the default model)

**Filters:**
- Provider
- Type
- Status

**Search:**
- Search by model name or ID

## Adding Models

### Add OpenAI Model

1. Click **Add Model** button
2. Select provider: **OpenAI**
3. Fill in model details:
   - **Name**: Display name (e.g., "GPT-4 Turbo")
   - **Model ID**: OpenAI model ID (e.g., "gpt-4-turbo-preview")
   - **Type**: Chat, Embedding, or other supported type
   - **Description**: Model description (via `provider_display_name` / config)

4. Configure API settings:
   - **API Key**: OpenAI API key
   - **API Base**: (Optional, for custom endpoints)

5. Set capabilities:
   - **Context Length**: Maximum context window
   - **Max Output Tokens**: Maximum response length
   - **Capabilities**: Streaming, function calling, vision, etc. (JSON)

6. Configure pricing:
   - **Input Price**: Cost per 1M input tokens
   - **Output Price**: Cost per 1M output tokens

7. Set default parameters (JSON, e.g. `{"temperature": 0.7, "top_p": 0.9}`)
8. Click **Test Connection**
9. Click **Save Model**

**OpenAI Model Configuration Example:**
```yaml
Name: GPT-4 Turbo
Model ID: gpt-4-turbo-preview
Provider: OpenAI
Type: chat

API Settings:
  API Key: sk-...
  API Base: https://api.openai.com/v1

Capabilities:
  Context Length: 128000
  Max Output Tokens: 4096
  capabilities: {"streaming": true, "function_calling": true}

Pricing (per 1M tokens):
  Input: $10.00
  Output: $30.00

Default Parameters:
  default_params: {"temperature": 0.7, "top_p": 0.9}
```

> **Note:** Models do not have an organization (`org-...`) field, and pricing has no currency field — prices are per 1M tokens in USD terms.

### Add Anthropic Model

1. Click **Add Model** button
2. Select provider: **Anthropic**
3. Fill in model details:
   - **Name**: "Claude 3.5 Sonnet"
   - **Model ID**: "claude-3-5-sonnet-20240620"
   - **Type**: Chat

4. Configure API settings:
   - **API Key**: Anthropic API key
   - **API Base**: (Optional)

5. Set capabilities and pricing (per 1M tokens)
6. Test and save

**Anthropic Model Configuration Example:**
```yaml
Name: Claude 3.5 Sonnet
Model ID: claude-3-5-sonnet-20240620
Provider: Anthropic
Type: chat

API Settings:
  API Key: sk-ant-...
  API Base: https://api.anthropic.com

Capabilities:
  Context Length: 200000
  Max Output Tokens: 4096

Pricing (per 1M tokens):
  Input: $3.00
  Output: $15.00

Default Parameters:
  default_params: {"temperature": 0.7}
```

### Add Azure OpenAI Model

1. Click **Add Model** button
2. Select provider: **Azure OpenAI**
3. Fill in model details:
   - **Name**: "GPT-4 (Azure)"
   - **Model ID**: Deployment name
   - **Type**: Chat

4. Configure API settings:
   - **API Key**: Azure API key
   - **API Base**: Azure endpoint URL
   - **API Version**: API version (e.g., "2024-02-15-preview") — via config
   - **Deployment Name**: Azure deployment name (as Model ID)

5. Set capabilities and pricing
6. Test and save

**Azure OpenAI Configuration Example:**
```yaml
Name: GPT-4 (Azure)
Model ID: gpt-4-deployment
Provider: Azure OpenAI
Type: chat

API Settings:
  API Key: ...
  API Base: https://your-resource.openai.azure.com
  config:
    api_version: "2024-02-15-preview"
    deployment: gpt-4-deployment

Capabilities:
  Context Length: 8192
  Max Output Tokens: 4096

Pricing (per 1M tokens):
  Input: $30.00
  Output: $60.00
```

### Add Custom Model

For custom or self-hosted models:

1. Click **Add Model** button
2. Select provider: **Custom**
3. Fill in model details
4. Configure API settings:
   - **Endpoint**: Custom API endpoint
   - **Authentication**: API Key, Bearer Token, or Custom
   - **Headers**: Custom headers
   - **Request Format**: OpenAI-compatible or Custom

5. Set capabilities
6. Test and save

## Editing Models

### Update Model Settings

1. Find model in list
2. Click **Edit** button
3. Modify settings:
   - Basic information
   - API credentials
   - Capabilities
   - Pricing
   - Default parameters

4. Click **Test Connection**
5. Click **Save Changes**

### Rotate API Keys

**Best Practice:** Rotate API keys regularly for security.

1. Edit model
2. Update API key
3. Test connection
4. Save changes
5. Monitor for errors

### Update Pricing

When provider pricing changes:

1. Edit model
2. Update pricing information:
   - Input price per 1M tokens
   - Output price per 1M tokens
3. Save changes

## Testing Models

### Test Model Connection

1. Select model
2. Click **Test** button
3. Enter test prompt:
   ```
   Hello, how are you?
   ```
4. Configure test parameters (temperature, max tokens)
5. Click **Run Test**

The test endpoint is `POST /api/v1/admin/models/{model_id}/test`; a configuration can also be tested before creating the model via `POST /api/v1/admin/models/test`.

**Test Results:**
```yaml
Status: Success
Response: "Hello! I'm doing well, thank you for asking..."
Tokens Used:
  Prompt: 6
  Completion: 18
  Total: 24
Response Time: 1.2 seconds
```

### Test Model Performance

> **Note:** Not implemented / Roadmap. There is no multi-request performance test (request count, concurrency, p50/p95/p99 percentiles, cost aggregation). Testing is a single connection/response test.

## Monitoring Model Usage

### Usage Statistics

> **Note:** Not implemented / Roadmap. There is no per-model usage endpoint (`GET /models/{id}/usage` does not exist) and no usage/cost dashboard (requests, tokens, cost, top users/agents, per-team breakdowns, cost reports). Model usage is visible indirectly through the dashboard statistics and audit logs.

## Model Status Management

### Model Statuses

**Enabled:**
- Model is operational
- Available for use
- Appears in model selection

**Disabled:**
- Model is disabled
- Cannot be used
- Hidden from users
- Preserves configuration

> **Note:** Models have a single `is_enabled` flag. There are no `testing` or `deprecated` statuses, no deprecation message/end-of-life date, and no "replacement model" suggestion.

### Change Model Status

**Enable Model:**
```bash
1. Select model
2. Set "Enabled" to on
3. Confirm
```

**Disable Model:**
```bash
1. Select model
2. Set "Enabled" to off
3. Confirm
```

## Model Limits

> **Note:** Not implemented / Roadmap. There are no global or team rate limits (requests/minute, tokens/day, cost caps, concurrent requests) for models. Model access control is done through team model authorization (which models a team may use), not quotas.

### Rate Limiting

> **Note:** Not implemented / Roadmap. No per-user, per-team, per-API-key, or global rate limiting for models.

## Provider Management

### Configure Providers

Providers are not configured as separate entities. Each model carries its own provider (`openai`, `anthropic`, `azure_openai`, `ollama`, `custom`, etc.), API key, base URL, and provider display name. There is no global provider registry with default API keys, timeouts, or retry policies.

### Update Provider Settings

1. Navigate to **Admin** → **Models**
2. Select the model
3. Update its provider, API key, base URL, or other fields
4. Test connection
5. Save changes

Remote model discovery is supported via `POST /api/v1/admin/models/discover`, which lists models available from a provider configuration before you save them.

### Approve Model API Origins

Before saving or testing a model with a new API endpoint:

1. Navigate to **Admin** → **Site Settings** → **Security**.
2. Add the endpoint Origin to **Model Endpoint Allowlist**, one per line.
3. Include only the scheme, hostname, and non-default port, for example `https://gateway.example.com` or `http://ollama.internal:11434`.
4. Save the Security settings, then save or test the model again.

> **Security:** Prefer HTTPS for remote endpoints. Use HTTP only for endpoints on a trusted private network because API keys and model traffic are otherwise sent without transport encryption.

Matching is exact. URL paths are ignored, but the scheme, hostname, and port must all match. Removing an Origin blocks subsequent model discovery, connection tests, and runtime requests without restarting the service.

## Troubleshooting

### Model Connection Failed

**Symptoms:**
- Test connection fails
- API errors in logs

**Solutions:**

1. **Check API key:**
   - Verify key is valid
   - Check key permissions
   - Try regenerating key

2. **Check endpoint:**
   - Verify URL is correct
   - Test endpoint with curl
   - Check firewall rules

3. **Check rate limits:**
   - Review provider dashboard
   - Check for quota exceeded
   - Wait for rate limit reset

4. **Check logs:**
   ```bash
   Admin → Models → Select model
   Logs → View recent errors
   ```

### High Model Costs

**Symptoms:**
- Unexpected high costs

**Solutions:**

1. **Review usage:**
   - Check dashboard statistics and audit logs for high-usage agents/teams

2. **Optimize usage:**
   - Use cheaper models for simple tasks
   - Reduce max_tokens
   - Optimize prompts

3. **Review agents:**
   - Check agent configurations
   - Identify inefficient agents
   - Optimize system prompts

> **Note:** Not implemented / Roadmap: cost dashboards, daily/monthly token limits, and cost alerts are not available.

### Slow Model Responses

**Symptoms:**
- Long response times
- Timeouts

**Solutions:**

1. **Check configuration:**
   - Review the model's context length and max output tokens
   - Verify the model is enabled and set as default where needed

2. **Optimize requests:**
   - Reduce max_tokens
   - Use streaming
   - Use faster models

3. **Check provider status:**
   - Review provider status page
   - Check for outages
   - Contact provider support

4. **Scale infrastructure:**
   - Increase timeout
   - Add retry logic
   - Use multiple providers

## Best Practices

### Model Configuration

**✅ Do:**
- Test models before enabling
- Set appropriate pricing (per 1M tokens)
- Configure reasonable defaults
- Rotate API keys regularly
- Document model purposes
- Keep models updated

**❌ Don't:**
- Enable untested models
- Use extreme parameters
- Use static API keys forever
- Skip documentation

### Cost Management

> **Note:** Cost limits and cost alerts are not implemented. Pricing per 1M tokens is stored per model for reference; usage-based cost reports are not available.

**✅ Do:**
- Monitor usage through the dashboard
- Use cheaper models when possible
- Optimize prompts
- Review model grants to teams

**❌ Don't:**
- Use expensive models for everything
- Skip testing
- Use verbose prompts
- Grant unnecessary models to teams

### Security

**✅ Do:**
- Rotate API keys regularly
- Use separate keys per environment
- Restrict model access by team
- Enable audit logging
- Monitor for abuse
- Use HTTPS only

**❌ Don't:**
- Share API keys
- Use production keys in development
- Allow unrestricted access
- Disable audit logs
- Ignore suspicious activity
- Allow HTTP connections

## Bulk Operations

### Bulk Actions

> **Note:** Not implemented / Roadmap. There are no bulk actions (activate/deactivate, update pricing, rotate API keys, export configuration). Models are managed individually; team grants use the team-model authorization endpoints.

## API Access

### Manage Models via API

Admin model endpoints live under `/api/v1/admin/models` and require `admin:model:*` permissions. See [Models API](../../api-reference/endpoints/models.md) for details.

**Common Operations:**
```python
# List models (admin)
models = api.get("/api/v1/admin/models")

# Create model
model = api.post("/api/v1/admin/models", json={
    "name": "GPT-4 Turbo",
    "provider": "openai",
    "model_id": "gpt-4-turbo-preview",
    "model_type": "chat",
    "api_key": "sk-...",
    "input_price": 10.0,   # per 1M tokens
    "output_price": 30.0   # per 1M tokens
})

# Test model connection
test_result = api.post(f"/api/v1/admin/models/{model_id}/test", json={
    "prompt": "Hello, how are you?",
    "temperature": 0.7
})

# Set default model
api.post(f"/api/v1/admin/models/{model_id}/set-default")

# Discover models from a provider config
discovery = api.post("/api/v1/admin/models/discover", json={...})
```

## Related Documentation

- [Models API](../../api-reference/endpoints/models.md) - API reference
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using models
- [System Settings](../settings/system-settings.md) - System config
- [Performance Tuning](../../best-practices/performance-tuning.md) - Performance guidance

---

**Last Updated**: 2026-02-11
