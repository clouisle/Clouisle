# Searching Documents

This guide explains how to search for documents and information in knowledge bases.

## Overview

Clouisle provides powerful search capabilities:

- **Vector Search**: Semantic similarity search using embeddings
- **Keyword Search**: Traditional full-text search
- **Hybrid Search**: Combines vector and keyword search
- **Filters**: Narrow results by metadata
- **Advanced Queries**: Complex search expressions

## Accessing Search

### From Knowledge Base

**Steps:**

1. Navigate to **Knowledge Bases** section
2. Click on a knowledge base to open it
3. Use the search bar at the top
4. Enter your search query
5. View results

**Search bar:**
```
┌─────────────────────────────────────────────────────┐
│ 🔍 Search documents...                    [Filters] │
└─────────────────────────────────────────────────────┘
```

### Global Search

**Search across all knowledge bases:**

1. Click the **search icon** in navigation bar
2. Or press **Ctrl+K** (Windows/Linux) or **Cmd+K** (Mac)
3. Enter search query
4. Select knowledge base (or search all)
5. View results

## Search Modes

### Vector Search (Semantic)

**What it does:**
- Finds documents by meaning, not just keywords
- Understands context and intent
- Returns semantically similar content

**Best for:**
- Natural language queries
- Conceptual searches
- Finding related content

**Example queries:**
```
"How do I reset my password?"
→ Finds password reset documentation

"troubleshooting login issues"
→ Finds login help, authentication errors, etc.

"sales performance last quarter"
→ Finds Q3 sales reports, analytics, etc.
```

**How to use:**

1. Enter natural language query
2. Select **"Semantic"** search mode (default)
3. Press **Enter** or click **Search**
4. View results ranked by relevance

### Keyword Search (Full-Text)

**What it does:**
- Finds exact keyword matches
- Supports boolean operators
- Fast and precise

**Best for:**
- Exact phrase matching
- Technical terms
- Specific keywords

**Example queries:**
```
"API key"
→ Finds documents containing "API key"

"error code 404"
→ Finds documents with "error code 404"

"invoice AND payment"
→ Finds documents with both terms
```

**How to use:**

1. Enter keywords
2. Select **"Keyword"** search mode
3. Press **Enter**
4. View results

**Boolean operators:**
- `AND`: Both terms must appear
- `OR`: Either term must appear
- `NOT`: Exclude term
- `"phrase"`: Exact phrase match

**Examples:**
```
sales AND report
→ Documents with both "sales" and "report"

python OR javascript
→ Documents with either language

security NOT password
→ Documents about security but not passwords

"customer support"
→ Exact phrase "customer support"
```

### Hybrid Search

**What it does:**
- Combines vector and keyword search
- Best of both worlds
- Balances semantic understanding with keyword precision

**Best for:**
- General searches
- When you're not sure which mode to use
- Maximum recall

**How to use:**

1. Enter query
2. Select **"Hybrid"** search mode
3. Press **Enter**
4. Results combine both methods

**Example:**
```
Query: "API authentication errors"

Hybrid search finds:
• Documents about API authentication (semantic)
• Documents with exact phrase "authentication errors" (keyword)
• Related documents about API security (semantic)
```

## Search Interface

### Search Results

