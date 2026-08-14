# 工作流设计模式

常见的工作流设计模式。

## 顺序模式

线性执行: A → B → C → D

**使用场景**: 文档处理流水线

## 并行模式

并发执行: A → (B, C, D) → E

**使用场景**: 多源数据聚合

## 条件模式

分支逻辑: A → if(条件) → B else C

**使用场景**: 内容路由

## 循环模式

迭代执行: A → while(条件) → B → A

**使用场景**: 批量处理

## 相关文档

- [Agent vs Workflow](../concepts/agent-vs-workflow_zh-CN.md) - 对比指南
- [系统架构](../concepts/architecture_zh-CN.md) - 架构概述
- [Prompt 工程最佳实践](./prompt-engineering_zh-CN.md) - 提示词编写
