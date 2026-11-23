# Agent Skills Design Document

## Background & Goals

Clouisle Agents need to call Skills, but the initial implementation exposed low-level sandbox JSON (`input_schema`, `skill_spec`, `command_template`) to users. That is the wrong product model. A Skill should be imported from a package root containing `SKILL.md`; common sources are a zip bundle containing multiple Skill directories or a Git repository containing multiple Skill directories.

Success criteria:

- Tool Center Skills tab can import Skills from a zip bundle or public HTTPS Git repository.
- A source can contain multiple Skill roots; each directory containing `SKILL.md` is previewed independently.
- Users preview scanned Skills, select which to install, and choose install/update/skip for conflicts.
- Installed Skills are stored as team/system resources with source, package path, package hash, manifest, frontmatter, instructions, input schema, and execution metadata.
- Agents select installed Skills through `tools_config` using `{ "type": "skill", "skill_id": "...", "config": {...} }`.
- LLM tool calls resolve only against the current Agent's configured and accessible Skills.
- Standard Skills default to instructions mode: the tool result returns `SKILL.md` instructions and metadata for the next model turn.
- Only Skills that declare a Clouisle script extension run code, and script execution always goes through the sandbox with `shell=false`.
- Skill import, execution, update, delete, and test paths enforce team permissions, use backend i18n `BusinessError` responses, and avoid logging raw arguments, package contents, env, credentials, or tokenized Git URLs.

## High-Level Design

Skills are package-backed backend resources. A package source is staged into a temporary isolated directory, scanned recursively for `SKILL.md`, previewed, and only then copied into private Skill storage during install.

Supported first-version source structures:

```text
skills-bundle.zip
├── summarize-doc/
│   ├── SKILL.md
│   └── references/...
└── nested/group/pdf-tools/
    └── SKILL.md
```

```text
repo/
├── skills/summarize-doc/SKILL.md
├── .claude/skills/review-pr/SKILL.md
└── other/path/custom-skill/SKILL.md
```

`SKILL.md` uses YAML frontmatter plus Markdown body. Required frontmatter fields are `name` and `description`; optional standard fields include `version`, `license`, `author`, `category`, `icon`, and `metadata`. Clouisle-specific behavior lives under `x-clouisle`:

```yaml
---
name: summarize-doc
description: Summarize documents and extract key action items. Use when the user asks to summarize documents or identify action items.
version: 1.0.0
x-clouisle:
  input_schema:
    type: object
    properties:
      prompt:
        type: string
        description: The user task for this skill.
    required: ["prompt"]
  test_arguments:
    prompt: "Run this skill on a simple sample."
  execution:
    mode: instructions # instructions | script
    runtime: python
    script: scripts/run.py
    limits:
      timeout_seconds: 30
    artifacts: []
---

Skill instructions for the model.
```

Default behavior:

- Missing `x-clouisle.input_schema` becomes a generic `prompt` object schema.
- Missing `x-clouisle.execution.mode` becomes `instructions`.
- Script paths must be relative to the Skill root and cannot contain `..` or be absolute.
- Shell command strings are not supported.

Runtime flow:

1. Agent configuration stores selected Skills by `skill_id`.
2. Chat or `AgentService` loads enabled, visible Skills configured on the current Agent.
3. Each Skill becomes a function tool named `skill_<normalized_name>_<short_id>` using the parsed input schema.
4. The model calls that function with JSON arguments.
5. Backend resolves the function name only through the current Agent's configured Skills.
6. Instructions mode returns an instruction payload containing the Skill instructions, manifest summary, metadata, and arguments.
7. Script mode builds a sandbox job with inline package/input files, writes them under `/workspace`, and runs the declared script with arguments/config passed through `/workspace/input/skill-input.json`.

## Implementation Plan

### Stage 1: Planning correction

- **Files modified**: `docs/IMPLEMENTATION_PLAN.md`, `docs/plan/agent-skills.md`
- **Specific logic**: Mark the initial raw JSON Skill implementation as requiring redesign. Document zip/Git multi-Skill import, package parsing, preview/install sessions, instructions mode, and sandbox-only script mode.
- **Validation**: The implementation index and this document no longer describe manual `skill_spec` editing as the primary path.

### Stage 2: Backend package-driven Skill model and schemas