**Results view:**
```
┌─────────────────────────────────────────────────────┐
│ 🔍 "password reset"              [Semantic ▼] [⚙️]  │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Found 15 results in 0.23s                          │
│                                                     │
│ 📄 Password Management Guide                        │
│    ...instructions for resetting your password...  │
│    Score: 0.95 • Updated: 2026-02-10               │
│    [View] [Copy Link]                              │
│                                                     │
│ 📄 User Authentication                              │
│    ...password reset process and security...       │
│    Score: 0.89 • Updated: 2026-02-08               │
│    [View] [Copy Link]                              │
│                                                     │
│ 📄 Account Security                                 │
│    ...reset password if you forgot it...           │
│    Score: 0.85 • Updated: 2026-02-05               │
│    [View] [Copy Link]                              │
│                                                     │
│ [Load More Results]                                │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Result Information

Each result shows:

| Field | Description |
|-------|-------------|
| **Title** | Document title |
| **Snippet** | Relevant excerpt with query highlighted |
| **Score** | Relevance score (0.0-1.0) |
| **Updated** | Last update date |
| **Source** | Document source/category |
| **Actions** | View, Copy Link, etc. |

### Relevance Score

**Score interpretation:**
- **0.9-1.0**: Highly relevant
- **0.7-0.9**: Very relevant
- **0.5-0.7**: Moderately relevant
- **0.3-0.5**: Somewhat relevant
- **<0.3**: Low relevance

**Note**: Scores below 0.5 are typically not shown.

## Filters

### Applying Filters

**Steps:**

1. Enter search query
2. Click **"Filters"** button
3. Select filter criteria
4. Click **"Apply"**
5. Results update automatically

**Filter panel:**
```
┌─────────────────────────────────────────┐
│ Filters                                 │
├─────────────────────────────────────────┤
│                                         │
│ Document Type:                          │
│ ☑ PDF                                   │
│ ☑ Word                                  │
│ ☐ Excel                                 │
│ ☐ Text                                  │
│                                         │
│ Date Range:                             │
│ ○ Any time                              │
│ ○ Last 7 days                           │
│ ● Last 30 days                          │
│ ○ Last year                             │
│ ○ Custom: [____] to [____]             │
│                                         │
│ Category:                               │
│ ☑ Documentation                         │
│ ☑ Reports                               │
│ ☐ Policies                              │
│                                         │
│ Language:                               │
│ ● English                               │
│ ○ Chinese                               │
│ ○ All                                   │
│                                         │
│ Tags:                                   │
│ [sales] [q3] [2026] [+ Add]            │
│                                         │
│ [Clear All]  [Apply]                    │
│                                         │
└─────────────────────────────────────────┘
```

### Available Filters

| Filter | Options |
|--------|---------|
| **Document Type** | PDF, Word, Excel, Text, etc. |
| **Date Range** | Last 7 days, 30 days, year, custom |
| **Category** | Documentation, Reports, Policies, etc. |
| **Language** | English, Chinese, etc. |
| **Tags** | Custom tags |
| **Author** | Document creator |
| **Size** | File size range |
| **Status** | Published, Draft, Archived |

### Filter Combinations

**Multiple filters:**
- Filters are combined with AND logic
- All selected criteria must match
- More filters = fewer results

**Example:**
```
Filters:
• Type: PDF
• Date: Last 30 days
• Category: Reports
• Tag: sales

→ Shows only PDF reports about sales from last 30 days
```

## Advanced Search

### Search Operators

**Supported operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `AND` | Both terms | `sales AND report` |
| `OR` | Either term | `python OR javascript` |
| `NOT` | Exclude term | `security NOT password` |
| `"phrase"` | Exact phrase | `"customer support"` |
| `*` | Wildcard | `auth*` (auth, authentication, etc.) |
| `field:value` | Field search | `title:API` |

**Examples:**

```
title:"API Documentation" AND category:technical
→ API docs in technical category

(python OR javascript) AND tutorial
→ Tutorials for either language

author:john AND date:2026
→ John's documents from 2026

"error code" NOT 404
→ Error codes except 404
```

### Field Search

**Search specific fields:**

| Field | Description | Example |
|-------|-------------|---------|
| `title:` | Document title | `title:API` |
| `content:` | Document content | `content:authentication` |
| `author:` | Document author | `author:john` |
| `category:` | Category | `category:reports` |
| `tag:` | Tag | `tag:sales` |
| `date:` | Date | `date:2026` |

**Examples:**
```
title:password AND content:reset
→ Documents with "password" in title and "reset" in content

author:alice OR author:bob
→ Documents by Alice or Bob

tag:urgent AND date:2026-02
→ Urgent documents from February 2026
```

### Proximity Search

**Find terms near each other:**

```
"API authentication"~5
→ "API" and "authentication" within 5 words

"sales report"~10
→ "sales" and "report" within 10 words
```

### Fuzzy Search

**Find similar terms:**

```
authentication~
→ Finds authentication, authentification, etc.

