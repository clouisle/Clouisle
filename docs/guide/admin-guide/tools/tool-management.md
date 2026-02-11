# Tool Management

This guide covers how to manage tools and integrations as an administrator.

## Overview

As an administrator, you can:

- **View all tools**: Access all available tools
- **Add tools**: Configure new tools and integrations
- **Update tools**: Modify tool settings
- **Test tools**: Verify tool functionality
- **Monitor usage**: Track tool usage and performance
- **Set limits**: Control tool access and usage
- **Manage integrations**: Configure third-party services

## Accessing Tool Management

### Admin Dashboard

1. Log in as administrator
2. Navigate to **Admin** → **Tools**
3. View tool management interface

### Tool List View

The tool list shows:

- **Tool name**
- **Type** (Built-in, Custom, Integration)
- **Category** (Search, Data, Communication, etc.)
- **Status** (Active, Inactive, Testing)
- **Usage** (calls, success rate)
- **Last used**

**Filters:**
- Type
- Category
- Status
- Date range

**Search:**
- Search by tool name or description

## Built-in Tools

### Available Built-in Tools

**Search Tools:**
- **Web Search**: Search the internet
- **Knowledge Base Search**: Search internal KBs
- **Document Search**: Search documents

**Data Tools:**
- **Calculator**: Perform calculations
- **Date/Time**: Get current date/time
- **Unit Converter**: Convert units

**Communication Tools:**
- **Email**: Send emails
- **Slack**: Send Slack messages
- **Webhook**: Trigger webhooks

**Utility Tools:**
- **JSON Parser**: Parse JSON data
- **Text Processor**: Process text
- **File Reader**: Read files

### Configure Built-in Tools

**Web Search Tool:**
```yaml
Tool: Web Search
Type: Built-in
Category: Search
Status: Active

Configuration:
  Search Engine: Google
  API Key: AIza...
  Max Results: 5
  Safe Search: Moderate
  Language: en
  Region: US

Limits:
  Max Calls per Day: 1000
  Max Calls per Agent: 100
  Timeout: 10 seconds
```

**Update Configuration:**
1. Select tool
2. Click **Configure**
3. Update settings:
   - API credentials
   - Parameters
   - Limits
4. Test tool
5. Save changes

**Calculator Tool:**
```yaml
Tool: Calculator
Type: Built-in
Category: Data
Status: Active

Configuration:
  Precision: 10 decimals
  Allow Complex Numbers: true
  Max Expression Length: 1000 chars

Limits:
  Max Calls per Minute: 60
  Timeout: 5 seconds
```

**Email Tool:**
```yaml
Tool: Email
Type: Built-in
Category: Communication
Status: Active

Configuration:
  SMTP Host: smtp.gmail.com
  SMTP Port: 587
  SMTP Security: TLS
  From Email: noreply@your-domain.com
  From Name: Clouisle

Limits:
  Max Emails per Day: 1000
  Max Recipients per Email: 10
  Max Attachment Size: 10 MB
```

## Custom Tools

### Create Custom Tool

1. Click **Add Tool** button
2. Select **Custom Tool**
3. Fill in tool details:
   - **Name**: Tool display name
   - **Description**: Tool purpose
   - **Category**: Tool category
   - **Icon**: Tool icon

4. Configure tool:
   - **Endpoint**: API endpoint URL
   - **Method**: HTTP method (GET, POST, etc.)
   - **Authentication**: Auth method
   - **Headers**: Custom headers
   - **Parameters**: Input parameters
   - **Response**: Response format

5. Test tool
6. Save tool

**Custom Tool Example:**
```yaml
Name: CRM Lookup
Description: Look up customer information in CRM
Category: Data
Type: Custom

Endpoint Configuration:
  URL: https://api.crm.example.com/customers/{customer_id}
  Method: GET
  Authentication: API Key
  API Key Header: X-API-Key
  API Key: crm_...
  Timeout: 30 seconds

Input Parameters:
  - name: customer_id
    type: string
    required: true
    description: Customer ID to lookup

Response Format:
  type: json
  schema:
    customer_id: string
    name: string
    email: string
    phone: string
    status: string

Example Request:
  GET https://api.crm.example.com/customers/12345
  Headers:
    X-API-Key: crm_...

Example Response:
  {
    "customer_id": "12345",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-0123",
    "status": "active"
  }
```

