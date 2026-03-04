# File Uploads Guide

This guide explains how to upload files to the Clouisle API.

## Overview

Clouisle supports file uploads for documents, images, and other file types. Files can be uploaded to knowledge bases, used as attachments, or processed for content extraction.

## Supported File Types

### Documents
- **PDF**: `.pdf`
- **Word**: `.doc`, `.docx`
- **Excel**: `.xls`, `.xlsx`
- **PowerPoint**: `.ppt`, `.pptx`
- **Text**: `.txt`, `.md`, `.csv`
- **HTML**: `.html`, `.htm`

### Images
- **Common**: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- **Vector**: `.svg`

### Archives
- **Compressed**: `.zip`, `.tar`, `.gz`

### File Limits
- Max file size: 50 MB
- Max files per request: 10
- Total request size: 100 MB

## Upload Methods

### Single File Upload

**Endpoint:**
```
POST /api/v1/kb/{kb_id}/documents/upload
```

**Request:**
```http
POST /api/v1/kb/kb-123/documents/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary
Authorization: Bearer YOUR_TOKEN

------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

[binary file content]
------WebKitFormBoundary
Content-Disposition: form-data; name="metadata"

{"title": "Product Manual", "category": "documentation"}
------WebKitFormBoundary--
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "doc-123",
    "filename": "document.pdf",
    "size": 1048576,
    "mime_type": "application/pdf",
    "status": "processing",
    "created_at": "2026-02-11T16:00:00Z"
  },
  "msg": "success"
}
```

### Multiple File Upload

**Endpoint:**
```
POST /api/v1/kb/{kb_id}/documents/upload/batch
```

**Request:**
```http
POST /api/v1/kb/kb-123/documents/upload/batch HTTP/1.1
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary
Authorization: Bearer YOUR_TOKEN

------WebKitFormBoundary
Content-Disposition: form-data; name="files"; filename="doc1.pdf"
Content-Type: application/pdf

[binary file content]
------WebKitFormBoundary
Content-Disposition: form-data; name="files"; filename="doc2.docx"
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document

[binary file content]
------WebKitFormBoundary--
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "success": [
      {
        "id": "doc-123",
        "filename": "doc1.pdf",
        "size": 1048576
      }
    ],
    "failed": [
      {
        "filename": "doc2.docx",
        "error": "File too large"
      }
    ],
    "summary": {
      "total": 2,
      "success_count": 1,
      "failed_count": 1
    }
  },
  "msg": "success"
}
```

### Upload from URL

**Endpoint:**
```
POST /api/v1/kb/{kb_id}/documents/upload/url
```

**Request:**
```json
{
  "url": "https://example.com/document.pdf",
  "filename": "document.pdf",
  "metadata": {
    "title": "Product Manual",
    "category": "documentation"
  }
}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "id": "doc-123",
    "filename": "document.pdf",
    "size": 1048576,
    "status": "processing"
  },
  "msg": "success"
}
```

## Python Examples

### Single File Upload

```python
import requests

def upload_file(kb_id, file_path, metadata=None):
    """Upload a single file to knowledge base."""
    url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload"

    with open(file_path, 'rb') as f:
        files = {
            'file': (file_path.split('/')[-1], f, get_mime_type(file_path))
        }

        data = {}
        if metadata:
            data['metadata'] = json.dumps(metadata)

        response = requests.post(
            url,
            headers={'Authorization': f'Bearer {TOKEN}'},
            files=files,
            data=data
        )

    return response.json()['data']

# Usage
result = upload_file(
    kb_id='kb-123',
    file_path='/path/to/document.pdf',
    metadata={
        'title': 'Product Manual',
        'category': 'documentation'
    }
)

print(f"Uploaded: {result['id']}")
```

### Multiple File Upload

```python
def upload_multiple_files(kb_id, file_paths):
    """Upload multiple files to knowledge base."""
    url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload/batch"

    files = []
    for file_path in file_paths:
        with open(file_path, 'rb') as f:
            files.append((
                'files',
                (file_path.split('/')[-1], f.read(), get_mime_type(file_path))
            ))

    response = requests.post(
        url,
        headers={'Authorization': f'Bearer {TOKEN}'},
        files=files
    )

    return response.json()['data']

# Usage
file_paths = [
    '/path/to/doc1.pdf',
    '/path/to/doc2.docx',
    '/path/to/doc3.txt'
]

result = upload_multiple_files('kb-123', file_paths)
print(f"Success: {result['summary']['success_count']}")
print(f"Failed: {result['summary']['failed_count']}")
```

