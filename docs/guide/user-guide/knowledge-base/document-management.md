# Document Management

This guide explains how to manage documents in knowledge bases.

## Overview

Document management allows you to:

- **Organize documents**: Categorize and structure content
- **Update documents**: Replace or modify existing documents
- **Delete documents**: Remove unwanted content
- **Monitor status**: Track processing and indexing
- **Manage metadata**: Edit titles, tags, and descriptions
- **Control access**: Set document permissions

## Accessing Documents

### From Knowledge Base

**Steps:**

1. Navigate to **Knowledge Bases** section
2. Click on a knowledge base to open it
3. Go to **Documents** tab
4. View all documents in the knowledge base

**Documents list:**
```
┌─────────────────────────────────────────────────────┐
│ Documents (156)                  [Upload ▼] [⚙️]    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ Sales Report Q3 2026.pdf                         │
│    2.3 MB • 15 pages • Completed                   │
│    Updated: 2026-02-11 • Category: Reports         │
│    [View] [Edit] [Download] [...]                  │
│                                                     │
│ ✅ Product Documentation.docx                       │
│    1.5 MB • 45 pages • Completed                   │
│    Updated: 2026-02-10 • Category: Documentation   │
│    [View] [Edit] [Download] [...]                  │
│                                                     │
│ ⏳ Marketing Strategy.pptx                          │
│    3.1 MB • Processing (45%)                       │
│    Uploaded: 2026-02-11                            │
│    [Cancel]                                        │
│                                                     │
│ ❌ Budget Analysis.xlsx                             │
│    5.2 MB • Failed                                 │
│    Error: File too large                           │
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
│ • Pages: 15                             │
│ • Words: ~3,450                         │
│                                    │
│ Metadata:                               │
│ • Title: Sales Report Q3 2026          │
│ • Category: Reports                     │
│ • Tags: sales, q3, 2026                │
│ • Language: English                     │
│ • Author: John Doe                      │
│                                         │
│ Processing:                             │
│ • Uploaded: 2026-02-11 10:00:00        │
│ • Processed: 2026-02-11 10:01:23       │
│ • Chunks: 45                            │
│ • Vectors: 45                           │
│                                         │
│ [Edit Metadata] [Reprocess]             │
│ [Download] [Delete]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Document Status

**Status types:**

| Status | Icon | Description |
|--------|------|-------------|
| **Uploading** | ⏫ | File is being uploaded |
| **Processing** | ⏳ | Content is being extracted and indexed |
| **Completed** | ✅ | Document is ready for use |
| **Failed** | ❌ | Processing failed |
| **Queued** | ⏸️ | Waiting in processing queue |
| **Archived** | 📦 | Archived (not searchable) |

## Editing Documents

### Updating Metadata

**Edit document metadata:**

1. Click on a document
2. Click **"Edit Metadata"** button
3. Update fields:
   - Title
   - Description
   - Tags
   - Category
   - Language
4. Click **"Save"**

**Metadata form:**
```
┌─────────────────────────────────────────┐
│ Edit Metadata                           │
├─────────────────────────────────────────┤
│                                         │
│ Title: *                                │
│ [Sales Report Q3 2026__________]        │
│                                         │
│ Description:                            │
│ [Quarterly sales analysis and trends_]  │
│ [for Q3 2026. Includes revenue data,_]  │
│ [customer metrics, and forecasts.___]   │
│                                         │
│ Category:                               │
│ [Reports ▼]                             │
│                                         │
│ Tags:                                   │
│ [sales] [q3] [2026] [revenue]          │
│ [+ Add Tag]                             │
│                                         │
│ Language:                               │
│ [English ▼]                             │
│                                         │
│ Author:                                 │
│ [John Doe_______________]               │
│                                         │
│ [Cancel]  [Save Changes]                │
│                                         │
└─────────────────────────────────────────┘
```

### Replacing Documents

**Replace document content:**

1. Click on a document
2. Click **"..."** menu
3. Select **"Replace"**
4. Upload new file
5. Choose replacement options:
   - Keep metadata
   - Keep tags
   - Keep category
6. Click **"Replace"**

**Replacement options:**
```
┌─────────────────────────────────────────┐
│ Replace Document                        │
├─────────────────────────────────────────┤
│                                         │
│ Current: Sales Report Q3 2026.pdf      │
│ New: Sales Report Q3 2026 Updated.pdf  │
│                                         │
│ Options:                                │
│ ☑ Keep existing metadata                │
│ ☑ Keep existing tags                    │
│ ☑ Keep existing category                │
│ ☐ Archive old version                   │
│                                         │
│ [Cancel]  [Replace Document]            │
│                                         │
└─────────────────────────────────────────┘
```

### Reprocessing Documents

**Reprocess document:**

1. Click on a document
2. Click **"Reprocess"** button
3. Select reprocessing options:
   - Re-extract text
   - Re-chunk content
   - Re-generate embeddings
4. Click **"Reprocess"**

**When to reprocess:**
- After updating chunking strategy
- After changing embedding model
- If processing failed initially
- To improve search quality

## Organizing Documents

### Categories

**Assign categories:**

1. Click on a document
2. Edit metadata
3. Select category from dropdown
4. Or create new category
5. Save changes

**Category management:**
```
┌─────────────────────────────────────────┐
│ Categories                              │
├─────────────────────────────────────────┤
│                                         │
│ 📁 Documentation (45 docs)              │
│ 📁 Reports (23 docs)                    │
│ 📁 Policies (12 docs)                   │
│ 📁 Guides (34 docs)                     │
│ 📁 Templates (8 docs)                   │
│                                         │
│ [+ Create Category]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Tags