### Custom Tool with POST

**Create Record Tool:**
```yaml
Name: Create Support Ticket
Description: Create a support ticket in ticketing system
Category: Communication
Type: Custom

Endpoint Configuration:
  URL: https://api.tickets.example.com/tickets
  Method: POST
  Authentication: Bearer Token
  Token: Bearer tk_...
  Content-Type: application/json
  Timeout: 30 seconds

Input Parameters:
  - name: title
    type: string
    required: true
    description: Ticket title

  - name: description
    type: string
    required: true
    description: Ticket description

  - name: priority
    type: enum
    required: false
    default: medium
    options: [low, medium, high, urgent]
    description: Ticket priority

  - name: assignee
    type: string
    required: false
    description: Assignee email

Response Format:
  type: json
  schema:
    ticket_id: string
    status: string
    created_at: string

Example Request:
  POST https://api.tickets.example.com/tickets
  Headers:
    Authorization: Bearer tk_...
    Content-Type: application/json
  Body:
    {
      "title": "Customer inquiry",
      "description": "Customer asking about pricing",
      "priority": "medium",
      "assignee": "support@example.com"
    }

Example Response:
  {
    "ticket_id": "TKT-12345",
    "status": "open",
    "created_at": "2026-02-11T14:30:00Z"
  }
```

### Edit Custom Tool

1. Select custom tool
2. Click **Edit**
3. Modify:
   - Tool details
   - Endpoint configuration
   - Parameters
   - Response format
4. Test tool
5. Save changes

### Delete Custom Tool

1. Select custom tool
2. Click **Delete**
3. Review impact:
   - Agents using this tool
   - Workflows using this tool
4. Confirm deletion

## Integration Tools

### Available Integrations

**CRM Integrations:**
- Salesforce
- HubSpot
- Pipedrive

**Communication:**
- Slack
- Microsoft Teams
- Discord

**Productivity:**
- Google Workspace
- Microsoft 365
- Notion

**Development:**
- GitHub
- GitLab
- Jira

### Configure Integration

**Slack Integration:**
```yaml
Integration: Slack
Type: Integration
Category: Communication
Status: Active

Configuration:
  Workspace: your-workspace
  Bot Token: xoxb-...
  Signing Secret: ...
  App ID: A...

Capabilities:
  - Send messages
  - Post to channels
  - Send DMs
  - Upload files
  - Get channel list
  - Get user list

Limits:
  Max Messages per Minute: 60
  Max File Size: 100 MB
```

**Setup Slack Integration:**
1. Navigate to **Tools** → **Integrations**
2. Click **Add Integration**
3. Select **Slack**
4. Click **Connect to Slack**
5. Authorize app in Slack
6. Configure settings:
   - Default channel
   - Message format
   - Notification preferences
7. Test integration
8. Save settings

**GitHub Integration:**
```yaml
Integration: GitHub
Type: Integration
Category: Development
Status: Active

Configuration:
  Organization: your-org
  Access Token: ghp_...
  Webhook Secret: ...

Capabilities:
  - Create issues
  - Create pull requests
  - Get repository info
  - Search code
  - Get commit history

Limits:
  Rate Limit: 5000 requests/hour
  Max File Size: 100 MB
```

## Testing Tools

### Test Tool

1. Select tool
2. Click **Test** button
3. Enter test parameters
4. Click **Run Test**

**Test Results:**
```yaml
Tool: Web Search
Test Parameters:
  query: "artificial intelligence"
  max_results: 5

Status: Success
Response Time: 1.2 seconds
Results:
  - title: "Artificial Intelligence - Wikipedia"
    url: "https://en.wikipedia.org/wiki/Artificial_intelligence"
    snippet: "Artificial intelligence (AI) is intelligence..."

  - title: "What is AI? | IBM"
    url: "https://www.ibm.com/topics/artificial-intelligence"
    snippet: "Artificial intelligence leverages computers..."

  [3 more results]

Metadata:
  total_results: 5
  search_time: 0.8s
  api_calls: 1
```

