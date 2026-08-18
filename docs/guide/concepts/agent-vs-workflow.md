# Agent vs Workflow

Understanding the difference between Agents and Workflows.

## Agents

**Conversational and autonomous**:
- Interactive chat interface and multi-turn conversations
- The model can decide whether to call configured tools
- Optional RAG modes (`off`, `auto`, `agentic`) and memory support

**Use cases**:
- Customer support chatbots
- Personal assistants
- Q&A systems grounded in team knowledge

## Workflows

**Visual graph execution**:
- A workflow is a published version of a graph, not necessarily a deterministic straight-line script
- Graphs can include entry and output nodes (user input, triggers, answer), model/media nodes (LLM, Agent, media generation), integrations (tool, HTTP request, and sub-workflow), retrieval/document nodes (knowledge retrieval, document extraction, and file-to-URL), transformation nodes (code, template, variable assignment/aggregation, and parameter extraction), and control-flow nodes (condition, question classifier, iteration/loop with exit markers, and pause)
- Runs can be started manually or by cron/webhook triggers
- Drafts can be tested in debug mode; published snapshots provide stable runtime definitions

**Use cases**:
- Data processing pipelines
- Automated reports
- API integrations and scheduled tasks

## Comparison

| Feature | Agent | Workflow |
|---------|-------|----------|
| Interface | Chat | Visual graph editor |
| Execution | Model/tool decisions during a conversation | User-defined graph with model and tool nodes |
| Control | Conversational and context-driven | Published graph, triggers, and node configuration |
| Use case | Interactive assistance | Repeatable automation and orchestration |

Choose an Agent when the user needs an open-ended conversation. Choose a Workflow when the business process benefits from explicit nodes, inputs, triggers, and a published version.

## Related documentation

- [RAG Explained](./rag-explained.md) - Retrieval modes and pipeline
- [System Architecture](./architecture.md) - Component overview
- [Workflow Patterns](../best-practices/workflow-patterns.md) - Common graph patterns
