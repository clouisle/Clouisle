# Model Management

This guide covers how to manage LLM models as an administrator.

## Overview

As an administrator, you can:

- **View all models**: Access all configured LLM models
- **Add models**: Configure new LLM providers and models
- **Update models**: Modify model settings and credentials
- **Test models**: Verify model connectivity and performance
- **Monitor usage**: Track model usage and costs
- **Set limits**: Control model access and usage
- **Manage providers**: Configure LLM provider settings

## Accessing Model Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Models**
3. View model management interface

### Model List View

The model list shows:

- **Model name**
- **Provider** (OpenAI, Anthropic, Azure, etc.)
- **Model ID** (gpt-4-turbo, claude-3-5-sonnet, etc.)
- **Type** (Chat, Completion, Embedding)
- **Status** (Active, Inactive, Testing)
- **Usage** (requests, tokens, cost)
- **Last used**

**Filters:**
- Provider
- Type
- Status
- Date range

**Search:**
- Search by model name or ID

## Adding Models

### Add OpenAI Model

1. Click **Add Model** button
2. Select provider: **OpenAI**
3. Fill in model details:
   - **Name**: Display name (e.g., "GPT-4 Turbo")
   - **Model ID**: OpenAI model ID (e.g., "gpt-4-turbo-preview")
   - **Type**: Chat, Completion, or Embedding
   - **Description**: Model description

4. Configure API settings:
   - **API Key**: OpenAI API key
   - **Organization ID**: (Optional)
   - **API Base**: (Optional, for custom endpoints)

5. Set capabilities:
   - **Streaming**: Enable/disable
   - **Function Calling**: Enable/disable
   - **Vision**: Enable/disable
   - **Max Tokens**: Maximum context length

6. Configure pricing:
   - **Input Cost**: Cost per 1K tokens
   - **Output Cost**: Cost per 1K tokens
   - **Currency**: USD

7. Set default parameters:
   - **Temperature**: 0.7
   - **Max Tokens**: 4096
   - **Top P**: 0.9

8. Click **Test Connection**
9. Click **Save Model**

**OpenAI Model Configuration Example:**
```yaml
Name: GPT-4 Turbo
Model ID: gpt-4-turbo-preview
Provider: OpenAI
Type: Chat

API Settings:
  API Key: sk-...
  Organization: org-...
  API Base: https://api.openai.com/v1

Capabilities:
  Streaming: true
  Function Calling: true
  Vision: false
  Max Tokens: 128000

Pricing:
  Input: $0.01 / 1K tokens
  Output: $0.03 / 1K tokens
  Currency: USD

Default Parameters:
  Temperature: 0.7
  Max Tokens: 4096
  Top P: 0.9
  Frequency Penalty: 0.0
  Presence Penalty: 0.0
```

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

5. Set capabilities:
   - **Streaming**: true
   - **Function Calling**: true
   - **Vision**: true
   - **Max Tokens**: 200000

6. Configure pricing:
   - **Input Cost**: $0.003 / 1K tokens
   - **Output Cost**: $0.015 / 1K tokens

7. Test and save

**Anthropic Model Configuration Example:**
```yaml
Name: Claude 3.5 Sonnet
Model ID: claude-3-5-sonnet-20240620
Provider: Anthropic
Type: Chat

API Settings:
  API Key: sk-ant-...
  API Base: https://api.anthropic.com

Capabilities:
  Streaming: true
  Function Calling: true
  Vision: true
  Max Tokens: 200000

Pricing:
  Input: $0.003 / 1K tokens
  Output: $0.015 / 1K tokens

Default Parameters:
  Temperature: 0.7
  Max Tokens: 4096
  Top P: 0.9
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
   - **Endpoint**: Azure endpoint URL
   - **API Version**: API version (e.g., "2024-02-15-preview")
   - **Deployment Name**: Azure deployment name

5. Set capabilities and pricing
6. Test and save

**Azure OpenAI Configuration Example:**
```yaml
Name: GPT-4 (Azure)
Model ID: gpt-4-deployment
Provider: Azure OpenAI
Type: Chat

API Settings:
  API Key: ...
  Endpoint: https://your-resource.openai.azure.com
  API Version: 2024-02-15-preview
  Deployment Name: gpt-4-deployment

Capabilities:
  Streaming: true
  Function Calling: true
  Vision: false
  Max Tokens: 8192

Pricing:
  Input: $0.03 / 1K tokens
  Output: $0.06 / 1K tokens
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
   - Input cost per 1K tokens
   - Output cost per 1K tokens
3. Save changes
4. Review cost reports

