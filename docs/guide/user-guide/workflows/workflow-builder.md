# Workflow Builder

This guide covers how to build and design workflows in Clouisle.

## Overview

The workflow builder allows you to:

- **Create workflows**: Design automated processes
- **Add nodes**: Use various node types
- **Connect nodes**: Define execution flow
- **Configure nodes**: Set node parameters
- **Test workflows**: Validate before deployment
- **Deploy workflows**: Activate for use

## Accessing Workflow Builder

### Create New Workflow

1. Navigate to **Workflows**
2. Click **Create Workflow** button
3. Enter workflow details:
   - Name
   - Description
   - Team
4. Click **Create**
5. Workflow builder opens

### Edit Existing Workflow

1. Navigate to **Workflows**
2. Click on workflow to edit
3. Click **Edit** button
4. Workflow builder opens

## Workflow Builder Interface

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Workflow Name                    [Test] [Save] [×]  │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│  Nodes   │                                          │
│  Panel   │         Canvas                           │
│          │         (Drag & Drop)                    │
│  ┌────┐  │                                          │
│  │Start│  │    ┌────────┐                          │
│  └────┘  │    │  Node  │                          │
│          │    └────────┘                          │
│  ┌────┐  │         │                               │
│  │ LLM│  │         ▼                               │
│  └────┘  │    ┌────────┐                          │
│          │    │  Node  │                          │
│  ┌────┐  │    └────────┘                          │
│  │Tool│  │                                          │
│  └────┘  │                                          │
│          │                                          │
│  ┌────┐  │                                          │
│  │ End│  │                                          │
│  └────┘  │                                          │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
```

### Components

**Nodes Panel (Left):**
- Available node types
- Drag to canvas
- Organized by category

**Canvas (Center):**
- Workflow design area
- Drag and drop nodes
- Connect nodes
- Zoom and pan

**Properties Panel (Right):**
- Node configuration
- Node settings
- Variables

**Toolbar (Top):**
- Save workflow
- Test workflow
- Deploy workflow
- Undo/Redo
- Zoom controls

## Building a Workflow

### Step 1: Add Start Node

Every workflow begins with a Start node.

**Start Node:**
- Entry point for workflow
- Defines input parameters
- Automatically added

**Configure Start Node:**
```yaml
Input Parameters:
  - name: customer_email
    type: string
    required: true
  - name: inquiry_text
    type: string
    required: true
  - name: priority
    type: enum
    values: [low, medium, high]
    default: medium
```

### Step 2: Add Processing Nodes

Add nodes to process data.

**Available Node Types:**
- LLM: Call language model
- Tool: Execute tool
- HTTP: Make HTTP request
- Transform: Transform data
- Condition: Branch logic
- Loop: Iterate over items
- Parallel: Execute in parallel

**Add Node:**
1. Drag node from panel
2. Drop on canvas
3. Node appears

### Step 3: Connect Nodes

Connect nodes to define flow.

**Connect Nodes:**
1. Click output port of source node
2. Drag to input port of target node
3. Connection created

**Connection Types:**
- **Success**: Green line (default path)
- **Error**: Red line (error handling)
- **Conditional**: Blue line (condition branch)

### Step 4: Configure Nodes

Configure each node's settings.

**Configure Node:**
1. Click on node
2. Properties panel opens
3. Set parameters
4. Save configuration

**Example - LLM Node:**
```yaml
Node: Analyze Inquiry
Type: LLM
Model: GPT-4 Turbo
Prompt: |
  Analyze the following customer inquiry:
  {{inquiry_text}}

  Classify the inquiry type and urgency.

  Return JSON:
  {
    "type": "technical|billing|general",
    "urgency": "low|medium|high",
    "summary": "brief summary"
  }

Temperature: 0.3
Max Tokens: 500
Output Variable: analysis
```

### Step 5: Add End Node

Every workflow ends with an End node.

**End Node:**
- Exit point for workflow
- Defines output
- Returns results

**Configure End Node:**
```yaml
Output:
  status: success
  analysis: {{analysis}}
  assigned_agent: {{assigned_agent}}
  response: {{response}}
```

### Step 6: Test Workflow

Test before deployment.

**Test Workflow:**
1. Click **Test** button
2. Enter test input
3. Run workflow
4. Review results
5. Check each node execution
6. Fix any errors

**Test Input Example:**
```json
{
  "customer_email": "test@example.com",
  "inquiry_text": "How do I reset my password?",
  "priority": "medium"
}
```

### Step 7: Save and Deploy

Save and activate workflow.

**Save Workflow:**
1. Click **Save** button
2. Workflow saved as draft

**Deploy Workflow:**
1. Click **Deploy** button
2. Workflow activated
3. Ready for execution

## Node Configuration

### LLM Node

Call language model for processing.

**Configuration:**
```yaml
Name: Generate Response
Model: GPT-4 Turbo
System Prompt: You are a helpful assistant.
User Prompt: |
  Based on this analysis:
  {{analysis}}

  Generate a response for the customer.

