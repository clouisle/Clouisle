# Workflow Nodes Reference

This document provides a complete reference for all workflow node types in Clouisle.

## Overview

Workflow nodes are building blocks for creating automated processes. Each node type serves a specific purpose and can be configured with various parameters.

## Node Categories

- **Input/Output**: Start, End, Input, Output
- **Processing**: LLM, Tool, HTTP, Transform, Code
- **Control Flow**: Condition, Loop, Parallel, Wait, Switch
- **Integration**: Database, API, Email, Webhook
- **Utility**: Variable, Log, Delay, Merge

## Input/Output Nodes

### Start Node

Entry point for workflow execution.

**Configuration:**
```yaml
Type: Start
Input Parameters:
  - name: parameter_name
    type: string|number|boolean|object|array
    required: true|false
    default: value
    description: Parameter description
```

**Example:**
```yaml
Input Parameters:
  - name: customer_email
    type: string
    required: true
    description: Customer email address

  - name: priority
    type: string
    required: false
    default: medium
    description: Inquiry priority
```

**Output:**
- All input parameters available as variables

### End Node

Exit point for workflow execution.

**Configuration:**
```yaml
Type: End
Output:
  status: success|error
  data: output_data
  message: completion_message
```

**Example:**
```yaml
Output:
  status: success
  data:
    ticket_id: "{{ticket.id}}"
    response: "{{response}}"
  message: "Inquiry processed successfully"
```

### Input Node

Accept additional input during execution.

**Configuration:**
```yaml
Type: Input
Prompt: "Enter additional information"
Fields:
  - name: field_name
    type: string
    required: true
Output Variable: user_input
```

### Output Node

Return intermediate results.

**Configuration:**
```yaml
Type: Output
Data:
  key: value
  result: "{{variable}}"
```

## Processing Nodes

### LLM Node

Call language model for text processing.

**Configuration:**
```yaml
Type: LLM
Name: Node name
Model: gpt-4-turbo|claude-3-5-sonnet|...
System Prompt: System instructions
User Prompt: User message with {{variables}}
Temperature: 0.0-1.0
Max Tokens: 1-128000
Top P: 0.0-1.0
Output Variable: variable_name
Output Format: text|json
```

**Example:**
```yaml
Type: LLM
Name: Analyze Customer Inquiry
Model: gpt-4-turbo
System Prompt: |
  You are a customer service analyst.
  Classify inquiries by type and urgency.

User Prompt: |
  Analyze this inquiry:
  {{inquiry_text}}

  Return JSON:
  {
    "type": "technical|billing|general",
    "urgency": "low|medium|high",
    "summary": "brief summary"
  }

Temperature: 0.3
Max Tokens: 500
Output Format: json
Output Variable: analysis
```

**Output:**
```javascript
{
  "type": "technical",
  "urgency": "high",
  "summary": "Password reset issue"
}
```

### Tool Node

Execute a tool or function.

**Configuration:**
```yaml
Type: Tool
Name: Node name
Tool: tool_id
Parameters:
  param1: value
  param2: "{{variable}}"
Timeout: 30s
Output Variable: variable_name
```

**Example:**
```yaml
Type: Tool
Name: Search Knowledge Base
Tool: kb_search
Parameters:
  query: "{{inquiry_text}}"
  kb_id: "kb-456"
  top_k: 5
  score_threshold: 0.7
Timeout: 10s
Output Variable: kb_results
```

**Available Tools:**
- `web_search`: Search the internet
- `kb_search`: Search knowledge base
- `calculator`: Perform calculations
- `datetime`: Get date/time
- `email`: Send email
- Custom tools

### HTTP Node

Make HTTP requests to external APIs.

**Configuration:**
```yaml
Type: HTTP
Name: Node name
Method: GET|POST|PUT|PATCH|DELETE
URL: https://api.example.com/endpoint
Headers:
  Header-Name: value
  Authorization: Bearer {{token}}
Query Parameters:
  param: value
Body: |
  {
    "key": "{{variable}}"
  }
Timeout: 30s
Retry: 3
Output Variable: variable_name
```

**Example:**
```yaml
Type: HTTP
Name: Create Support Ticket
Method: POST
URL: https://api.tickets.example.com/tickets
Headers:
  Authorization: Bearer {{api_token}}
  Content-Type: application/json
Body: |
  {
    "title": "{{analysis.summary}}",
    "description": "{{inquiry_text}}",
    "priority": "{{priority}}",
    "customer_email": "{{customer_email}}"
  }
Timeout: 30s
Retry: 3
Output Variable: ticket
```

**Output:**
```javascript
{
  "status": 200,
  "headers": {...},
  "body": {
    "id": "TKT-12345",
    "status": "open",
    "created_at": "2026-02-11T16:00:00Z"
  }
}
```

### Transform Node

Transform data using JavaScript.

**Configuration:**
```yaml
Type: Transform
Name: Node name
Transform: |
  // JavaScript code
  return {
    key: value
  };
Output Variable: variable_name
```