## Testing Models

### Test Model Connection

1. Select model
2. Click **Test** button
3. Enter test prompt:
   ```
   Hello, how are you?
   ```
4. Configure test parameters:
   - Temperature
   - Max tokens
5. Click **Run Test**

**Test Results:**
```yaml
Status: Success
Response: "Hello! I'm doing well, thank you for asking..."
Tokens Used:
  Prompt: 6
  Completion: 18
  Total: 24
Response Time: 1.2 seconds
Cost: $0.00024
```

### Test Model Performance

**Performance Test:**
1. Select model
2. Click **Performance Test**
3. Configure test:
   - Number of requests: 10
   - Concurrent requests: 3
   - Test prompt
4. Run test

**Performance Results:**
```yaml
Total Requests: 10
Successful: 10
Failed: 0
Success Rate: 100%

Response Time:
  Average: 1.5s
  Min: 0.8s
  Max: 2.3s
  P50: 1.4s
  P95: 2.1s
  P99: 2.3s

Tokens:
  Total: 450
  Average per request: 45

Cost:
  Total: $0.0135
  Average per request: $0.00135
```

## Monitoring Model Usage

### Usage Statistics

**Overview Metrics:**
- Total requests (24h, 7d, 30d)
- Total tokens (input, output, total)
- Total cost
- Average response time
- Success rate
- Error rate

**View Model Statistics:**
1. Select model
2. Click **Statistics** tab
3. View metrics:
   - **Usage**: Requests, tokens, cost
   - **Performance**: Response time, success rate
   - **Trends**: Daily/weekly/monthly trends
   - **Top Users**: Users by usage
   - **Top Agents**: Agents using this model

4. Filter by date range
5. Export statistics

### Usage by Team

**Team Usage Report:**
```yaml
Support Team:
  Requests: 5,234
  Tokens: 2,456,789
  Cost: $73.70
  Percentage: 45%

Sales Team:
  Requests: 3,456
  Tokens: 1,678,901
  Cost: $50.37
  Percentage: 30%

Engineering Team:
  Requests: 2,890
  Tokens: 1,345,678
  Cost: $40.37
  Percentage: 25%
```

### Cost Analysis

**Cost Breakdown:**
- By model
- By team
- By agent
- By time period

**View Cost Analysis:**
1. Navigate to **Admin** → **Models** → **Costs**
2. Select date range
3. View cost breakdown:
   - Total cost
   - Cost by model
   - Cost by team
   - Cost trends
4. Export report

**Cost Report Example:**
```yaml
Period: 2026-02-01 to 2026-02-11
Total Cost: $1,234.56

By Model:
  GPT-4 Turbo: $678.90 (55%)
  Claude 3.5 Sonnet: $345.67 (28%)
  GPT-3.5 Turbo: $209.99 (17%)

By Team:
  Support Team: $567.89 (46%)
  Sales Team: $345.67 (28%)
  Engineering Team: $321.00 (26%)

Daily Trend:
  2026-02-11: $123.45
  2026-02-10: $109.87
  2026-02-09: $98.76
  ...
```

## Model Status Management

### Model Statuses

**Active:**
- Model is operational
- Available for use
- Appears in model selection

**Inactive:**
- Model is disabled
- Cannot be used
- Hidden from users
- Preserves configuration

**Testing:**
- Model is being tested
- Only available to admins
- Not visible to users

**Deprecated:**
- Model is deprecated
- Still usable but not recommended
- Warning shown to users

### Change Model Status

**Activate Model:**
```bash
1. Select model
2. Click "Activate"
3. Confirm activation
```

**Deactivate Model:**
```bash
1. Select model
2. Click "Deactivate"
3. Optionally notify users
4. Confirm deactivation
```

**Deprecate Model:**
```bash
1. Select model
2. Click "Deprecate"
3. Set deprecation message
4. Set end-of-life date
5. Suggest replacement model
6. Confirm deprecation
```

## Model Limits

### Set Model Limits

**Global Limits:**
1. Navigate to **Admin** → **Models** → **Limits**
2. Configure global limits:
   - Max requests per minute
   - Max tokens per day
   - Max cost per month
   - Max concurrent requests

3. Save limits

**Team Limits:**
1. Navigate to **Teams** → Select team
2. Go to **Limits** tab
3. Configure model limits:
   - Allowed models
   - Max requests per day
   - Max tokens per day
   - Max cost per month

4. Save limits

