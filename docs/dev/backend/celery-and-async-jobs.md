# Celery and Async Job Guide

This document covers backend conventions for Celery task modules, long-running jobs, and large payload handling.

## Registering a new Celery task module

When adding a new task module, update `app/core/celery.py`.

### 1. Include the module

```python
celery_app = Celery(
    "clouisle",
    broker=f"{REDIS_URL}/0",
    backend=f"{REDIS_URL}/1",
    include=[
        "app.tasks.knowledge_base",
        "app.tasks.your_new_module",
    ],
)
```

### 2. Configure routing if needed

```python
celery_app.conf.task_routes = {
    "app.tasks.your_new_module.*": {"queue": "default"},
}
```

### 3. Restart workers

New task modules are not picked up until the worker is restarted.

## Task function rules

Celery task functions must be synchronous.

If task logic is async, wrap it with `asyncio.run()`:

```python
@celery_app.task(bind=True, name="your_task_name")
def your_task(self, param1, param2):
    async def _async_work():
        result = await some_async_function()
        return result

    return asyncio.run(_async_work())
```

## Large payload handling

Use `StorageService` for large files or large task payloads.

### Flow

```text
API endpoint -> StorageService -> Local / Redis / S3 backend
Celery task  -> StorageService -> read file and metadata
```

### Typical usage

```python
from app.services.storage_service import StorageService

file_content = await file.read()
await StorageService.save_import_file(file_content, task_id, file.filename)
await StorageService.save_team_info(task_id, str(team_id))

file_content, filename = await StorageService.get_import_file(task_id)
team_id = await StorageService.get_team_info(task_id)

await StorageService.delete_import_file(task_id)
```

### Backend choices

- Local filesystem: default, simple, single-node deployments
- Redis: distributed, smaller files, memory-backed
- S3/MinIO: future direction for distributed large-file storage

## Progress updates

### Backend task progress

```python
self.update_state(
    state="PROGRESS",
    meta={"progress": 50, "status": "Processing data"}
)
```

### Frontend polling pattern

The frontend should keep polling until a task reaches `completed` or `failed`, rather than treating task creation as completion.

## Common issues

### Task is queued but worker does not execute it

Check:
1. the task module is listed in `include`
2. the worker listens to the correct queue
3. the worker has been restarted after registration

### UI shows success before processing is actually done

Fix by:
1. opening a progress dialog immediately after task creation
2. polling task status until completion
3. showing the final result only when the task finishes

## Related docs

- `./api-conventions.md`
- `../design/app-platform/WORKFLOW_ENGINE_ARCHITECTURE.md`
- `../status/WORKFLOW_BACKEND_SPEC.md`