pasword~2
→ Finds password (allows 2 character differences)
```

## Search Tips

### Writing Effective Queries

**✅ Do:**
- Use natural language for semantic search
- Be specific but not too narrow
- Use multiple keywords
- Try different phrasings
- Use filters to narrow results

**❌ Don't:**
- Use single generic words
- Use too many keywords
- Expect exact matches only
- Ignore filters
- Give up after first try

**Examples:**

**Good queries:**
```
"How to configure SSO authentication"
"Q3 2026 sales performance analysis"
"Troubleshooting API connection errors"
"Python data processing tutorial"
```

**Poor queries:**
```
"help" (too generic)
"how to configure single sign on authentication with oauth2 and saml" (too long)
"api" (too broad)
```

### Refining Results

**If too many results:**
1. Add more specific keywords
2. Use filters
3. Use exact phrases with quotes
4. Narrow date range
5. Select specific categories

**If too few results:**
1. Use fewer keywords
2. Remove filters
3. Try synonyms
4. Use OR operator
5. Check spelling

**If no results:**
1. Check spelling
2. Try different keywords
3. Use broader terms
4. Remove all filters
5. Try semantic search mode

## Search History

### Viewing History

**Recent searches:**

1. Click search bar
2. View recent searches dropdown
3. Click on a previous search to repeat

**Search history:**
```
┌─────────────────────────────────────────┐
│ Recent Searches                         │
├─────────────────────────────────────────┤
│                                         │
│ 🕐 password reset                       │
│    2 hours ago • 15 results             │
│                                         │
│ 🕐 API authentication                   │
│    Yesterday • 8 results                │
│                                         │
│ 🕐 sales report Q3                      │
│    3 days ago • 23 results              │
│                                         │
│ [Clear History]                         │
│                                         │
└─────────────────────────────────────────┘
```

### Saved Searches

**Save frequent searches:**

1. Perform a search
2. Click **"Save Search"** button
3. Enter name for saved search
4. Click **"Save"**

**Using saved searches:**

1. Click **"Saved Searches"** dropdown
2. Select a saved search
3. Search is executed with saved parameters

## Search Results Actions

### Viewing Documents

**Open document:**

1. Click **"View"** on search result
2. Document opens in viewer
3. Search terms are highlighted
4. Navigate to relevant sections

**Document viewer:**
```
┌─────────────────────────────────────────┐
│ Password Management Guide        [✕]    │
├─────────────────────────────────────────┤
│                                         │
│ # Password Management                   │
│                                         │
│ This guide explains how to reset your   │
│ password if you forgot it.              │
│                                         │
│ ## Resetting Your Password              │
│                                         │
│ 1. Go to login page                     │
│ 2. Click "Forgot Password?"             │
│ 3. Enter your email                     │
│ ...                                     │
│                                         │
│ [Download] [Share] [Close]              │
│                                         │
└─────────────────────────────────────────┘
```

### Copying Links

**Share search results:**

1. Click **"Copy Link"** on result
2. Link is copied to clipboard
3. Share link with team members

**Link format:**
```
https://your-domain.com/kb/kb-123/documents/doc-456
```

### Exporting Results

**Export search results:**

1. Perform search
2. Click **"Export"** button
3. Select format:
   - CSV: Spreadsheet
   - JSON: Structured data
   - PDF: Formatted document
4. Click **"Download"**

**CSV export:**
```csv
Title,Score,Updated,Category,URL
"Password Management",0.95,"2026-02-10","Documentation","https://..."
"User Authentication",0.89,"2026-02-08","Documentation","https://..."
```

## Search Performance

### Optimization Tips

**For faster searches:**
- Use specific keywords
- Apply filters early
- Limit date range
- Use keyword search for exact matches
- Avoid wildcards at start of term

**For better results:**
- Use semantic search for concepts
- Try multiple phrasings
- Use filters to narrow scope
- Check spelling
- Use synonyms

## Troubleshooting

### No Results Found

**Problem**: Search returns no results

**Solutions:**
1. Check spelling
2. Try different keywords
3. Remove filters
4. Use broader terms
5. Try semantic search mode
6. Check if documents exist in KB

### Irrelevant Results

**Problem**: Results don't match query

**Solutions:**
1. Use more specific keywords
2. Use exact phrases with quotes
3. Apply filters
4. Try keyword search mode
5. Use field search
6. Add more context to query

### Slow Search

**Problem**: Search takes too long

**Solutions:**
1. Use filters to narrow scope
2. Try keyword search (faster)
3. Limit date range
4. Check internet connection
5. Contact administrator

### Results Not Updated

**Problem**: New documents don't appear in search

**Solutions:**
1. Wait for indexing to complete
2. Refresh the page
3. Check document status (must be published)
4. Verify document is in selected KB
5. Contact administrator

## Best Practices

### Search Strategy

**✅ Do:**
- Start with broad search, then narrow
- Use semantic search for concepts
- Use keyword search for exact terms
- Apply filters progressively
- Save frequent searches
- Review search history

**❌ Don't:**
- Use too many keywords at once
- Ignore filters
- Give up after first try
- Use only single words
- Forget to check spelling

### Performance

**✅ Do:**
- Use specific queries
- Apply filters early
- Limit date range
- Use appropriate search mode
- Cache frequent searches

**❌ Don't:**
- Search entire KB unnecessarily
- Use wildcards excessively
- Ignore search mode
- Search without filters

## Related Documentation

- [Browsing Knowledge Bases](./browsing-kb.md) - Viewing documents
- [Uploading Documents](./uploading-documents.md) - Adding documents
- [Document Management](./document-management.md) - Managing documents
- [Knowledge Base Concepts](../../concepts/knowledge-bases.md) - Understanding KBs

## Getting Help

If you need assistance with searching:

1. **Documentation**: Review this guide
2. **Search Help**: Click **?** icon in search interface
3. **Support**: Contact your organization's support team
4. **Administrator**: Reach out to your Clouisle administrator

---

**Last Updated**: 2026-02-11
