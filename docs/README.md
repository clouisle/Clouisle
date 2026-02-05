# Clouisle Documentation

## Directory Structure

```
docs/
├── guide/                        # User guides and usage documentation
│   ├── README_zh-CN.md           # Chinese README
│   ├── DEPLOYMENT.md             # Deployment guide (English)
│   ├── DEPLOYMENT_zh-CN.md       # Deployment guide (Chinese)
│   ├── PERMISSIONS.md            # Permission system (English)
│   ├── PERMISSIONS_zh-CN.md      # Permission system (Chinese)
│   ├── AUTO_NOTIFICATIONS.md     # Auto notifications (English)
│   ├── AUTO_NOTIFICATIONS_zh-CN.md # Auto notifications (Chinese)
│   ├── CHANGELOG.md              # Changelog (English)
│   └── CHANGELOG_zh-CN.md        # Changelog (Chinese)
│
└── dev/                          # Development documentation
    ├── analysis/                 # Code analysis documents
    ├── api/                      # API documentation
    │   └── BACKEND_API.md
    ├── design/                   # Design specification documents
    │   ├── AGENT_WORKFLOW_SPEC.md
    │   ├── KNOWLEDGE_BASE_SPEC.md
    │   ├── LLM_SPEC.md
    │   ├── NOTIFICATION_SPEC.md
    │   ├── RBAC_SPEC.md
    │   ├── TEAM_MODEL_AUTH_SPEC.md
    │   ├── TOOL_SYSTEM_SPEC.md
    │   ├── WORKFLOW_ENGINE_ARCHITECTURE.md
    │   └── WORKFLOW_NODE_SPEC.md
    ├── AGENT_DEVELOPMENT_PROGRESS.md
    ├── WORKFLOW_BACKEND_SPEC.md
    └── WORKFLOW_ENGINE_STATUS.md
```

## User Guides (guide/)

Documentation for users and operators:

| Document | English | 中文 |
|----------|---------|------|
| Project Introduction | [README](../README.md) | [README_zh-CN](guide/README_zh-CN.md) |
| Deployment Guide | [DEPLOYMENT](guide/DEPLOYMENT.md) | [DEPLOYMENT_zh-CN](guide/DEPLOYMENT_zh-CN.md) |
| Permission System | [PERMISSIONS](guide/PERMISSIONS.md) | [PERMISSIONS_zh-CN](guide/PERMISSIONS_zh-CN.md) |
| Auto Notifications | [AUTO_NOTIFICATIONS](guide/AUTO_NOTIFICATIONS.md) | [AUTO_NOTIFICATIONS_zh-CN](guide/AUTO_NOTIFICATIONS_zh-CN.md) |
| Changelog | [CHANGELOG](guide/CHANGELOG.md) | [CHANGELOG_zh-CN](guide/CHANGELOG_zh-CN.md) |

## Development Documentation (dev/)

Technical documentation for developers:

### Design Specifications (design/)

- **AGENT_WORKFLOW_SPEC.md** - Agent and workflow design specification
- **KNOWLEDGE_BASE_SPEC.md** - Knowledge base system design
- **LLM_SPEC.md** - LLM integration specification
- **NOTIFICATION_SPEC.md** - Notification system design
- **RBAC_SPEC.md** - Permission system design
- **TOOL_SYSTEM_SPEC.md** - Tool system design
- **WORKFLOW_ENGINE_ARCHITECTURE.md** - Workflow engine architecture
- **WORKFLOW_NODE_SPEC.md** - Workflow node specification

### API Documentation (api/)

- **BACKEND_API.md** - Backend API interface documentation

### Development Progress

- **AGENT_DEVELOPMENT_PROGRESS.md** - Agent development progress
- **WORKFLOW_ENGINE_STATUS.md** - Workflow engine development status
