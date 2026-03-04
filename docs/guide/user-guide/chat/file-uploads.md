# File Uploads in Chat

This guide explains how to upload and use files when chatting with AI agents.

## Overview

Clouisle allows you to upload files during chat conversations to:

- **Analyze documents**: Upload PDFs, Word docs, spreadsheets for analysis
- **Process images**: Upload images for vision-based AI agents
- **Share context**: Provide files as context for better responses
- **Extract information**: Get data extracted from documents
- **Generate content**: Use files as input for content generation

## Supported File Types

### Documents

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **PDF** | `.pdf` | 50 MB | Portable Document Format |
| **Word** | `.docx`, `.doc` | 50 MB | Microsoft Word documents |
| **Excel** | `.xlsx`, `.xls` | 50 MB | Microsoft Excel spreadsheets |
| **PowerPoint** | `.pptx`, `.ppt` | 50 MB | Microsoft PowerPoint presentations |
| **Text** | `.txt`, `.md` | 10 MB | Plain text and Markdown |
| **CSV** | `.csv` | 50 MB | Comma-separated values |
| **JSON** | `.json` | 10 MB | JSON data files |

### Images

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **JPEG** | `.jpg`, `.jpeg` | 20 MB | JPEG images |
| **PNG** | `.png` | 20 MB | PNG images |
| **GIF** | `.gif` | 20 MB | GIF images |
| **WebP** | `.webp` | 20 MB | WebP images |
| **BMP** | `.bmp` | 20 MB | Bitmap images |

### Code Files

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **Python** | `.py` | 5 MB | Python source code |
| **JavaScript** | `.js`, `.ts` | 5 MB | JavaScript/TypeScript |
| **HTML/CSS** | `.html`, `.css` | 5 MB | Web markup and styles |
| **Java** | `.java` | 5 MB | Java source code |
| **C/C++** | `.c`, `.cpp`, `.h` | 5 MB | C/C++ source code |

**Note**: Maximum file sizes are configurable by administrators.

## Uploading Files

### Method 1: Drag and Drop

**Steps:**

1. Open a chat conversation
2. Drag a file from your computer
3. Drop it into the chat input area
4. File is uploaded and attached to your message
5. Add text message (optional)
6. Click **"Send"** or press **Enter**

**Visual indicator:**
```
┌─────────────────────────────────────┐
│  Drop file here to upload           │
│                                     │
│         📄                          │
│                                     │
└─────────────────────────────────────┘
```

### Method 2: File Picker

**Steps:**

1. Click the **📎 attachment icon** in the chat input
2. File picker dialog opens
3. Select one or more files
4. Click **"Open"**
5. Files are uploaded and attached
6. Add text message (optional)
7. Click **"Send"**

### Method 3: Paste from Clipboard

**Steps:**

1. Copy a file or image to clipboard
2. Click in the chat input area
3. Press **Ctrl+V** (Windows/Linux) or **Cmd+V** (Mac)
4. File is pasted and uploaded
5. Add text message (optional)
6. Click **"Send"**

**Note**: Works best for images copied from screenshots or other applications.

## File Upload Process

### Upload Flow

**What happens when you upload:**

1. **Validation**: File type and size are checked
2. **Upload**: File is uploaded to server
3. **Processing**: File is processed (text extraction, image analysis)
4. **Attachment**: File is attached to your message
5. **Display**: File preview is shown in chat
6. **Analysis**: Agent analyzes the file content

**Upload progress:**
```
Uploading document.pdf...
[████████████████░░░░] 80%
```

### File Processing

**Document processing:**
- Text extraction from PDFs, Word docs
- Table extraction from Excel, CSV
- Slide content extraction from PowerPoint
- OCR for scanned documents (if enabled)

**Image processing:**
- Image compression for faster loading
- Thumbnail generation
- Metadata extraction (dimensions, format)
- Vision analysis (if agent supports it)

**Processing time:**
- Small files (<1 MB): Instant
- Medium files (1-10 MB): 1-5 seconds
- Large files (10-50 MB): 5-30 seconds

## Using Uploaded Files

### Asking Questions About Files

**Example prompts:**

**For documents:**
```
"Summarize this document"
"What are the key points in this PDF?"
"Extract all dates mentioned in this file"
"Translate this document to Spanish"
"Find all mentions of 'revenue' in this spreadsheet"
```