**Add tags:**

1. Click on a document
2. Edit metadata
3. Enter tag name
4. Press **Enter** or click **"Add"**
5. Repeat for multiple tags
6. Save changes

**Tag suggestions:**
- Auto-suggested based on content
- Previously used tags shown
- Can create new tags

**Tag management:**
```
┌─────────────────────────────────────────┐
│ Tags                                    │
├─────────────────────────────────────────┤
│                                         │
│ Current Tags:                           │
│ [sales] [q3] [2026] [revenue]          │
│                                         │
│ Suggested Tags:                         │
│ [+ analysis] [+ quarterly]              │
│ [+ performance] [+ metrics]             │
│                                         │
│ Popular Tags:                           │
│ sales (45) • reports (34) • 2026 (67)  │
│ q3 (23) • documentation (56)            │
│                                         │
└─────────────────────────────────────────┘
```

### Folders (If Available)

**Organize in folders:**

1. Click **"Create Folder"** button
2. Enter folder name
3. Drag documents into folder
4. Or use **"Move to Folder"** option

**Folder structure:**
```
📁 Knowledge Base
├── 📁 2026 Reports
│   ├── 📄 Q1 Sales Report.pdf
│   ├── 📄 Q2 Sales Report.pdf
│   └── 📄 Q3 Sales Report.pdf
├── 📁 Documentation
│   ├── 📄 User Guide.docx
│   ├── 📄 API Reference.pdf
│   └── 📄 FAQ.md
└── 📁 Policies
    ├── 📄 Privacy Policy.pdf
    └── 📄 Terms of Service.pdf
```

## Bulk Operations

### Selecting Multiple Documents

**Select documents:**

1. Check boxes next to documents
2. Or click **"Select All"** to select all
3. Selected count shows in header

**Selection toolbar:**
```
┌─────────────────────────────────────────┐
│ 5 documents selected                    │
│ [Edit Metadata] [Move] [Delete] [More] │
└─────────────────────────────────────────┘
```

### Bulk Edit Metadata

**Edit multiple documents:**

1. Select documents
2. Click **"Edit Metadata"**
3. Update fields (applies to all)
4. Click **"Apply to All"**

**Bulk edit:**
```
┌─────────────────────────────────────────┐
│ Bulk Edit Metadata (5 documents)       │
├─────────────────────────────────────────┤
│                                         │
│ Category:                               │
│ [Reports ▼]                             │
│                                         │
│ Add Tags:                               │
│ [2026] [+ Add]                          │
│                                         │
│ Language:                               │
│ [English ▼]                             │
│                                         │
│ ☑ Overwrite existing values             │
│ ☐ Only update empty fields              │
│                                         │
│ [Cancel]  [Apply to All]                │
│                                         │
└─────────────────────────────────────────┘
```

### Bulk Move

**Move documents:**

1. Select documents
2. Click **"Move"**
3. Select destination:
   - Different knowledge base
   - Different folder
   - Different category
4. Click **"Move"**

### Bulk Delete

**Delete multiple documents:**

