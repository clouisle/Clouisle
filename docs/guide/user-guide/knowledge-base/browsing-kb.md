# Browsing Knowledge Bases

This guide explains how to browse and explore knowledge bases in Clouisle.

## Overview

Knowledge bases in Clouisle store documents that AI agents can access for answering questions. As a user, you can browse knowledge bases to:
- View available documents
- Search for specific information
- Download documents
- Understand what information agents can access

## Accessing Knowledge Bases

### From Platform Interface

1. Navigate to **Knowledge Bases** or **KB** section in the sidebar
2. You'll see a list of knowledge bases you have access to
3. Click on a knowledge base to open it

### Knowledge Base List

The list shows:

| Column | Description |
|--------|-------------|
| **Name** | Knowledge base name |
| **Team** | Team that owns the KB |
| **Documents** | Number of documents |
| **Chunks** | Number of text chunks |
| **Updated** | Last update time |
| **Status** | Active, Processing, Error, or Archived |

**Filtering:**
- Filter by status
- Search by name

## Knowledge Base Details

### Overview Tab

Shows knowledge base information:

**Basic Information:**
- Name and description
- Team ownership
- Creation date
- Last updated
- Total documents
- Total chunks
- Total tokens

**Embedding Model:**
- Model name
- Embedding dimension (set after the first document is processed)

**Statistics:**
- Document count by type (PDF, DOCX, etc.)
- Processing status (Completed, Processing, Failed)

### Documents Tab

Lists all documents in the knowledge base:

**Document List:**

| Column | Description |
|--------|-------------|
| **Name** | Document filename |
| **Type** | File format (PDF, DOCX, etc.) |
| **Size** | File size |
| **Chunks** | Number of chunks |
| **Status** | Processing status |
| **Uploaded** | Upload date |
| **Actions** | View, Download, Delete |

**Document Status:**
- ✅ **Completed**: Successfully processed and indexed
- ⏳ **Processing**: Currently being processed
- ❌ **Error**: Processing failed (see error message)
- 📝 **Pending**: Waiting to be processed

### Search Tab

Search within the knowledge base:

**Search Interface:**
1. Enter your search query
2. Select search mode:
   - **Vector**: Semantic similarity
   - **Fulltext**: Exact term matching (keyword/full-text)
   - **Hybrid**: Combined (default, recommended)
3. Adjust parameters:
   - **Top K**: Number of results (default: 5)
   - **Score Threshold**: Minimum relevance (default: 0.0)
4. Click **Search**

**Search Results:**

Each result shows:
- **Chunk text**: Relevant text excerpt
- **Score**: Relevance score (0.0 - 1.0)
- **Source**: Document name and location
- **Metadata**: Additional information

**Example:**
```
Score: 0.85
Source: user-manual.pdf (Page 12)

"To reset your password, navigate to Settings >
Security > Password. Click 'Change Password' and
enter your current password followed by your new
password..."

[View Full Document]
```

## Viewing Documents

### Document Viewer

Click on a document to open the viewer:

**Viewer Features:**
- **Preview**: View document content
- **Metadata**: Document information
- **Chunks**: View how the document is chunked
- **Download**: Download the original file

### Document Metadata

Shows document details:

| Field | Description |
|-------|-------------|
| **Filename** | Original filename |
| **Type** | File format |
| **Size** | File size |
| **Uploaded** | Upload date and time |
| **Uploaded By** | User who uploaded |
| **Status** | Processing status |
| **Chunks** | Number of chunks |
| **Tokens** | Total token count |

### Chunk View

See how the document is split into chunks:

**Chunk List:**
- Chunk number
- Chunk text (preview)
- Token count
- Metadata

**Example:**
```
Chunk 1 (245 tokens)
"Introduction to Clouisle

Clouisle is an enterprise-grade AI platform that
enables organizations to build and deploy intelligent
agents..."

[View Full Chunk]
```

**Why view chunks?**
- Understand how agents see the document
- Verify chunking quality
- Debug search issues

## Searching Documents

### Vector Search

**Best for:**
- Semantic similarity
- Paraphrased questions
- Conceptual queries

**Example:**
```
Query: "How do I change my password?"

Results:
1. "To reset your password, go to Settings..." (0.89)
2. "Password management is available in..." (0.82)
3. "Security settings include password..." (0.76)
```