### Upload with Progress

```python
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

def upload_with_progress(kb_id, file_path, callback=None):
    """Upload file with progress tracking."""
    url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload"

    with open(file_path, 'rb') as f:
        encoder = MultipartEncoder(
            fields={
                'file': (file_path.split('/')[-1], f, get_mime_type(file_path))
            }
        )

        def progress_callback(monitor):
            progress = (monitor.bytes_read / monitor.len) * 100
            if callback:
                callback(progress)
            print(f"Upload progress: {progress:.1f}%")

        monitor = MultipartEncoderMonitor(encoder, progress_callback)

        response = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {TOKEN}',
                'Content-Type': monitor.content_type
            },
            data=monitor
        )

    return response.json()['data']

# Usage
def on_progress(progress):
    print(f"Uploading: {progress:.1f}%")

result = upload_with_progress(
    kb_id='kb-123',
    file_path='/path/to/large-file.pdf',
    callback=on_progress
)
```

### Upload from URL

```python
def upload_from_url(kb_id, url, filename=None, metadata=None):
    """Upload file from URL."""
    api_url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload/url"

    payload = {
        'url': url,
        'filename': filename or url.split('/')[-1]
    }

    if metadata:
        payload['metadata'] = metadata

    response = requests.post(
        api_url,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'application/json'
        },
        json=payload
    )

    return response.json()['data']

# Usage
result = upload_from_url(
    kb_id='kb-123',
    url='https://example.com/document.pdf',
    filename='product-manual.pdf',
    metadata={
        'title': 'Product Manual',
        'category': 'documentation'
    }
)
```

### Chunked Upload (Large Files)

```python
def chunked_upload(kb_id, file_path, chunk_size=5*1024*1024):
    """Upload large file in chunks."""
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)

    # Initialize upload
    init_url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload/init"
    init_response = requests.post(
        init_url,
        headers={'Authorization': f'Bearer {TOKEN}'},
        json={
            'filename': filename,
            'size': file_size,
            'mime_type': get_mime_type(file_path)
        }
    )

    upload_id = init_response.json()['data']['upload_id']

    # Upload chunks
    with open(file_path, 'rb') as f:
        chunk_num = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            chunk_num += 1
            chunk_url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload/chunk"

            response = requests.post(
                chunk_url,
                headers={'Authorization': f'Bearer {TOKEN}'},
                files={'chunk': (f'chunk-{chunk_num}', chunk)},
                data={
                    'upload_id': upload_id,
                    'chunk_num': chunk_num
                }
            )

            progress = (f.tell() / file_size) * 100
            print(f"Upload progress: {progress:.1f}%")

    # Complete upload
    complete_url = f"{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload/complete"
    complete_response = requests.post(
        complete_url,
        headers={'Authorization': f'Bearer {TOKEN}'},
        json={'upload_id': upload_id}
    )

    return complete_response.json()['data']

# Usage
result = chunked_upload('kb-123', '/path/to/large-file.pdf')
```

## JavaScript Examples

### Single File Upload

```javascript
async function uploadFile(kbId, file, metadata = {}) {
  const formData = new FormData();
  formData.append('file', file);

  if (Object.keys(metadata).length > 0) {
    formData.append('metadata', JSON.stringify(metadata));
  }

  const response = await fetch(
    `${API_BASE_URL}/api/v1/kb/${kbId}/documents/upload`,
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

const result = await uploadFile('kb-123', file, {
  title: 'Product Manual',
  category: 'documentation'
});

console.log(`Uploaded: ${result.id}`);
```

### Multiple File Upload

