# Document Metadata

This guide explains how to configure and use document metadata in knowledge bases.

## Overview

Metadata provides additional information about documents, enabling better organization, filtering, and retrieval. Proper metadata configuration improves search accuracy and document management.

## What is Metadata?

Metadata is structured information about documents:

- **Descriptive**: Title, author, description
- **Administrative**: Created date, modified date, version
- **Technical**: File type, size, encoding
- **Custom**: Department, category, tags, status

## Default Metadata Fields

### System Fields

Automatically extracted by Clouisle:

**File Information:**
- `filename`: Original file name
- `file_type`: File extension (pdf, docx, etc.)
- `file_size`: File size in bytes
- `mime_type`: MIME type

**Timestamps:**
- `created_at`: Upload timestamp
- `updated_at`: Last modification timestamp
- `processed_at`: Processing completion timestamp

**Processing:**
- `status`: processing, completed, failed
- `chunk_count`: Number of chunks generated
- `token_count`: Total tokens

**Source:**
- `source_url`: Original URL (if uploaded from URL)
- `source_type`: upload, url, api

### Extracted Fields

Automatically extracted from documents:

**Document Properties:**
- `title`: Document title
- `author`: Document author
- `subject`: Document subject
- `keywords`: Document keywords
- `created_date`: Document creation date (from file)
- `modified_date`: Document modification date (from file)

**Content:**
- `language`: Detected language
- `page_count`: Number of pages (PDF)
- `word_count`: Approximate word count

## Custom Metadata Fields

### Creating Custom Fields

1. Go to **Knowledge Base** → **Settings** → **Metadata**
2. Click **Add Custom Field**
3. Configure field properties

**Field Configuration:**

```yaml
Field Name: department
Display Name: Department
Type: select
Required: false
Options:
  - Engineering
  - Sales
  - Marketing
  - Support
Default: Engineering
```

### Field Types

**Text:**
- Single-line text input
- Use for: Names, IDs, short descriptions
- Max length: 500 characters

**Textarea:**
- Multi-line text input
- Use for: Descriptions, notes
- Max length: 5000 characters

**Number:**
- Numeric input
- Use for: Version numbers, scores
- Range: -999999 to 999999

**Date:**
- Date picker
- Use for: Dates, deadlines
- Format: YYYY-MM-DD

**Select:**
- Dropdown selection
- Use for: Categories, status
- Options: Define list of values

**Multi-select:**
- Multiple selection
- Use for: Tags, categories
- Options: Define list of values

**Boolean:**
- Checkbox
- Use for: Flags, toggles
- Values: true/false

**URL:**
- URL input with validation
- Use for: Links, references
- Validation: Must be valid URL

### Field Examples

**Department Field:**
```yaml
Name: department
Type: select
Options:
  - Engineering
  - Sales
  - Marketing
  - Support
  - HR
Required: true
```

**Version Field:**
```yaml
Name: version
Type: text
Pattern: ^\d+\.\d+\.\d+$
Placeholder: "1.0.0"
Required: false
```

**Tags Field:**
```yaml
Name: tags
Type: multi-select
Options:
  - documentation
  - tutorial
  - reference
  - guide
  - api
Required: false
```

**Status Field:**
```yaml
Name: status
Type: select
Options:
  - draft
  - review
  - approved
  - published
  - archived
Default: draft
Required: true
```

**Security Level:**
```yaml
Name: security_level
Type: select
Options:
  - public
  - internal
  - confidential
  - restricted
Default: internal
Required: true
```

## Setting Metadata

### During Upload

**Web Interface:**
1. Click **Upload Document**
2. Select file
3. Fill metadata form
4. Click **Upload**

**Metadata Form:**
```
Title: Product Manual v2.0
Department: Engineering
Category: Documentation
Tags: manual, product, v2
Status: published
Security Level: internal
```

### Via API

**Upload with Metadata:**
```python
import requests

# Upload document with metadata
with open('document.pdf', 'rb') as f:
    files = {'file': f}
    data = {
        'metadata': json.dumps({
            'title': 'Product Manual v2.0',
            'department': 'Engineering',
            'category': 'Documentation',
            'tags': ['manual', 'product', 'v2'],
            'status': 'published',
            'security_level': 'internal'
        })
    }

    response = requests.post(
        f'{API_BASE_URL}/api/v1/kb/{kb_id}/documents/upload',
        headers={'Authorization': f'Bearer {TOKEN}'},
        files=files,
        data=data
    )
```

