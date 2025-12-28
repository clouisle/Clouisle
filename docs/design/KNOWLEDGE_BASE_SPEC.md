# Clouisle 知识库规范

## 1. 概述

本文档定义了 Clouisle 项目中知识库（Knowledge Base）功能的设计规范，用于实现 RAG（Retrieval-Augmented Generation）能力。

### 1.1 设计目标

- **团队隔离**：知识库归属于团队，实现数据隔离
- **格式丰富**：支持多种文档格式
- **智能处理**：自动文本提取、分块和向量化
- **高效检索**：基于向量的语义搜索

### 1.2 技术选型

| 功能 | 技术方案 | 说明 |
|------|----------|------|
| 文档解析 | MarkItDown | 微软开源，统一转换为 Markdown |
| 文本分块 | 自研 TextChunker | 语义感知分块 |
| 向量存储 | pgvector | PostgreSQL 扩展 |
| 向量生成 | LangChain Embeddings | 复用 LLM 模块 |
| 异步处理 | Celery | 大文档异步处理 |

---

## 2. 支持的文档格式

### 2.1 MarkItDown 处理的格式

| 格式 | 扩展名 | MIME Type | 说明 |
|------|--------|-----------|------|
| PDF | `.pdf` | `application/pdf` | 需要 `markitdown[pdf]` |
| Word | `.docx`, `.doc` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | 内置支持 |
| PowerPoint | `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | 内置支持 |
| Excel | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | 需要 `markitdown[xlsx]` |
| Excel (旧版) | `.xls` | `application/vnd.ms-excel` | 需要 `markitdown[xls]` |
| HTML | `.html`, `.htm` | `text/html` | 内置支持 |
| URL | - | - | 支持网页和 YouTube |

### 2.2 标准库处理的格式

| 格式 | 扩展名 | MIME Type | 说明 |
|------|--------|-----------|------|
| 纯文本 | `.txt` | `text/plain` | 直接读取 |
| Markdown | `.md`, `.markdown` | `text/markdown` | 直接读取 |
| CSV | `.csv` | `text/csv` | Python csv 模块 |
| JSON | `.json` | `application/json` | Python json 模块 |

### 2.3 MarkItDown 可选依赖

```bash
# 安装所有可选依赖
pip install 'markitdown[all]'

# 或按需安装
pip install 'markitdown[pdf]'       # PDF 支持
pip install 'markitdown[docx]'      # Word 支持 (可选增强)
pip install 'markitdown[pptx]'      # PowerPoint 支持 (可选增强)
pip install 'markitdown[xlsx]'      # Excel 支持
pip install 'markitdown[xls]'       # 旧版 Excel 支持
pip install 'markitdown[outlook]'   # Outlook 邮件
pip install 'markitdown[audio-transcription]'    # 音频转录
pip install 'markitdown[youtube-transcription]'  # YouTube 字幕
```

---

## 3. 数据模型

### 3.1 知识库 (KnowledgeBase)

```python
class KnowledgeBase(Model):
    id: UUID
    team_id: UUID              # 所属团队
    name: str                  # 知识库名称
    description: str           # 描述
    embedding_model_id: UUID   # 使用的向量模型
    chunk_size: int = 500      # 分块大小 (tokens)
    chunk_overlap: int = 50    # 分块重叠
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
```

### 3.2 文档 (Document)

```python
class DocumentStatus(str, Enum):
    PENDING = "pending"        # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 完成
    FAILED = "failed"          # 失败

class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    TXT = "txt"
    MD = "md"
    HTML = "html"
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    JSON = "json"
    URL = "url"

class Document(Model):
    id: UUID
    knowledge_base_id: UUID
    name: str                  # 文档名称
    file_path: str             # 存储路径
    file_size: int             # 文件大小
    doc_type: DocumentType
    status: DocumentStatus
    chunk_count: int = 0       # 分块数量
    error_message: str         # 错误信息
    metadata: dict             # 元数据
    created_at: datetime
    updated_at: datetime
```

### 3.3 文档分块 (DocumentChunk)

```python
class DocumentChunk(Model):
    id: UUID
    document_id: UUID
    content: str               # 文本内容
    chunk_index: int           # 分块序号
    token_count: int           # Token 数量
    embedding: list[float]     # 向量 (pgvector)
    metadata: dict             # 元数据
    created_at: datetime
