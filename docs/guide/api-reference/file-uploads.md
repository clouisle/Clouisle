# File Uploads Guide

This guide explains how to upload files to the Clouisle API.

## Overview

Clouisle exposes several upload endpoints, each with its own purpose and file-type restrictions:

- **Knowledge-base document upload** — ingest documents (PDF, DOCX, TXT, ...) into a knowledge base for RAG
- **URL document** — create a KB document from a source URL
- **Generic image/document upload** — upload images, PDFs, and text documents (for chat attachments, avatars, etc.)
- **Sandbox artifact upload** — upload files produced by sandbox executions
- **File parsing** — extract text content from a file (single or batch)

## Supported File Types

### Knowledge-Base Document Upload

`POST /api/v1/knowledge-bases/{kb_id}/documents/upload` accepts:

- **PDF**: `.pdf`
- **Word**: `.doc`, `.docx`
- **Text/Markdown**: `.txt`, `.md`, `.markdown`
- **HTML**: `.html`, `.htm`
- **CSV**: `.csv`
- **Excel**: `.xls`, `.xlsx`
- **JSON**: `.json`
- **PowerPoint**: `.pptx`

Images, archives (`.zip`, `.tar`), and video are **not** accepted here — use the generic upload endpoints below.

### Generic Upload (`/api/v1/upload/image` and `/api/v1/upload/file`)

**Images** (`POST /api/v1/upload/image`):
- JPEG, PNG, GIF, WebP, SVG, ICO

**Documents** (`POST /api/v1/upload/file`):
- All image types above, plus PDF, TXT, MD, HTML, CSV, JSON, DOC, DOCX, XLSX, PPTX

### File Limits

| Endpoint | Max File Size |
|----------|---------------|
| `POST /api/v1/upload/image` | 10 MB |
| `POST /api/v1/upload/file` | 10 MB |
| `POST /api/v1/upload/parse` | 10 MB |
| `POST /api/v1/upload/parse/batch` | 10 MB per file (max 5 files) |
| `POST /api/v1/knowledge-bases/{kb_id}/documents/upload` | Default 50 MB per document (site setting `kb_document_max_upload_size_mb`, range 1–1024 MB) |

There is no per-request file-count limit beyond the parse batch cap of 5 files.

## Upload Methods

### 1. Upload a Document to a Knowledge Base

**Endpoint:**
```
POST /api/v1/knowledge-bases/{kb_id}/documents/upload
```

**Request (multipart/form-data):**
```http
POST /api/v1/knowledge-bases/550e8400-e29b-41d4-a716-446655440000/documents/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary
Authorization: Bearer YOUR_TOKEN

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

[binary file content]
------WebKitFormBoundary--
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "doc-123",
    "name": "document.pdf",
    "doc_type": "pdf",
    "status": "pending",
    "file_size": 1048576,
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

The document is created with `status: "pending"`. After configuring chunk settings, call the KB's **process** endpoint to start processing (embedding + indexing).

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/knowledge-bases/$KB_ID/documents/upload" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "file=@/path/to/document.pdf"
```

### 2. Create a Document from a URL

**Endpoint:**
```
POST /api/v1/knowledge-bases/{kb_id}/documents/url
```

**Request (JSON):**
```json
{
  "source_url": "https://example.com/document.pdf",
  "doc_type": "url"
}
```

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/knowledge-bases/$KB_ID/documents/url" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://example.com/document.pdf", "doc_type": "url"}'
```

### 3. Upload an Image

**Endpoint:** `POST /api/v1/upload/image`

**Query parameters:** `category` (default `general`; e.g. `avatar`, `icon`)

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/upload/image?category=general" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "file=@/path/to/avatar.png"
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "asset_id": "550e8400-e29b-41d4-a716-446655440000",
    "url": "/uploads/general/2026/02/avatar.png",
    "filename": "avatar.png",
    "original_name": "avatar.png",
    "size": 20480,
    "content_type": "image/png"
  },
  "msg": "success"
}
```

### 4. Upload a Generic File

**Endpoint:** `POST /api/v1/upload/file`

Accepts images and documents (up to 10 MB). Same response shape as image upload.

### 5. Upload a Sandbox Artifact

**Endpoint:** `POST /api/v1/upload/sandbox-artifact`

Used by sandbox executions to upload produced artifacts. Authentication is optional: either a Bearer token (JWT or `clou_` API key) or a signature — the `X-Sandbox-Artifact-Timestamp` and `X-Sandbox-Artifact-Signature` headers when unauthenticated. The size limit is governed by the `SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB` setting.

**Response:**
```json
{
  "code": 0,
  "data": {
    "path": "sandbox-artifacts/2026/02/artifact.txt",
    "url": "/uploads/sandbox-artifacts/2026/02/artifact.txt",
    "filename": "artifact.txt",
    "size": 512,
    "content_type": "text/plain"
  },
  "msg": "success"
}
```

### 6. Parse a File (Extract Text)

**Endpoint:** `POST /api/v1/upload/parse`

Extracts the textual content of a supported file. Query parameters: `max_content_length` (default 100000, range 1000–500000) and `truncate_strategy` (`end`, `start`, or `middle`, default `end`).

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/upload/parse?max_content_length=100000&truncate_strategy=end" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "file=@/path/to/document.pdf"
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "filename": "document.pdf",
    "content": "[extracted markdown text...]",
    "mime_type": "application/pdf",
    "size": 1048576,
    "truncated": false,
    "original_length": 5000,
    "title": "document"
  },
  "msg": "success"
}
```

### 7. Parse Multiple Files

**Endpoint:** `POST /api/v1/upload/parse/batch`

Parses up to **5 files** per request. Each file is parsed independently; per-file failures are returned in an `errors` array without failing the whole request (unless all files fail). Same query parameters as the single parse endpoint.

**curl:**
```bash
curl -X POST "$API_BASE_URL/api/v1/upload/parse/batch" \
  -H "Authorization: Bearer $CLOUISLE_TOKEN" \
  -F "files=@doc1.pdf" \
  -F "files=@doc2.md"