**JavaScript:**
```javascript
const formData = new FormData();
formData.append('file', fileBlob);
formData.append('metadata', JSON.stringify({
  title: 'Product Manual v2.0',
  department: 'Engineering',
  category: 'Documentation',
  tags: ['manual', 'product', 'v2'],
  status: 'published',
  security_level: 'internal'
}));

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
```

### Bulk Update

**Update Multiple Documents:**
```python
# Update metadata for multiple documents
document_ids = ['doc-1', 'doc-2', 'doc-3']

for doc_id in document_ids:
    response = requests.patch(
        f'{API_BASE_URL}/api/v1/kb/{kb_id}/documents/{doc_id}',
        headers={'Authorization': f'Bearer {TOKEN}'},
        json={
            'metadata': {
                'status': 'published',
                'reviewed_by': 'john@example.com',
                'reviewed_at': '2026-02-11'
            }
        }
    )
```

## Using Metadata

### Filtering Documents

**By Single Field:**
```python
# Get documents by department
documents = api.get(f'/api/v1/kb/{kb_id}/documents', params={
    'metadata.department': 'Engineering'
})
```

**By Multiple Fields:**
```python
# Get published engineering documents
documents = api.get(f'/api/v1/kb/{kb_id}/documents', params={
    'metadata.department': 'Engineering',
    'metadata.status': 'published'
})
```

**By Tags:**
```python
# Get documents with specific tags
documents = api.get(f'/api/v1/kb/{kb_id}/documents', params={
    'metadata.tags': 'manual,tutorial'  # OR condition
})
```

### Search with Metadata

**Filter Search Results:**
```python
# Search within specific department
results = api.post(f'/api/v1/kb/{kb_id}/search', json={
    'query': 'How to reset password?',
    'filters': {
        'metadata.department': 'Support',
        'metadata.status': 'published'
    },
    'top_k': 5
})
```

**Boost by Metadata:**
```python
# Boost recent documents
results = api.post(f'/api/v1/kb/{kb_id}/search', json={
    'query': 'API documentation',
    'boost': {
        'metadata.created_at': {
            'type': 'date',
            'decay': 0.5,
            'scale': '30d'
        }
    }
})
```

### RAG with Metadata

**Filter Retrieved Context:**
```python
# Agent retrieves only from specific category
message = api.post(f'/api/v1/conversations/{conv_id}/messages', json={
    'content': 'How do I configure SSO?',
    'rag_config': {
        'filters': {
            'metadata.category': 'Configuration',
            'metadata.security_level': ['internal', 'public']
        }
    }
})
```

## Metadata Templates

### Creating Templates

**Template Definition:**
```yaml
Template Name: Technical Documentation
Description: Standard metadata for technical docs
Fields:
  - name: title
    type: text
    required: true
  - name: version
    type: text
    required: true
    pattern: ^\d+\.\d+\.\d+$
  - name: author
    type: text
    required: true
  - name: department
    type: select
    required: true
    options: [Engineering, Product]
  - name: category
    type: select
    required: true
    options: [API, Guide, Reference, Tutorial]
  - name: tags
    type: multi-select
    required: false
    options: [api, sdk, integration, security]
  - name: status
    type: select
    required: true
    default: draft
    options: [draft, review, published]
```

### Using Templates

**Apply Template on Upload:**
1. Select **Template**: Technical Documentation
2. Form auto-populates with template fields
3. Fill required fields
4. Upload document

**API with Template:**
```python
# Upload with template
response = api.post(f'/api/v1/kb/{kb_id}/documents/upload',
    files={'file': file},
    data={
        'template': 'technical-documentation',
        'metadata': json.dumps({
            'title': 'API Reference',
            'version': '2.0.0',
            'author': 'John Doe',
            'department': 'Engineering',
            'category': 'API',
            'tags': ['api', 'reference'],
            'status': 'published'
        })
    }
)
```

## Metadata Validation

### Validation Rules

**Required Fields:**
```yaml
Field: department
Required: true
Error: "Department is required"
```

**Pattern Validation:**
```yaml
Field: version
Pattern: ^\d+\.\d+\.\d+$
Error: "Version must be in format X.Y.Z"
```

