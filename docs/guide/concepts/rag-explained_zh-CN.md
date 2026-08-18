# RAG 详解

理解 Clouisle 中 RAG 的工作原理。

## 什么是 RAG？

RAG 将检索与语言模型生成结合起来。Clouisle 检索已完成处理的知识库分块，将其加入模型上下文，并基于这些分块生成回答。

## 检索流程

1. **准备**：MarkItDown 提取文本；知识库分块器按确定性的字符规则拆分文本。
2. **建立索引**：每个分块及其元数据存储在 PostgreSQL，嵌入向量存储在 Qdrant 集合中；PostgreSQL `pg_search` 提供词法索引。
3. **召回**：查询可以使用 `vector`、`fulltext` 或 `hybrid` 搜索。混合检索合并稠密和词法候选；可选的、已授权的重排序模型可以重新排列候选集。
4. **增强**：选中的分块被格式化为提供给 Agent 的知识库上下文。
5. **生成**：配置的 LLM 生成响应；检索和生成是两个独立阶段。

检索模式与 Agent 的 RAG 模式相互独立。`off`、`auto`、`agentic` 控制 Agent 是否以及何时调用检索；`vector`、`fulltext`、`hybrid` 控制知识库如何搜索。

## Clouisle 中的 RAG 模式

智能体提供三种 RAG 模式（`RAGMode`）：

- **Off（关闭）**：不进行知识库检索，即使已配置知识库。
- **Auto（自动）**：每条消息自动检索相关分块。
- **Agentic（智能体式）**：由智能体根据对话自行决定何时搜索。

## 嵌入兼容性

知识库在第一个文档处理时记录嵌入维度。后续文档和查询必须使用兼容维度；Qdrant 集合名称按配置前缀和维度分区。知识库创建后更换嵌入模型会被拒绝，应显式执行重新处理/重新分块流程，或创建替代知识库，不要假设系统会自动重建索引。

## 何时使用 RAG

- 回答有关特定文档的问题
- 需要基于团队知识库的回答
- 比较向量、词法和混合模式的检索实验

检索调优请参考[知识库优化](../best-practices/kb-optimization_zh-CN.md)。

## 相关文档

- [多租户模型](./multi-tenancy_zh-CN.md) - 基于团队的授权
- [向量嵌入](./vector-embeddings_zh-CN.md) - 向量搜索概念
- [Agent vs Workflow](./agent-vs-workflow_zh-CN.md) - 对比指南
- [知识库优化](../best-practices/kb-optimization_zh-CN.md) - 检索调优
