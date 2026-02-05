# 知识库管理 API

**文件**: `backend/app/api/v1/endpoints/knowledge_bases.py`
**路径前缀**: `/api/v1/knowledge-bases`

## 概述

知识库用于存储和检索文档，支持 RAG（检索增强生成）功能。使用 Qdrant 作为向量数据库。

## 接口列表

### GET /

获取知识库列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` |
| 说明 | 获取用户可访问的知识库列表 |

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `search`: 搜索关键词
- `team_id`: 团队 ID

**响应**:
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "uuid",
        "name": "string",
        "description": "string",
        "team": {...},
        "embedding_model": {...},
        "document_count": 10,
        "chunk_count": 500,
        "created_at": "2024-01-01T00:00:00Z"
      }
    ],
    "total": 100
  }
}
```

---

### POST /

创建知识库

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:create` |
| 说明 | 创建新知识库 |

**请求体**:
```json
{
  "name": "string",
  "description": "string (可选)",
  "team_id": "uuid",
  "embedding_model_id": "uuid",
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

---

### GET /{kb_id}

获取知识库详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 获取知识库详细信息 |

**路径参数**:
- `kb_id`: 知识库 UUID

---

### PUT /{kb_id}

更新知识库

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 更新知识库配置 |

**路径参数**:
- `kb_id`: 知识库 UUID

---

### DELETE /{kb_id}

删除知识库

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:delete` + 团队成员 |
| 说明 | 删除知识库及其所有文档 |

**路径参数**:
- `kb_id`: 知识库 UUID

---

### GET /{kb_id}/stats

获取知识库统计

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 获取知识库统计信息 |

**路径参数**:
- `kb_id`: 知识库 UUID

**响应**:
```json
{
  "code": 0,
  "data": {
    "document_count": 10,
    "chunk_count": 500,
    "total_tokens": 50000,
    "storage_size": "10MB"
  }
}
```

---

## 文档管理

### GET /{kb_id}/documents

获取文档列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 获取知识库中的文档列表 |

**路径参数**:
- `kb_id`: 知识库 UUID

**查询参数**:
- `page`: 页码
- `page_size`: 每页数量
- `status`: 状态筛选

---

### POST /{kb_id}/documents

上传文档

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 上传文档到知识库 |

**路径参数**:
- `kb_id`: 知识库 UUID

**请求体**: `multipart/form-data`
- `file`: 文件

**支持格式**:
- PDF, DOCX, XLSX, PPTX
- TXT, MD, HTML
- CSV, JSON

---

### POST /{kb_id}/documents/import-url

从 URL 导入

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 从 URL 导入文档 |

**路径参数**:
- `kb_id`: 知识库 UUID

**请求体**:
```json
{
  "url": "string",
  "title": "string (可选)"
}
```

---

### GET /{kb_id}/documents/{doc_id}

获取文档详情

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 获取文档详细信息 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

---

### DELETE /{kb_id}/documents/{doc_id}

删除文档

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:delete` + 团队成员 |
| 说明 | 删除文档及其所有分块 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

---

### POST /{kb_id}/documents/{doc_id}/process

处理文档

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 对文档进行分块和向量化 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

---

### POST /{kb_id}/documents/{doc_id}/rechunk

重新分块

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 使用新参数重新分块文档 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

**请求体**:
```json
{
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

---

## 分块管理

### GET /{kb_id}/documents/{doc_id}/chunks

获取分块列表

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 获取文档的所有分块 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

---

### POST /{kb_id}/documents/{doc_id}/chunks

创建分块

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 手动创建分块 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID

**请求体**:
```json
{
  "content": "string",
  "metadata": {}
}
```

---

### PUT /{kb_id}/documents/{doc_id}/chunks/{chunk_id}

更新分块

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:update` + 团队成员 |
| 说明 | 更新分块内容 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID
- `chunk_id`: 分块 UUID

---

### DELETE /{kb_id}/documents/{doc_id}/chunks/{chunk_id}

删除分块

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:delete` + 团队成员 |
| 说明 | 删除指定分块 |

**路径参数**:
- `kb_id`: 知识库 UUID
- `doc_id`: 文档 UUID
- `chunk_id`: 分块 UUID

---

## 搜索

### POST /{kb_id}/search

搜索知识库

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 向量相似度搜索 |

**路径参数**:
- `kb_id`: 知识库 UUID

**请求体**:
```json
{
  "query": "string",
  "top_k": 5,
  "score_threshold": 0.7
}
```

**响应**:
```json
{
  "code": 0,
  "data": [
    {
      "chunk_id": "uuid",
      "content": "string",
      "score": 0.85,
      "document": {
        "id": "uuid",
        "title": "string"
      },
      "metadata": {}
    }
  ]
}
```

---

### POST /{kb_id}/documents/preview-chunks

预览分块

| 属性 | 值 |
|------|-----|
| 认证 | Bearer Token |
| 权限 | `kb:read` + 团队成员 |
| 说明 | 预览文档分块结果（不保存） |

**路径参数**:
- `kb_id`: 知识库 UUID

**请求体**:
```json
{
  "content": "string",
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

---

## 权限字符串

| 权限 | 说明 |
|------|------|
| `kb:read` | 查看知识库列表、详情、文档和分块 |
| `kb:create` | 创建新知识库 |
| `kb:update` | 更新知识库、上传文档、处理文档 |
| `kb:delete` | 删除知识库、文档和分块 |

---

## 文档状态

| 状态 | 说明 |
|------|------|
| `PENDING` | 待处理 |
| `PROCESSING` | 处理中 |
| `COMPLETED` | 已完成 |
| `FAILED` | 处理失败 |
