# Knowledge Bases API

This document describes the API endpoints for managing knowledge bases and documents.

## Overview

The Knowledge Bases API allows you to:

- **List knowledge bases**: Get all accessible knowledge bases
- **Get KB details**: Retrieve knowledge base information
- **Create knowledge bases**: Create new knowledge bases (admin only)
- **Update knowledge bases**: Modify KB configuration (admin only)
- **Delete knowledge bases**: Remove knowledge bases (admin only)
- **Upload documents**: Add documents to knowledge bases
- **Search documents**: Query documents with vector/keyword search
- **Manage documents**: Update and delete documents

**Base URL**: `/api/v1/kb`

## Authentication

All endpoints require authentication via JWT token or API key.

**Required scopes:**
- `kb:read` - List and view knowledge bases
- `kb:create` - Create knowledge bases
- `kb:update` - Update knowledge bases and upload documents
- `kb:delete` - Delete knowledge bases and documents

## List Knowledge Bases

Get a list of all knowledge bases you have access to.

### Endpoint

```
GET /api/v1/kb
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `page` | integer | No | 1 | Page number |
| `page_size` | integer | No | 20 | Items per page (max: 100) |
| `team_id` | string | No | - | Filter by team ID |
| `search` | string | No | - | Search by name or description |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/kb?page=1&page_size=20" \
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
        "team_id": "team-123",
        "team_name": "Support Team",
        "embedding_model": "text-embedding-3-small",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "chunking_strategy": "semantic",
        "document_count": 156,
        "total_chunks": 2340,
        "storage_used": 234567890,
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T15:30:00Z",
        "created_by": "user-001"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20,
    "total_pages": 3
  },
  "msg": "success"
}
```

## Get Knowledge Base

Get details of a specific knowledge base.

### Endpoint

```
GET /api/v1/kb/{kb_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000" \
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
    "team_id": "team-123",
    "team_name": "Support Team",
    "embedding_model": "text-embedding-3-small",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "chunking_strategy": "semantic",
    "document_count": 156,
    "total_chunks": 2340,
    "storage_used": 234567890,
    "storage_limit": 10737418240,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T15:30:00Z",
    "created_by": "user-001",
    "stats": {
      "documents_by_type": {
        "pdf": 89,
        "docx": 34,
        "txt": 18,
        "md": 15
      },
      "avg_document_size": 1504273,
      "total_searches": 1234,
      "last_search": "2026-02-11T14:30:00Z"
    }
  },
  "msg": "success"
}
```

## Create Knowledge Base

Create a new knowledge base.

### Endpoint

```
POST /api/v1/kb
```

### Request Body

```json
{
  "name": "Product Documentation",
  "description": "Product docs and FAQs",
  "team_id": "team-123",
  "embedding_model": "text-embedding-3-small",
  "chunk_size": 1000,
  "chunk_overlap": 200,
  "chunking_strategy": "semantic"
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | KB name (max 100 chars) |
| `description` | string | No | KB description (max 500 chars) |
| `team_id` | string | Yes | Team UUID |
| `embedding_model` | string | No | Embedding model (default: text-embedding-3-small) |
| `chunk_size` | integer | No | Chunk size in characters (default: 1000) |
| `chunk_overlap` | integer | No | Chunk overlap (default: 200) |
| `chunking_strategy` | string | No | Strategy: semantic, fixed, sentence (default: semantic) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/kb" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Documentation",
    "description": "Product docs and FAQs",
    "team_id": "team-123",
    "chunk_size": 1000
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
    "team_id": "team-123",
    "created_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Knowledge base created successfully"
}
```

## Update Knowledge Base

Update an existing knowledge base.

### Endpoint

```
PATCH /api/v1/kb/{kb_id}
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
  "chunk_size": 1500
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000" \
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
DELETE /api/v1/kb/{kb_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000" \
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
POST /api/v1/kb/{kb_id}/documents
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Body

**Content-Type**: `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | Document file |
| `title` | string | No | Document title (default: filename) |
| `description` | string | No | Document description |
| `tags` | string | No | Comma-separated tags |
| `category` | string | No | Document category |
| `language` | string | No | Document language (default: auto-detect) |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/documents" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "title=Sales Report Q3 2026" \
  -F "description=Quarterly sales analysis" \
  -F "tags=sales,q3,2026" \
  -F "category=reports"
```

### Response

**Success (201 Created):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "kb_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Sales Report Q3 2026",
    "filename": "document.pdf",
    "file_type": "pdf",
    "file_size": 2345678,
    "status": "processing",
    "created_at": "2026-02-11T10:00:00Z"
  },
  "msg": "Document uploaded successfully"
}
```

## List Documents

Get documents in a knowledge base.

### Endpoint

```
GET /api/v1/kb/{kb_id}/documents
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
| `status` | string | No | - | Filter by status: processing, completed, failed |
| `category` | string | No | - | Filter by category |
| `search` | string | No | - | Search by title or content |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/documents?page=1&page_size=20" \
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
        "kb_id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Sales Report Q3 2026",
        "description": "Quarterly sales analysis",
        "filename": "document.pdf",
        "file_type": "pdf",
        "file_size": 2345678,
        "status": "completed",
        "category": "reports",
        "tags": ["sales", "q3", "2026"],
        "language": "en",
        "page_count": 15,
        "word_count": 3450,
        "chunk_count": 45,
        "created_at": "2026-02-11T10:00:00Z",
        "updated_at": "2026-02-11T10:01:23Z",
        "created_by": "user-001"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  },
  "msg": "success"
}
```