1. Select documents
2. Click **"Delete"**
3. Confirm deletion
4. All selected documents are deleted

**Warning**: Deleted documents cannot be recovered.

## Downloading Documents

### Download Single Document

**Steps:**

1. Click on a document
2. Click **"Download"** button
3. File is downloaded to your computer

**Or:**

1. Click **"..."** menu on document
2. Select **"Download"**

### Bulk Download

**Download multiple documents:**

1. Select documents
2. Click **"Download"** button
3. Choose format:
   - **ZIP**: All files in archive
   - **Individual**: Download each separately
4. Click **"Download"**

**ZIP contents:**
```
documents.zip
├── Sales Report Q3 2026.pdf
├── Product Documentation.docx
├── Marketing Strategy.pptx
└── metadata.json
```

## Archiving Documents

### Archive Document

**Archive instead of delete:**

1. Click on a document
2. Click **"..."** menu
3. Select **"Archive"**
4. Document is archived

**What happens:**
- Document is hidden from main list
- Not included in search results
- Metadata preserved
- Can be restored later

### Viewing Archived Documents

**Access archived documents:**

1. Go to knowledge base
2. Click **"Archived"** tab or filter
3. View all archived documents

**Restore archived document:**

1. Find document in archived list
2. Click **"Restore"**
3. Document returns to main list

## Deleting Documents

### Delete Single Document

**Steps:**

1. Click on a document
2. Click **"..."** menu
3. Select **"Delete"**
4. Confirm deletion
5. Document is permanently deleted

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
│ What will be deleted:                   │
│ • Original file                         │
│ • Extracted text                        │
│ • Vector embeddings                     │
│ • All metadata                          │
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
- Metadata (title, tags, etc.)
- Processing history
- Search index entries

**Not deleted:**
- Audit logs (for compliance)
- References in chat history

## Document Permissions

### Setting Permissions

**Control document access:**

1. Click on a document
2. Click **"Permissions"** button
3. Configure access:
   - **Public**: Everyone can view
   - **Team**: Only team members
   - **Private**: Only you
   - **Custom**: Specific users/roles
4. Save permissions

**Permissions panel:**
```
┌─────────────────────────────────────────┐
│ Document Permissions                    │
├─────────────────────────────────────────┤
│                                         │
│ Visibility:                             │
│ ○ Public (everyone)                     │
│ ● Team (team members only)              │
│ ○ Private (only me)                     │
│ ○ Custom                                │
│                                         │
│ Team Access:                            │
│ ☑ Can view                              │
│ ☑ Can download                          │
│ ☐ Can edit metadata                     │
│ ☐ Can delete                            │
│                                         │
│ [Save Permissions]                      │
│                                         │
└─────────────────────────────────────────┘
```

### Sharing Documents

**Share with specific users:**

1. Click **"Share"** button
2. Enter user email or name
3. Select permission level:
   - View only
   - View and download
   - Edit metadata
4. Click **"Share"**

**Share link:**
```
┌─────────────────────────────────────────┐
│ Share Document                          │
├─────────────────────────────────────────┤
│                                         │
│ Share with:                             │
│ [alice@example.com_________] [Add]      │
│                                         │
│ Current Shares:                         │
│ • Alice (View only)      [Remove]       │
│ • Bob (Edit metadata)    [Remove]       │
│                                         │
│ Or share via link:                      │
│ [Copy Link] [Generate New Link]         │
│                                         │
│ Link expires: [7 days ▼]                │
│                                         │
└─────────────────────────────────────────┘
```

## Monitoring Documents

### Processing Status

**Track processing:**

1. Go to **Documents** tab
2. View processing status for each document
3. Click on processing document for details

**Processing details:**
```
┌─────────────────────────────────────────┐
│ Processing: Marketing Strategy.pptx     │
├─────────────────────────────────────────┤
│                                         │
│ Progress: 45%                           │
│ [████████████░░░░░░░░░░░░░░] 45%       │
│                                         │
│ Current Step: Extracting text (3/5)    │
│                                         │
│ Steps:                                  │
│ ✅ Upload complete                      │
│ ✅ File validation                      │
│ ⏳ Text extraction (in progress)        │
│ ⏸️ Chunking                             │
│ ⏸️ Embedding generation                 │
│                                         │
│ Estimated time: 2 minutes               │
│                                         │
│ [Cancel Processing]                     │
│                                         │
└─────────────────────────────────────────┘
```

