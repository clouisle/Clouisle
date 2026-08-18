# Workflow Nodes Reference

This document provides a reference for the user-configurable workflow node types shown in the Clouisle builder.

## Overview

Workflow nodes are building blocks for creating automated processes. Each node type serves a specific purpose and can be configured with various parameters.

## Node Categories

Clouisle supports the following user-configurable node types:

- **Flow / Logic**: `trigger`, `user_input`, `end`, `condition`, `question_classifier`, `iteration_start`, `loop_start`, `iteration`, `loop`, `pause`
- **Model**: `llm`, `media_generation`
- **Data**: `code`, `template`, `file_to_url`, `variable_assignment`, `variable_aggregator`, `parameter_extractor`
- **Knowledge**: `knowledge_retrieval`
- **Integration**: `tool`, `agent`, `sub_workflow`, `answer`

`document_extractor` and `http_request` remain executor/API-level capabilities rather than nodes shown in the builder palette. `iteration_exit` and `loop_exit` are internal container nodes used by the workflow engine; do not add them as standalone nodes.

> **Note:** Node types such as Transform, Parallel, Wait, Switch, Database, Email, Webhook (as a node), Log, Delay, Merge, Input, and Output are **not implemented**. Variable handling is done via `variable_assignment` and `variable_aggregator`.

## Start / Entry Nodes

### user_input (Start)

The entry point for a manually executed workflow. Defines the input parameters collected from the user when the workflow starts.

**Example:**
```yaml
Type: user_input
Input Parameters:
  - name: customer_email
    type: string
    required: true
  - name: priority
    type: string
    required: false
    default: medium
```

**Output:** All input parameters are available as variables.

### trigger

The entry point for triggered workflows (e.g. webhook). A webhook-triggered workflow receives the webhook request body as its input variables.

### end

The terminal node of a workflow. Every workflow ends at an `end` node; the final outputs are collected there.

## Model Nodes

### llm

Call a language model for text processing.

**Configuration:**
```yaml
Type: llm
Model: <model reference>
System Prompt: System instructions
User Prompt: User message with {{variables}}
Temperature: 0.0-1.0
Max Tokens: 1-128000
Top P: 0.0-1.0
Output Variable: variable_name
```

**Output variables:** `response`, `reasoning`, `usage` (plus the configured output variable).

### media_generation

Generate images or videos (via `generate_image` / `generate_video` tools).

**Configuration:**
```yaml
Type: media_generation
Provider: image | video
Prompt: "{{prompt}}"
Width/Height: (image)
Duration/Aspect Ratio: (video)
```

## Data Nodes

### code

Execute custom code (Python or JavaScript) in the sandbox.

**Configuration:**
```yaml
Type: code
Language: python|javascript
Code: |
  # Your code here
  return result
Output Variable: variable_name
```

### template

Render a template string with variables (e.g. Jinja-like `{{variable}}` substitution).

### file_to_url

Convert a file (e.g. a sandbox artifact) into a downloadable URL.

### variable_assignment

Assign a value to a variable.

**Configuration:**
```yaml
Type: variable_assignment
Variables:
  var1: value
  var2: "{{expression}}"
```

### variable_aggregator

Aggregate values (e.g. collect loop iteration results into an array).

### parameter_extractor

Extract structured parameters from text using LLM, regex, or JSON path.

**Configuration:**
```yaml
Type: parameter_extractor
Extraction Method: llm|regex|json_path
Source Variable: "{{source}}"
Parameters: [...]
```

## Knowledge Nodes

### knowledge_retrieval

Retrieve chunks from a knowledge base for RAG.

**Configuration:**
```yaml
Type: knowledge_retrieval
Knowledge Base: <kb_id>
Query: "{{query}}"
Top K: 5
Score Threshold: 0.3
Search Mode: hybrid
```

### document_extractor

Extract text/content from a document.

## Integration Nodes

### tool

Execute a configured tool (builtin, custom, MCP, or skill).

**Configuration:**
```yaml
Type: tool
Tool: <tool id or builtin name>
Inputs:
  - name: query
    source: variable
    variableRef: "{{start.query}}"
  - name: limit
    constantValue: "10"
Output Variable: result
```

**Built-in tools available:** `web_search`, `fetch_webpage`, `calculate`, `unit_convert`, `get_weather`, `get_current_time`, `format_datetime`, `markitdown`, plus sandbox tools (`bash`, `read`, `edit`, `write`, `artifact`).

### agent

Invoke an AI agent with a message and optional context.

### sub_workflow

Run another workflow as a sub-step and capture its output.

### http_request

Make HTTP requests to external APIs.

**Configuration:**
```yaml
Type: http_request
Method: GET|POST|PUT|PATCH|DELETE
URL: https://api.example.com/endpoint
Headers: {...}
Body: |
  { "key": "{{variable}}" }
Output Variable: variable_name
```

> **Note:** The `http_request` executor has no retry configuration.

### answer

Return a final answer/output from the workflow.

## Control Flow Nodes

### condition

Branch execution based on a condition.

**Configuration:**
```yaml
Type: condition
Condition: "{{analysis.urgency}} == 'high'"
True Branch: <node>
False Branch: <node>
```

### question_classifier

Classify the user's input into one of several intents/categories and route accordingly.

### iteration_start / loop_start

Mark the beginning of an iteration/loop block.

### iteration / loop

Iterate over a collection (or loop until a condition is met).

**Configuration:**
```yaml
Type: iteration
Collection: "{{items}}"
Item Variable: item
Body: [...]
Output Variable: results
```

### pause

Pause execution until a team member supplies requested variables or submits an approval decision. A pause can be configured in **Variables** mode or **Approval** mode; a waiting run resumes after the request is handled.

**Configuration:**
```yaml
Type: pause
Mode: variables | approval
Title: Review request
Input Variables:
  - name: customer_email
    type: string
    required: true
```

## Node Properties

### Common Properties

All nodes share these properties:

```yaml
id: unique_node_id
type: node_type
label: Display name
description: Node description
```

### Variables

Use `{{variable_name}}` to reference variables in prompts, conditions, and parameters. Variables flow from earlier nodes to later nodes in the execution graph.

## Best Practices

### Node Naming

**✅ Do:**
- Use descriptive names
- Include an action verb
- Be specific

**❌ Don't:**
- Use generic names ("Node 1", "Process")
- Use abbreviations

### Node Configuration

**✅ Do:**
- Set appropriate timeouts
- Use variables
- Validate inputs

**❌ Don't:**
- Hardcode values
- Skip validation

## Related Documentation

- [Workflow Builder](./workflow-builder.md) - Building workflows
- [Running Workflows](./running-workflows.md) - Executing workflows
- [Workflow History](./workflow-history.md) - Execution history

---

**Last Updated**: 2026-02-11