### Fulltext Search

**Best for:**
- Exact term matching
- Product names, IDs
- Technical terms

**Example:**
```
Query: "API-KEY-12345"

Results:
1. "Your API key API-KEY-12345 was created..." (exact match)
2. "API keys like API-KEY-12345 provide..." (exact match)
```

### Hybrid Search

**Best for:**
- General purpose
- Combines semantic and keyword matching
- Recommended for most searches

### Search Tips

**✅ Do:**
- Use natural language questions
- Be specific about what you're looking for
- Try different phrasings if no results
- Use hybrid search for best results

**❌ Don't:**
- Expect results for information not in the KB
- Search for real-time information

## Filtering and Sorting

### Filter Options

**By Document Type:**
- PDF
- DOCX
- TXT
- MD
- XLSX
- CSV
- All types

**By Status:**
- Completed
- Processing
- Error
- Pending
- All statuses

### Sort Options

**Sort by:**
- Name (A-Z, Z-A)
- Upload date (Newest, Oldest)
- Size (Largest, Smallest)
- Chunks (Most, Least)
- Relevance (for search results)

## Downloading Documents

### Single Document

1. Open document details
2. Click **Download** button
3. File downloads to your computer

> **Note:** Bulk download as a ZIP archive is **not implemented** — documents are downloaded one at a time.

## Understanding Document Status

### Completed ✅

Document successfully processed:
- Text extracted
- Chunked into segments
- Embedded with vector model
- Indexed and searchable

**What you can do:**
- Search within the document
- View chunks
- Use in agent conversations
- Download

### Processing ⏳

Document currently being processed:
- Text extraction in progress
- Chunking and embedding

**What you can do:**
- Wait for completion
- View basic metadata
- Cannot search yet

### Error ❌

Processing failed:
- Error during text extraction
- Unsupported format
- Corrupted file

**What you can do:**
- View error message
- Download the original file
- Delete and re-upload
- Retry the failed chunks / reprocess

### Pending 📝

Document uploaded but not yet processed — processing starts when the document is processed (automatically or via the process action).

## Knowledge Base Statistics

### Document Statistics

View statistics for the knowledge base:

**Document Count:**
- Total documents
- By file type (PDF: 45, DOCX: 23, etc.)
- By status (Completed: 65, Processing: 2, Error: 1)

**Content Statistics:**
- Total chunks: 1,234
- Total tokens: 456,789
- Average chunks per document: 18

## Best Practices

### Browsing Efficiently

**✅ Do:**
- Use search instead of scrolling through long lists
- Filter by document type for specific formats
- Sort by date to find recent documents
- Check document status before expecting results

**❌ Don't:**
- Expect instant results for large documents
- Search for information not in the KB

### Search Effectively

**For specific information:**
```
Good: "What is the refund policy for cancelled orders?"
Bad: "refund"
```

**For concepts:**
```
Good: Use vector or hybrid search
Bad: Use only fulltext search for semantic queries
```

## Troubleshooting

### No Search Results

**Problem**: Search returns no results

**Solutions:**
1. Lower the score threshold (default is already 0.0)
2. Increase top K (try 10 instead of 5)
3. Try a different search mode (hybrid)
4. Rephrase your query
5. Verify documents are indexed (status: Completed)

### Document Not Visible

**Problem**: Cannot see a document you uploaded

**Solutions:**
1. Check if you're viewing the correct knowledge base
2. Verify you have access to the team
3. Check if the document is still processing
4. Refresh the page

### Cannot Download Document

**Problem**: Download button disabled or fails

**Solutions:**
1. Verify you have download permission
2. Check if document processing completed
3. Try a different browser
4. Check your internet connection

### Search Results Irrelevant

**Problem**: Search returns unrelated results

**Solutions:**
1. Increase the score threshold
2. Be more specific in your query
3. Use fulltext search for exact terms
4. Try hybrid search mode

## Related Documentation

- [Uploading Documents](./uploading-documents.md) - How to upload documents
- [Searching](./searching.md) - Advanced search techniques
- [Document Management](./document-management.md) - Managing documents

## Getting Help

If you need assistance:

1. **Documentation**: Review this guide
2. **Support**: Contact your organization's support team
3. **Administrator**: Reach out to your KB administrator

---

**Last Updated**: 2026-02-11