### Failed Documents

**Handle failures:**

1. Find failed document
2. Click to view error details
3. Follow suggested solutions
4. Retry or delete

**Error details:**
```
┌─────────────────────────────────────────┐
│ ❌ Processing Failed                    │
├─────────────────────────────────────────┤
│                                         │
│ Document: Budget Analysis.xlsx          │
│                                         │
│ Error: File size exceeds limit          │
│                                         │
│ Details:                                │
│ File size: 5.2 MB                       │
│ Maximum allowed: 5.0 MB                 │
│                                         │
│ Solutions:                              │
│ • Compress the file                     │
│ • Split into smaller files              │
│ • Contact admin for limit increase      │
│                                         │
│ [Retry] [Delete] [Contact Support]      │
│                                         │
└─────────────────────────────────────────┘
```

## Document Statistics

### View Statistics

**Access document stats:**

1. Go to knowledge base
2. Click **"Statistics"** tab
3. View document metrics

**Statistics dashboard:**
```
┌─────────────────────────────────────────┐
│ Document Statistics                     │
├─────────────────────────────────────────┤
│                                         │
│ Total Documents:     156                │
│ Total Size:          2.3 GB             │
│ Completed:           147 (94%)          │
│ Processing:          3 (2%)             │
│ Failed:              6 (4%)             │
│                                         │
│ By Type:                                │
│ • PDF:      89 (57%)                    │
│ • Word:     34 (22%)                    │
│ • Excel:    18 (12%)                    │
│ • Text:     15 (9%)                     │
│                                         │
│ By Category:                            │
│ • Documentation:  45 (29%)              │
│ • Reports:        34 (22%)              │
│ • Guides:         23 (15%)              │
│ • Other:          54 (34%)              │
│                                         │
│ Storage Usage:                          │
│ [████████████████░░░░] 2.3 GB / 10 GB   │
│                                         │
└─────────────────────────────────────────┘
```

## Best Practices

### Document Organization

**✅ Do:**
- Use descriptive titles
- Add relevant tags
- Assign categories
- Keep metadata updated
- Archive old documents
- Delete duplicates

**❌ Don't:**
- Leave default filenames
- Skip metadata
- Mix unrelated documents
- Keep failed uploads
- Forget to categorize
- Accumulate duplicates

### Document Maintenance

**✅ Do:**
- Review documents regularly
- Update outdated content
- Monitor processing status
- Clean up failed uploads
- Archive completed projects
- Backup important documents

**❌ Don't:**
- Ignore failed documents
- Keep outdated content
- Let storage fill up
- Forget to update metadata
- Skip regular cleanup

### Performance

**✅ Do:**
- Use appropriate file formats
- Compress large files
- Split very large documents
- Monitor storage usage
- Archive unused documents
- Delete unnecessary files

**❌ Don't:**
- Upload unnecessarily large files
- Keep all versions forever
- Ignore storage warnings
- Upload duplicate content

## Troubleshooting

### Cannot Edit Document

**Problem**: Edit button is disabled

**Solutions:**
1. Check if you have permission
2. Verify document is not locked
3. Check if document is processing
4. Try refreshing the page
5. Contact administrator

### Cannot Delete Document

**Problem**: Delete fails or is disabled

**Solutions:**
1. Check if you have permission
2. Verify document is not in use
3. Check if document is referenced
4. Try archiving instead
5. Contact administrator

### Document Not Searchable

**Problem**: Document doesn't appear in search

**Solutions:**
1. Check document status (must be completed)
2. Verify document is not archived
3. Check if document is in selected KB
4. Wait for indexing to complete
5. Try reprocessing document
6. Contact administrator

### Metadata Not Saving

**Problem**: Changes don't persist

**Solutions:**
1. Check internet connection
2. Verify all required fields
3. Check field validation
4. Try refreshing the page
5. Clear browser cache
6. Contact administrator

## Related Documentation

- [Uploading Documents](./uploading-documents.md) - Adding documents
- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Searching Documents](./searching.md) - Finding documents
- [Knowledge Base Concepts](../../concepts/knowledge-bases.md) - Understanding KBs

## Getting Help

If you need assistance with document management:

1. **Documentation**: Review this guide
2. **Document Help**: Click **?** icon in document interface
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