### Test Custom Tool

**Test CRM Lookup:**
```yaml
Tool: CRM Lookup
Test Parameters:
  customer_id: "12345"

Status: Success
Response Time: 0.5 seconds
Response:
  {
    "customer_id": "12345",
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1-555-0123",
    "status": "active"
  }

Validation: Passed
  ✓ Response format matches schema
  ✓ All required fields present
  ✓ Data types correct
```

## Monitoring Tool Usage

### Usage Statistics

**Overview Metrics:**
- Total tool calls (24h, 7d, 30d)
- Success rate
- Average response time
- Error rate
- Most used tools

**View Tool Statistics:**
1. Select tool
2. Click **Statistics** tab
3. View metrics:
   - **Usage**: Calls, success rate
   - **Performance**: Response time
   - **Errors**: Error types, frequency
   - **Top Users**: Users by usage
   - **Top Agents**: Agents using this tool

4. Filter by date range
5. Export statistics

**Tool Usage Report:**
```yaml
Tool: Web Search
Period: 2026-02-01 to 2026-02-11

Usage:
  Total Calls: 5,234
  Successful: 5,123 (97.9%)
  Failed: 111 (2.1%)

Performance:
  Average Response Time: 1.2s
  Min: 0.5s
  Max: 5.3s
  P50: 1.1s
  P95: 2.8s
  P99: 4.2s

Top Users:
  1. john.doe@example.com: 1,234 calls
  2. jane.smith@example.com: 987 calls
  3. bob.wilson@example.com: 765 calls

Top Agents:
  1. Customer Support Agent: 2,345 calls
  2. Research Assistant: 1,456 calls
  3. Content Creator: 789 calls

Error Breakdown:
  Rate Limit Exceeded: 45 (40.5%)
  Timeout: 34 (30.6%)
  Invalid Query: 23 (20.7%)
  API Error: 9 (8.1%)
```

### Usage by Team

**Team Usage Report:**
```yaml
Period: 2026-02-01 to 2026-02-11

Support Team:
  Total Calls: 2,345
  Tools Used:
    - Web Search: 1,234 calls
    - CRM Lookup: 678 calls
    - Email: 433 calls

Sales Team:
  Total Calls: 1,678
  Tools Used:
    - CRM Lookup: 987 calls
    - Email: 456 calls
    - Calendar: 235 calls

Engineering Team:
  Total Calls: 1,211
  Tools Used:
    - GitHub: 567 calls
    - Web Search: 345 calls
    - Calculator: 299 calls
```

## Tool Limits

### Set Tool Limits

**Global Limits:**
1. Navigate to **Admin** → **Tools** → **Limits**
2. Configure global limits:
   - Max calls per minute
   - Max calls per day
   - Max concurrent calls
   - Timeout

3. Save limits

**Tool-Specific Limits:**
1. Select tool
2. Click **Limits** tab
3. Configure limits:
   - Per user
   - Per team
   - Per agent
   - Global

4. Save limits

**Limit Configuration:**
```yaml
Tool: Web Search

Global Limits:
  Max Calls per Minute: 100
  Max Calls per Day: 10,000
  Max Concurrent Calls: 10
  Timeout: 10 seconds

Per User Limits:
  Max Calls per Minute: 10
  Max Calls per Day: 1,000

Per Team Limits:
  Max Calls per Minute: 50
  Max Calls per Day: 5,000

Per Agent Limits:
  Max Calls per Execution: 5
  Max Calls per Day: 500
```

### Rate Limiting

**Rate Limit Behavior:**
- Requests exceeding limit are rejected
- 429 status code returned
- Retry-After header included
- User notified of limit

**Rate Limit Response:**
```json
{
  "code": 5400,
  "msg": "Rate limit exceeded",
  "data": {
    "tool": "web_search",
    "limit": "10 calls per minute",
    "retry_after": 45
  }
}
```

## Tool Status Management

### Tool Statuses

**Active:**
- Tool is operational
- Available for use
- Appears in tool selection

**Inactive:**
- Tool is disabled
- Cannot be used
- Hidden from users

**Testing:**
- Tool is being tested
- Only available to admins
- Not visible to users

