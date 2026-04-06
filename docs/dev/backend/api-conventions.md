# Backend API Conventions

This document captures backend implementation rules that complement the endpoint reference in `../api/BACKEND_API.md`.

## Response helpers

All API endpoints must use the unified response format:

```json
{
  "code": 0,
  "data": {},
  "msg": "success"
}
```

Use helpers from `app/schemas/response.py`:

- `success(data=..., msg=..., msg_key=...)`
- `error(code=..., msg=..., data=...)`

Prefer `Response[T]` and `PageData[T]` for response typing.

## Business errors

Use `BusinessError` for business logic failures instead of `HTTPException`.

```python
raise BusinessError(
    code=ResponseCode.USERNAME_EXISTS,
    msg_key="username_already_registered",
)
```

### Rules

- Prefer `msg_key` over hardcoded `msg` for user-facing messages.
- Use the closest `ResponseCode` enum value for each scenario.
- Set `status_code` to match the error type (`403`, `404`, etc.).
- Reserve `HTTPException` for framework-level HTTP concerns rather than application business rules.

## i18n requirements

All user-facing backend messages must be internationalized through `app/core/i18n.py`.

### Translation rules

- Add new keys to `TRANSLATIONS` in `app/core/i18n.py`.
- Use `t()` or `msg_key`-based helpers for responses and errors.
- Language is resolved from `X-Language` first, then `Accept-Language`.

## Route isolation

Backend routes are split under `/api/v1/` into two groups.

### Platform routes

Location: `app/api/v1/endpoints/`

Used for user-facing and self-service operations, for example:
- `users.py` → `/users/me`, `/users/me/change-password`
- `teams.py` → `/teams/my`, `/teams/{id}`
- `site_settings.py` → `/site-settings/public`
- `models.py` → `/models/providers`, `/models/available`
- `notifications.py` → `/notifications`

### Admin routes

Location: `app/api/v1/admin/endpoints/`

Used for privileged operations and always mounted with `/admin/`, for example:
- `dashboard.py` → `/admin/dashboard`
- `users.py` → `/admin/users`
- `roles.py` → `/admin/roles`
- `permissions.py` → `/admin/permissions`
- `site_settings.py` → `/admin/site-settings`
- `models.py` → `/admin/models`
- `teams.py` → `/admin/teams`
- `notifications.py` → `/admin/notifications`

### Frontend API module mapping

- `frontend/lib/api/` is for platform-side modules.
- `frontend/lib/api/admin/` is for dashboard/admin modules and keeps the `/admin/` prefix.

Do not mix the two namespaces when adding new endpoints.

## Validation error handling

Validation failures should return field-level errors in the standard response shape so the frontend can map them to form fields.

```json
{
  "code": 1001,
  "data": {
    "errors": {
      "email": "value is not a valid email address"
    }
  },
  "msg": "验证错误"
}
```

Use dot notation for nested fields such as `user.email`.

## Related docs

- `../api/BACKEND_API.md`
- `./audit-logging.md`
- `./migrations-and-init-data.md`
- `./celery-and-async-jobs.md`
- `../design/access-control/RBAC_SPEC.md`