## Get Document

Get details of a specific document.

### Endpoint

```
GET /api/v1/kb/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "kb_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Sales Report Q3 2026",
    "description": "Quarterly sales analysis",
    "filename": "document.pdf",
    "file_type": "pdf",
    "file_size": 2345678,
    "file_url": "https://storage.example.com/...",
    "status": "completed",
    "category": "reports",
    "tags": ["sales", "q3", "2026"],
    "language": "en",
    "page_count": 15,
    "word_count": 3450,
    "chunk_count": 45,
    "processing_time": 83,
    "created_at": "2026-02-11T10:00:00Z",
    "updated_at": "2026-02-11T10:01:23Z",
    "created_by": "user-001",
    "chunks": [
      {
        "id": "chunk-001",
        "content": "Q3 2026 Sales Report...",
        "page": 1,
        "position": 0
      }
    ]
  },
  "msg": "success"
}
```

## Update Document

Update document metadata.

### Endpoint

```
PATCH /api/v1/kb/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Body

```json
{
  "title": "Updated Title",
  "description": "Updated description",
  "tags": ["sales", "q3", "2026", "updated"],
  "category": "reports"
}
```

### Request Example

```bash
curl -X PATCH "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "tags": ["sales", "q3", "2026", "updated"]
  }'
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "id": "doc-789",
    "title": "Updated Title",
    "updated_at": "2026-02-11T16:00:00Z"
  },
  "msg": "Document updated successfully"
}
```

## Delete Document

Delete a document from knowledge base.

### Endpoint

```
DELETE /api/v1/kb/{kb_id}/documents/{document_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |
| `document_id` | string | Yes | Document UUID |

### Request Example

```bash
curl -X DELETE "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/documents/doc-789" \
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
POST /api/v1/kb/{kb_id}/search
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Request Body

```json
{
  "query": "How to reset password",
  "mode": "vector",
  "top_k": 5,
  "score_threshold": 0.7,
  "filters": {
    "category": "documentation",
    "tags": ["authentication"]
  }
}
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `mode` | string | No | Search mode: vector, keyword, hybrid (default: vector) |
| `top_k` | integer | No | Number of results (default: 5, max: 20) |
| `score_threshold` | float | No | Minimum relevance score (0.0-1.0, default: 0.5) |
| `filters` | object | No | Filter by metadata |

### Request Example

```bash
curl -X POST "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to reset password",
    "mode": "vector",
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
    "mode": "vector",
    "results": [
      {
        "document_id": "doc-789",
        "document_title": "Password Management Guide",
        "chunk_id": "chunk-012",
        "content": "To reset your password, go to the login page and click 'Forgot Password'...",
        "score": 0.95,
        "page": 3,
        "metadata": {
          "category": "documentation",
          "tags": ["authentication", "password"]
        }
      },
      {
        "document_id": "doc-790",
        "document_title": "User Authentication",
        "chunk_id": "chunk-045",
        "content": "Password reset process involves email verification...",
        "score": 0.89,
        "page": 5,
        "metadata": {
          "category": "documentation",
          "tags": ["authentication"]
        }
      }
    ],
    "total_results": 2,
    "search_time": 0.23
  },
  "msg": "success"
}
```

## Get KB Statistics

Get usage statistics for a knowledge base.

### Endpoint

```
GET /api/v1/kb/{kb_id}/stats
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `kb_id` | string | Yes | Knowledge base UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `start_date` | string | No | 30 days ago | Start date (ISO 8601) |
| `end_date` | string | No | Now | End date (ISO 8601) |

### Request Example

```bash
curl -X GET "https://your-domain.com/api/v1/kb/550e8400-e29b-41d4-a716-446655440000/stats" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response

**Success (200 OK):**

```json
{
  "code": 0,
  "data": {
    "document_count": 156,
    "total_chunks": 2340,
    "storage_used": 234567890,
    "storage_limit": 10737418240,
    "total_searches": 1234,
    "avg_search_time": 0.23,
    "documents_by_type": {
      "pdf": 89,
      "docx": 34,
      "txt": 18,
      "md": 15
    },
    "documents_by_status": {
      "completed": 147,
      "processing": 3,
      "failed": 6
    },
    "daily_stats": [
      {
        "date": "2026-02-11",
        "documents_uploaded": 5,
        "searches": 89,
        "avg_search_time": 0.21
      }
    ]
  },
  "msg": "success"
}
```

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| `6000` | KB not found | Knowledge base does not exist |
| `4000` | Document not found | Document does not exist |
| `3000` | Permission denied | Insufficient permissions |
| `1001` | Validation failed | Invalid request data |
| `5100` | Name already exists | KB name is taken |
| `6001` | Document processing failed | Document processing error |
| `6002` | Embedding failed | Embedding generation error |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/kb` | 100/minute |
| `GET /api/v1/kb/{id}` | 100/minute |
| `POST /api/v1/kb` | 10/minute |
| `PATCH /api/v1/kb/{id}` | 30/minute |
| `DELETE /api/v1/kb/{id}` | 10/minute |
| `POST /api/v1/kb/{id}/documents` | 10/minute |
| `POST /api/v1/kb/{id}/search` | 60/minute |

## Related Documentation

- [API Overview](../overview.md) - API introduction
- [Authentication](../authentication.md) - Authentication methods
- [Rate Limiting](../rate-limiting.md) - Rate limit details
- [Agents API](./agents.md) - Agents endpoints
- [KB Concepts](../../concepts/knowledge-bases.md) - Understanding KBs

---

**Last Updated**: 2026-02-11
