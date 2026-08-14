# Knowledge Bases API

This document describes the API endpoints for managing knowledge bases and documents.

## Overview

The Knowledge Bases API allows you to:

- **List knowledge bases**: Get all accessible knowledge bases
- **Get KB details**: Retrieve knowledge base information
- **Create knowledge bases**: Create new knowledge bases
- **Update knowledge bases**: Modify KB configuration
- **Delete knowledge bases**: Remove knowledge bases
- **Upload documents**: Add documents to knowledge bases
- **Search documents**: Query documents with vector/keyword search
- **Manage documents**: Update and delete documents

**Base URL**: `/api/v1/knowledge-bases`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `kb:read` - List and view knowledge bases
- `kb:test` - Run searches against knowledge bases
- `kb:create` - Create knowledge bases
- `kb:update` - Update knowledge bases and upload documents
- `kb:delete` - Delete knowledge bases and documents

## List Knowledge Bases

Get a list of all knowledge bases you have access to.

### Endpoint

```
GET /api/v1/knowledge-bases
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `team_id` | string | No | - | Filter by team ID |
| `status` | array | No | - | Filter by status: `active`, `archived` (repeatable) |
| `search` | string | No | - | Search by name or description |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Product Documentation",
        "description": "Product docs and FAQs",
        "icon": "📚",
        "team": {
          "id": "team-123",
          "name": "Support Team",
          "avatar_url": null
        },
        "created_by": {
          "id": "user-001",
          "username": "alice",
          "avatar_url": null
        },
        "status": "active",
        "embedding_model_id": "model-emb-01",
        "embedding_model": {
          "id": "model-emb-01",
          "name": "text-embedding-3-small",
          "provider": "openai",
          "model_id": "text-embedding-3-small"
        },
        "rerank_model_id": "model-rerank-01",
        "rerank_model": {
          "id": "model-rerank-01",
          "name": "bge-reranker-v2-m3",
          "provider": "bge",
          "model_id": "bge-reranker-v2-m3"
        },
        "embedding_dimension": 1536,
        "document_count": 156,
        "total_chunks": 2340,
        "total_tokens": 456789,
        "created_at": "2026-02-11T10:00:00Z"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Get Knowledge Base

Get details of a specific knowledge base.

### Endpoint

```
GET /api/v1/knowledge-bases/{kb_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Product Documentation",
    "description": "Product docs and FAQs",
    "icon": "📚",
    "team": {
      "id": "team-123",
      "name": "Support Team",
      "avatar_url": null
    },
    "created_by": {
      "id": "user-001",
      "username": "alice",
      "avatar_url": null
    },
    "status": "active",
    "embedding_model_id": "model-emb-01",
    "embedding_model": {
      "id": "model-emb-01",
      "name": "text-embedding-3-small",
      "provider": "openai",
      "model_id": "text-embedding-3-small"
    },
    "rerank_model_id": "model-rerank-01",
    "rerank_model": {
      "id": "model-rerank-01",
      "name": "bge-reranker-v2-m3",
      "provider": "bge",
      "model_id": "bge-reranker-v2-m3"
    },
    "embedding_dimension": 1536,
    "settings": {
      "chunk_size": 1000,
      "chunk_overlap": 100,
      "rerank_enabled": true,
      "rerank_candidate_k": 10,
      "search_mode": "hybrid",
      "top_k": 5,
      "score_threshold": 0.0
    },
    "document_count": 156,
    "total_chunks": 2340,
    "total_tokens": 456789,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z"
  },
  "msg": "success"
}
```

## Create Knowledge Base

Create a new knowledge base.

### Endpoint

```
POST /api/v1/knowledge-bases
```

### Request Body

```json
{
  "name": "Product Documentation",
  "description": "Product docs and FAQs",
  "icon": "📚",
  "team_id": "team-123",
  "embedding_model_id": "model-emb-01",
  "rerank_model_id": "model-rerank-01",
  "settings": {
    "chunk_size": 1000,
    "chunk_overlap": 100,
    "rerank_enabled": true,
    "rerank_candidate_k": 10,
    "search_mode": "hybrid"
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | KB name (max 100 chars) |
| `description` | string | No | KB description (max 500 chars) |
| `icon` | string | No | Icon name or emoji (max 50 chars) |
| `team_id` | string | Yes | Team UUID |
| `embedding_model_id` | string | No | Embedding model UUID (must be authorized for the team) |
| `rerank_model_id` | string | No | Rerank model UUID (must be authorized for the team) |
| `settings` | object | No | KB settings: `chunk_size` (default 1000, min 100), `chunk_overlap` (default 100, min 0), `separator`, `rerank_enabled` (default true), `rerank_candidate_k` (default 10), `rerank_score_threshold`, `search_mode` (`vector`/`fulltext`/`hybrid`), `top_k`, `score_threshold`, `dense_weight`, `lexical_weight`, `rrf_k` |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/knowledge-bases" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Documentation",
    "description": "Product docs and FAQs",
    "team_id": "team-123",
    "embedding_model_id": "model-emb-01",
    "settings": {
      "chunk_size": 1000
    }
  }'
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Product Documentation",
    "description": "Product docs and FAQs",
    "team": {
      "id": "team-123",
      "name": "Support Team",
      "avatar_url": null
    },
    "status": "active",
    "settings": {
      "chunk_size": 1000,
      "chunk_overlap": 100
    },
    "document_count": 0,
    "total_chunks": 0,
    "total_tokens": 0,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Knowledge base created successfully"
}
```

## Update Knowledge Base

Update an existing knowledge base.

### Endpoint

```
PUT /api/v1/knowledge-bases/{kb_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Body

All fields are optional. Only include fields you want to update.

```json
{
  "name": "Updated KB Name",
  "description": "Updated description",
  "icon": "📚",
  "settings": {
    "chunk_size": 1500
  }
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated KB Name",
    "description": "Updated description"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Updated KB Name",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Knowledge base updated successfully"
}
```

## Delete Knowledge Base

Delete a knowledge base permanently.

### Endpoint

```
DELETE /api/v1/knowledge-bases/{kb_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Knowledge base deleted successfully"
}
```

## Upload Document

Upload a document to a knowledge base.

### Endpoint

```
POST /api/v1/knowledge-bases/{kb_id}/documents/upload
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Body

**Content-Type**: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Document file (`.pdf`, `.docx`, `.txt`, `.md`, etc.) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf"
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "knowledge_base_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "document.pdf",
    "doc_type": "pdf",
    "file_path": "uploads/documents/doc-789.pdf",
    "file_size": 2345678,
    "status": "pending",
    "chunk_count": 0,
    "token_count": 0,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Document uploaded successfully"
}
```

**Note:** URL-based documents use `POST /api/v1/knowledge-bases/{kb_id}/documents/url` with body `{"name": "...", "source_url": "...", "doc_type": "url"}`.

## List Documents

Get documents in a knowledge base.

### Endpoint

```
GET /api/v1/knowledge-bases/{kb_id}/documents
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `status` | array | No | - | Filter by status: `pending`, `processing`, `completed`, `failed` (repeatable) |
| `doc_type` | array | No | - | Filter by doc type: `pdf`, `docx`, `txt`, `md`, `url`, etc. (repeatable) |
| `search` | string | No | - | Search by document name |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents?page=1&page_size=20&status=completed" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "doc-789",
        "name": "Sales Report Q3 2026.pdf",
        "doc_type": "pdf",
        "file_path": "uploads/documents/doc-789.pdf",
        "file_size": 2345678,
        "source_url": null,
        "status": "completed",
        "error_message": null,
        "chunk_count": 45,
        "token_count": 12345,
        "metadata": {
          "page_count": 15
        },
        "created_at": "2026-02-11T10:00:00Z"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20
  },
  "msg": "success"
}
```

## Get Document

Get details of a specific document.

### Endpoint

```
GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "knowledge_base_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Sales Report Q3 2026.pdf",
    "doc_type": "pdf",
    "file_path": "uploads/documents/doc-789.pdf",
    "file_size": 2345678,
    "source_url": null,
    "status": "completed",
    "error_message": null,
    "chunk_count": 45,
    "token_count": 12345,
    "metadata": {
      "page_count": 15
    },
    "uploaded_by": {
      "id": "user-001",
      "username": "alice",
      "avatar_url": null
    },
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:01:23Z",
    "processed_at": "2026-02-11T10:01:23Z"
  },
  "msg": "success"
}
```

## Update Document

Update document metadata.

### Endpoint

```
PUT /api/v1/knowledge-bases/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Body

```json
{
  "name": "Updated Title.pdf"
}
```

### Request Example

```bash
curl -X PUT "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Title.pdf"
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "knowledge_base_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Updated Title.pdf",
    "doc_type": "pdf",
    "status": "completed",
    "chunk_count": 45,
    "token_count": 12345,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Document updated successfully"
}
```

## Delete Document

Delete a document from knowledge base.

### Endpoint

```
DELETE /api/v1/knowledge-bases/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": null,
  "msg": "Document deleted successfully"
}
```

## Search Documents

Search documents using vector or keyword search.

### Endpoint

```
POST /api/v1/knowledge-bases/{kb_id}/search
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Body

