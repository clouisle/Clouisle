# Changelog

This document records all significant changes to the project.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

#### Workflow Variable Reference Validation System

Added variable reference validity checking to workflow validation checklist, ensuring variables referenced in node configurations actually exist and are accessible.

##### Core Features

- **Upstream Variable Calculation**: BFS traversal of edge relationships to compute accessible upstream variable set for each node
- **System Variable Support**: Built-in support for `sys.user_id`, `sys.app_id`, `sys.workflow_id`, `sys.run_id`, `sys.timestamp` system variables
- **Conversation Variable Support**: Automatically skips validation for `conversation.*` format variables
- **Variable Format Cleanup**: Automatically handles `{{nodeId.varName}}` format, correctly extracting variable names for validation and display

##### Supported Node Types

| Node Type | Validated Fields |
|-----------|------------------|
| `question_classifier` | `sourceVariable` |
| `answer` | `outputs[].sourceVariable` |
| `condition` | `branches[].conditions[].variable` |
| `code` | `inputs[].value` |
| `template` | `variables[].variable` |
| `tool` | `inputs[].value` |
| `parameter_extractor` | `sourceVariable` |
| `variable_aggregator` | `variables[].sourceVariable` |
| `variable_assignment` | `assignments[].sourceVariable` |
| `iteration` | `iterateVariable` |
| `loop` | `conditionVariable` |
| `sub_workflow` | `inputMappings[].sourceVariable` |
| `file_to_url` | `inputs[].sourceVariable` |
| `agent` | `inputVariable` |

---

#### Loop/Iteration Node Internal Variable Access

Support for accessing internal variables provided by parent containers within loop and iteration node subgraphs.

##### Feature Description

**Iteration Node**:
- `{iterationNodeId}.item` - Current iteration item (Any type)
- `{iterationNodeId}.index` - Current index (Number type)

**Loop Node**:
- `{loopNodeId}.index` - Current loop index (Number type)
- `{loopNodeId}.{loopVarName}` - Custom loop variable

---

### Refactored

#### Workflow Node Config Drawer Componentization

Modular refactoring of `node-config-drawer.tsx` (2685 lines) to improve maintainability and reusability.

##### Before Refactoring

- Single file with 2685 lines containing all node type configuration logic

##### After Refactoring

Main file reduced to 529 lines (80% reduction), split into modular structure:

```
frontend/app/(platform)/app/apps/workflow/[id]/_components/
├── node-config-drawer.tsx      # Main file (529 lines)
└── node-config/                # Component directory (2618 lines)
    ├── index.ts                # Unified exports
    ├── types.ts                # Type definitions
    ├── constants.ts            # Constants configuration
    ├── utils.ts                # Utility functions
    ├── variable-selector.tsx   # Variable selector component
    ├── configs/                # Node config components
    │   ├── start-node-config.tsx
    │   ├── llm-node-config.tsx
    │   ├── condition-node-config.tsx
    │   ├── iteration-node-config.tsx
    │   ├── loop-node-config.tsx
    │   └── code-node-config.tsx
    └── dialogs/                # Dialog components
        ├── parameter-edit-dialog.tsx
        └── code-input-dialog.tsx
```

---

### Fixed

#### Knowledge Base Retrieval Optimization

- **Similarity Calculation Fix**: Corrected cosine similarity calculation formula
  - Before: `1 - (distance / 2)` - resulted in inflated scores
  - After: `GREATEST(0, 1 - distance)` - correctly converts cosine distance to similarity

- **Default Threshold Adjustment**: Lowered `score_threshold` default from `0.5` to `0.3`

#### Text Chunking Algorithm Fix

- **Chunk Size Limit Enforcement**: Fixed issue where `chunk_size` setting was not being enforced
  - When split fragments exceed target size, now recursively uses finer-grained separators
  - Falls back to hard character-based splitting when further splitting is not possible

#### Streamdown Image Rendering Hydration Error

- **Issue**: Images in Markdown rendered by Streamdown as `<div>` wrappers, causing `<div>` nested in `<p>` when images appear in paragraphs, violating HTML spec and causing React hydration errors
- **Fix**: Provided custom `p` component for Streamdown that checks if AST nodes and React children contain images, using `<div>` instead of `<p>` when they do

---

### Added

#### Platform Header About Dialog

- Added "About" dialog accessible from platform header user menu
- Displays app logo, version number, copyright info
- Provides quick links to GitHub, docs, changelog

#### Chat History Management Optimization

Fixed multiple pages using local state filtering instead of server refresh after delete operations:

- **Public Chat Page**: Fixed sidebar history not updating after new conversation
- **Dashboard Conversation Management**: Server refresh after single/batch delete
- **Knowledge Base Document Chunks**: Server refresh after chunk delete

---

### Added

#### API Key Management - Complete Implementation

##### Agent Binding Feature

- **API Key to Agent Many-to-Many Association**:
  - One API Key can bind multiple Agents
  - Bound API Key can only access bound Agents
  - Unbound API Key can access all public Agents

- **Backend Implementation**:
  - `api_key_agents` association table (many-to-many)
  - Support for `agent_ids` when creating/updating API Key
  - Chat endpoint supports API Key authentication (`X-API-Key` header)
  - Agent access permission validation for API Key auth

- **Frontend Implementation**:
  - Agent binding selector in API Key create/edit dialog
  - API Key list shows bound Agent count

---

### Added

#### Agent API Access Page

Implemented API access documentation page for Agents:

