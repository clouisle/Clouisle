# 知识库优化

优化知识库性能。

## 分块策略

> **Note:** 以下预设为建议值，非硬性默认值。Clouisle 按字符分块，默认 `chunk_size` 为 1000、`chunk_overlap` 为 100；没有内置的按文档类型预设表。

| 文档类型 | 块大小 | 重叠 |
|---------|--------|------|
| 通用文档 | 500-1000 tokens | 10-20% |
| 问答 | 200-400 tokens | 5-10% |
| 代码 | 300-600 tokens | 15-25% |

## 搜索参数

> **Note:** 以下数值为建议值，非硬性默认值。实现中默认 `top_k = 5`、`score_threshold = 0.0`；上下文长度由 Token 预算控制，而非固定的 `max_tokens`。

- **top_k**: 大多数场景 3-5（建议）
- **score_threshold**: 追求质量时 0.7-0.8（建议）
- **max_tokens**: 上下文 2000-4000（建议；实际限制遵循配置的 Token 预算）

## 何时重新索引

- 文档内容发生变化
- 分块策略更新
- 嵌入模型变更

## 相关文档

- [向量嵌入](../concepts/vector-embeddings_zh-CN.md) - 向量搜索概念
- [RAG 详解](../concepts/rag-explained_zh-CN.md) - 检索增强生成
- [性能调优](./performance-tuning_zh-CN.md) - 性能优化技巧