Temperature: 0.7
Max Tokens: 1024
Output Variable: response
```

**Variables:**
- Use `{{variable_name}}` to reference variables
- Access nested properties: `{{analysis.type}}`
- Use in prompts and parameters

### Tool Node

Execute a tool.

**Configuration:**
```yaml
Name: Search Knowledge Base
Tool: kb_search
Parameters:
  query: "{{inquiry_text}}"
  kb_id: "kb-456"
  top_k: 3
Output Variable: kb_results
```

**Available Tools:**
- Web Search
- Calculator
- Date/Time
- Email
- Custom tools

### HTTP Node

Make HTTP requests.

**Configuration:**
```yaml
Name: Create Ticket
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
Output Variable: ticket
```

### Condition Node

Branch based on condition.

**Configuration:**
```yaml
Name: Check Urgency
Condition: analysis.urgency == "high"
True Branch: notify-manager
False Branch: assign-agent
```

**Condition Syntax:**
```javascript
// Comparison
analysis.urgency == "high"
priority != "low"
score > 0.8
count >= 5

// Logical operators
urgency == "high" && type == "technical"
priority == "low" || priority == "medium"
!(status == "closed")

// String operations
inquiry_text.includes("password")
customer_email.endsWith("@example.com")

// Array operations
tags.includes("urgent")
results.length > 0
```

### Loop Node

Iterate over items.

**Configuration:**
```yaml
Name: Process Results
Loop Over: kb_results
Item Variable: result
Max Iterations: 10
Body:
  - Transform Node
  - LLM Node
Output Variable: processed_results
```

### Parallel Node

Execute nodes concurrently.

**Configuration:**
```yaml
Name: Parallel Processing
Branches:
  - Search KB
  - Call API
  - Send Email
Wait For: all  # or: any, first
Timeout: 60s
```

### Transform Node

Transform data.

**Configuration:**
```yaml
Name: Format Response
Transform: |
  {
    "customer_email": input.customer_email,
    "response": response,
    "ticket_id": ticket.id,
    "kb_articles": kb_results.map(r => r.id),
    "timestamp": new Date().toISOString()
  }
Output Variable: formatted_response
```

**Transform Functions:**
```javascript
// String operations
text.toUpperCase()
text.toLowerCase()
text.trim()
text.substring(0, 10)
text.replace("old", "new")

// Array operations
array.map(item => item.id)
array.filter(item => item.score > 0.7)
array.reduce((sum, item) => sum + item.value, 0)
array.sort((a, b) => b.score - a.score)
array.slice(0, 5)

// Object operations
Object.keys(obj)
Object.values(obj)
Object.entries(obj)
{...obj, newKey: "value"}

// Date operations
new Date().toISOString()
Date.now()
```

## Variables and Data Flow

### Variable Scope

**Global Variables:**
- Available throughout workflow
- Set in Start node
- Accessible in all nodes

**Node Variables:**
- Output from nodes
- Named in node configuration
- Used in subsequent nodes

**System Variables:**
```yaml
{{workflow.id}}          # Workflow ID
{{workflow.name}}        # Workflow name
{{execution.id}}         # Execution ID
{{execution.started_at}} # Start time
{{user.id}}              # User ID
{{user.email}}           # User email
{{team.id}}              # Team ID
{{team.name}}            # Team name
```

### Variable Usage

**In Prompts:**
```
Analyze this inquiry from {{customer_email}}:
{{inquiry_text}}

Previous analysis: {{analysis.summary}}
```

**In Conditions:**
```javascript
analysis.urgency == "high"
kb_results.length > 0
customer_email.includes("@vip.com")
```

**In Transforms:**
```javascript
{
  "email": customer_email,
  "type": analysis.type,
  "articles": kb_results.map(r => r.title)
}
```

## Error Handling

### Try-Catch Pattern

**Add Error Handling:**
1. Add error output from node
2. Connect to error handler node
3. Configure error handling

**Example:**
```yaml
Main Flow:
  LLM Node → Success → Next Node
         ↓ Error
  Error Handler Node → Log Error → Notify Admin
```

### Retry Logic

**Configure Retries:**
```yaml
Node: Call External API
Max Retries: 3
Retry Delay: 5s
Retry On:
  - Timeout
  - 5xx errors