```

---

## 4. API 接口

### 4.1 知识库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/knowledge-bases` | 列表 |
| POST | `/api/v1/knowledge-bases` | 创建 |
| GET | `/api/v1/knowledge-bases/{id}` | 详情 |
| PUT | `/api/v1/knowledge-bases/{id}` | 更新 |
| DELETE | `/api/v1/knowledge-bases/{id}` | 删除 |
| GET | `/api/v1/knowledge-bases/{id}/stats` | 统计 |
| POST | `/api/v1/knowledge-bases/{id}/search` | 搜索 |

### 4.2 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/knowledge-bases/{kb_id}/documents` | 文档列表 |
| POST | `/api/v1/knowledge-bases/{kb_id}/documents/upload` | 上传文档 |
| POST | `/api/v1/knowledge-bases/{kb_id}/documents/url` | 导入 URL |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents/{id}` | 文档详情 |
| DELETE | `/api/v1/knowledge-bases/{kb_id}/documents/{id}` | 删除文档 |
| POST | `/api/v1/knowledge-bases/{kb_id}/documents/{id}/reprocess` | 重新处理 |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents/{id}/chunks` | 查看分块 |

---

## 5. 处理流程

### 5.1 文档上传流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   上传文件   │────▶│   保存文件   │────▶│  创建记录   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   完成入库   │◀────│  生成向量   │◀────│  文本分块   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               ▲
                                               │
                                        ┌─────────────┐
                                        │  提取文本   │
                                        │ (MarkItDown)│
                                        └─────────────┘
```

### 5.2 文本提取

```python
# MarkItDown 统一处理
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert(file_path)  # 或 URL

text = result.text_content      # Markdown 格式文本
title = result.title            # 标题 (如有)
```

### 5.3 文本分块

```python
# 语义感知分块
chunker = TextChunker(
    chunk_size=500,      # tokens
    chunk_overlap=50,    # overlap tokens
)

chunks = chunker.chunk_text(text)
# [
#     {"content": "...", "chunk_index": 0, "token_count": 480},
#     {"content": "...", "chunk_index": 1, "token_count": 495},
#     ...
# ]
```

### 5.4 向量生成与存储

```python
from app.llm import model_manager

# 生成向量
embeddings = await model_manager.embed(
    texts=[chunk["content"] for chunk in chunks],
    model_id=kb.embedding_model_id,
)

# 存储到 pgvector
for chunk, embedding in zip(chunks, embeddings):
    await DocumentChunk.create(
        document_id=doc.id,
        content=chunk["content"],
        chunk_index=chunk["chunk_index"],
        token_count=chunk["token_count"],
        embedding=embedding,
    )
```

---

## 6. 搜索功能

### 6.1 语义搜索

```python
async def search(
    kb_id: UUID,
    query: str,
    top_k: int = 10,
    threshold: float = 0.7,
) -> list[SearchResult]:
    # 1. 生成查询向量
    query_embedding = await model_manager.embed([query])
    
    # 2. 向量检索 (pgvector)
    results = await DocumentChunk.filter(
        document__knowledge_base_id=kb_id
    ).annotate(
        similarity=CosineDistance("embedding", query_embedding[0])
    ).filter(
        similarity__gte=threshold
    ).order_by(
        "-similarity"
    ).limit(top_k)
    
    return results
```

### 6.2 混合搜索 (规划中)

- 向量搜索 + 关键词搜索
- BM25 + Cosine Similarity
- Reciprocal Rank Fusion (RRF)

---

## 7. 文件结构

```
backend/app/
├── models/
│   └── knowledge_base.py      # 数据模型
├── schemas/
│   └── knowledge_base.py      # Pydantic schemas
├── api/v1/endpoints/
│   └── knowledge_bases.py     # API 端点
├── services/
│   ├── document_processor.py  # 文档处理 + 分块
│   └── vector_store.py        # 向量存储服务
└── tasks/
    └── knowledge_base.py      # Celery 异步任务