**Limit Configuration Example:**
```yaml
Global Limits:
  Max Requests per Minute: 1000
  Max Tokens per Day: 10,000,000
  Max Cost per Month: $10,000
  Max Concurrent Requests: 100

Team Limits (Support Team):
  Allowed Models:
    - GPT-4 Turbo
    - Claude 3.5 Sonnet
  Max Requests per Day: 10,000
  Max Tokens per Day: 5,000,000
  Max Cost per Month: $2,000
```

### Rate Limiting

**Rate Limit Configuration:**
```yaml
Model: GPT-4 Turbo
Rate Limits:
  Per User: 60 requests/minute
  Per Team: 300 requests/minute
  Per API Key: 100 requests/minute
  Global: 1000 requests/minute

Burst Limits:
  Per User: 120 requests
  Per Team: 600 requests
```

## Provider Management

### Configure Providers

**OpenAI Provider:**
```yaml
Provider: OpenAI
Status: Active
API Base: https://api.openai.com/v1
Default API Key: sk-...
Organization: org-...
Timeout: 60 seconds
Max Retries: 3
```

**Anthropic Provider:**
```yaml
Provider: Anthropic
Status: Active
API Base: https://api.anthropic.com
Default API Key: sk-ant-...
Timeout: 60 seconds
Max Retries: 3
```

**Azure OpenAI Provider:**
```yaml
Provider: Azure OpenAI
Status: Active
Default Endpoint: https://your-resource.openai.azure.com
Default API Version: 2024-02-15-preview
Timeout: 60 seconds
Max Retries: 3
```

### Update Provider Settings

1. Navigate to **Admin** → **Models** → **Providers**
2. Select provider
3. Update settings:
   - API base URL
   - Default API key
   - Timeout
   - Retry policy
4. Test connection
5. Save changes

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
- Cost alerts triggered

**Solutions:**

1. **Review usage:**
   ```bash
   Admin → Models → Costs
   View cost breakdown
   Identify high-usage teams/agents
   ```

2. **Optimize usage:**
   - Use cheaper models for simple tasks
   - Reduce max_tokens
   - Enable caching
   - Optimize prompts

3. **Set limits:**
   - Daily token limits
   - Monthly cost limits
   - Cost alerts

4. **Review agents:**
   - Check agent configurations
   - Identify inefficient agents
   - Optimize system prompts

### Slow Model Responses

**Symptoms:**
- Long response times
- Timeouts

**Solutions:**

1. **Check performance metrics:**
   ```bash
   Admin → Models → Statistics
   View response time trends
   ```

2. **Optimize requests:**
   - Reduce max_tokens
   - Use streaming
   - Enable caching
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
- Set appropriate pricing
- Configure reasonable defaults
- Monitor usage and costs
- Rotate API keys regularly
- Document model purposes
- Keep models updated

**❌ Don't:**
- Enable untested models
- Forget to set pricing
- Use extreme parameters
- Ignore cost alerts
- Use static API keys forever
- Skip documentation
- Use deprecated models

### Cost Management

**✅ Do:**
- Set cost limits
- Monitor usage daily
- Use cheaper models when possible
- Enable caching
- Optimize prompts
- Review costs regularly
- Set up alerts

**❌ Don't:**
- Allow unlimited spending
- Ignore cost trends
- Use expensive models for everything
- Skip caching
- Use verbose prompts
- Forget to review
- Disable alerts

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

**Available Actions:**
- Activate/Deactivate models
- Update pricing
- Rotate API keys
- Export configuration

**Perform Bulk Action:**
```bash
1. Select models (checkbox)
2. Click "Bulk Actions"
3. Choose action
4. Configure options
5. Review changes
6. Confirm execution
```

## API Access

### Manage Models via API

See [Models API](../../api-reference/endpoints/models.md) for details.

**Common Operations:**
```python
# List all models
models = api.get("/api/v1/models")

# Create model
model = api.post("/api/v1/models", json={
    "name": "GPT-4 Turbo",
    "model_id": "gpt-4-turbo-preview",
    "provider": "openai",
    "config": {"api_key": "sk-..."}
})

# Test model
test_result = api.post(f"/api/v1/models/{model_id}/test", json={
    "prompt": "Hello, how are you?",
    "temperature": 0.7
})

# Get model usage
usage = api.get(f"/api/v1/models/{model_id}/usage", params={
    "start_date": "2026-02-01",
    "end_date": "2026-02-11"
})
```

## Related Documentation

- [Models API](../../api-reference/endpoints/models.md) - API reference
- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using models
- [System Settings](../settings/system-settings.md) - System config
- [Cost Optimization](../../best-practices/cost-optimization.md) - Cost best practices

---

**Last Updated**: 2026-02-11