**Example:**
```yaml
Type: Transform
Name: Format Response
Transform: |
  return {
    customer_email: input.customer_email,
    ticket_id: ticket.body.id,
    response: response,
    kb_articles: kb_results.map(r => ({
      id: r.id,
      title: r.title,
      score: r.score
    })),
    processed_at: new Date().toISOString()
  };
Output Variable: formatted_response
```

**Available Functions:**
```javascript
// String operations
text.toUpperCase()
text.toLowerCase()
text.trim()
text.split(separator)
text.replace(old, new)
text.substring(start, end)

// Array operations
array.map(fn)
array.filter(fn)
array.reduce(fn, initial)
array.find(fn)
array.sort(fn)
array.slice(start, end)
array.length

// Object operations
Object.keys(obj)
Object.values(obj)
Object.entries(obj)
Object.assign(target, source)
{...obj, key: value}

// Math operations
Math.round(num)
Math.floor(num)
Math.ceil(num)
Math.max(...numbers)
Math.min(...numbers)
Math.random()

// Date operations
new Date()
Date.now()
date.toISOString()
date.getTime()
```

### Code Node

Execute custom code (Python or JavaScript).

**Configuration:**
```yaml
Type: Code
Name: Node name
Language: python|javascript
Code: |
  # Your code here
  return result
Timeout: 60s
Output Variable: variable_name
```

**Example (Python):**
```yaml
Type: Code
Name: Calculate Sentiment
Language: python
Code: |
  from textblob import TextBlob

  text = input_data['inquiry_text']
  blob = TextBlob(text)
  sentiment = blob.sentiment.polarity

  return {
    'sentiment': 'positive' if sentiment > 0 else 'negative' if sentiment < 0 else 'neutral',
    'score': sentiment
  }
Output Variable: sentiment
```

## Control Flow Nodes

### Condition Node

Branch execution based on condition.

**Configuration:**
```yaml
Type: Condition
Name: Node name
Condition: boolean_expression
True Branch: node_id
False Branch: node_id
```

**Example:**
```yaml
Type: Condition
Name: Check Urgency
Condition: analysis.urgency == "high"
True Branch: notify-manager
False Branch: assign-agent
```

**Condition Syntax:**
```javascript
// Comparison
value == "string"
number > 10
score >= 0.8
status != "closed"

// Logical operators
urgency == "high" && type == "technical"
priority == "low" || priority == "medium"
!(status == "completed")

// String operations
text.includes("keyword")
email.endsWith("@example.com")
name.startsWith("Mr.")

// Array operations
array.includes(item)
array.length > 0
array.some(item => item.score > 0.8)

// Null checks
variable != null
variable !== undefined
variable || default_value
```

### Switch Node

Multi-way branching.

**Configuration:**
```yaml
Type: Switch
Name: Node name
Expression: variable_or_expression
Cases:
  - value: case1
    branch: node_id
  - value: case2
    branch: node_id
Default Branch: node_id
```

**Example:**
```yaml
Type: Switch
Name: Route by Type
Expression: analysis.type
Cases:
  - value: technical
    branch: technical-team
  - value: billing
    branch: billing-team
  - value: general
    branch: general-support
Default Branch: escalate
```

### Loop Node

Iterate over items.

**Configuration:**
```yaml
Type: Loop
Name: Node name
Loop Over: array_variable
Item Variable: item
Index Variable: index
Max Iterations: 100
Body:
  - node1
  - node2
Output Variable: results
```

**Example:**
```yaml
Type: Loop
Name: Process KB Results
Loop Over: kb_results
Item Variable: article
Index Variable: i
Max Iterations: 10
Body:
  - Transform: Extract Content
  - LLM: Summarize Article
Output Variable: summaries
```

**Loop Control:**
```javascript
// Break loop
if (condition) {
  break;
}

// Continue to next iteration
if (condition) {
  continue;
}
```

### Parallel Node

Execute multiple branches concurrently.

**Configuration:**
```yaml
Type: Parallel
Name: Node name
Branches:
  - branch1:
      - node1
      - node2
  - branch2:
      - node3
      - node4
Wait For: all|any|first
Timeout: 60s
Output Variable: results
```

**Example:**
```yaml
Type: Parallel
Name: Multi-Source Search
Branches:
  - kb_search:
      - Tool: Search KB
  - web_search:
      - Tool: Web Search
  - api_call:
      - HTTP: Call External API
Wait For: all
Timeout: 30s
Output Variable: search_results
```

**Wait For Options:**
- `all`: Wait for all branches to complete
- `any`: Wait for any branch to complete
- `first`: Return first completed branch

### Wait Node

Pause execution for specified duration.

**Configuration:**
```yaml
Type: Wait
Name: Node name
Duration: 5s|1m|1h
Until: timestamp
Condition: boolean_expression
```

**Example:**
```yaml
Type: Wait
Name: Wait for Processing
Duration: 30s
```

**Duration Formats:**
- `5s`: 5 seconds
- `1m`: 1 minute
- `1h`: 1 hour
- `1d`: 1 day