```

---

## 8. 依赖配置

```toml
# pyproject.toml
[project]
dependencies = [
    # Document processing
    "markitdown[pdf,xlsx,xls]>=0.0.1a3",
]
```

---

## 9. 实现状态

| 功能 | 状态 | 实现细节 |
|------|------|----------|
| 数据模型 | ✅ 完成 | KnowledgeBase, Document, DocumentChunk |
| API 端点 | ✅ 完成 | 完整 CRUD + 搜索 + 下载 |
| 文档上传 | ✅ 完成 | 多格式支持，存储路径 `uploads/documents/{kb_id}/{YYYY}/{MM}/` |
| URL 导入 | ✅ 完成 | MarkItDown 抓取网页内容 |
| 文本提取 (MarkItDown) | ✅ 完成 | PDF, DOCX, HTML, XLSX 等 |
| 文本分块 | ✅ 完成 | 支持 chunk_size, chunk_overlap, separator 配置 |
| Celery 异步任务 | ✅ 完成 | 后台处理大文档 |
| 向量生成 | ✅ 完成 | 通过 embedding_model 配置 |
| pgvector 存储 | ✅ 完成 | 动态维度列支持 (embedding_768, embedding_1536 等) |
| 语义搜索 | ✅ 完成 | pgvector 余弦距离搜索 |
| 混合搜索 | ✅ 完成 | RRF 融合算法 (向量 + jieba 全文) |
| 动态维度支持 | ✅ 完成 | 按需创建维度列，KB 级别维度绑定 |
| 文档下载 | ✅ 完成 | Authorization Bearer Token 鉴权 |
| 前端 UI (后台) | ✅ 完成 | 完整的知识库管理界面 |
| 前端 UI (中台) | ✅ 完成 | 平台级知识库管理 |
| 搜索测试页面 | ✅ 完成 | 圆角胶囊式搜索栏，Popover 高级设置 |

---

## 10. 实现细节

### 10.1 文档列表 Schema

`DocumentList` schema 返回以下字段用于前端展示：

```python
class DocumentList(BaseModel):
    id: UUID
    name: str
    doc_type: str
    file_path: Optional[str] = None      # 文件存储路径，用于下载
    file_size: Optional[int] = None
    source_url: Optional[str] = None     # URL 类型文档的源链接
    status: str
    error_message: Optional[str] = None  # 处理失败时的错误信息
    chunk_count: int
    token_count: int
    created_at: datetime
