# Document Management

This guide explains how to manage documents in knowledge bases.

## Overview

Document management allows you to:

- **Monitor status**: Track processing and indexing
- **Rename documents**: Change the display name
- **Delete documents**: Remove unwanted content
- **Reprocess documents**: Re-run processing after configuration changes
- **Manage chunks**: View, edit, and delete chunks
- **Run bulk actions**: Process pending documents, retry failed chunks, or delete selected documents

> **Note:** Document categories, tags, folders, bulk ZIP download, archiving, replacing a document's content, and per-document permissions/sharing are **not implemented**.

## Accessing Documents

### From Knowledge Base

1. In the platform header, select **Knowledge Base** (`/app/kb`).
2. Open a knowledge base at `/app/kb/{id}`.
3. Use the document list and its row or selection actions.

**Documents list:**
```
┌─────────────────────────────────────────────────────┐
│ Documents (156)                  [Upload ▼] [⚙️]    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ Sales Report Q3 2026.pdf                         │
│    2.3 MB • 15 pages • Completed                   │
│    Updated: 2026-02-11                             │
│    [View] [Rename] [Download] [...]                │
│                                                     │
│ ✅ Product Documentation.docx                      │
│    1.5 MB • 45 pages • Completed                   │
│    Updated: 2026-02-10                             │
│    [View] [Rename] [Download] [...]                │
│                                                     │
│ ⏳ Marketing Strategy.pptx                          │
│    3.1 MB • Processing                             │
│    Uploaded: 2026-02-11                            │
│                                                     │
│ ❌ Budget Analysis.xlsx                             │
│    5.2 MB • Error                                  │
│    Error: ...                                      │
│    [Retry] [Delete]                                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Document Information

### Document Details

**View document information:**

1. Click on a document
2. Document details panel opens
3. View complete information

**Details panel:**
```
┌─────────────────────────────────────────┐
│ Sales Report Q3 2026.pdf         [✕]   │
├─────────────────────────────────────────┤
│                                         │
│ Status: ✅ Completed                    │
│                                         │
│ File Information:                       │
│ • Size: 2.3 MB                          │
│ • Type: PDF                             │
│                                         │
│ Processing:                             │
│ • Uploaded: 2026-02-11 10:00:00        │
│ • Processed: 2026-02-11 10:01:23       │
│ • Chunks: 45                            │
│ • Tokens: 12,345                        │
│ • Metadata: (auto-extracted JSON)       │
│                                         │
│ [Rename] [Reprocess]                    │
│ [Download] [Delete]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Document Status

**Status types:**

| Status | Description |
|--------|-------------|
| **Pending** | Uploaded, waiting to be processed |
| **Processing** | Content is being extracted and indexed |
| **Completed** | Document is ready for use |
| **Error** | Processing failed (see error message) |

## Editing Documents

### Renaming a Document

The only editable metadata field is the document **name** (via `PUT /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}`). Titles, descriptions, tags, categories, and languages are not editable fields — the `metadata` JSON is auto-extracted from the file.

## Reprocessing Documents

**Reprocess a document:**

1. Click on a document
2. Click **"Reprocess"** button
3. Optionally adjust processing settings (chunk size, chunk overlap, separator)
4. Click **"Reprocess"**

**When to reprocess:**
- After updating the KB chunking strategy
- After changing the embedding model
- If processing failed initially

## Managing Chunks

Each document is split into chunks that can be viewed, edited, or deleted individually:

- **List chunks**: `GET /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/chunks`
- **Edit a chunk**: `PUT /.../chunks/{chunk_id}` (update content/metadata)
- **Delete a chunk**: `DELETE /.../chunks/{chunk_id}`
- **Add a chunk**: `POST /.../chunks`
- **Retry failed embedding**: `POST /.../chunks/{chunk_id}/retry-embedding` or `POST /.../retry-failed-chunks`

**When to edit chunks:**
- Fix extraction errors
- Clean up noisy content
- Re-run a failed chunk embedding

## Deleting Documents

### Delete Single Document

**Steps:**

1. Click on a document
2. Click the **"..."** menu
3. Select **"Delete"**
4. Confirm deletion
5. The document is permanently deleted

**Delete confirmation:**
```
┌─────────────────────────────────────────┐
│ ⚠️ Delete Document?                     │
├─────────────────────────────────────────┤
│                                         │
│ Are you sure you want to delete:       │
│                                         │
│ Sales Report Q3 2026.pdf                │
│                                         │
│ This action cannot be undone.           │
│                                         │
│ [Cancel]  [Delete Permanently]          │
│                                         │
└─────────────────────────────────────────┘
```

### What Gets Deleted

**Permanently removed:**
- Original file
- Extracted text
- Vector embeddings
- Chunks
- Search index entries

### Bulk actions

1. In the Documents list, select one or more rows.
2. Choose the available bulk action:
   - **Process** starts processing for selected pending documents.
   - **Retry** retries failed chunks for selected documents in error state.
   - **Delete** permanently deletes the selected documents after confirmation.
3. Refresh the list to confirm the updated statuses.

Bulk ZIP download is not available; download documents individually.

## Downloading Documents

### Download Single Document

1. Click on a document
2. Click **"Download"** button
3. The file is downloaded to your computer

**Or:**

1. Click the **"..."** menu on the document
2. Select **"Download"**

> **Note:** Bulk ZIP download is **not implemented**.

## Best Practices

### Document Maintenance

**✅ Do:**
- Review documents regularly
- Update outdated content
- Monitor processing status
- Clean up failed uploads
- Delete duplicates

**❌ Don't:**
- Ignore failed documents
- Keep outdated content
- Forget to monitor processing status

### Performance

**✅ Do:**
- Use appropriate file formats
- Compress large files
- Split very large documents

**❌ Don't:**
- Upload unnecessarily large files
- Upload duplicate content

## Troubleshooting

### Cannot Rename Document

**Problem**: Rename fails or is disabled

**Solutions:**
1. Check if you have permission
2. Verify the new name is valid (max 255 chars)
3. Try refreshing the page

### Cannot Delete Document

**Problem**: Delete fails or is disabled

**Solutions:**
1. Check if you have permission
2. Refresh the page
3. Contact the administrator

### Document Not Searchable

**Problem**: Document doesn't appear in search

**Solutions:**
1. Check document status (must be completed)
2. Check if the document is in the selected KB
3. Wait for indexing to complete
4. Try reprocessing the document

## Related Documentation

- [Uploading Documents](./uploading-documents.md) - Adding documents
- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Searching Documents](./searching.md) - Finding documents

## Getting Help

If you need assistance with document management:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