**Range Validation:**
```yaml
Field: priority
Type: number
Min: 1
Max: 5
Error: "Priority must be between 1 and 5"
```

**Custom Validation:**
```python
def validate_metadata(metadata):
    """Custom metadata validation."""
    errors = []

    # Check required fields
    if not metadata.get('title'):
        errors.append('Title is required')

    # Validate version format
    version = metadata.get('version', '')
    if version and not re.match(r'^\d+\.\d+\.\d+$', version):
        errors.append('Invalid version format')

    # Validate security level
    valid_levels = ['public', 'internal', 'confidential', 'restricted']
    if metadata.get('security_level') not in valid_levels:
        errors.append(f'Security level must be one of: {valid_levels}')

    return errors

# Usage
errors = validate_metadata(metadata)
if errors:
    print(f"Validation errors: {errors}")
```

## Metadata Best Practices

### Naming Conventions

**✅ Do:**
- Use lowercase with underscores: `security_level`
- Be descriptive: `document_category` not `cat`
- Use consistent naming across fields
- Avoid special characters
- Keep names short but clear

**❌ Don't:**
- Use spaces: `security level`
- Use camelCase: `securityLevel`
- Use abbreviations: `sec_lvl`
- Use special characters: `security-level`
- Use very long names

### Field Design

**✅ Do:**
- Define clear field purposes
- Use appropriate field types
- Set sensible defaults
- Make critical fields required
- Provide helpful descriptions
- Limit select options (< 20)
- Use multi-select for tags

**❌ Don't:**
- Create redundant fields
- Use wrong field types
- Skip default values
- Make everything required
- Skip field descriptions
- Create too many options
- Use select for tags

### Organization

**✅ Do:**
- Group related fields
- Use consistent categories
- Create reusable templates
- Document metadata schema
- Review and update regularly
- Train users on metadata

**❌ Don't:**
- Mix unrelated fields
- Use inconsistent categories
- Create one-off fields
- Skip documentation
- Let schema become stale
- Assume users know metadata

## Advanced Features

### Computed Fields

**Auto-calculate values:**
```python
# Compute field based on other metadata
def compute_priority(metadata):
    """Compute priority based on security and status."""
    security = metadata.get('security_level')
    status = metadata.get('status')

    if security == 'restricted' and status == 'published':
        return 'high'
    elif security == 'confidential':
        return 'medium'
    else:
        return 'low'

# Apply computed field
metadata['priority'] = compute_priority(metadata)
```

### Metadata Inheritance

**Inherit from parent:**
```python
# Child documents inherit parent metadata
parent_metadata = {
    'department': 'Engineering',
    'project': 'Product X',
    'security_level': 'internal'
}

child_metadata = {
    **parent_metadata,  # Inherit parent metadata
    'title': 'Chapter 1',
    'page_range': '1-10'
}
```

### Metadata Versioning

**Track metadata changes:**
```python
# Store metadata history
metadata_history = [
    {
        'version': 1,
        'timestamp': '2026-01-01T00:00:00Z',
        'metadata': {'status': 'draft'},
        'changed_by': 'user-123'
    },
    {
        'version': 2,
        'timestamp': '2026-02-01T00:00:00Z',
        'metadata': {'status': 'published'},
        'changed_by': 'user-456'
    }
]
```

## Troubleshooting

### Metadata Not Showing

**Problem:** Custom metadata fields not visible

**Solutions:**
1. Check field is enabled
2. Verify user permissions
3. Refresh page
4. Check field visibility settings
5. Review field configuration

### Validation Errors

**Problem:** Metadata validation fails

**Solutions:**
1. Check required fields
2. Verify field formats
3. Review validation rules
4. Check field types
5. Test with valid data

### Search Not Filtering

**Problem:** Metadata filters not working

**Solutions:**
1. Check filter syntax
2. Verify field names
3. Check field indexing
4. Review filter values
5. Test with simple filters

## Related Documentation

- [Knowledge Base Settings](./kb-settings.md) - KB configuration
- [Document Upload](./document-upload.md) - Upload documents
- [Search Configuration](./search-configuration.md) - Search setup
- [KB Management](../../admin-guide/knowledge-base/kb-management.md) - Admin guide

---

**Last Updated**: 2026-02-11
