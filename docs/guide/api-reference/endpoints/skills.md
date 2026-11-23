# Skills API

The Skills API manages skills: sandboxed capabilities that Agent packages can call. Skills are installed as packages imported from a ZIP archive or a Git repository, are owned either by a team or by the platform (`team_id` is `null` for system skills), and are executed inside the code sandbox.

Base URL: `/api/v1/skills`. All endpoints require an authenticated JWT user session (`Authorization: Bearer <token>`); API-key authentication is not accepted.

**Required permissions:**

- `skill:read` — List and read skills
- `skill:create` — Preview and install skill imports
- `skill:update` — Update skills
- `skill:delete` — Delete skills
- `skill:execute` — Test-execute a skill

Team scoping is enforced separately from the permission codes: every team-scoped operation also requires the global `team:read` permission, team skills require membership of the owning team (team admin for update, delete, and test), and system skills require a superuser for update, delete, and test.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/skills` | List system and team skills available to a team |
| `POST` | `/api/v1/skills/import/preview-zip` | Scan an uploaded skill ZIP and start an import session |
| `POST` | `/api/v1/skills/import/preview-git` | Clone a Git repository, scan it, and start an import session |
| `POST` | `/api/v1/skills/import/{session_id}/install` | Install or update the packages selected from a preview session |
| `GET` | `/api/v1/skills/{skill_id}` | Get skill details |
| `PATCH` | `/api/v1/skills/{skill_id}` | Update skill metadata and configuration |
| `DELETE` | `/api/v1/skills/{skill_id}` | Delete a skill |
| `POST` | `/api/v1/skills/{skill_id}/test` | Execute a skill once with test arguments |

All responses use the standard envelope `{"code": 0, "data": ..., "msg": "success"}`.

---

## Skill Object

| Field | Type | Description |
|---|---|---|
| `id` | `string` (UUID) | Skill ID |
| `team_id` | `string \| null` | Owning team; `null` for a system skill |
| `name` | `string` | Stable skill name |
| `display_name` | `string` | Display name |
| `description` | `string` | Description |
| `icon` | `string \| null` | Icon emoji or URL |
| `category` | `string` | Skill category (see below) |
| `version` | `string` | Skill version |
| `source_type` | `string` | How the package was installed: `zip`, `git`, `manual_text`, or `legacy` |
| `source_uri` | `string \| null` | Redacted source URI for Git/imported packages |
| `source_ref` | `string \| null` | Git ref or resolved source revision |
| `source_subdir` | `string \| null` | Source subdirectory scanned during import |
| `package_path` | `string \| null` | Storage path of the installed package |
| `package_hash` | `string \| null` | Content hash of the installed package |
| `input_schema` | `object` | JSON Schema of the arguments the skill accepts |
| `default_config` | `object` | Default configuration merged into an agent's per-tool config |
| `is_enabled` | `boolean` | Whether the skill can be selected/executed |
| `is_system` | `boolean` | `true` when `team_id` is `null` |
| `import_warnings` | `array` of `string` | Warnings recorded when the package was imported |
| `created_by_id` | `string \| null` | Creator user ID |
| `created_by_name` | `string \| null` | Creator username |
| `created_at` | `string` | Creation timestamp |
| `updated_at` | `string` | Last update timestamp |

`category` is one of: `file`, `code`, `data`, `web`, `api`, `other`.

### Skill Detail Object

Skill detail responses extend the object above with the package contents:

| Field | Type | Description |
|---|---|---|
| `skill_md` | `string` | Raw `SKILL.md` contents |
| `instructions` | `string` | Instructions extracted from the package |
| `frontmatter` | `object` | Parsed `SKILL.md` frontmatter |
| `package_manifest` | `object` | Package manifest |
| `execution_config` | `object` | Execution configuration |
| `config_schema` | `object` | JSON Schema of the skill configuration |

---

## List Skills

Returns every skill available to the given team, partitioned into system skills and team skills. Results are not paginated.

```http
GET /api/v1/skills?team_id=b7f2c9d4-1a3e-4f5b-8c6d-9e0a1b2c3d4e&include_system=true&enabled=true&search=analysis&category=data HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `team_id` | `string` (UUID) | Yes | - | Team whose skills are listed; the caller must be a member |
| `include_system` | `boolean` | No | `true` | Also return system skills (`team_id` is `null`) |
| `enabled` | `boolean` | No | - | When set, only return skills with this `is_enabled` value |
| `search` | `string` | No | - | Case-insensitive match against `name`, `display_name`, and `description` |
| `category` | `string` | No | - | Filter by skill category |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "system": [
      {
        "id": "5c2f9a10-8b3d-4e6f-9a71-b2c3d4e5f607",
        "team_id": null,
        "name": "file_read",
        "display_name": "File Reader",
        "description": "Reads files from the workspace",
        "icon": "📄",
        "category": "file",
        "version": "1.0.0",
        "source_type": "zip",
        "source_uri": "system-skills.zip",
        "source_ref": null,
        "source_subdir": null,
        "package_path": "/data/skills/system/file_read",
        "package_hash": "sha256:1f0c0b7d2a9e4c8f",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        "default_config": {},
        "is_enabled": true,
        "is_system": true,
        "import_warnings": [],
        "created_by_id": null,
        "created_by_name": null,
        "created_at": "2026-01-10T09:00:00Z",
        "updated_at": "2026-01-10T09:00:00Z"
      }
    ],
    "team": [
      {
        "id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
        "team_id": "b7f2c9d4-1a3e-4f5b-8c6d-9e0a1b2c3d4e",
        "name": "data_analysis_skill",
        "display_name": "Data Analysis Skill",
        "description": "Analyzes tabular CSV datasets and generates statistical charts",
        "icon": null,
        "category": "data",
        "version": "1.0.0",
        "source_type": "git",
        "source_uri": "https://github.com/example/skills.git",
        "source_ref": "9c1f4a7b2d8e3f5061a2b3c4d5e6f70819a2b3c4",
        "source_subdir": "data_analysis",
        "package_path": "/data/skills/team/data_analysis_skill",
        "package_hash": "sha256:8d2e6f1a4b0c9d3e",
        "input_schema": {"type": "object", "properties": {"dataset": {"type": "string"}}},
        "default_config": {"max_rows": 1000},
        "is_enabled": true,
        "is_system": false,
        "import_warnings": [],
        "created_by_id": "3d1f7a92-5b6c-4f8e-9a01-2c3d4e5f6a7b",
        "created_by_name": "alice",
        "created_at": "2026-03-01T12:00:00Z",
        "updated_at": "2026-03-01T12:00:00Z"
      }
    ]
  },
  "msg": "success"
}
```

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4004` | `team_not_found` — the supplied `team_id` does not exist |
| `403` | `3000` | `operation_not_permitted` — caller lacks the global `skill:read` permission |
| `403` | `3002` | `not_team_member` |

