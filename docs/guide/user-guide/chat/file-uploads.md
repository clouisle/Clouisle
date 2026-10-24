# File Uploads in Chat

This guide explains how to upload and use files when chatting with AI agents.

## Overview

Clouisle allows you to upload files during chat conversations to:

- **Analyze documents**: Upload PDFs, Word docs, spreadsheets for analysis
- **Process images**: Upload images for vision-based AI agents
- **Share context**: Provide files as context for better responses

## Supported File Types

### Documents

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **PDF** | `.pdf` | 10 MB | Portable Document Format |
| **Word** | `.doc`, `.docx` | 10 MB | Microsoft Word documents |
| **Excel** | `.xls`, `.xlsx` | 10 MB | Microsoft Excel spreadsheets |
| **PowerPoint** | `.pptx` | 10 MB | Microsoft PowerPoint presentations |
| **Text** | `.txt`, `.md` | 10 MB | Plain text and Markdown |
| **CSV** | `.csv` | 10 MB | Comma-separated values |
| **JSON** | `.json` | 10 MB | JSON data files |
| **HTML** | `.html` | 10 MB | HTML documents |

### Images

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **JPEG** | `.jpg`, `.jpeg` | 10 MB | JPEG images |
| **PNG** | `.png` | 10 MB | PNG images |
| **GIF** | `.gif` | 10 MB | GIF images |
| **WebP** | `.webp` | 10 MB | WebP images |
| **SVG** | `.svg` | 10 MB | SVG images |
| **ICO** | `.ico` | 10 MB | Icon files |

> **Note:** All chat uploads share a single **10 MB per file** limit. There are no separate per-format limits, and BMP/code files are not supported.

## Uploading Files

### Method 1: Drag and Drop

**Steps:**

1. Open a chat conversation
2. Drag a file from your computer
3. Drop it into the chat input area
4. The file is uploaded and attached to your message
5. Add text message (optional)
6. Click **"Send"** or press **Enter**

### Method 2: File Picker

**Steps:**

1. Click the **📎 attachment icon** in the chat input
2. File picker dialog opens
3. Select one or more files
4. Click **"Open"**
5. The files are uploaded and attached
6. Add text message (optional)
7. Click **"Send"**

### Method 3: Paste from Clipboard

**Steps:**

1. Copy a file or image to clipboard
2. Click in the chat input area
3. Press **Ctrl+V** (Windows/Linux) or **Cmd+V** (Mac)
4. The file is pasted and uploaded
5. Add text message (optional)
6. Click **"Send"**

**Note**: Works best for images copied from screenshots or other applications.

## File Upload Process

### Upload Flow

**What happens when you upload:**

1. **Validation**: File type and size are checked
2. **Upload**: File is uploaded to the server
3. **Attachment**: The original Asset is attached to your message
4. **On-demand extraction**: The first document read or search prepares and persists the complete extracted text
5. **Analysis**: The Agent searches and reads bounded ranges, continuing as needed

### File Parsing

- **Documents**: Supported formats are converted to persistent text on first use. Text is not automatically injected into model context. `read_asset` provides line ranges and continuation, including oversized lines; `search_asset` locates literal text with bounded snippets. A continuation cursor must be followed until `eof` to finish reading.
- **Images**: Sent as native image content for capable model adapters. Native PDF page viewing remains separate from text line reading.
- **Extraction limits**: Text extraction is not OCR or a guarantee of layout fidelity. Failed or empty extraction is reported; it is not treated as a successfully read document. A model run can stop before finishing a long file if its execution budget is exhausted.
- **Per-call bounds**: Reading and search responses are limited to 32 KiB of serialized UTF-8. A large line continues in another segment with the same line number; concatenate those fragments before inserting a newline. Search snippets can be clipped and are not a replacement for reading the matching lines.
- **Resource limits**: Complete extraction supports up to 5,000,000 extracted characters. Larger or undecodable files fail explicitly rather than returning only a prefix. A concurrent first extraction may report that it is still in progress; call again later.

## Using Uploaded Files

### Asking Questions About Files

**Example prompts:**

**For documents:**
```
"Summarize this document"
"What are the key points in this PDF?"
"Extract all dates mentioned in this file"
```

**For images:**
```
"What's in this image?"
"Describe this diagram"
"Extract text from this screenshot"
```

### File Context

**How agents use files:**

1. **Reference discovery**: Current attachments provide file metadata and scope-local refs; older files can be discovered with `list_assets`.
2. **Bounded reading**: The Agent uses `search_asset` to locate passages and `read_asset` to read line ranges. Later calls reuse persisted extracted text rather than re-parsing the file.
3. **Response generation**: Answers are based on the passages actually read. Original Asset permissions and active-branch visibility are checked on every operation.

### Multiple Files

You can attach several files to one message (subject to the agent's configured max files, default 5).

## File Limitations

### Size Limits

**Default limits:**
- All file types: 10 MB per file (server-enforced)

**Exceeding limits:**
```
❌ Error: File too large
   document.pdf (15 MB) exceeds the maximum size of 10 MB.
```

### Unsupported File Types

**If you upload an unsupported file:**
```
❌ Error: Unsupported file type
   file.xyz is not a supported file type.
```

## File Security

### Privacy

**File handling:**
- Files are stored on the server (no client-side encryption).
- Chat submission authorizes referenced Assets before attaching them to a message.
- Generated images, generated videos, and sandbox artifacts use protected download categories; viewing or downloading them requires an authenticated user or API key with access to the related conversation or workflow run.
- Non-protected upload URLs can be fetched directly by URL, so do not use them for sensitive data unless your deployment adds an access boundary.
- Deleting a conversation removes its message links; it does not currently guarantee deletion of the uploaded asset.

> **Note:** There is no virus scanning of uploaded files.

## Best Practices

### Uploading Files

**✅ Do:**
- Compress large files before uploading
- Use descriptive file names
- Upload relevant files only
- Provide context with your message

**❌ Don't:**
- Upload files without explaining what you need
- Upload the same file multiple times

## Troubleshooting

### Upload Fails

**Problem**: File upload fails or gets stuck

**Solutions:**
1. Check your internet connection
2. Verify the file size is under 10 MB
3. Check the file type is supported
4. Try a different browser
5. Try uploading a smaller file first
6. Contact the administrator if the issue persists

### File Not Processed

**Problem**: File uploaded but agent doesn't respond

**Solutions:**
1. Wait a few moments (files take time to parse)
2. Check if the file type is supported for parsing
3. Try asking a specific question about the file
4. Re-upload the file

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Chat basics
- [Conversation Management](./conversation-management.md) - Managing conversations

## Getting Help

If you need assistance with file uploads:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-09-08
