# Uploading Documents

This guide explains how to upload documents to knowledge bases in Clouisle.

## Overview

You can upload documents to knowledge bases to:

- **Build knowledge repositories**: Create searchable document collections
- **Enable RAG**: Provide context for AI agents
- **Share information**: Make documents accessible to team members

## Supported File Types

The knowledge-base upload dialog accepts:

| Format | Extensions |
|--------|------------|
| PDF | `.pdf` |
| Word | `.doc`, `.docx` |
| Excel | `.xls`, `.xlsx` |
| PowerPoint | `.pptx` |
| Text | `.txt` |
| Markdown | `.md`, `.markdown` |
| HTML | `.html`, `.htm` |
| CSV | `.csv` |
| JSON | `.json` |

### Web Pages

Documents can also be added from a **URL** (web page).

**Max file size:** 50 MB per file by default, configurable by administrators between 1 MB and 1024 MB (`kb_document_max_upload_size_mb`).

> **Note:** The KB upload UI and endpoint support `.pptx`, not legacy `.ppt`. XML files and archive auto-extraction (ZIP/TAR/GZ) are not supported. OCR for scanned documents/images is not implemented.

## Accessing Knowledge Bases

1. In the platform header, select **Knowledge Base** (`/app/kb`).
2. Select a knowledge base to open `/app/kb/{id}`.
3. Open the **Documents** area, then choose **Upload**.

## Uploading Documents

### Method 1: File Picker

**Steps:**

1. Open a knowledge base.
2. Click **Upload**.
3. Click the upload dialog's drop zone to open the file picker.
4. Select one or more files, then click **Open**.
5. Review the selection and click **Upload**.
6. Each file is uploaded as a `pending` document; process it to index it.

### Method 2: Drag and Drop

**Steps:**

1. Open a knowledge base and click **Upload**.
2. Open file explorer on your computer.
3. Drag one or more files into the upload dialog's drop zone.
4. Review the selection and click **Upload**.
5. Each file is uploaded as a `pending` document; process it to index it.

### Method 3: Add from URL

1. Click **Import URL**.
2. Enter the web page URL and, optionally, a document name.
3. Click **Import** — a `pending` URL document is created and its preview editor opens. Generate a preview to fetch the page, then process the reviewed chunks.

> **Note:** Folder upload is not implemented. The upload dialog accepts multiple files, but each file is created as a separate `pending` document; uploading does not process it. Use the document's **Process** action or preview editor for each file.

## Upload Process

### Processing Steps

**What happens when you upload:**

1. **Upload**: File is uploaded to the server
2. **Validation**: File type and size are checked
3. **Status**: Document is created in `pending` status
4. **Process**: The document must be processed manually through the process action or preview editor to:
   - Extract text
   - Split into chunks (default: size 1000, overlap 100)
   - Generate embeddings
   - Index for search

**Processing time:**
- Small files: seconds
- Medium files: seconds to a minute
- Large files: longer

### Processing Status

**Document status:**

| Status | Description |
|--------|-------------|
| **Pending** | Uploaded, waiting to be processed |
| **Processing** | Content is being extracted and indexed |
| **Completed** | Document is ready for search |
| **Error** | Processing failed (see error message) |

## Document Name

For file uploads, the current UI uses the filename and does not provide a rename action. When importing a URL, you can provide an optional document name before creating it.

## Upload Errors

### Common Errors

**File too large:**
```
❌ Error: File too large
   document.pdf (150 MB) exceeds the maximum size of 50 MB.
```

**Unsupported file type:**
```
❌ Error: Unsupported file type
   file.xyz is not a supported file type.
```

**Processing failed:**
```
❌ Error: Processing failed
   Could not extract text from document.pdf

   Possible reasons:
   • File is corrupted
   • File is password-protected
   • File contains only images (OCR not supported)

   Solutions:
   • Try re-uploading
   • Remove password protection
   • Convert to a different format
```

### Handling Errors

**Retry failed processing:**

1. Find the failed document in the list
2. Click **"Reprocess"** (or **"Retry"**)
3. The document is processed again

## Document Limits

### Upload Limits

- **File size**: 50 MB per file by default (configurable 1-1024 MB)
- **Storage**: No per-KB quota; monitor storage at the team level

## Best Practices

### Preparing Documents

**✅ Do:**
- Use clear, descriptive filenames
- Remove password protection
- Compress large PDFs
- Use standard file formats
- Remove sensitive information

**❌ Don't:**
- Upload password-protected files
- Upload corrupted files
- Upload proprietary formats
- Upload low-quality scans (no OCR)

### Organizing Documents

**✅ Do:**
- Use descriptive names
- Keep the KB focused on related content
- Remove duplicate documents

**❌ Don't:**
- Leave default filenames
- Mix unrelated documents
- Upload duplicate content

## Troubleshooting

### Upload Fails

**Problem**: File upload fails or gets stuck

**Solutions:**
1. Check your internet connection
2. Verify the file size is within limits
3. Check the file type is supported
4. Try a different browser
5. Clear browser cache
6. Try uploading one file at a time

### Processing Stuck

**Problem**: Document stuck in "Processing" status

**Solutions:**
1. Wait longer (large files take time)
2. Refresh the page
3. Try reprocessing
4. Contact the administrator

### Text Not Extracted

**Problem**: Document uploaded but no text extracted

**Solutions:**
1. Check if the file contains actual text (not just images)
2. Try converting to a different format
3. Check if the file is corrupted
4. Try re-uploading

### Cannot Upload

**Problem**: Upload button disabled or not working

**Solutions:**
1. Check if you have permission
2. Try a different browser
3. Contact the administrator

## Related Documentation

- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Searching Documents](./searching.md) - Finding documents
- [Document Management](./document-management.md) - Managing documents

## Getting Help

If you need assistance with uploading documents:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
