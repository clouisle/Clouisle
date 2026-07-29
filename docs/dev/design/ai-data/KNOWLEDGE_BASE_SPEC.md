# Clouisle 知识库规范

## 1. 概述

本文档定义了 Clouisle 项目中知识库（Knowledge Base）功能的设计规范，用于实现 RAG（Retrieval-Augmented Generation）能力。

### 1.1 设计目标

- **团队隔离**：知识库归属于团队，实现数据隔离
- **格式丰富**：支持多种文档格式
- **智能处理**：自动文本提取、分块和向量化
- **高效检索**：基于 Qdrant Dense 与 PostgreSQL pg_search BM25 的混合检索、全局重排和受限上下文组装

### 1.2 技术选型

| 功能 | 技术方案 | 说明 |
|------|----------|------|
| 文档解析 | MarkItDown | 微软开源，统一转换为 Markdown |
| 文本分块 | 自研 TextChunker | 语义感知分块 |
| 权威数据 | PostgreSQL | 保存知识库、文档、分块及索引状态 |
| Dense 索引 | Qdrant | 保存向量并执行语义召回 |
| Lexical 检索 | PostgreSQL pg_search | 对同库可重建的 Chunk 投影执行 BM25 关键词召回 |
| 向量与重排模型 | ModelManager | 复用团队模型配置 |
| 异步处理 | Celery | 文档处理和索引回填 |

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
    embedding_id: str             # Qdrant 向量点引用
    status: str                   # pending / embedded / failed
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

#### 5.3.1 分块参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `chunk_size` | 500 | 目标分块大小 (tokens) |
| `chunk_overlap` | 50 | 分块重叠 (tokens) |
| `separator` | 自动 | 自定义分隔符 (可选) |

> **Token 估算**：约 4 个字符 ≈ 1 token

#### 5.3.2 分块策略

使用递归分割策略，按优先级尝试不同分隔符：

```python
DEFAULT_SEPARATORS = [
    "\n\n",   # 段落
    "\n",     # 行
    "。",     # 中文句号
    "！",     # 中文感叹号
    "？",     # 中文问号
    ". ",     # 英文句号
    "! ",     # 英文感叹号
    "? ",     # 英文问号
    "；",     # 中文分号
    "; ",     # 英文分号
    "，",     # 中文逗号
    ", ",     # 英文逗号
    " ",      # 空格
    "",       # 字符级
]
```

#### 5.3.3 分块算法

```
1. 计算目标字符数: target_chars = chunk_size × 4
2. 按分隔符列表顺序尝试分割文本
3. 对每个分割片段:
   - 如果 <= target_chars: 累积到当前块
   - 如果 > target_chars: 递归使用更细粒度分隔符分割
4. 应用重叠: 下一块开头包含上一块末尾的 overlap 字符
5. 无法继续分割时: 硬切分到目标长度
```

#### 5.3.4 使用示例

```python
from app.services.document_processor import TextChunker

chunker = TextChunker(
    chunk_size=100,      # 100 tokens (~400 字符)
    chunk_overlap=10,    # 10 tokens (~40 字符) 重叠
)

chunks = chunker.chunk_text(text)
# [
#     {"content": "...", "chunk_index": 0, "token_count": 95, "char_count": 380},
#     {"content": "...", "chunk_index": 1, "token_count": 98, "char_count": 392},
#     ...
# ]
```

> **注意**：分块大小是目标值，实际大小会在分隔符边界处变化，以保持语义完整性。

### 5.4 向量与 Lexical 索引

文档分块首先写入 PostgreSQL 权威表；Dense 向量另行写入可重建的 Qdrant 索引，Lexical 检索使用同一 PostgreSQL 服务内的可重建投影：

1. 通过团队 Embedding 模型生成向量并写入 Qdrant，`DocumentChunk.embedding_id` 保存向量点引用。
2. 文档处理流程把可检索 Chunk 投影到 PostgreSQL 的 `knowledge_lexical_chunks`，pg_search BM25 索引在该表上执行关键词召回，无需独立 Lexical 服务。
3. 只有成功生成向量的 Chunk 才参与 Dense 召回；已完成文档的 Chunk 可独立参与 BM25 召回。
4. Dense 索引或 Lexical 投影写入失败保留明确状态，并由幂等重试、回填和数量对账修复；原始知识库、文档和 Chunk 表始终是权威来源。
5. Lexical 索引随 PostgreSQL 数据库和扩展管理，不使用独立服务的索引版本、读写别名或跨服务回填。