- **Route**: `/app/apps/[id]/api`
- **Features**:
  - API endpoint URL and authentication method display
  - Request/response format documentation
  - Code examples (cURL, Python, JavaScript)
  - Agent variable definitions display
  - Unpublished Agent warning
  - Multi-turn conversation documentation

---

### Added

#### Dashboard Tool Management Page

Implemented tool management for dashboard:

- **Route**: `/tools`
- **Tool Types Supported**:
  - **HTTP API Tools**: Configure URL, method, headers, body template
  - **MCP Server Tools**: Configure stdio/sse transport, command, environment variables
  - **Code Tools**: Online editor supporting JavaScript/Python

---

### Added

#### Agent Monitor Page - Statistics & Visualization

Implemented monitoring functionality in Agent orchestration page with usage statistics and performance metrics visualization.

##### Backend

- **Agent Stats API** (`/agents/{agent_id}/stats`):
  - Conversations, messages (by role)
  - Token usage (prompt/completion)
  - Average response time
  - Active users
  - Tool call count

- **Trends API** (`/agents/{agent_id}/stats/trends`):
  - Support for 24h/7d/30d time ranges
  - Hourly/daily aggregation

##### Frontend

- Overview stat cards
- Conversation trend chart (Area Chart)
- Token usage trend chart
- Response time trend chart
- Tool usage distribution chart (Bar Chart)
- Recent conversations list
- Time period filter

---

### Added

#### Knowledge Base Module - Dynamic Embedding Dimension Support

##### Multi-Dimension Embedding Vector Storage

- **KnowledgeBase Model Extension**:
  - Added `embedding_dimension` field
  - Auto-detect and lock dimension on first document processing
  - Subsequent documents must use same dimension model

- **Dynamic Vector Column Management**:
  - Support for multiple dimensions: 768 (BGE), 1024 (Cohere), 1536 (OpenAI ada), 3072 (OpenAI large)
  - On-demand embedding column creation
  - Independent HNSW index per dimension

---

### Added

#### Chat Module - Universal Chat Components & MCP Tool Support

##### Frontend Chat Component Library

Created complete reusable Chat component library at `/frontend/components/chat/`:

- **Chat Main Component** (`chat.tsx`): Complete chat interface combining Container + Input
- **Message Container** (`chat-container.tsx`): Auto-scroll, Streamdown rendering
- **Input Box** (`chat-input.tsx`): OpenAI-style design, IME support, file attachments
- **Message Component** (`message.tsx`): ChainOfThought integration, multiple message types
- **Variable Form** (`variable-form.tsx`): Agent variable input form

##### Message Parts System

Located at `/frontend/components/chat/message-parts/`:

- **Text Content** (`text-content.tsx`): Markdown rendering, streaming cursor, citation markers
- **Reasoning Content** (`reasoning-content.tsx`): Chain of thought display, collapsible
- **Tool Calls** (`tool-content.tsx`): Tool execution status, input/output display
- **File Content** (`file-content.tsx`): Image preview, file info display
- **Source Content** (`source-content.tsx`): RAG source aggregation, segment popup

##### MCP (Model Context Protocol) Tool Support

- **MCP Client** (`/backend/app/llm/tools/mcp_client.py`):
  - Support for `stdio` and `sse` transport methods
  - Tool discovery and execution
  - Connection pool management
  - Timeout handling

##### Built-in Tools

Located at `/backend/app/llm/tools/builtin/`:

- **Calculator** (`calculator.py`): Math expression calculation, unit conversion
- **Time Tool** (`time.py`): Current time, timezone conversion

---

### Added

#### Application Module - Agent Orchestration Page Refactoring

##### Layout Refactoring

Refactored Agent configuration page from traditional tab form layout to modern three-column layout:

- **Left Sidebar** (`agent-sidebar.tsx`):
  - Agent icon, name, and type label
  - Navigation menu: Orchestration, API Access, Logs, Monitor

- **Center Main Content** (`agent-orchestration-form.tsx`):
  - Prompt editor with AI generation button
  - Variable configuration
  - Knowledge base association
  - Tool configuration
  - Vision capability

- **Right Preview Panel** (`agent-preview-panel.tsx`):
  - Debug and preview chat window
  - Real-time conversation testing

- **Top Toolbar** (`agent-toolbar.tsx`):
  - Agent settings button
  - Model selector dropdown
  - Model parameter adjustment dialog
  - Publish/unpublish dropdown

---

### Added

#### Knowledge Base Module - Complete Implementation

##### Backend

- **Knowledge Base CRUD API**: Complete management interface
- **Document Management**: Multi-format upload support (PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON, PPTX)
- **URL Import**: Import content from web URLs
- **Document Processing Pipeline**:
  - Document parsing and text extraction
  - Smart chunking (customizable chunk_size, chunk_overlap, separator)
  - Chunk preview before committing
  - Text cleaning options
- **Three Search Modes**:
  - `vector`: Semantic vector search based on embedding similarity
  - `fulltext`: Full-text keyword search with jieba Chinese tokenization
  - `hybrid`: Hybrid search using RRF (Reciprocal Rank Fusion) algorithm

##### Frontend

- **Knowledge Base List Page**: Search, status filter, batch operations, pagination
- **Knowledge Base Detail Page**: Stats cards, document list
- **Document Upload**: Drag-and-drop, batch upload, progress display
- **Document Processing Preview**: Single/batch chunk preview, parameter adjustment
- **Search Test Page**: Three search modes, collapsible result cards, advanced settings

---

## Contributing

When submitting code, please reference related Issues in commit messages:

```
feat(knowledge-base): implement knowledge base search

- Add vector search, full-text search, hybrid search modes
- Integrate jieba Chinese tokenization

Closes #12
```