- **Files modified**: `backend/app/models/skill.py`, `backend/app/schemas/skill.py`, `backend/app/core/init_data.py`
- **Specific logic**:
  - Add Skill package fields: `source_type`, `source_uri`, `source_ref`, `package_path`, `package_storage_path`, `package_hash`, `package_manifest`, `skill_md`, `instructions`, `frontmatter`, `execution_config`, and `import_warnings`.
  - Keep legacy `skill_spec` / `config_schema` fields temporarily for existing incomplete data, but remove them from the primary create UI and package import schemas.
  - Add import session model/schema or equivalent persistent session contract with `previewed` / `installed` / `expired` status.
  - Add preview and install request/response schemas for zip/Git sources and selected items.
  - Make `PATCH /skills/{id}` limited to safe metadata overrides such as enabled state and display fields.
- **Validation**:
  - Startup migration is idempotent for both new and existing `skills` tables.
  - Schemas represent valid previews, invalid package entries, conflicts, and install/update/skip actions.

### Stage 3: Zip/Git scanning, package parsing, and import sessions

- **Files modified**: `backend/app/services/skill_package.py`, `backend/app/services/skill_import.py`, `backend/app/services/skill.py`
- **Specific logic**:
  - Recursively scan for `SKILL.md` up to a bounded depth.
  - Ignore `.git`, `node_modules`, `.next`, `dist`, `build`, `__pycache__`, `.venv`, `venv`, and `.tox`.
  - Parse frontmatter, instructions, default prompt schema, `x-clouisle` input schema, execution config, manifest, file count, and package hash.
  - Detect duplicate names within one source and existing team/system conflicts.
  - Preview zip sources with size, count, path traversal, symlink, special-file, and nested-archive checks.
  - Preview Git sources only from public HTTPS URLs without embedded credentials, with clone timeout and scan limits.
  - Install selected packages into private Skill storage and create/update DB rows.
- **Validation**:
  - Unit tests cover valid multi-Skill zip, nested Skills, duplicate names, invalid frontmatter, path traversal, symlink rejection, oversized packages, Git URL rejection, and conflict actions.

### Stage 4: Skills import API, permissions, audit, and i18n

- **Files modified**: `backend/app/api/v1/endpoints/skills.py`, `backend/app/api/v1/api.py`, `backend/app/locales/en/LC_MESSAGES/messages.po`, `backend/app/locales/zh/LC_MESSAGES/messages.po`
- **Specific logic**:
  - Add `POST /skills/import/preview-zip`.
  - Add `POST /skills/import/preview-git`.
  - Add `POST /skills/import/{session_id}/install`.
  - Keep `GET /skills`, `GET /skills/{id}`, `PATCH /skills/{id}`, `DELETE /skills/{id}`, and `POST /skills/{id}/test` with package semantics.
  - Enforce team owner/admin for team imports and superuser for system imports.
  - Block delete when any Agent references the Skill.
  - Audit preview/install/update/delete/test/execute without raw content or credentials.
- **Validation**:
  - API tests cover permissions, team isolation, conflict update, delete protection, i18n errors, and audit redaction.

### Stage 5: Skill tool definition and instructions/script execution

- **Files modified**: `backend/app/services/skill.py`, `backend/app/services/skill_executor.py`, `backend/app/api/v1/endpoints/chat.py`, `backend/app/api/v1/endpoints/chat_helpers/tool_utils.py`, `backend/app/api/v1/endpoints/chat_helpers/tool_executor.py`, `backend/app/services/agent.py`
- **Specific logic**:
  - Build tool definitions from parsed description and input schema.
  - Preserve function-name scoping through current Agent configured Skills.
  - Instructions mode returns `SKILL.md` body and metadata as a tool result without sandbox execution.
  - Script mode generates a sandbox job with `SandboxJobSource.SKILL`, `shell=false`, inline package files staged under `/workspace/skill`, arguments/config written to `/workspace/input/skill-input.json`, and artifacts collected from declared `/workspace` paths.
  - Disabled, cross-team, and unconfigured Skills fail before execution.
- **Validation**:
  - Tests verify configured Skills appear as tools, unconfigured `skill_*` names fail, instructions mode returns instruction payload, and script mode submits a sandbox Skill job.

### Stage 6: Frontend import, preview, install, detail, and test UI

- **Files modified**: `frontend/lib/api/skills.ts`, `frontend/app/(platform)/app/tools/_components/skills-panel.tsx`, optional split components under the same directory, `frontend/i18n/en/platform.json`, `frontend/i18n/zh/platform.json`, generated i18n types
- **Specific logic**:
  - Remove raw JSON create/edit form from the Skills tab.
  - Add “Import Skills” dialog with zip and Git tabs.
  - Zip tab uploads `.zip` and requests scan preview.
  - Git tab accepts repo URL and ref, then scans the full checked-out repository for `SKILL.md`.
  - Preview table shows checkbox, package path, name, description, version, mode, file count, warnings/errors, conflict, and action.
  - Install selected packages and refresh Skill cards.
  - Detail/test views show `SKILL.md`, manifest/source metadata, execution mode, and prompt/simple JSON test input.