---

## 6. 检索架构与执行逻辑

### 6.1 组件职责

PostgreSQL 是知识库、文档和分块的权威数据源。检索索引可重建，不反向覆盖权威数据。

| 组件 | 职责 |
|------|------|
| 统一检索服务（`services/retrieval.py`） | 统一请求校验、目标并发、降级、融合、全局重排、上下文组装和诊断 |
| `VectorStore` | Qdrant Dense 索引写入与语义召回 |
| `LexicalStore` | 维护 PostgreSQL Lexical 投影，并通过 pg_search 执行 BM25 召回和授权范围过滤 |
| PostgreSQL | 权威知识库、文档、分块、授权范围和索引状态 |
| Retrieval Lab | 即时 A/B 检索与结果诊断 |

API 搜索、AUTO RAG、Agentic 知识库工具、Agent 服务和 Workflow 知识节点均使用同一个 `retrieve()` 入口。调用方只保留授权、错误翻译和结果展示职责。

### 6.2 请求与授权边界

检索请求使用不可变的 `RetrievalRequest` 和 `RetrievalTarget`。请求支持以下严格模式：

| 模式 | 召回通道 | 阈值语义 |
|------|----------|----------|
| `vector` | Qdrant Dense | `score_threshold` 仅过滤 Dense 相似度 |
| `fulltext` | PostgreSQL pg_search BM25 | 不套用 Dense 相似度阈值 |
| `hybrid` | Dense 与 BM25 并行 | 通过加权 RRF 融合，不把融合分数当作概率 |

调用方必须先解析用户已授权的知识库和文档范围，再构造 `RetrievalTarget`：

- 知识库必须处于 `active` 状态。
- 文档必须处于 `completed` 状态。
- `allowed_document_ids` 表示已授权上限。
- 请求指定的 `document_ids` 只能缩小 `allowed_document_ids`，不能扩大权限。
- Dense 候选要求知识库具有可用的 Embedding 模型和有效向量状态。
- BM25 可独立检索没有 Embedding 模型的知识库。
- 空查询、非法模式、非正数 Top K/超时/RRF 参数及无效上下文限制会在执行前失败。

### 6.3 AUTO RAG 查询上下文化

查询上下文化只用于对话型 AUTO RAG，不默认改写显式 Agentic 工具查询。

```text
原始用户问题
    -> 检查环境开关
    -> 检查是否为短且含指代的后续问题
    -> 使用最近最多 6 条对话生成独立检索查询
    -> 严格验证 JSON、证据来源和输出格式
    -> 仅将改写结果用于检索
```

约束如下：

- 只处理长度不超过 160 且含中英文指代词的查询。
- `evidence` 必须是历史对话中的非空原文片段。
- 改写结果必须严格为 `evidence + 空格 + 原始问题`，防止引入新事实。
- 模型缺失、超时、异常、无效 JSON 或不合规输出全部回退原查询。
- 原始问题继续用于最终回答，改写查询不会替换用户问题。
- 日志只记录 `disabled`、`not_needed`、`rewritten` 或 `fallback`，不记录查询内容或异常正文。

### 6.4 并发召回与失败策略

多个知识库并发检索，服务级并发上限为 8，每个目标受 `timeout_seconds` 约束。同一次逻辑调用内，相同原始查询、团队和 Embedding 模型 UUID 的 Dense 目标共享一个进行中的查询向量任务；共享范围覆盖主检索与可选 Shadow 检索，但不跨请求持久化。每个目标仍独立校验向量维度和授权过滤，完整召回结果不会共享。

```text
每个授权知识库
    +-> Qdrant Dense 召回
    +-> PostgreSQL pg_search BM25 召回
              |
              v
       加权 RRF（Hybrid）
              |
              v
       跨知识库全局候选池
```

各模式的失败行为：

- `vector`：Embedding 或 Qdrant 失败时，该目标返回明确诊断，不静默伪造结果。
- `fulltext`：PostgreSQL 或 pg_search 查询失败时，该目标返回明确诊断。
- `hybrid`：单通道失败时使用另一通道继续，并在结果中附加结构化 `degradation_reasons`；双通道失败时该目标失败。
- 某些目标失败不影响其他知识库的有效结果；仅当全部目标失败时抛出 `RetrievalError`。
- 诊断区分 `inactive`、`missing_embedding_model`、`timeout` 和 `failed`。

### 6.5 加权 RRF 融合

Dense 相似度和 BM25 分数的量纲不同，Hybrid 使用排名而不是原始分数融合：

