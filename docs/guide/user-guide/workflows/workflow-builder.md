# Workflow Builder

This guide covers how to build and design workflows in Clouisle.

## Overview

The workflow builder allows you to:

- **Create workflows**: Design automated processes
- **Add nodes**: Use the supported node types
- **Connect nodes**: Define execution flow
- **Configure nodes**: Set node parameters
- **Test workflows**: Validate with debug runs
- **Publish workflows**: Activate for use

## Accessing Workflow Builder

### Create New Workflow

1. Navigate to **Workflows**
2. Click **Create Workflow** button
3. Enter workflow details:
   - Name
   - Description
   - Team
4. Click **Create**
5. The workflow builder opens

### Edit Existing Workflow

1. Navigate to **Workflows**
2. Click on the workflow to edit
3. Click **Edit** button
4. The workflow builder opens

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
│          │                                          │
│  ┌────┐  │    ┌────────┐                          │
│  │llm │  │    │  Node  │                          │
│  └────┘  │    └────────┘                          │
│          │         │                               │
│  ┌────┐  │         ▼                               │
│  │tool │  │    ┌────────┐                          │
│  └────┘  │    │  Node  │                          │
│          │    └────────┘                          │
│          │                                          │
└──────────┴──────────────────────────────────────────┘
```

### Components

**Nodes Panel (Left):**
- Available node types, organized by category:
  - **Model**: LLM, Media Generation
  - **Logic**: Condition, Question Classifier, Iteration, Loop
  - **Transform**: Code, Template, File to URL, Variable Aggregator, Variable Assignment, Parameter Extractor
  - **Extension**: Sub-workflow, Agent, Tool, Knowledge Retrieval, Answer

**Canvas (Center):**
- Workflow design area
- Add, connect, and arrange nodes

**Properties Panel (Right):**
- Node configuration
- Node settings
- Variables

**Toolbar (Top):**
- Save workflow
- Test (debug) workflow
- Zoom controls

## Building a Workflow

### Step 1: Add a Start Node

Every workflow begins with a start node (user input or trigger), which defines the input parameters.

**Configure Start Node:**
```yaml
Input Parameters:
  - name: customer_email
    type: string
    required: true
  - name: inquiry_text
    type: string
    required: true
```

### Step 2: Add Processing Nodes

Add nodes to process data. See [Workflow Nodes](./workflow-nodes.md) for the full node reference.

### Step 3: Connect Nodes

Connect nodes to define the flow:
1. Click the output port of the source node
2. Drag to the input port of the target node
3. The connection is created

### Step 4: Configure Nodes

Configure each node's settings in the properties panel.

**Example - LLM Node:**
```yaml
Type: LLM
Model: <model reference>
System Prompt: |
  You are a customer service analyst.

User Prompt: |
  Analyze this inquiry:
  {{inquiry_text}}

Temperature: 0.3
Max Tokens: 500
Output Variable: analysis
```

**Example - Tool Node:**
```yaml
Type: Tool
Tool: kb_search
Inputs:
  - name: query
    variableRef: "{{inquiry_text}}"
  - name: kb_id
    constantValue: "kb-456"
  - name: top_k
    constantValue: "3"
Output Variable: kb_results
```

**Example - HTTP Node:**
```yaml
Type: HTTP Request
Method: POST
URL: https://api.tickets.example.com/tickets
Headers:
  Authorization: Bearer {{api_token}}
  Content-Type: application/json
Body: |
  {
    "title": "{{analysis.summary}}",
    "description": "{{inquiry_text}}",
    "priority": "{{priority}}"
  }
Output Variable: ticket
```

> **Note:** The HTTP request node has no retry configuration.

**Example - Condition Node:**
```yaml
Type: Condition
Condition: "{{analysis.urgency}} == 'high'"
True Branch: <node>
False Branch: <node>
```

### Step 5: Add an End Node

Every workflow ends with an end node that collects the final outputs.

### Step 6: Test the Workflow

1. Click **Test** (debug) button
2. Enter test input
3. Run the workflow
4. Review results and each node's execution
5. Fix any errors

**Test Input Example:**
```json
{
  "customer_email": "test@example.com",
  "inquiry_text": "How do I reset my password?",
  "priority": "medium"
}
```

### Step 7: Save and Publish

1. Click **Save** — the workflow is saved as a draft
2. Click **Publish** — the workflow is activated and ready for execution

## Variables and Data Flow

### Variable Scope

**Input Variables:**
- Defined at the start node, collected from the user or trigger

**Node Variables:**
- Outputs from nodes, referenced in subsequent nodes

**System Variables:**
```yaml
{{workflow.id}}          # Workflow ID
{{workflow.name}}        # Workflow name
{{run.id}}               # Current run ID
```

### Variable Usage

**In Prompts:**
```
Analyze this inquiry from {{customer_email}}:
{{inquiry_text}}
```

**In Conditions:**
```
{{analysis.urgency}} == "high"
{{kb_results.length}} > 0
```

## Error Handling

> **Note:** There is no try-catch / retry UI in the builder. Failed node executions stop the run (unless the workflow continues), and the error is recorded on the run/node execution for inspection. See [Workflow History](./workflow-history.md).

## Workflow Templates

The built-in workflow templates are:

- **Simple Q&A Bot**: A basic question-answering bot using an LLM
- **RAG Knowledge Bot**: Knowledge-base-powered Q&A with retrieval augmentation
- **Intent Router**: Route conversations based on detected intent
- **Code Review Assistant**: Automated code review with multiple perspectives

Templates are instantiated into new workflows (variables such as `model_id` / `knowledge_base_id` are filled in during instantiation).

## Best Practices

### Workflow Design

**✅ Do:**
- Keep workflows simple and focused
- Use descriptive node names
- Test thoroughly before publishing
- Use variables for reusability

**❌ Don't:**
- Create overly complex workflows
- Use vague node names
- Publish untested workflows
- Hardcode values

### Debugging

**✅ Do:**
- Use test mode frequently
- Check each node's output
- Review execution history

**❌ Don't:**
- Skip testing
- Ignore node errors

## Keyboard Shortcuts

**Canvas Navigation:**
- `Space + Drag`: Pan canvas
- `Ctrl/Cmd + Scroll`: Zoom
- `Ctrl/Cmd + 0`: Reset zoom

## Troubleshooting

### Node Not Executing

**Solutions:**
1. Check connections
2. Verify input variables exist
3. Check conditions
4. Review node configuration

### Variable Not Found

**Solutions:**
1. Check variable name spelling
2. Verify the node executed before the reference
3. Check variable scope

### Workflow Timeout

**Solutions:**
1. Optimize slow nodes
2. Reduce the number of steps
3. Break into smaller workflows

## Related Documentation

- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow Nodes](./workflow-nodes.md) - Node reference
- [Workflow History](./workflow-history.md) - Execution history

---

**Last Updated**: 2026-02-11