```javascript
async function uploadMultipleFiles(kbId, files) {
  const formData = new FormData();

  for (const file of files) {
    formData.append('files', file);
  }

  const response = await fetch(
    `${API_BASE_URL}/api/v1/kb/${kbId}/documents/upload/batch`,
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
const fileInput = document.querySelector('input[type="file"][multiple]');
const files = Array.from(fileInput.files);

const result = await uploadMultipleFiles('kb-123', files);
console.log(`Success: ${result.summary.success_count}`);
console.log(`Failed: ${result.summary.failed_count}`);
```

### Upload with Progress

```javascript
async function uploadWithProgress(kbId, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    // Track upload progress
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const progress = (e.loaded / e.total) * 100;
        onProgress(progress);
      }
    });

    // Handle completion
    xhr.addEventListener('load', () => {
      if (xhr.status === 200) {
        const result = JSON.parse(xhr.responseText);
        resolve(result.data);
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    });

    // Handle errors
    xhr.addEventListener('error', () => {
      reject(new Error('Upload failed'));
    });

    // Send request
    xhr.open('POST', `${API_BASE_URL}/api/v1/kb/${kbId}/documents/upload`);
    xhr.setRequestHeader('Authorization', `Bearer ${TOKEN}`);
    xhr.send(formData);
  });
}

// Usage
const file = fileInput.files[0];

const result = await uploadWithProgress('kb-123', file, (progress) => {
  console.log(`Upload progress: ${progress.toFixed(1)}%`);
});
```

### Upload from URL

```javascript
async function uploadFromUrl(kbId, url, filename = null, metadata = {}) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/kb/${kbId}/documents/upload/url`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${TOKEN}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url,
        filename: filename || url.split('/').pop(),
        metadata
      })
    }
  );

  const result = await response.json();
  return result.data;
}

// Usage
const result = await uploadFromUrl(
  'kb-123',
  'https://example.com/document.pdf',
  'product-manual.pdf',
  {
    title: 'Product Manual',
    category: 'documentation'
  }
);
```

### Drag and Drop Upload

```javascript
function setupDragAndDrop(dropZone, kbId) {
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');

    const files = Array.from(e.dataTransfer.files);

    for (const file of files) {
      try {
        const result = await uploadWithProgress(kbId, file, (progress) => {
          console.log(`${file.name}: ${progress.toFixed(1)}%`);
        });
        console.log(`Uploaded: ${result.id}`);
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
      }
    }
  });
}

// Usage
const dropZone = document.getElementById('drop-zone');
setupDragAndDrop(dropZone, 'kb-123');
```

## UI Implementation

### React File Upload Component

```jsx
import { useState } from 'react';
import { toast } from 'sonner';

