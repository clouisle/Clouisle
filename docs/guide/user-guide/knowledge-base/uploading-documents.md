# Uploading Documents

This guide explains how to upload documents to knowledge bases in Clouisle.

## Overview

You can upload documents to knowledge bases to:

- **Build knowledge repositories**: Create searchable document collections
- **Enable RAG**: Provide context for AI agents
- **Share information**: Make documents accessible to team members
- **Organize content**: Categorize and manage documents

## Supported File Types

### Documents

| Format | Extension | Max Size | Description |
|--------|-----------|----------|-------------|
| **PDF** | `.pdf` | 100 MB | Portable Document Format |
| **Word** | `.docx`, `.doc` | 100 MB | Microsoft Word documents |
| **Excel** | `.xlsx`, `.xls` | 100 MB | Microsoft Excel spreadsheets |
| **PowerPoint** | `.pptx`, `.ppt` | 100 MB | Microsoft PowerPoint presentations |
| **Text** | `.txt` | 50 MB | Plain text files |
| **Markdown** | `.md` | 50 MB | Markdown documents |
| **CSV** | `.csv` | 100 MB | Comma-separated values |
| **JSON** | `.json` | 50 MB | JSON data files |
| **HTML** | `.html`, `.htm` | 50 MB | HTML documents |
| **XML** | `.xml` | 50 MB | XML documents |

**Note**: Maximum file sizes are configurable by administrators.

## Accessing Knowledge Bases

### From Platform Interface

**Steps:**

1. Navigate to **Knowledge Bases** section
2. Click on a knowledge base to open it
3. Go to **Documents** tab
4. Click **"Upload"** button

**Or:**

- Navigate directly to `/kb/{kb_id}/documents`

## Uploading Documents

### Method 1: File Picker

**Steps:**

1. Open a knowledge base
2. Click **"Upload"** button
3. File picker dialog opens
4. Select one or more files
5. Click **"Open"**
6. Files are uploaded and processed
7. Wait for processing to complete

**Upload button:**
```
┌─────────────────────────────────────────┐
│ Documents                    [Upload ▼] │
├─────────────────────────────────────────┤
│                                         │
│ [Document list...]                      │
│                                         │
└─────────────────────────────────────────┘
```

### Method 2: Drag and Drop

**Steps:**

1. Open a knowledge base
2. Open file explorer on your computer
3. Select files to upload
4. Drag files into the documents area
5. Drop files when you see the drop zone
6. Files are uploaded automatically

**Drop zone:**
```
┌─────────────────────────────────────────┐
│                                         │
│         📄 Drop files here              │
│                                         │
│    Or click to browse files             │
│                                         │
│  Supported: PDF, DOCX, TXT, MD, etc.   │
│  Max size: 100 MB per file              │
│                                         │
└─────────────────────────────────────────┘
```

### Method 3: Bulk Upload

**For many files:**

1. Click **"Upload"** dropdown
2. Select **"Bulk Upload"**
3. Choose folder or multiple files
4. Click **"Upload All"**
5. Monitor progress

**Bulk upload:**
```
┌─────────────────────────────────────────┐
│ Bulk Upload                             │
├─────────────────────────────────────────┤
│                                         │
│ Selected: 25 files (45.2 MB)           │
│                                         │
│ ✓ document1.pdf (2.3 MB)               │
│ ✓ document2.docx (1.5 MB)              │
│ ⏳ document3.pdf (3.1 MB) - 45%        │
│ ⏸️ document4.txt (0.5 MB)              │
│ ...                                     │
│                                         │
│ Progress: 12/25 files (48%)             │
│ [████████░░░░░░░░░░░░] 48%             │
│                                         │
│ [Pause] [Cancel]                        │
│                                         │
└─────────────────────────────────────────┘
```

## Upload Process

### Processing Steps

**What happens when you upload:**

1. **Upload**: File is uploaded to server
2. **Validation**: File type and size are checked
3. **Text Extraction**: Content is extracted from file
4. **Chunking**: Content is split into chunks
5. **Embedding**: Chunks are converted to vectors
6. **Indexing**: Vectors are stored in database
7. **Complete**: Document is ready for search

**Processing time:**
- Small files (<1 MB): 5-30 seconds
- Medium files (1-10 MB): 30 seconds - 2 minutes
- Large files (10-100 MB): 2-10 minutes

### Upload Progress

**Progress indicator:**
```
Uploading: sales_report.pdf
[████████████████████░░] 90%

Processing: sales_report.pdf
⏳ Extracting text... (Step 2/5)
```

**Status icons:**
- ⏳ **Processing**: Currently being processed
- ✅ **Completed**: Successfully processed
- ❌ **Failed**: Processing failed
- ⏸️ **Queued**: Waiting to be processed