---

## Preview ZIP Import

Upload a ZIP archive, scan it for skill packages, and create a short-lived import session. The archive must be at most 50 MB, contain at most 500 files, and expand to at most 50 MB.

```http
POST /api/v1/skills/import/preview-zip HTTP/1.1
Authorization: Bearer <token>
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

------WebKitFormBoundary7MA4YWxkTrZu0gW
Content-Disposition: form-data; name="team_id"

b7f2c9d4-1a3e-4f5b-8c6d-9e0a1b2c3d4e
------WebKitFormBoundary7MA4YWxkTrZu0gW
Content-Disposition: form-data; name="file"; filename="skills.zip"
Content-Type: application/zip

<zip bytes>
------WebKitFormBoundary7MA4YWxkTrZu0gW--
```

### Form Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | `file` | Yes | ZIP archive (`.zip`); other extensions are rejected |
| `team_id` | `string` (UUID) | No | Team that will own the imported skills; the caller must be a team admin. Omit it to import system skills, which is reserved for superusers |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "session_id": "f0e1d2c3-b4a5-4968-8778-99aabbccddee",
    "source_type": "zip",
    "source_uri": "skills.zip",
    "source_ref": null,
    "source_subdir": null,
    "skills": [
      {
        "package_path": "data_analysis_skill",
        "name": "data_analysis_skill",
        "display_name": "Data Analysis Skill",
        "description": "Analyzes tabular CSV datasets",
        "version": "1.0.0",
        "category": "data",
        "icon": null,
        "valid": true,
        "errors": [],
        "warnings": [],
        "conflict": null,
        "file_count": 4,
        "package_hash": "sha256:8d2e6f1a4b0c9d3e"
      }
    ],
    "invalid": [],
    "warnings": []
  },
  "msg": "success"
}
```

### Preview Item

| Field | Type | Description |
|---|---|---|
| `package_path` | `string` | Package path relative to the archive/repository root |
| `name` | `string \| null` | Skill name |
| `display_name` | `string \| null` | Display name |
| `description` | `string` | Description |
| `version` | `string` | Version (defaults to `1.0.0`) |
| `category` | `string` | Skill category |
| `icon` | `string \| null` | Icon |
| `valid` | `boolean` | `false` for packages that cannot be installed |
| `errors` | `array` of `string` | Message keys describing why a package is invalid (e.g. `skill_md_not_found`) |
| `warnings` | `array` of `string` | Message keys such as `skill_name_conflict` or `skill_duplicate_name_in_source` |
| `conflict` | `object \| null` | `{"type": "existing_team_skill", "skill_id": null, "message": null}` when a skill of the same name already exists in the target team |
| `file_count` | `integer` | Files in the package |
| `package_hash` | `string \| null` | Package content hash |

Packages with `valid: false` are returned in `invalid` instead of `skills`; `errors`/`warnings` entries are i18n message keys.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `1002` | `skill_zip_required`, `skill_zip_invalid`, `skill_zip_too_large`, or `skill_zip_too_many_files` |
| `404` | `4004` | `team_not_found` — the supplied `team_id` does not exist |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:create` permission) or `skill_system_admin_required` (`team_id` omitted and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — `team_id` provided and the caller is not a member |
| `403` | `3003` | `team_admin_required` — `team_id` provided and the caller is a member but not an owner/admin |

---

## Preview Git Import

Clone a Git repository, scan it for skill packages, and create a short-lived import session. The clone times out after 180 seconds.

```http
POST /api/v1/skills/import/preview-git HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "team_id": "b7f2c9d4-1a3e-4f5b-8c6d-9e0a1b2c3d4e",
  "repo_url": "https://github.com/example/skills.git",
  "ref": "main"
}
```

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `team_id` | `string \| null` (UUID) | No | Team that will own the imported skills; the caller must be a team admin. Omit it to import system skills, which is reserved for superusers |
| `repo_url` | `string` | Yes | Repository URL (1–2000 characters); the URL is validated before cloning |
| `ref` | `string \| null` | No | Branch, tag, or commit to check out (max 255 characters); defaults to the repository's default branch |

### Response (`200 OK`)

Same shape as the ZIP preview, with `source_type: "git"`, `source_uri` set to the redacted repository URL, and `source_ref` set to the resolved revision.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `400` | `1002` | `skill_git_url_invalid` or the clone failed |
| `404` | `4004` | `team_not_found` — the supplied `team_id` does not exist |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:create` permission) or `skill_system_admin_required` (`team_id` omitted and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — `team_id` provided and the caller is not a member |
| `403` | `3003` | `team_admin_required` — `team_id` provided and the caller is a member but not an owner/admin |

---

## Install Import

Install the packages selected from a preview session. Preview sessions expire one hour after creation; `team_id` and the source are taken from the session, so the install request only selects packages.

```http
POST /api/v1/skills/import/f0e1d2c3-b4a5-4968-8778-99aabbccddee/install HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "items": [
    {"package_path": "data_analysis_skill", "action": "install"},
    {"package_path": "charts_skill", "action": "update", "skill_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"}
  ],
  "is_enabled": true
}
```

### Path Parameters

| Parameter | Type | Description |
|---|---|---|
| `session_id` | `string` (UUID) | The `session_id` returned by a preview endpoint |

### Request Body

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `items` | `array` | No | `[]` | Packages to install; when empty nothing is installed |
| `items[].package_path` | `string` | Yes | - | Must match a `package_path` in the session preview |
| `items[].action` | `string` | No | `install` | `install`, `update`, or `skip` |
| `items[].skill_id` | `string \| null` (UUID) | No | - | Explicit target for `update`; must belong to the session's team |
| `is_enabled` | `boolean` | No | `true` | `is_enabled` applied to every installed/updated skill |

Package selection rules:

- `install` fails per package (`skill_name_exists`) when a skill with the same name already exists in the session's team.
- `update` targets the explicit `skill_id` when given, otherwise the team skill whose `name` matches the package name; when neither exists the whole request fails with `404` / `4000` `skill_not_found`.
- `skip` records the package path without touching any skill.

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "installed": ["a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"],
    "updated": [],
    "skipped": ["charts_skill"],
    "errors": ["other_skill: skill_name_exists"]
  },
  "msg": "Skills imported successfully"
}
```