```text
fusion_score(chunk)
  = dense_weight   / (rrf_k + dense_rank)
  + lexical_weight / (rrf_k + lexical_rank)
```

默认 `dense_weight = 1.0`、`lexical_weight = 1.0`、`rrf_k = 60`。同一 Chunk 在两条通道命中时累计贡献，只命中一条时仍可进入候选池。

结果保留各阶段信息：

- `dense_score`、`dense_rank`
- `lexical_score`、`lexical_rank`
- `fusion_score`、`fusion_rank`
- `rerank_score`、`rerank_rank`（启用重排时）
- `final_score_stage`

RRF 分数只用于排序，不归一化或展示为相关概率。相同分数按知识库、文档和 Chunk ID 稳定排序，保证评估可复现。

### 6.6 全局排序与重排

所有知识库的结果先汇总成一个全局候选池，再统一截取 `candidate_k`。如果启用 Rerank：

1. 选择全局候选，而不是分别重排各知识库。
2. 使用同一模型对候选内容执行一次重排。
3. 保留 Dense、BM25 和 Fusion 的原始分数与排名。
4. 只使用 `rerank_score_threshold` 过滤重排分数。
5. `rerank_fail_open=true` 时，重排失败继续使用召回排序；否则按失败配置终止。

最终 Top K 在全局排序和可选重排后应用，避免多个知识库分别截断后简单拼接造成偏差。Retrieval Lab A/B 批量请求只共享查询向量；A、B 各自独立召回、融合、截断和重排，因此每个启用重排的配置最多调用一次 Rerank，候选池不会跨配置合并。

### 6.7 上下文组装

全局排序后可执行受限上下文组装：

- 每个命中 Chunk 最多扩展前后各一个相邻 Chunk。
- 相邻 Chunk 必须仍属于同一授权文档，并满足知识库 `active`、文档 `completed` 条件。
- 按文档聚合内容，同时保留 `context_chunks` 和 `citation_chunk_ids`，确保引用能追溯到实际提供给模型的内容。
- 可限制 `top_k`、`max_documents`、`max_chunks_per_document` 和全局 `context_token_budget`。
- 超出 Token 预算时跳过不能完整放入的 Chunk，不截断文本制造不可追溯引用。
- 未启用扩展或预算限制时，直接返回全局 Top K，避免额外数据库读取。

### 6.8 灰度、Shadow 与回滚

Hybrid 主链路按以下优先级决定：

1. `RETRIEVAL_HYBRID_KILL_SWITCH=true`：最高优先级，立即强制 Vector。
2. 私有 `SiteSetting`：`retrieval_hybrid_mode=enabled|disabled|rollout`。
3. `retrieval_hybrid_team_ids`：显式纳入团队。
4. `retrieval_hybrid_percentage`：按团队 ID 的 SHA-256 稳定哈希分桶。

推荐发布顺序：

```text
internal -> 5% -> 25% -> 50% -> 100%
```

未进入 Hybrid 灰度的请求以不可变副本转换为 Vector 主请求。启用 `RETRIEVAL_SHADOW_ENABLED` 后可额外执行 Hybrid Shadow，但 Shadow 的成功、失败和耗时都不能改变主响应。

Shadow 只保存以下数据，最多 1,000 条并保留 7 天：

- Chunk ID 与排名
- 检索版本与 pg_search 扩展版本
- 总耗时

Shadow 不保存原始查询、Chunk 内容、凭据或异常正文。Lexical 检索不维护独立服务或别名版本；回滚 PostgreSQL 或 pg_search 变更时使用数据库备份和与应用版本匹配的迁移流程。

### 6.9 可观测性

检索指标以 Redis 聚合数据记录，保留 7 天：

- 请求数、候选数和空结果数
- 降级次数和错误数
- PostgreSQL、pg_search 扩展和 BM25 索引健康状态
- `recall`、`rerank`、`context`、`total` 阶段耗时
- 各阶段延迟计数、总和和直方图桶

指标与 Shadow 写入均为 fail-open：Redis 或遥测故障不能中断检索，也不能改变返回答案。

### 6.10 端到端执行流程

