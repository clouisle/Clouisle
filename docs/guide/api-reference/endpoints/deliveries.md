# Delivery Log API

Messaging integrations (Feishu Agent chat, WeChat Agent chat) share one durable outbound queue. Operators inspect delivery outcomes on the standalone **Delivery log** page (`/deliveries`), which calls this endpoint.

The queue is internal delivery state, not message history. A `sent` row means the provider accepted the reply request; it does not prove the recipient opened or downloaded anything.

## Permissions

Both the page and the endpoint require `admin:integrations:settings:read`. Superusers bypass the check. Message text, provider resource keys (`media_key`), credentials and file contents are never returned.

## List deliveries

`GET /api/v1/admin/deliveries`

| Parameter | Type | Description |
|---|---|---|
| `provider_type` | repeated `feishu` / `wechat` | Optional integration filter. Repeat the parameter to match any listed provider (OR). |
| `status` | repeated `pending` / `sending` / `sent` / `error` / `unavailable` / `unknown` | Optional delivery-state filter. Repeat to match any listed status (OR). |
| `run_id` | UUID | Optional `AgentRun` filter. |
| `filename` | string (1–500) | Optional case-insensitive substring filter on artifact file names. |
| `limit` | integer 1–100 | Page size; default 25. |
| `offset` | integer ≥ 0 | Page offset; default 0. |

Example with multiple values (provider values are ORed, statuses are ORed, and the two filters are combined with AND):

```text
GET /api/v1/admin/deliveries?provider_type=feishu&provider_type=wechat&status=error&status=unknown
```

Sending one value is equivalent to a singleton filter, e.g. `?provider_type=feishu&status=error`.
Response `data`:

```json
{
  "items": [
    {
      "id": "uuid",
      "provider_type": "feishu",
      "run_id": "uuid",
      "user_id": "uuid",
      "agent_id": "uuid",
      "chat_id": "oc_...",
      "message_id": "om_...",
      "event_key": "final-asset",
      "sequence": 0,
      "kind": "asset",
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "size": 12345,
      "media_type": "file",
      "status": "error",
      "error": "feishu_agent_asset_upload_failed",
      "error_detail": "FeishuAPIError: Feishu API error 234001: Invalid request param. | HTTP 400 | code 234001 | {\"code\":234001,...}",
      "has_media_key": false,
      "created_at": "2026-10-22T10:03:13Z",
      "updated_at": "2026-10-22T10:03:13Z"
    }
  ],
  "total": 1,
  "limit": 25,
  "offset": 0
}
```

`error` is the stable failure key used by behaviour and localization; `error_detail` keeps the provider's original error message, HTTP status, code and response excerpt so operators can fix the cause. The page shows `error_detail` when present and falls back to the key.

Rows are ordered newest first. `event_key` identifies what the row is (for example `final`, `final-asset`, `ask:<tool-call>`, `received`); `sequence` orders chunks of the same event. `has_media_key` reports whether an uploaded provider resource key is already stored for the row without exposing it.

## Status meanings

| Status | Meaning |
|---|---|
| `pending` | Queued, not yet claimed by a sender. Preserved across restarts and feature pauses. |
| `sending` | Claimed by one worker under a lease. A row whose lease expired becomes `unknown` instead of being resent. |
| `sent` | The provider accepted the reply request. |
| `error` | A permanent failure, such as a provider rejection or an unavailable artifact. |
| `unavailable` | The run finished but the reply must not be sent (disabled channel, revoked access, missing conversation context). |
| `unknown` | A timeout after transmission. The row is never resent blindly. |

## Upgrade note

One table (`integration_deliveries`) replaces the former per-provider delivery tables. Startup copies existing rows and drops `feishu_agent_deliveries` and `wechat_agent_deliveries`; deploy the matching API and worker versions together because an older process would write to a table that no longer exists.