### Processing Status

**Document status:**

| Status | Description |
|--------|-------------|
| **Uploading** | File is being uploaded |
| **Processing** | Content is being extracted and indexed |
| **Completed** | Document is ready for use |
| **Failed** | Processing failed (see error message) |
| **Queued** | Waiting in processing queue |

## Document Metadata

### Setting Metadata

**During upload:**

1. Upload file(s)
2. Click **"Edit Metadata"** on uploaded file
3. Fill in metadata:
   - **Title**: Document title (auto-detected from filename)
   - **Description**: Brief description
   - **Tags**: Keywords for categorization
   - **Category**: Document category
   - **Language**: Document language
4. Click **"Save"**

**Metadata form:**
```
┌─────────────────────────────────────────┐
│ Document Metadata                       │
├─────────────────────────────────────────┤
│                                         │
│ Title: *                                │
│ [Sales Report Q3 2026__________]        │
│                                         │
│ Description:                            │
│ [Quarterly sales analysis and trends]   │
│                                         │
│ Tags:                                   │
│ [sales] [q3] [2026] [+ Add]            │
│                                         │
│ Category:                               │
│ [Reports ▼]                             │
│                                         │
│ Language:                               │
│ [English ▼]                             │
│                                         │
│ [Cancel]  [Save]                        │
│                                         │
└─────────────────────────────────────────┘
```

### Auto-detected Metadata

**Automatically extracted:**
- **Title**: From filename or document title
- **Language**: Detected from content
- **File type**: From file extension
- **File size**: Actual file size
- **Page count**: For PDFs and documents
- **Word count**: Estimated word count
- **Created date**: File creation date
- **Modified date**: File modification date

## Chunking Strategy

### What is Chunking?

Chunking splits documents into smaller pieces for better search and retrieval.

**Why chunk:**
- Improves search accuracy
- Reduces context size for LLMs
- Enables precise citations
- Better semantic matching

### Chunking Options

**Default strategy:**
- **Chunk size**: 1000 characters
- **Overlap**: 200 characters
- **Method**: Semantic (respects paragraphs)

**Custom chunking:**

1. Click **"Advanced Options"** during upload
2. Configure chunking:
   - **Chunk size**: 500-2000 characters
   - **Overlap**: 0-500 characters
   - **Method**: Semantic, Fixed, Sentence
3. Click **"Upload"**

**Chunking methods:**

| Method | Description | Best For |
|--------|-------------|----------|
| **Semantic** | Respects paragraphs and sections | General documents |
| **Fixed** | Fixed character count | Structured data |
| **Sentence** | Splits by sentences | Short documents |
| **Page** | One chunk per page | PDFs with page structure |

## Batch Operations

### Uploading Multiple Files

**Steps:**

1. Select multiple files in file picker
2. Or drag and drop multiple files
3. All files are uploaded together
4. Monitor progress for each file

**Batch progress:**
```
┌─────────────────────────────────────────┐
│ Uploading 10 files...                   │
├─────────────────────────────────────────┤
│                                         │
│ ✅ file1.pdf - Completed                │
│ ✅ file2.docx - Completed               │
│ ⏳ file3.pdf - Processing (45%)         │
│ ⏸️ file4.txt - Queued                   │
│ ⏸️ file5.md - Queued                    │
│ ...                                     │
│                                         │
│ Overall: 2/10 completed (20%)           │
│                                         │
└─────────────────────────────────────────┘
```

### Folder Upload

**Uploading entire folders:**

1. Click **"Upload"** dropdown
2. Select **"Upload Folder"**
3. Choose folder
4. All files in folder are uploaded
5. Folder structure is preserved (optional)

**Note**: Browser support for folder upload varies.

## Upload Errors

### Common Errors

**File too large:**
```
❌ Error: File too large
   document.pdf (150 MB) exceeds the maximum size of 100 MB.

   Solutions:
   • Compress the PDF
   • Split into smaller files
   • Contact administrator for limit increase
```

**Unsupported file type:**
```
❌ Error: Unsupported file type
   file.xyz is not a supported file type.

   Supported types: PDF, DOCX, XLSX, TXT, MD, CSV, JSON, HTML
```

**Processing failed:**
```
❌ Error: Processing failed
   Could not extract text from document.pdf

   Possible reasons:
   • File is corrupted
   • File is password-protected
   • File contains only images (OCR not enabled)

   Solutions:
   • Try re-uploading
   • Remove password protection
   • Convert to different format
```

