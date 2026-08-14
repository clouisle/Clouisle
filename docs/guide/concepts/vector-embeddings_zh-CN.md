# 向量嵌入

理解向量嵌入和相似度搜索。

## 什么是嵌入？

嵌入是捕获语义含义的文本数值表示。

## 相似度搜索的工作原理

1. 将查询转换为向量
2. 在数据库中搜索相似向量
3. 返回最相似的文档

## 嵌入模型

- OpenAI `text-embedding-ada-002`（模型 ID 可配置）
- 自定义 OpenAI 兼容嵌入端点
- 模型注册表中其他提供嵌入模型的提供商（如 Azure OpenAI、Google、DeepSeek、Ollama）

## 分块

Clouisle 使用 LangChain 基于字符的 `RecursiveCharacterTextSplitter` 拆分文档：

- `chunk_size` 默认为 **1000 字符**（每个知识库可配置）
- `chunk_overlap` 默认为 **100 字符**
- 按优先级递归分隔符：段落、换行、中英文句末标点、单词，最后到单个字符
- 每个知识库可配置自定义分隔符

没有基于语义/ML 的分块；拆分是确定性的、字符级的。

## 相关文档

- [多租户模型](./multi-tenancy_zh-CN.md) - 基于团队的隔离
- [RAG 详解](./rag-explained_zh-CN.md) - 检索增强生成
- [Agent vs Workflow](./agent-vs-workflow_zh-CN.md) - 对比指南
- [知识库优化](../best-practices/kb-optimization_zh-CN.md) - 检索调优