- **Validation**:
  - Manual verification imports multiple Skills from zip, previews Git repository Skills, updates/skips conflicts, tests an instructions Skill, and reloads the Skill list.
  - Run frontend i18n generation/check, lint, and build.

### Stage 7: Agent selection and end-to-end security/regression tests

- **Files modified**: `frontend/app/(platform)/app/apps/[id]/_components/tool-selector.tsx`, `frontend/app/(platform)/app/apps/[id]/_components/agent-orchestration-form.tsx`, backend service/API/chat/workflow tests
- **Specific logic**:
  - Agent selector continues showing installed enabled Skills and saving `{ type: "skill", "skill_id": "..." }`.
  - Chat and Workflow Agent nodes can execute Agents configured with instructions or script Skills.
  - Existing builtin/custom/MCP tool behavior remains unchanged.
- **Validation**:
  - End-to-end regression covers Agent save/reload, chat Skill call, Workflow AgentNode Skill call, disabled Skill rejection, cross-team rejection, unsafe zip rejection, and unsafe Git URL rejection.

## Testing Strategy

Happy path:

- Upload a zip with multiple Skill directories and install selected valid Skills.
- Preview a public HTTPS Git repo by scanning the full repository and install selected valid Skills.
- Select an installed Skill for an Agent, save, reload, and verify the function tool appears.
- Invoke an instructions Skill and verify the tool result contains instructions and arguments.
- Invoke a script Skill and verify sandbox source is `SKILL`, shell is false, and package files are available.
- Run a Workflow Agent node that invokes an Agent configured with a Skill.

Error path:

- Missing `SKILL.md`, malformed frontmatter, missing `name`, missing `description`, invalid input schema, invalid execution mode, unsafe script path.
- Zip path traversal, absolute path, symlink, special file, nested archive, excessive file count, excessive uncompressed size.
- Git `file://`, SSH, local path, embedded credentials, unsupported protocol, excessive clone/scan size.
- Duplicate Skill names in one source.
- Install conflict without update action.
- Non-admin team import/update/delete.
- Cross-team access, disabled Skill execution, and unconfigured `skill_*` function name.

Regression scope:

- Existing builtin/custom/MCP Agent tools.
- Existing media tool rendering and execution.
- Existing Workflow Agent node behavior.
- Tool Center non-Skill tool list/create/edit/delete/share flows.

Verification commands:

- `PYTHONPATH=backend uv run --directory backend pytest tests/services/test_skill_package.py tests/services/test_skill_import.py tests/services/test_skill_executor.py tests/api/test_skills_api.py`
- `uv run --directory backend ruff check .`
- `uv run --directory backend ruff format --check .`
- `uv run --directory backend mypy app/`
- `bun run --cwd frontend i18n:gen-types`
- `bun run --cwd frontend i18n:lint --strict`
- `bun run --cwd frontend lint`
- `bun run --cwd frontend build`

## Risks & Mitigation

- **Package import security risk**: Zip and Git import can expose path traversal, oversized payloads, symlinks, SSRF-style URL issues, or credential leakage. Mitigate with strict archive validation, HTTPS-only Git without credentials, bounded clone/scan, private storage, and audit redaction.
- **Ambiguous Skill standard risk**: External Skill formats may evolve. Keep only `name` and `description` required, preserve raw frontmatter, and place Clouisle-specific behavior under `x-clouisle`.
- **Execution confusion risk**: Users may expect all Skills to run code. Make instructions mode explicit in UI and only run script mode when the package declares a valid script extension.
- **Migration risk**: Existing incomplete raw JSON Skill rows may exist. Preserve legacy columns temporarily and migrate additively.
- **Chat integration duplication risk**: Chat and `AgentService` both execute tools. Keep Skill lookup and execution semantics in shared services.

Rollback plan:

- Disable Skill import endpoints if package ingestion must be halted.
- Disable affected Skills to stop runtime usage immediately.
- Remove Skill configs from affected Agents.
- Revert chat/AgentService Skill branches while leaving existing builtin/custom/MCP paths untouched.
- Keep `skills` rows and package storage unused; no destructive rollback is required.