**Duplicate document:**
```
⚠️ Warning: Duplicate document
   A document with the same name already exists.

   Options:
   • Replace existing document
   • Keep both (rename new document)
   • Cancel upload
```

### Handling Errors

**Retry failed uploads:**

1. Find failed document in list
2. Click **"Retry"** button
3. Document is re-uploaded and processed

**View error details:**

1. Click on failed document
2. View error message and details
3. Follow suggested solutions

## Document Limits

### Upload Limits

**Default limits:**
- **File size**: 100 MB per file
- **Batch size**: 50 files per batch
- **Total storage**: 10 GB per knowledge base
- **Daily uploads**: 1000 files per day

**Exceeding limits:**
```
⚠️ Storage limit reached
   This knowledge base has reached its storage limit (10 GB).

   Current usage: 10.2 GB / 10 GB

   Solutions:
   • Delete unused documents
   • Archive old documents
   • Request storage increase
   • Create new knowledge base
```

### Processing Queue

**Queue limits:**
- Maximum 100 documents in processing queue
- Documents are processed in order
- Large files may take longer

**Queue status:**
```
┌─────────────────────────────────────────┐
│ Processing Queue                        │
├─────────────────────────────────────────┤
│                                         │
│ Position: 5 of 23                       │
│ Estimated wait: 2 minutes               │
│                                         │
│ Your documents:                         │
│ • document1.pdf - Position 5            │
│ • document2.docx - Position 12          │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Preparing Documents

**✅ Do:**
- Use clear, descriptive filenames
- Remove password protection
- Compress large PDFs
- Use standard file formats
- Check document quality
- Remove sensitive information

**❌ Don't:**
- Use special characters in filenames
- Upload password-protected files
- Upload corrupted files
- Use proprietary formats
- Upload low-quality scans
- Include confidential data

### Organizing Documents

**✅ Do:**
- Add descriptive titles
- Use consistent tags
- Categorize documents
- Add descriptions
- Use meaningful metadata
- Group related documents

**❌ Don't:**
- Leave default filenames
- Skip metadata
- Mix unrelated documents
- Use inconsistent naming
- Forget to tag documents

### Performance

**✅ Do:**
- Upload during off-peak hours
- Use batch upload for many files
- Compress large files
- Monitor processing status
- Wait for processing to complete

**❌ Don't:**
- Upload extremely large files
- Upload too many files at once
- Close browser during upload
- Interrupt processing
- Upload duplicate files

## Troubleshooting

### Upload Fails

**Problem**: File upload fails or gets stuck

**Solutions:**
1. Check internet connection
2. Verify file size is within limits
3. Check file type is supported
4. Try a different browser
5. Clear browser cache
6. Try uploading one file at a time
7. Contact administrator

### Processing Stuck

**Problem**: Document stuck in "Processing" status

**Solutions:**
1. Wait longer (large files take time)
2. Refresh the page
3. Check processing queue
4. Try re-uploading
5. Contact administrator

### Text Not Extracted

**Problem**: Document uploaded but no text extracted

**Solutions:**
1. Check if file contains actual text (not just images)
2. Try converting to different format
3. Enable OCR if available
4. Check if file is corrupted
5. Try re-uploading

### Cannot Upload

**Problem**: Upload button disabled or not working

**Solutions:**
1. Check if you have permission
2. Verify knowledge base is not full
3. Check if knowledge base is locked
4. Try different browser
5. Contact administrator

## Advanced Features

### OCR (Optical Character Recognition)

If enabled by administrator:

**What it does:**
- Extracts text from scanned documents
- Reads text from images in PDFs
- Converts handwritten notes to text

**Usage:**
1. Upload scanned document
2. Enable **"Use OCR"** option
3. Document is processed with OCR
4. Text is extracted and indexed

**Note**: OCR processing takes longer.

### Custom Embeddings

**For advanced users:**

1. Click **"Advanced Options"** during upload
2. Select **"Custom Embeddings"**
3. Choose embedding model
4. Configure parameters
5. Upload document

**Embedding models:**
- Default: OpenAI text-embedding-3-small
- Alternative: Custom embedding models

### Metadata Extraction

**Auto-extract metadata:**

1. Enable **"Extract Metadata"** option
2. System extracts:
   - Author
   - Creation date
   - Keywords
   - Summary
   - Categories
3. Review and edit extracted metadata
4. Save document

## Related Documentation

- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Searching Documents](./searching.md) - Finding documents
- [Document Management](./document-management.md) - Managing documents
- [Knowledge Base Concepts](../../concepts/knowledge-bases.md) - Understanding KBs

## Getting Help

If you need assistance with uploading documents:

1. **Documentation**: Review this guide
2. **Upload Help**: Click **?** icon in upload dialog
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