**Deprecated:**
- Tool is deprecated
- Still usable but not recommended
- Warning shown to users

### Change Tool Status

**Activate Tool:**
```bash
1. Select tool
2. Click "Activate"
3. Confirm activation
```

**Deactivate Tool:**
```bash
1. Select tool
2. Click "Deactivate"
3. Review impact
4. Confirm deactivation
```

## Troubleshooting

### Tool Call Failed

**Symptoms:**
- Tool returns error
- Timeout
- Invalid response

**Solutions:**

1. **Check tool configuration:**
   - Verify credentials
   - Check endpoint URL
   - Test connectivity

2. **Check tool logs:**
   ```bash
   Admin → Tools → Select tool
   Logs → View recent errors
   ```

3. **Common errors:**
   - **Authentication failed**: Invalid credentials
   - **Timeout**: Increase timeout or check endpoint
   - **Rate limit**: Wait or increase limit
   - **Invalid parameters**: Check parameter format

4. **Test tool:**
   ```bash
   Select tool
   Click "Test"
   Review test results
   ```

### High Tool Costs

**Symptoms:**
- Unexpected API costs
- Cost alerts triggered

**Solutions:**

1. **Review usage:**
   ```bash
   Admin → Tools → Costs
   View cost breakdown
   ```

2. **Optimize usage:**
   - Set stricter limits
   - Cache results
   - Use cheaper alternatives
   - Optimize tool calls

3. **Set cost alerts:**
   - Daily cost limit
   - Monthly cost limit
   - Alert thresholds

### Slow Tool Response

**Symptoms:**
- Long response times
- Timeouts

**Solutions:**

1. **Check performance metrics:**
   ```bash
   Admin → Tools → Statistics
   View response time trends
   ```

2. **Optimize tool:**
   - Increase timeout
   - Reduce data transfer
   - Use caching
   - Optimize endpoint

3. **Check external service:**
   - Review service status
   - Check for outages
   - Contact support

## Best Practices

### Tool Configuration

**✅ Do:**
- Test tools before enabling
- Set appropriate limits
- Monitor usage and costs
- Rotate credentials regularly
- Document tool purposes
- Keep tools updated
- Use error handling

**❌ Don't:**
- Enable untested tools
- Allow unlimited usage
- Ignore cost alerts
- Use static credentials forever
- Skip documentation
- Use deprecated tools
- Ignore errors

### Security

**✅ Do:**
- Use secure authentication
- Rotate API keys regularly
- Restrict tool access
- Enable audit logging
- Monitor for abuse
- Use HTTPS only
- Validate responses

**❌ Don't:**
- Use weak authentication
- Use static API keys forever
- Allow unrestricted access
- Disable audit logs
- Ignore suspicious activity
- Allow HTTP connections
- Trust responses blindly

### Performance

**✅ Do:**
- Set appropriate timeouts
- Use caching where possible
- Monitor response times
- Optimize tool calls
- Use async processing
- Handle errors gracefully

**❌ Don't:**
- Use very long timeouts
- Skip caching
- Ignore performance metrics
- Make unnecessary calls
- Use synchronous processing
- Ignore errors

## API Access

### Manage Tools via API

**List Tools:**
```python
# List all tools
tools = api.get("/api/v1/tools")

# List tools by category
tools = api.get("/api/v1/tools", params={"category": "search"})
```

**Call Tool:**
```python
# Call tool
result = api.post("/api/v1/tools/web_search/call", json={
    "query": "artificial intelligence",
    "max_results": 5
})
```

**Get Tool Usage:**
```python
# Get tool usage statistics
usage = api.get("/api/v1/tools/web_search/usage", params={
    "start_date": "2026-02-01",
    "end_date": "2026-02-11"
})
```

## Related Documentation

- [Agent Configuration](../../user-guide/agents/agent-configuration.md) - Using tools with agents
- [Workflow Nodes](../../user-guide/workflows/workflow-nodes.md) - Tool nodes in workflows
- [API Reference](../../api-reference/endpoints/tools.md) - Tools API
- [Security Best Practices](../../best-practices/security.md) - Security guide

---

**Last Updated**: 2026-02-11