**For images:**
```
"What's in this image?"
"Describe this diagram"
"Extract text from this screenshot"
"What colors are used in this design?"
"Identify objects in this photo"
```

**For code files:**
```
"Review this code for bugs"
"Explain what this function does"
"Optimize this code"
"Convert this Python code to JavaScript"
"Add comments to this code"
```

### File Context

**How agents use files:**

1. **Content extraction**: Text, tables, images are extracted
2. **Context building**: File content is added to conversation context
3. **Analysis**: Agent analyzes the content
4. **Response generation**: Agent generates response based on file content

**Example conversation:**
```
You: [Uploads sales_report.pdf]
     "What were the top 3 products by revenue?"

Agent: Based on the sales report, the top 3 products by revenue were:
       1. Product A: $1,234,567
       2. Product B: $987,654
       3. Product C: $765,432
```

### Multiple Files

**Uploading multiple files:**

1. Select multiple files in file picker
2. Or drag and drop multiple files at once
3. All files are uploaded together
4. Agent can reference all files in response

**Example:**
```
You: [Uploads Q1_report.pdf, Q2_report.pdf, Q3_report.pdf]
     "Compare revenue trends across these quarterly reports"

Agent: Analyzing the three quarterly reports:
       - Q1 revenue: $5.2M
       - Q2 revenue: $6.1M (+17%)
       - Q3 revenue: $7.3M (+20%)

       Revenue shows consistent growth with Q3 being the strongest quarter.
```

## File Display in Chat

### File Preview

**Document preview:**
```
┌─────────────────────────────────────┐
│ 📄 sales_report.pdf                 │
│ 2.3 MB • 15 pages                   │
│ [View] [Download]                   │
└─────────────────────────────────────┘
```

**Image preview:**
```
┌─────────────────────────────────────┐
│ 🖼️ screenshot.png                   │
│ [Image thumbnail displayed]         │
│ 1920x1080 • 456 KB                  │
│ [View Full Size] [Download]         │
└─────────────────────────────────────┘
```

**Code file preview:**
```
┌─────────────────────────────────────┐
│ 💻 script.py                        │
│ 3.2 KB • Python                     │
│ [View Code] [Download]              │
└─────────────────────────────────────┘
```

### File Actions

**Available actions:**

| Action | Description |
|--------|-------------|
| **View** | Open file in viewer |
| **Download** | Download file to your computer |
| **Remove** | Remove file from message (before sending) |
| **Copy Link** | Copy file URL to clipboard |

## File Viewer

### Opening Files

**Steps:**

1. Click **"View"** on a file preview
2. File viewer opens in modal
3. View file content
4. Use viewer controls (zoom, navigate pages)
5. Click **"Close"** or press **Esc** to close

### Viewer Features

**Document viewer:**
- Page navigation (previous/next)
- Zoom in/out
- Full-screen mode
- Search within document
- Download option

**Image viewer:**
- Zoom in/out
- Pan (drag to move)
- Rotate
- Full-screen mode
- Download option

**Code viewer:**
- Syntax highlighting
- Line numbers
- Copy code
- Download option

## File Limitations

### Size Limits

**Default limits:**
- Documents: 50 MB per file
- Images: 20 MB per file
- Code files: 5 MB per file
- Total per message: 100 MB

**Exceeding limits:**
```
❌ Error: File too large
   document.pdf (75 MB) exceeds the maximum size of 50 MB.

   Please compress the file or split it into smaller parts.
```

### File Count Limits

**Default limits:**
- Maximum 10 files per message
- Maximum 100 files per conversation

**Exceeding limits:**
```
❌ Error: Too many files
   You can upload a maximum of 10 files per message.

   Please send files in multiple messages.
```

### Unsupported File Types

**If you upload an unsupported file:**
```
❌ Error: Unsupported file type
   file.xyz is not a supported file type.

   Supported types: PDF, DOCX, XLSX, PNG, JPG, TXT, etc.
```

## File Security

### Privacy

**File handling:**
- Files are encrypted during upload
- Files are stored securely on server
- Files are only accessible to conversation participants
- Files are deleted when conversation is deleted

**Access control:**
- Only team members can access files in team conversations
- Only you can access files in personal conversations
- Administrators cannot access your private conversation files

