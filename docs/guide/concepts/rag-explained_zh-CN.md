# RAG 详解

理解 Clouisle 中 RAG 的工作原理。

## 什么是 RAG？

RAG 将信息检索与语言模型生成相结合，提供准确、上下文感知的响应。

## RAG 工作流程

1. **检索**: 在知识库中搜索相关文档
2. **增强**: 将检索到的上下文添加到提示中
3. **生成**: LLM 使用上下文生成响应

## Clouisle 中的 RAG 模式

智能体提供三种 RAG 模式（`RAGMode`）：

- **Off（关闭）**: 不进行知识库检索，即使已配置知识库
- **Auto（自动）**: 传统 RAG——每条消息自动检索相关分块
- **Agentic（智能体式）**: 智能体式 RAG——由智能体根据对话自行决定何时搜索

## 何时使用 RAG

- 回答有关特定文档的问题
- 提供准确、有出处的信息
- 减少幻觉
- 将回答建立在实际事实之上

## 相关文档

- [多租户模型](./multi-tenancy_zh-CN.md) - 基于团队的隔离
- [向量嵌入](./vector-embeddings_zh-CN.md) - 向量搜索概念
- [Agent vs Workflow](./agent-vs-workflow_zh-CN.md) - 对比指南
- [知识库优化](../best-practices/kb-optimization_zh-CN.md) - 检索调优
