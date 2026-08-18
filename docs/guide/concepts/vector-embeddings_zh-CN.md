# 向量嵌入

理解向量嵌入和相似度搜索。

## 什么是嵌入？

嵌入是捕获文本语义的数值表示。Clouisle 使用配置的嵌入模型编码文档分块和搜索查询；只有使用相同模型系列和向量维度时，相似度才有意义。

## 相似度搜索的工作原理

1. 提取文档并按字符分块。
2. 将每个分块转换为向量，并与分块元数据一起保存。
3. 使用相同的嵌入配置将查询转换为向量。
4. 搜索对应的 Qdrant 集合；使用混合检索时，再与可选的 `pg_search` 词法检索结果合并。

## 嵌入模型

- 模型注册表提供启用的嵌入模型，包括 OpenAI 兼容端点和已配置的提供商。
- 模型 ID 可配置；`text-embedding-ada-002` 只是示例，并非必需的默认值。
- 知识库在首次处理时记录 `embedding_dimension`。Qdrant 集合使用配置前缀和维度命名（例如 `<prefix>_1536`）。
- 后续文档的向量维度与知识库不一致时会被拒绝。知识库创建后更换嵌入模型也会被拒绝；请显式重新处理/重新分块到兼容的知识库，或创建替代知识库。

## 分块

Clouisle 使用 LangChain 基于字符的 `RecursiveCharacterTextSplitter` 拆分文档：

- `chunk_size` 默认为 **1000 字符**（每个知识库可配置）
- `chunk_overlap` 默认为 **100 字符**
- UI 接受 100 到 2000 字符的块大小
- 分隔符优先级为段落、换行、句末标点、单词，最后到单个字符
- 每个知识库可配置自定义分隔符

没有基于语义/ML 的分块；拆分是确定性的、字符级的。

完整检索流程请参阅 [RAG 详解](./rag-explained_zh-CN.md)，调优请参阅[知识库优化](../best-practices/kb-optimization_zh-CN.md)。

## 相关文档

- [多租户模型](./multi-tenancy_zh-CN.md) - 基于团队的授权
- [RAG 详解](./rag-explained_zh-CN.md) - 检索增强生成
- [知识库优化](../best-practices/kb-optimization_zh-CN.md) - 检索调优
