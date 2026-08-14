# Document Metadata

This guide explains how document metadata works in knowledge bases.

## Overview

Metadata is structured information extracted from or stored alongside documents. Clouisle automatically extracts a `metadata` JSON object for each document; metadata is used for retrieval context but is not editable field-by-field and cannot be configured as custom schemas.

> **Note:** Custom metadata field definitions, upload-time metadata forms, metadata-based filtering, templates, validation rules, computed fields, and versioning are **not implemented**.

## System Fields

### Document Fields

Stored directly on each document:

- `filename` / `name`: Document name
- `doc_type`: File type (pdf, docx, doc, txt, markdown, html, csv, xlsx, xls, json, url)
- `file_size`: File size in bytes
- `status`: pending, processing, completed, error
- `chunk_count`: Number of chunks generated
- `token_count`: Estimated token count
- `source_url`: Original URL (for web documents added via URL)
- `processed_at`: When processing completed
- `created_at` / `updated_at`: Timestamps

### Extracted Metadata

The `metadata` JSON field is automatically extracted from the document (for example `title`, `author`, `language`, `section`, and other properties depending on the file format). The exact contents depend on the file and the extraction pipeline.

## Viewing Metadata

View the metadata JSON in the document details panel / chunk view. Chunks also carry their own `metadata` (e.g., page number, section) used for retrieval context.

## Updating Metadata

The only editable document field is the **name** (`PUT /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}` with `{"name": "..."}`). The `metadata` JSON itself is regenerated during processing and cannot be edited through a dedicated metadata endpoint.

## Using Metadata in Retrieval

Metadata is returned as part of search results and RAG context (each chunk's metadata is included in retrieved context). There is no metadata-based filtering or boosting in search requests — the only search filter is `filter_doc_ids` (restrict to specific document IDs).

## Related Documentation

- [Document Management](./document-management.md) - Managing documents
- [Searching](./searching.md) - Finding documents
- [Knowledge Base Settings](./kb-settings.md) - KB configuration

---

**Last Updated**: 2026-02-11