| Field | Type | Description |
|---|---|---|
| `installed` | `array` of UUID | IDs of newly created skills |
| `updated` | `array` of UUID | IDs of updated skills |
| `skipped` | `array` of `string` | `package_path` of skipped packages |
| `errors` | `array` of `string` | `"<package_path>: <message_key>"` entries for packages that could not be installed |

A non-empty `errors` array still returns `200 OK` with `code: 0`; the per-package errors are only reported in `data.errors`.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4000` | `skill_import_session_not_found`, or the target of an `update` item is missing (`skill_not_found`) |
| `400` | `1002` | `skill_import_session_expired` |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:create` permission) or `skill_system_admin_required` (the session imports system skills and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — caller is not a member of the session's team |
| `403` | `3003` | `team_admin_required` — caller is a member of the session's team but not an owner/admin |

---

## Get Skill

```http
GET /api/v1/skills/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d?team_id=b7f2c9d4-1a3e-4f5b-8c6d-9e0a1b2c3d4e HTTP/1.1
Authorization: Bearer <token>
```

### Query Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `team_id` | `string` (UUID) | No | Team context. For a team skill, the caller must be a member of the owning team regardless of this parameter. For a system skill, passing `team_id` requires membership of that team; omitting it applies no team check |

### Response (`200 OK`)

`data` is the [Skill Detail Object](#skill-detail-object).

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4000` | `skill_not_found` |
| `404` | `4004` | `team_not_found` — the supplied `team_id` does not exist |
| `403` | `3000` | `operation_not_permitted` — caller lacks the global `skill:read` permission |
| `403` | `3002` | `not_team_member` |

---

## Update Skill

```http
PATCH /api/v1/skills/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "display_name": "Advanced Data Analysis",
  "description": "Analyzes CSV datasets and renders charts",
  "is_enabled": false,
  "default_config": {"max_rows": 5000}
}
```

### Request Body

All fields are optional; only the fields present in the body are applied.

| Field | Type | Description |
|---|---|---|
| `display_name` | `string \| null` | Display name (1–100 characters) |
| `description` | `string \| null` | Description |
| `icon` | `string \| null` | Icon (max 100 characters) |
| `category` | `string \| null` | Skill category |
| `is_enabled` | `boolean \| null` | Enable or disable the skill |
| `default_config` | `object \| null` | Default configuration |

### Response (`200 OK`)

`data` is the updated [Skill Detail Object](#skill-detail-object) and `msg` is `Skill updated successfully`.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4000` | `skill_not_found` |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:update` permission) or `skill_system_admin_required` (system skill and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — team skill and the caller is not a member of the owning team |
| `403` | `3003` | `team_admin_required` — team skill and the caller is a member but not an owner/admin |

---

## Delete Skill

Deletes the skill row and its private package storage. A skill that is still referenced by an agent's `tools_config` cannot be deleted.

```http
DELETE /api/v1/skills/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d HTTP/1.1
Authorization: Bearer <token>
```

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": null,
  "msg": "Skill deleted successfully"
}
```

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4000` | `skill_not_found` |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:delete` permission) or `skill_system_admin_required` (system skill and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — team skill and the caller is not a member of the owning team |
| `403` | `3003` | `team_admin_required` — team skill and the caller is a member but not an owner/admin |
| `400` | `1002` | `skill_referenced_by_agent` |

---

## Test Skill

Executes the skill once in the code sandbox with the supplied arguments. Test execution requires the same privileges as updating the skill: superuser for system skills, team admin for team skills.

```http
POST /api/v1/skills/a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d/test HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "arguments": {"dataset": "sales.csv"},
  "config": {"max_rows": 100}
}
```

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| `arguments` | `object` | No | Arguments passed to the skill (default: `{}`) |
| `config` | `object` | No | Configuration overrides for this run (default: `{}`) |

### Response (`200 OK`)

```json
{
  "code": 0,
  "data": {
    "success": true,
    "result": {"rows": 1200, "columns": 8},
    "error": null,
    "stdout": "processed sales.csv\n",
    "stderr": "",
    "artifacts": [
      {
        "path": "/workspace/report.html",
        "optional": false,
        "description": "Generated report",
        "file_type": "file",
        "size": 20480,
        "checksum": "sha256:...",
        "content_type": "text/html",
        "storage_path": "skills/artifacts/report.html",
        "url": null,
        "filename": "report.html"
      }
    ],
    "duration_ms": 842
  },
  "msg": "success"
}
```

| Field | Type | Description |
|---|---|---|
| `success` | `boolean` | Whether the skill run succeeded |
| `result` | `any` | Skill return value |
| `error` | `string \| null` | Error message when the run failed |
| `stdout` | `string` | Captured standard output |
| `stderr` | `string` | Captured standard error |
| `artifacts` | `array` | Artifacts produced by the run |
| `duration_ms` | `integer \| null` | Run duration in milliseconds |

A failed skill run is reported as `200 OK` with `code: 0`, `data.success: false`, and the reason in `data.error`.

### Errors

| HTTP | `code` | Meaning |
|---|---|---|
| `404` | `4000` | `skill_not_found` |
| `403` | `3000` | `operation_not_permitted` (caller lacks the global `skill:execute` permission) or `skill_system_admin_required` (system skill and the caller is not a superuser) |
| `403` | `3002` | `not_team_member` — team skill and the caller is not a member of the owning team |
| `403` | `3003` | `team_admin_required` — team skill and the caller is a member but not an owner/admin |

---

## Validation Errors

FastAPI request validation failures (bad UUID format, `display_name` outside 1–100 characters, unknown `category`, …) return HTTP `422` with the standard error envelope:

```json
{
  "code": 1001,
  "data": {
    "errors": {
      "display_name": ["Validation error"]
    }
  },
  "msg": "Validation error"
}
```
