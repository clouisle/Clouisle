# Basic Concepts

Core concepts you need to understand to use Clouisle effectively.

## Teams and Multi-Tenancy

Most resources in Clouisle belong to a team, and users can be members of multiple teams. Platform resources are the exceptions: users, roles, permissions, and site settings are platform-global, system skills have no team, and tools can be shared across teams.

## AI Agents

Conversational AI assistants that can use tools, access knowledge bases, and execute workflows.

## Knowledge Bases

Document repositories with vector search capabilities for RAG (Retrieval-Augmented Generation).

## Workflows

Visual automation workflows with 19 node types for complex business logic, composing agents, tools, and knowledge retrieval into multi-agent pipelines.

## RAG Modes

- **off**: No knowledge base retrieval, even when knowledge bases are configured
- **auto**: Traditional RAG — automatically retrieve on every message
- **agentic**: Agentic RAG — the agent decides when to search

For detailed explanations, see [Concepts](../concepts/).
