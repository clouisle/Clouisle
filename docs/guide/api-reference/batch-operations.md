# Batch Operations Guide

This guide explains the batch operations available in the Clouisle API.

## Overview

Clouisle does **not** provide generic batch create/update endpoints (`/agents/batch`, `/users/batch`, ...). Batch operations exist for specific use cases where they are genuinely useful:

- **Batch delete conversations** — `DELETE /api/v1/conversations?ids=...`
- **Batch authorize/revoke team models** — `POST`/`DELETE /api/v1/teams/{team_id}/models/batch`
- **Batch KB search** — evaluate multiple retrieval configurations for one query
- **Batch file parsing** — `POST /api/v1/upload/parse/batch` (max 5 files)
- **Admin batch delete conversations** — `DELETE /api/v1/admin/conversations?ids=...`

There are no batch-size limits like "max 100 items" or "10 MB request" — each endpoint defines its own constraints (documented below).

## 1. Batch Delete Conversations

Deletes multiple conversations (and their messages) in one request.

**Endpoint:**
```
DELETE /api/v1/conversations?ids=<uuid1>&ids=<uuid2>&...
```

**Authorization:** `conversation:delete` permission. Super Admins/Admins can delete conversations in accessible teams; Members/Viewers can only delete their own.

**curl:**
```bash
curl -X DELETE "$API_BASE_URL/api/v1/conversations?ids=550e8400-e29b-41d4-a716-446655440000&ids=550e8400-e29b-41d4-a716-446655440001" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN"
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "deleted_count": 2,
    "ids": [
      "550e8400-e29b-41d4-a716-446655440000",
      "550e8400-e29b-41d4-a716-446655440001"
    ]
  },
  "msg": "success"
}
```

The request succeeds only if the user has permission to delete **all** listed conversations; otherwise a permission error (`3000`) or not-found error (`4000`) is returned.

## 2. Batch Authorize Team Models

Grants a team access to multiple models at once. **Super admin only.**

**Endpoint:**
```
POST /api/v1/teams/{team_id}/models/batch
```

**Request:**
```json
{
  "model_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ],
  "daily_token_limit": 1000000,
  "monthly_token_limit": 30000000,
  "daily_request_limit": 1000,
  "monthly_request_limit": 30000
}
```

Quota limits are optional and apply to all authorized models in the batch.

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/teams/$TEAM_ID/models/batch" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_ids": ["550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001"]
  }'
```

**Response:** a list of newly created team-model authorization records (`TeamModelResponse` objects), each containing `id`, `team_id`, `model_id`, `model` (brief info), and quota fields. Existing authorizations are skipped, and unknown model IDs are ignored.

## 3. Batch Revoke Team Models

Removes a team's access to multiple models. **Super admin only.**

**Endpoint:**
```
DELETE /api/v1/teams/{team_id}/models/batch
```

**Request:**
```json
{
  "model_ids": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ]
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "deleted_count": 2
  },
  "msg": "success"
}
```

## 4. Batch Knowledge-Base Search

Evaluates **one query** against **up to 10 independent retrieval configurations** in a single request (request-scoped embedding reuse).

**Endpoint:**
```
POST /api/v1/knowledge-bases/{kb_id}/search/batch
```

**Request:**
```json
{
  "query": "How to reset password?",
  "configurations": [
    {
      "id": "hybrid-top5",
      "search_mode": "hybrid",
      "top_k": 5,
      "score_threshold": 0.0
    },
    {
      "id": "vector-top10",
      "search_mode": "vector",
      "top_k": 10
    }
  ]
}
```

Configuration fields: `search_mode` (`vector` | `fulltext` | `hybrid`), `top_k` (1-20), `score_threshold` (0-1), `dense_weight`, `lexical_weight`, `rrf_k`, `filter_doc_ids`, `rerank_enabled`, `rerank_candidate_k`, `rerank_score_threshold`. Configuration `id`s must be unique.

**Response:** each configuration produces an independent outcome:

```json
{
  "code": 0,
  "data": {
    "query": "How to reset password?",
    "outcomes": [
      {
        "id": "hybrid-top5",
        "status": "fulfilled",
        "response": {
          "query": "How to reset password?",
          "results": [
            {"chunk_id": "...", "document_id": "...", "document_name": "guide.pdf", "content": "...", "score": 0.93}
          ],
          "total": 1,
          "diagnostics": [],
          "timings": []
        },
        "error": null
      },
      {
        "id": "vector-top10",
        "status": "rejected",
        "response": null,
        "error": {
          "code": 6104,
          "retrieval_error_category": "model_configuration",
          "stage": "recall"
        }
      }
    ]
  },
  "msg": "success"
}
```

One failed configuration does not fail the others.

## 5. Batch File Parsing

Extracts text from up to **5 files** in one request.

**Endpoint:**
```
POST /api/v1/upload/parse/batch
```

Query parameters: `max_content_length` (default 100000, range 1000–500000) and `truncate_strategy` (`end` | `start` | `middle`).

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/upload/parse/batch" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "files=@doc1.pdf" \
  -F "files=@doc2.md"
```

**Response:** a list of `FileParseResponse` objects (`filename`, `content`, `mime_type`, `size`, `truncated`, `original_length`, `title`). Per-file failures (unsupported type, too large, parse error) are collected in an `errors` array in the response `data`; if **all** files fail, the request returns `1001` (`VALIDATION_ERROR`) with `data.errors`.

## 6. Admin Batch Delete Conversations

**Endpoint:**
```
DELETE /api/v1/admin/conversations?ids=<uuid1>&ids=<uuid2>&...
```

**Authorization:** `admin:conversation:delete` permission (Admin can delete conversations in accessible teams; Super Admin any).

Same semantics as the platform batch delete, under the `/admin` prefix.

## Best Practices

**✅ Do:**
- Use batch team-model authorization instead of N single requests
- Use `search/batch` when comparing retrieval configurations
- Use `upload/parse/batch` (max 5 files) instead of looping the single parse endpoint
- Verify the user/API key has permission to act on **all** resources in a batch delete

**❌ Don't:**
- Expect generic `/batch` endpoints for arbitrary resources — they do not exist
- Send more than 5 files to `upload/parse/batch` (returns `1001`)
- Send more than 10 configurations to `search/batch`
- Assume partial success semantics — batch deletes are all-or-nothing

## Related Documentation

- [Error Handling](./error-handling.md) - Error handling patterns
- [File Uploads](./file-uploads.md) - Upload and parse endpoints
- [Knowledge Base API](./endpoints/knowledge-bases.md) - KB search endpoints
- [API Reference](./endpoints/) - Endpoint documentation

---

**Last Updated**: 2026-08-14