```json
{
  "query": "How to reset password",
  "search_mode": "hybrid",
  "top_k": 5,
  "score_threshold": 0.0,
  "filter_doc_ids": ["doc-789"],
  "rerank_enabled": true,
  "rerank_candidate_k": 10
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query (max 1000 chars) |
| `search_mode` | string | No | Search mode: `vector`, `fulltext`, `hybrid` (default: `hybrid`) |
| `top_k` | integer | No | Number of results (default: 5, max: 20) |
| `score_threshold` | float | No | Minimum dense similarity score (0.0-1.0, default: 0.0) |
| `dense_weight` | float | No | Dense RRF weight (default: 1.0) |
| `lexical_weight` | float | No | Lexical RRF weight (default: 1.0) |
| `rrf_k` | integer | No | RRF rank constant (default: 60) |
| `filter_doc_ids` | array | No | Restrict search to specific document IDs |
| `rerank_enabled` | boolean | No | Override rerank enabled setting |
| `rerank_candidate_k` | integer | No | Override rerank candidate pool size |
| `rerank_score_threshold` | float | No | Override rerank score threshold (null disables) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to reset password",
    "search_mode": "hybrid",
    "top_k": 5
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "query": "How to reset password",
    "results": [
      {
        "chunk_id": "chunk-012",
        "document_id": "doc-789",
        "document_name": "Password Management Guide.pdf",
        "content": "To reset your password, go to the login page and click 'Forgot Password'...",
        "score": 0.95,
        "metadata": {
          "page": 3
        },
        "search_type": "hybrid",
        "dense_score": 0.93,
        "lexical_score": 0.87,
        "fusion_score": 0.95,
        "rerank_score": 0.97,
        "rerank_rank": 1
      }
    ],
    "total": 2,
    "diagnostics": [],
    "timings": [
      {
        "stage": "recall",
        "latency_ms": 120
      },
      {
        "stage": "rerank",
        "latency_ms": 80
      },
      {
        "stage": "total",
        "latency_ms": 210
      }
    ]
  },
  "msg": "success"
}
```

## Get KB Statistics

Get usage statistics for a knowledge base.

### Endpoint

```
GET /api/v1/knowledge-bases/{kb_id}/stats
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Product Documentation",
    "document_count": 156,
    "total_chunks": 2340,
    "total_tokens": 456789,
    "documents_by_status": {
      "completed": 147,
      "pending": 0,
      "processing": 3,
      "failed": 6
    },
    "documents_by_type": {
      "pdf": 89,
      "docx": 34,
      "txt": 18,
      "md": 15
    },
    "embedding_dimension": 1536,
    "embedding_stats": {
      "total_vectors": 2340,
      "missing_vectors": 0
    }
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6000` | KB not found | Knowledge base does not exist |
| `6001` | Name already exists | KB name is taken |
| `6002` | Document not found | Document does not exist |
| `6003` | Invalid document type | Document type is not supported |
| `6004` | Document processing failed | Document processing error |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |

> **Note:** No per-endpoint rate limits are implemented. There is no rate-limit middleware on these endpoints.

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Agents API](./agents.md) - Agents endpoints
- [KB Concepts](../../concepts/knowledge-bases.md) - Understanding KBs

---

**Last Updated**: 2026-02-11