```

**Response:**
```json
{
  "code": 0,
  "data": [
    {"filename": "doc1.pdf", "content": "...", "mime_type": "application/pdf", "size": 100, "truncated": false, "original_length": 100, "title": "doc1"},
    {"filename": "doc2.md", "content": "...", "mime_type": "text/markdown", "size": 200, "truncated": false, "original_length": 200, "title": "doc2"}
  ],
  "msg": "success"
}
```

## Python Examples

### KB Document Upload

```python
import requests

def upload_document(kb_id, file_path):
    """Upload a single document to a knowledge base."""
    url = f"{API_BASE_URL}/api/v1/knowledge-bases/{kb_id}/documents/upload"

    with open(file_path, 'rb') as f:
        response = requests.post(
            url,
            headers={'Authorization': f'Bearer {TOKEN}'},
            files={'file': (file_path.split('/')[-1], f)}
        )

    return response.json()['data']

# Usage
result = upload_document(
    kb_id='550e8400-e29b-41d4-a716-446655440000',
    file_path='/path/to/document.pdf'
)

print(f"Uploaded: {result['id']} (status: {result['status']})")
```

### Generic Image/File Upload

```python
def upload_image(file_path, category='general'):
    """Upload an image."""
    url = f"{API_BASE_URL}/api/v1/upload/image?category={category}"

    with open(file_path, 'rb') as f:
        response = requests.post(
            url,
            headers={'Authorization': f'Bearer {TOKEN}'},
            files={'file': (file_path.split('/')[-1], f)}
        )

    return response.json()['data']

# Usage
result = upload_image('/path/to/avatar.png', category='avatar')
print(f"URL: {result['url']}")
```

### Parse a File

```python
def parse_file(file_path, max_content_length=100000, truncate_strategy='end'):
    """Extract text content from a file."""
    url = (
        f"{API_BASE_URL}/api/v1/upload/parse"
        f"?max_content_length={max_content_length}"
        f"&truncate_strategy={truncate_strategy}"
    )

    with open(file_path, 'rb') as f:
        response = requests.post(
            url,
            headers={'Authorization': f'Bearer {TOKEN}'},
            files={'file': (file_path.split('/')[-1], f)}
        )

    return response.json()['data']

# Usage
parsed = parse_file('/path/to/document.pdf')
print(parsed['content'][:500])
```

## JavaScript Examples

### KB Document Upload

```javascript
async function uploadDocument(kbId, file) {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE_URL}/api/v1/knowledge-bases/${kbId}/documents/upload`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${TOKEN}`
      },
      body: formData
    }
  );

  const result = await response.json();
  return result.data;
}

// Usage
const fileInput = document.querySelector('input[type="file"]');
const file = fileInput.files[0];

const result = await uploadDocument(
  '550e8400-e29b-41d4-a716-446655440000',
  file
);
console.log(`Uploaded: ${result.id} (status: ${result.status})`);
```

### Generic Image Upload

```javascript
async function uploadImage(file, category = 'general') {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE_URL}/api/v1/upload/image?category=${category}`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${TOKEN}`
      },
      body: formData
    }
  );

  const result = await response.json();
  return result.data;
}

// Usage
const file = fileInput.files[0];
const result = await uploadImage(file, 'avatar');
console.log(`URL: ${result.url}`);
```

## Error Handling

| Error | Code | Cause |
|-------|------|-------|
| File too large | `1001` (`VALIDATION_ERROR`) | Exceeds the endpoint's size limit; `data.max_size` indicates the limit |
| Unsupported file type | `1001` / `6003` | The MIME type / extension is not in the allowed list; KB uploads return `6003` (`INVALID_DOCUMENT_TYPE`) |
| Too many files (parse batch) | `1001` | More than 5 files in `POST /api/v1/upload/parse/batch` |
| File not found (download) | `4000` | The stored file no longer exists |

```python
response = requests.post(url, headers=headers, files=files)
result = response.json()

if result['code'] != 0:
    if result['code'] == 1001:
        errors = result['data']['errors']
        print(f"Validation failed: {errors}")
    else:
        print(f"Upload failed ({result['code']}): {result['msg']}")
```

## Best Practices

- Check file type and size client-side before uploading to avoid wasted requests
- Use `POST /api/v1/upload/parse/batch` (max 5 files) instead of multiple single parse calls
- After a KB document upload, configure chunk settings and call the process endpoint; uploaded documents are not processed automatically
- Handle 422 validation responses (`code: 1001`) by reading `data.errors` (field → messages dictionary)

## Troubleshooting

### File Too Large

**Problem:** Upload rejected

**Solutions:**
1. For KB documents, the limit is the `kb_document_max_upload_size_mb` site setting (default 50 MB) — an administrator can raise it (max 1024 MB)
2. For `/api/v1/upload/*` endpoints the limit is fixed at 10 MB
3. Compress or split the file

### Unsupported File Type

**Problem:** File type not accepted

**Solutions:**
1. Convert to a supported format (see lists above)
2. Check the file extension and MIME type
3. Images and archives are only accepted by the generic upload endpoints, not KB document upload

## Related Documentation

- [Batch Operations](./batch-operations.md) - Batch upload/parse operations
- [Error Handling](./error-handling.md) - Error handling patterns
- [Knowledge Base API](./endpoints/knowledge-bases.md) - KB endpoints

---

**Last Updated**: 2026-08-14