function FileUpload({ kbId, onUploadComplete }) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState([]);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    setSelectedFiles(files);
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setProgress(0);

    try {
      const formData = new FormData();
      selectedFiles.forEach(file => {
        formData.append('files', file);
      });

      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percent = (e.loaded / e.total) * 100;
          setProgress(percent);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          const result = JSON.parse(xhr.responseText);
          toast.success(`Uploaded ${result.data.summary.success_count} files`);
          onUploadComplete(result.data);
          setSelectedFiles([]);
        } else {
          toast.error('Upload failed');
        }
        setUploading(false);
      });

      xhr.addEventListener('error', () => {
        toast.error('Upload failed');
        setUploading(false);
      });

      xhr.open('POST', `/api/v1/kb/${kbId}/documents/upload/batch`);
      xhr.setRequestHeader('Authorization', `Bearer ${TOKEN}`);
      xhr.send(formData);

    } catch (error) {
      toast.error(`Upload failed: ${error.message}`);
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="border-2 border-dashed rounded-lg p-8 text-center">
        <input
          type="file"
          multiple
          onChange={handleFileSelect}
          disabled={uploading}
          className="hidden"
          id="file-input"
        />
        <label
          htmlFor="file-input"
          className="cursor-pointer text-primary hover:underline"
        >
          Click to select files
        </label>
        <p className="text-sm text-muted-foreground mt-2">
          or drag and drop files here
        </p>
      </div>

      {selectedFiles.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium">Selected Files ({selectedFiles.length})</h4>
          <ul className="space-y-1">
            {selectedFiles.map((file, index) => (
              <li key={index} className="text-sm flex items-center justify-between">
                <span>{file.name}</span>
                <span className="text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {uploading && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span>Uploading...</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-primary h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      <button
        onClick={handleUpload}
        disabled={uploading || selectedFiles.length === 0}
        className="w-full px-4 py-2 bg-primary text-white rounded disabled:opacity-50"
      >
        {uploading ? 'Uploading...' : `Upload ${selectedFiles.length} Files`}
      </button>
    </div>
  );
}
```

### Drag and Drop Component

```jsx
import { useState } from 'react';

function DragDropUpload({ kbId, onUploadComplete }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    await uploadFiles(files);
  };

  const uploadFiles = async (files) => {
    setUploading(true);

    try {
      const formData = new FormData();
      files.forEach(file => formData.append('files', file));

      const response = await fetch(
        `/api/v1/kb/${kbId}/documents/upload/batch`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${TOKEN}`
          },
          body: formData
        }
      );

      const result = await response.json();
      toast.success(`Uploaded ${result.data.summary.success_count} files`);
      onUploadComplete(result.data);

    } catch (error) {
      toast.error(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`
        border-2 border-dashed rounded-lg p-12 text-center transition-colors
        ${isDragging ? 'border-primary bg-primary/5' : 'border-gray-300'}
        ${uploading ? 'opacity-50 pointer-events-none' : ''}
      `}
    >
      {uploading ? (
        <div>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto" />
          <p className="mt-4 text-sm text-muted-foreground">Uploading...</p>
        </div>
      ) : (
        <div>
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            stroke="currentColor"
            fill="none"
            viewBox="0 0 48 48"
          >
            <path
              d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="mt-4 text-sm text-gray-600">
            Drag and drop files here, or click to select
          </p>
          <p className="mt-1 text-xs text-gray-500">
            PDF, DOCX, TXT, and more (max 50 MB per file)
          </p>
        </div>
      )}
    </div>
  );
}
```

## Best Practices

### File Uploads

**✅ Do:**
- Validate file types before upload
- Check file size limits
- Show upload progress
- Handle upload errors gracefully
- Provide clear feedback
- Support drag and drop
- Allow multiple file selection
- Compress large files when possible

**❌ Don't:**
- Upload without validation
- Ignore file size limits
- Block UI during upload
- Hide upload progress
- Skip error handling
- Force single file uploads
- Forget to show file names
- Upload uncompressed large files

### Performance

**✅ Do:**
- Use chunked upload for large files
- Compress files before upload
- Upload multiple files in parallel
- Show progress indicators
- Implement retry logic
- Use appropriate chunk sizes
- Cancel uploads when needed

**❌ Don't:**
- Upload large files in one request
- Skip compression
- Upload files sequentially
- Hide progress
- Give up on first failure
- Use too small chunks
- Leave failed uploads hanging

### Security

**✅ Do:**
- Validate file types on server
- Scan for malware
- Limit file sizes
- Use secure connections (HTTPS)
- Sanitize filenames
- Check user permissions
- Log upload activities

**❌ Don't:**
- Trust client-side validation only
- Skip malware scanning
- Allow unlimited file sizes
- Use HTTP for uploads
- Use original filenames directly
- Skip permission checks
- Forget audit logging

## Troubleshooting

### Upload Failed

**Problem:** File upload fails

**Solutions:**
1. Check file size (max 50 MB)
2. Verify file type is supported
3. Check network connection
4. Verify authentication token
5. Check server logs

### File Too Large

**Problem:** File exceeds size limit

**Solutions:**
1. Compress the file
2. Split into smaller files
3. Use chunked upload
4. Contact admin for limit increase

### Unsupported File Type

**Problem:** File type not accepted

**Solutions:**
1. Convert to supported format
2. Check file extension
3. Verify MIME type
4. Contact admin for support

### Upload Timeout

**Problem:** Upload times out

**Solutions:**
1. Use chunked upload
2. Improve network connection
3. Reduce file size
4. Increase timeout (if possible)

## Related Documentation

- [Batch Operations](./batch-operations.md) - Batch upload operations
- [Error Handling](./error-handling.md) - Error handling patterns
- [Knowledge Base API](./endpoints/knowledge-base.md) - KB endpoints
- [Documents API](./endpoints/documents.md) - Document management

---

**Last Updated**: 2026-02-11