```text
调用方完成授权并构造 RetrievalTarget
        ↓
仅 AUTO RAG：按需上下文化检索查询
        ↓
Kill Switch / 全局 / 团队 / 百分比灰度判断
        ↓
在授权文档范围内并发检索（上限 8）
        ↓
Qdrant Dense + PostgreSQL pg_search BM25
        ↓
按知识库执行加权 RRF；单通道失败可降级
        ↓
跨知识库汇总并全局排序
        ↓
可选：对全局候选池执行 Rerank
        ↓
可选：邻接扩展、文档聚合和 Token/数量限制
        ↓
返回结果、结构化诊断和各阶段耗时
        ↓
旁路记录聚合指标；Shadow 永不影响答案
```

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
│   ├── vector_store.py        # Qdrant Dense 索引与召回
│   ├── lexical_store.py       # PostgreSQL pg_search 投影与 BM25 召回
│   ├── retrieval.py           # 统一检索、融合、重排与上下文组装
│   └── retrieval_rollout.py   # 灰度、Shadow 与聚合指标
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
| Dense 索引与语义召回 | ✅ 完成 | Qdrant 向量索引、状态过滤和授权范围过滤 |
| BM25 关键词召回 | ✅ 完成 | PostgreSQL pg_search 索引、授权过滤和关键词召回 |
| 混合检索 | ✅ 完成 | Dense + BM25 加权 RRF，保留各阶段分数与排名 |
| 全局重排与上下文 | ✅ 完成 | 跨知识库 Rerank、邻接扩展、文档/Chunk/Token 上限 |
| 查询上下文化 | ✅ 完成 | 仅 AUTO RAG 按需改写，严格验证并回退原查询 |
| Retrieval Lab | ✅ 完成 | 即时 A/B 检索和结果诊断 |
| 灰度与可观测性 | ✅ 完成 | Kill Switch、团队/比例灰度、隐私安全 Shadow 和 Redis 指标 |
| 文档下载 | ✅ 完成 | Authorization Bearer Token 鉴权 |
| 前端 UI (后台) | ✅ 完成 | 完整的知识库管理界面 |
| 前端 UI (中台) | ✅ 完成 | 平台级知识库管理 |

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

### 10.3 Retrieval Lab UI

后台与中台共用 Retrieval Lab 组件，但保持各自路由和 API 权限边界。即时检索支持：

- Simple 参数：检索模式、最终 Top K、是否启用 Rerank。
- Advanced 参数：各通道候选数、Dense/Lexical 权重、RRF 参数和阶段专属阈值。
- 结果诊断：Dense、Lexical、Fusion、Rerank 分数与排名、排名变化、通道、耗时和降级原因。
- A/B：通过一个批量请求执行两个相互独立的统一检索变体，仅复用匹配的调用内查询向量，并展示结果重合及排名移动。
- 应用检索参数需要确认和 `kb:update`；即时测试受 `kb:test` 控制。
- 输入框保留中文 IME 组合状态检测，避免拼音输入过程中按 Enter 误触发检索。

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

### 10.5 Embedding 维度与外部索引

不同 Embedding 模型会输出不同维度的向量。知识库通过 `embedding_dimension` 记录首次成功处理时确定的维度；后续写入必须保持一致，切换到不同维度的模型前需重新建立该知识库的 Dense 索引。

向量正文不保存在 PostgreSQL：

- PostgreSQL 的 `DocumentChunk` 保存权威文本、顺序、Token 数、元数据、Embedding 状态和 `embedding_id`。
- Qdrant 保存向量点，并使用知识库、文档、Chunk 和状态字段进行过滤。
- PostgreSQL 的 `knowledge_lexical_chunks` 保存可重建的 Chunk 检索投影，pg_search 在该表上维护 BM25 索引；它不替代原始知识库、文档和 Chunk 权威表。
- 文档重处理、Chunk 删除、文档删除和知识库删除必须在现有生命周期内同步更新 Lexical 投影和 Qdrant；失败操作由幂等任务重试。
- Qdrant Dense 索引和 PostgreSQL Lexical 投影都不是权威数据源，发生漂移时以权威表为准执行回填与数量对账。

维度不匹配必须在写入 Qdrant 前失败，并保留明确的索引错误状态，不能把不兼容向量写入现有集合。

#### 10.5.1 索引重建与回滚

索引重建不修改 PostgreSQL 权威表。Dense 索引通过重新写入 Qdrant 点完成；Lexical 索引通过从权威表回填 `knowledge_lexical_chunks` 并重建同库 pg_search BM25 索引完成，不需要跨服务复制或切换读别名。运维必须核对投影与符合条件的权威 Chunk 数量，并验证扩展版本、索引有效性和 BM25 查询计划。升级 pg_search 前先备份数据库并确认扩展与 PostgreSQL、应用版本兼容；若升级异常，恢复匹配版本的数据库备份和应用镜像。