## Integration Nodes

### Database Node

Query or update database.

**Configuration:**
```yaml
Type: Database
Name: Node name
Operation: query|insert|update|delete
Connection: connection_id
Query: |
  SELECT * FROM table
  WHERE condition = {{variable}}
Parameters:
  param1: value
Output Variable: variable_name
```

**Example:**
```yaml
Type: Database
Name: Get Customer Info
Operation: query
Connection: postgres-main
Query: |
  SELECT * FROM customers
  WHERE email = $1
Parameters:
  - "{{customer_email}}"
Output Variable: customer
```

### Email Node

Send email messages.

**Configuration:**
```yaml
Type: Email
Name: Node name
To: recipient@example.com
Cc: cc@example.com
Bcc: bcc@example.com
Subject: Email subject
Body: |
  Email body with {{variables}}
Attachments:
  - file_url
```

**Example:**
```yaml
Type: Email
Name: Send Response to Customer
To: "{{customer_email}}"
Subject: "Re: {{analysis.summary}}"
Body: |
  Dear Customer,

  {{response}}

  Ticket ID: {{ticket.body.id}}

  Best regards,
  Support Team
```

### Webhook Node

Trigger external webhook.

**Configuration:**
```yaml
Type: Webhook
Name: Node name
URL: https://webhook.example.com
Method: POST
Headers:
  Content-Type: application/json
Body: |
  {
    "event": "workflow_completed",
    "data": {{output}}
  }
Retry: 3
```

## Utility Nodes

### Variable Node

Set or update variables.

**Configuration:**
```yaml
Type: Variable
Name: Node name
Variables:
  var1: value
  var2: "{{expression}}"
```

**Example:**
```yaml
Type: Variable
Name: Set Defaults
Variables:
  priority: "{{priority || 'medium'}}"
  assigned_to: "{{assigned_to || 'unassigned'}}"
  created_at: "{{new Date().toISOString()}}"
```

### Log Node

Log information for debugging.

**Configuration:**
```yaml
Type: Log
Name: Node name
Level: debug|info|warn|error
Message: Log message with {{variables}}
Data:
  key: value
```

**Example:**
```yaml
Type: Log
Name: Log Analysis Result
Level: info
Message: "Inquiry analyzed: {{analysis.type}} - {{analysis.urgency}}"
Data:
  customer: "{{customer_email}}"
  analysis: "{{analysis}}"
```

### Delay Node

Add delay between nodes.

**Configuration:**
```yaml
Type: Delay
Name: Node name
Duration: 5s
```

### Merge Node

Merge multiple inputs.

**Configuration:**
```yaml
Type: Merge
Name: Node name
Inputs:
  - input1
  - input2
Strategy: first|all|any
Output Variable: merged
```

## Node Properties

### Common Properties

All nodes share these properties:

```yaml
id: unique_node_id
type: node_type
name: Display name
description: Node description
position:
  x: 100
  y: 200
```

### Input/Output Ports

**Input Ports:**
- Receive data from previous nodes
- Can have multiple inputs (Merge node)

**Output Ports:**
- Send data to next nodes
- Success output (green)
- Error output (red)
- Conditional outputs (blue)

### Error Handling

**Configure Error Handling:**
```yaml
On Error:
  action: continue|stop|retry
  retry_count: 3
  retry_delay: 5s
  fallback_value: default_value
```

## Best Practices

### Node Naming

**✅ Do:**
- Use descriptive names
- Follow naming convention
- Include action verb
- Be specific

**Examples:**
- "Analyze Customer Inquiry"
- "Search Knowledge Base"
- "Send Email to Customer"
- "Create Support Ticket"

**❌ Don't:**
- Use generic names ("Node 1", "Process")
- Use abbreviations
- Skip naming

### Node Configuration

**✅ Do:**
- Set appropriate timeouts
- Add error handling
- Use variables
- Validate inputs
- Add logging
- Document complex logic

**❌ Don't:**
- Use very long timeouts
- Skip error handling
- Hardcode values
- Skip validation
- Forget logging
- Leave complex logic undocumented

### Performance

**✅ Do:**
- Use parallel execution
- Set reasonable timeouts
- Limit loop iterations
- Cache results
- Optimize transforms

**❌ Don't:**
- Execute sequentially when parallel is possible
- Use infinite timeouts
- Create infinite loops
- Repeat expensive operations
- Use complex transforms

## Node Limits

**Per Workflow:**
- Max nodes: 100
- Max depth: 20 levels
- Max loop iterations: 1000
- Max parallel branches: 10

**Per Node:**
- Max timeout: 300s (5 minutes)
- Max retries: 5
- Max output size: 10 MB

## Related Documentation

- [Workflow Builder](./workflow-builder.md) - Building workflows
- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow History](./workflow-history.md) - Execution history
- [Workflow Management](../../admin-guide/workflows/workflow-management.md) - Admin guide

---

**Last Updated**: 2026-02-11
