# Clouisle Developer Documentation

Internal engineering documentation lives here.

## Structure

### Backend
- [Section index](backend/README.md)
- [API conventions](backend/api-conventions.md)
- [Migrations and init data](backend/migrations-and-init-data.md)
- [Audit logging](backend/audit-logging.md)
- [Celery and async jobs](backend/celery-and-async-jobs.md)

### Frontend
- [Section index](frontend/README.md)
- [Frontend conventions](frontend/conventions.md)

### API
- [Backend API reference](api/BACKEND_API.md)

### Design specs
- [RBAC spec](design/access-control/RBAC_SPEC.md)
- [Team model auth spec](design/access-control/TEAM_MODEL_AUTH_SPEC.md)
- [Workflow engine architecture](design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md)
- [Tool system spec](design/app-platform/TOOL_SYSTEM_SPEC.md)

### Analysis
- [Section index](analysis/README.md)
- [Backend overview](analysis/backend/00-overview.md)
- [Frontend overview](analysis/frontend/00-overview.md)

### Status
- [Section index](status/README.md)
- [Agent development progress](status/AGENT_DEVELOPMENT_PROGRESS.md)
- [Workflow backend spec](status/WORKFLOW_BACKEND_SPEC.md)
- [Workflow engine status](status/WORKFLOW_ENGINE_STATUS.md)

## Usage

- Keep root guidance files minimal and link back here for details.
- Put internal engineering and implementation rules under `docs/dev/`.
- Keep user/operator documentation under `docs/guide/`.