### Virus Scanning

**Security measures:**
- All uploaded files are scanned for viruses
- Malicious files are rejected
- You're notified if a file is blocked

**Blocked file:**
```
❌ Error: Security threat detected
   file.exe was blocked because it contains malicious content.

   Please do not upload executable files.
```

### Data Retention

**File storage:**
- Files are stored for the lifetime of the conversation
- Files are deleted when conversation is deleted
- You can manually delete files from messages

**Deleting files:**
1. Hover over the message with the file
2. Click **"..."** menu
3. Select **"Delete message"**
4. File is permanently deleted

## Best Practices

### Uploading Files

**✅ Do:**
- Compress large files before uploading
- Use descriptive file names
- Upload relevant files only
- Provide context with your message
- Check file type is supported

**❌ Don't:**
- Upload sensitive/confidential files to public agents
- Upload files with personal information unnecessarily
- Upload extremely large files (split them instead)
- Upload executable files (.exe, .bat, .sh)
- Upload files without explaining what you need

### File Organization

**✅ Do:**
- Name files clearly (e.g., "Q3_Sales_Report.pdf")
- Group related files in one message
- Mention file names in your message
- Use folders/zip for many related files

**❌ Don't:**
- Use generic names (e.g., "document.pdf")
- Upload unrelated files together
- Forget to mention which file you're referring to

### Performance

**✅ Do:**
- Compress images before uploading
- Use PDF instead of large image scans
- Split very large documents
- Upload files one at a time if experiencing issues

**❌ Don't:**
- Upload unnecessarily high-resolution images
- Upload the same file multiple times
- Upload files during poor network connection

## Troubleshooting

### Upload Fails

**Problem**: File upload fails or gets stuck

**Solutions:**
1. Check your internet connection
2. Verify file size is within limits
3. Check file type is supported
4. Try a different browser
5. Clear browser cache
6. Try uploading a smaller file first
7. Contact administrator if issue persists

### File Not Processing

**Problem**: File uploaded but agent doesn't respond

**Solutions:**
1. Wait a few moments (large files take time)
2. Check if file type is supported for analysis
3. Try asking a specific question about the file
4. Re-upload the file
5. Try a different file format

### Cannot View File

**Problem**: File viewer doesn't open or shows error

**Solutions:**
1. Try downloading the file instead
2. Check if file is corrupted
3. Try a different browser
4. Clear browser cache
5. Re-upload the file

### File Preview Not Showing

**Problem**: File uploaded but no preview displayed

**Solutions:**
1. Refresh the page
2. Check browser console for errors
3. Try a different browser
4. File may be processing (wait a moment)
5. Contact administrator

## Advanced Features

### OCR (Optical Character Recognition)

If enabled by your administrator:

**What it does:**
- Extracts text from scanned documents
- Reads text from images
- Converts handwritten notes to text

**Usage:**
```
You: [Uploads scanned_document.pdf]
     "Extract all text from this scanned document"

Agent: [Performs OCR and extracts text]
       Here's the extracted text:
       [Full text content...]
```

### Vision Analysis

For agents with vision capabilities:

**What it does:**
- Analyzes image content
- Identifies objects, people, text
- Describes scenes and diagrams
- Extracts information from screenshots

**Usage:**
```
You: [Uploads diagram.png]
     "Explain this architecture diagram"

Agent: This diagram shows a microservices architecture with:
       - Frontend (React)
       - API Gateway
       - 3 backend services
       - Database cluster
       - Message queue
```

### Batch Processing

**Processing multiple files:**
```
You: [Uploads 10 invoice PDFs]
     "Extract invoice numbers, dates, and totals from all these invoices"

Agent: Processing 10 invoices...

       Invoice Summary:
       1. INV-001 | 2026-01-15 | $1,234.56
       2. INV-002 | 2026-01-16 | $2,345.67
       ...
```

## Related Documentation

- [Chatting with Agents](./chatting-with-agents.md) - Chat basics
- [Conversation Management](./conversation-management.md) - Managing conversations
- [Agent Capabilities](../../concepts/agents.md) - What agents can do
- [Security Best Practices](../../best-practices/security.md) - Security guidelines

## Getting Help

If you need assistance with file uploads:

1. **Documentation**: Review this guide
2. **File Limits**: Check with administrator for your organization's limits
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