Backoff: Exponential
```

### Fallback Values

**Use Default Values:**
```javascript
// In transform
{
  "priority": analysis.urgency || "medium",
  "type": analysis.type || "general",
  "score": analysis.score || 0.5
}
```

## Best Practices

### Workflow Design

**✅ Do:**
- Keep workflows simple and focused
- Use descriptive node names
- Add comments for complex logic
- Test thoroughly before deployment
- Handle errors gracefully
- Use variables for reusability
- Document workflow purpose
- Version control workflows

**❌ Don't:**
- Create overly complex workflows
- Use vague node names
- Skip error handling
- Deploy untested workflows
- Hardcode values
- Duplicate logic
- Forget documentation
- Make breaking changes without versioning

### Performance

**✅ Do:**
- Use parallel execution where possible
- Set appropriate timeouts
- Limit loop iterations
- Cache repeated operations
- Use efficient transforms
- Monitor execution time

**❌ Don't:**
- Execute everything sequentially
- Use very long timeouts
- Create infinite loops
- Repeat expensive operations
- Use complex transforms
- Ignore performance metrics

### Debugging

**✅ Do:**
- Use test mode frequently
- Check each node output
- Add logging nodes
- Use meaningful variable names
- Test edge cases
- Review execution history

**❌ Don't:**
- Skip testing
- Ignore node errors
- Forget logging
- Use cryptic names
- Only test happy path
- Deploy without review

## Workflow Templates

### Customer Support Template

```yaml
Name: Customer Inquiry Processing
Trigger: Webhook

Nodes:
  1. Start
     Input: customer_email, inquiry_text, priority

  2. LLM: Analyze Inquiry
     Classify type and urgency

  3. Condition: Check Urgency
     If high → Notify Manager
     Else → Continue

  4. Tool: Search Knowledge Base
     Find relevant articles

  5. LLM: Generate Response
     Create customer response

  6. HTTP: Create Ticket
     Log in ticketing system

  7. Tool: Send Email
     Send response to customer

  8. End
     Return ticket ID and response
```

### Data Processing Template

```yaml
Name: Document Processing Pipeline
Trigger: File Upload

Nodes:
  1. Start
     Input: file_url, file_type

  2. HTTP: Download File
     Fetch file content

  3. Tool: Extract Text
     Parse document

  4. Loop: Process Chunks
     Split into chunks
     For each chunk:
       - Generate embeddings
       - Store in vector DB

  5. Transform: Create Metadata
     Format document metadata

  6. HTTP: Update Status
     Mark as processed

  7. End
     Return document ID
```

### Integration Template

```yaml
Name: CRM Sync Workflow
Trigger: Schedule (Daily)

Nodes:
  1. Start
     Input: sync_date

  2. HTTP: Fetch CRM Data
     Get updated records

  3. Loop: Process Records
     For each record:
       - Transform data
       - Validate
       - Update database

  4. Parallel: Notifications
     - Send email summary
     - Post to Slack
     - Update dashboard

  5. End
     Return sync summary
```

## Keyboard Shortcuts

**Canvas Navigation:**
- `Space + Drag`: Pan canvas
- `Ctrl/Cmd + Scroll`: Zoom
- `Ctrl/Cmd + 0`: Reset zoom

**Node Operations:**
- `Ctrl/Cmd + C`: Copy node
- `Ctrl/Cmd + V`: Paste node
- `Delete`: Delete node
- `Ctrl/Cmd + D`: Duplicate node

**Workflow Operations:**
- `Ctrl/Cmd + S`: Save workflow
- `Ctrl/Cmd + Z`: Undo
- `Ctrl/Cmd + Shift + Z`: Redo
- `Ctrl/Cmd + F`: Find node

## Troubleshooting

### Node Not Executing

**Symptoms:**
- Node skipped
- No output

**Solutions:**
1. Check connections
2. Verify input variables exist
3. Check conditions
4. Review node configuration
5. Test in isolation

### Variable Not Found

**Symptoms:**
- "Variable not defined" error
- Empty output

**Solutions:**
1. Check variable name spelling
2. Verify node executed before use
3. Check variable scope
4. Use default values
5. Add null checks

### Workflow Timeout

**Symptoms:**
- Execution stops
- Timeout error

**Solutions:**
1. Increase workflow timeout
2. Optimize slow nodes
3. Use parallel execution
4. Add timeouts to individual nodes
5. Break into smaller workflows

## Related Documentation

- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow Nodes](./workflow-nodes.md) - Node reference
- [Workflow History](./workflow-history.md) - Execution history
- [Workflow Management](../../admin-guide/workflows/workflow-management.md) - Admin guide

---

**Last Updated**: 2026-02-11