```

### 10.2 文档下载 API

```
GET /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/download
Authorization: Bearer <token>
```

实现要点：
- 需要 Bearer Token 鉴权
- 返回原始上传文件
- 前端使用 `fetch` + `blob` + `createObjectURL` 触发下载

```typescript
// frontend/lib/api/knowledge-bases.ts
downloadDocument: async (kbId: string, docId: string, filename: string) => {
  const token = localStorage.getItem('access_token')
  const response = await fetch(url, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  const blob = await response.blob()
  // 创建临时下载链接
  const link = document.createElement('a')
  link.href = window.URL.createObjectURL(blob)
  link.download = filename
  link.click()
}
```

### 10.3 搜索测试 UI

搜索测试页面采用现代 AI 聊天应用风格：

**布局结构**：
```
┌────────────────────────────────┐
│  ← 命中测试                    │  页头 (无分割线)
│    知识库名称                  │
├────────────────────────────────┤
│                                │
│       搜索结果区域             │  flex-1 可滚动
│       (可折叠卡片)             │
│                                │
├────────────────────────────────┤
│ ╭──────────────────────────╮   │  底部搜索栏 (sticky)
│ │ 🔍 输入搜索内容...  ⚙️ ➤ │   │  圆角胶囊样式
│ ╰──────────────────────────╯   │
└────────────────────────────────┘
```

**高级设置 Popover**：
- 检索方式: 混合检索 / 向量检索 / 全文检索 (ToggleGroup)
- 最大结果数: 1-20 (number input)
- 相似度阈值: 0-1 (text input with decimal support)

**关键实现**：
```tsx
// 中文 IME 组合状态检测，避免回车误触发
const handleKeyDown = (e: React.KeyboardEvent) => {
  if (e.nativeEvent.isComposing) return
  if (e.key === 'Enter') handleSearch()
}

// 小数输入支持
const [thresholdInput, setThresholdInput] = useState('0')
onChange={(e) => {
  const val = e.target.value
  if (val === '' || /^\d*\.?\d*$/.test(val)) {
    setThresholdInput(val)
  }
}}

// 中台高度计算 (平台 Header 64px)
<div style={{ height: 'calc(100vh - 64px)' }}>
```

### 10.4 文件存储路径

文档上传后存储在：
```
uploads/documents/{knowledge_base_id}/{YYYY}/{MM}/{filename}
```

路径计算 (backend/app/services/document_processor.py):
```python
# 项目根目录 = backend 的父目录
project_root = Path(__file__).resolve().parent.parent.parent.parent
uploads_dir = project_root / "uploads" / "documents"
```

### 10.5 动态 Embedding 维度支持

#### 10.5.1 设计背景

不同的 Embedding 模型输出不同维度的向量：
- text-embedding-3-small: 1536 维
- text-embedding-3-large: 3072 维
- nomic-embed-text: 768 维
- 其他模型: 可能是 512, 1024 等维度

系统需要支持不同知识库使用不同维度的 Embedding 模型。

#### 10.5.2 数据库设计

采用多维度列方案，在 `documentchunk` 表中创建多个向量列：

```sql
-- 预创建常用维度列
ALTER TABLE documentchunk ADD COLUMN IF NOT EXISTS embedding_768 vector(768);
ALTER TABLE documentchunk ADD COLUMN IF NOT EXISTS embedding_1024 vector(1024);
ALTER TABLE documentchunk ADD COLUMN IF NOT EXISTS embedding_1536 vector(1536);
ALTER TABLE documentchunk ADD COLUMN IF NOT EXISTS embedding_3072 vector(3072);

-- 为每个维度列创建 HNSW 索引
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_768
ON documentchunk USING hnsw (embedding_768 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ... 其他维度类似
```

#### 10.5.3 知识库维度绑定

每个知识库绑定到一个特定的 Embedding 维度，确保同一知识库内所有文档使用相同维度：

```python
class KnowledgeBase(Model):
    # ... 其他字段
    embedding_dimension = fields.IntField(null=True)  # 首次处理时自动设置
```

**绑定规则**：
- 首次处理文档时，根据 Embedding 模型输出的维度自动设置
- 一旦设置后不可更改（除非清空所有文档）
- 切换 Embedding 模型时检查维度兼容性

#### 10.5.4 核心实现

**存储流程** (backend/app/services/vector_store.py):

```python
class VectorStore:
    async def store_chunks(self, chunks, kb_id):
        # 1. 检测向量维度
        dimension = len(chunks[0].embedding)
        
        # 2. 获取知识库已有维度
        kb_dimension = await get_kb_embedding_dimension(kb_id)
        
        # 3. 维度一致性检查
        if kb_dimension and kb_dimension != dimension:
            raise DimensionMismatchError(
                f"知识库已绑定 {kb_dimension} 维度, "
                f"当前模型输出 {dimension} 维度"
            )
        
        # 4. 首次处理时设置维度
        if not kb_dimension:
            await set_kb_embedding_dimension(kb_id, dimension)
        
        # 5. 确保对应维度列存在
        await ensure_embedding_column(dimension)
        
        # 6. 存储到对应列
        column_name = f"embedding_{dimension}"
        # ... 执行存储
```

**搜索流程**:

```python
async def search(self, query, query_embedding, kb_id):
    # 1. 获取知识库的维度
    dimension = await get_kb_embedding_dimension(kb_id)
    
    # 2. 使用对应的维度列进行搜索
    column_name = f"embedding_{dimension}"
    
    # 3. pgvector 余弦距离搜索
    results = await self._vector_search(
        column_name, query_embedding, kb_id, top_k
    )
```

#### 10.5.5 错误处理

当维度不匹配时，返回特定错误类型：

```python
class DimensionMismatchError(Exception):
    """Embedding 维度不匹配异常"""
    pass
```

前端展示友好错误信息：
```typescript
// tasks/knowledge_base.py 返回
{
    "success": false,
    "error": "dimension_mismatch",
    "message": "知识库已绑定 768 维度, 当前模型输出 1536 维度..."
}
```

#### 10.5.6 迁移脚本

现有数据迁移脚本 (backend/app/scripts/migrate_embeddings.py):

```bash
# 检测现有向量维度并迁移到新列
cd backend
python -m app.scripts.migrate_embeddings
```

功能：
1. 检测现有 `embedding` 列的向量维度
2. 创建对应的新维度列（如 `embedding_768`）
3. 将数据从旧列迁移到新列
4. 更新知识库的 `embedding_dimension` 字段
