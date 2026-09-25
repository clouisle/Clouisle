# Clouisle 简介

Clouisle 是面向生产环境的多智能体协同平台与工作流引擎。

## 什么是 Clouisle？

Clouisle 让组织能够构建、编排并部署面向生产的 AI 智能体团队，具备安全沙箱执行、混合知识检索（RAG）与企业级安全能力。Agent、工作流、知识库、工具与模型均按团队配置，受 RBAC 治理，并可在管理后台统一观测。

## 主要功能

- **多智能体编排**：通过可视化工作流将已发布的 Agent 组合为多智能体流水线（`agent` 与 `sub_workflow` 节点）
- **AI Agent 管理**：创建并配置带工具、技能、记忆与 RAG 模式的对话式 AI Agent
- **可视化工作流引擎**：拖拽式图编排，19 种节点、嵌套子流程与人工审批
- **知识库系统**：使用向量 + 全文混合检索与重排序存储、检索文档
- **沙箱执行**：Agent 与工作流代码在隔离沙箱会话中运行，具备 CPU/内存/磁盘限额
- **企业安全**：多租户、RBAC、SSO（OIDC/SAML/CAS）、TOTP 双因素与字段级审计日志
- **多 LLM 支持**：内置 23 个提供商，并支持任意 OpenAI 兼容端点

## 为什么选择 Clouisle？

- **生产就绪**: 为企业部署而构建
- **灵活**: 支持多个 LLM 提供商和自定义工具
- **安全**: 全面的安全功能和合规性
- **可扩展**: 水平扩展以实现高可用性

## 下一步

- 使用[开发环境搭建](./development_zh-CN.md)在本地启动。
- 在[多租户模型](../concepts/multi-tenancy_zh-CN.md)中了解团队授权模型。
- 在 [Agent vs Workflow](../concepts/agent-vs-workflow_zh-CN.md) 中比较对话式 Agent 与图式 Workflow。
- 参阅 [RAG 详解](../concepts/rag-explained_zh-CN.md) 了解检索模式，参阅[向量嵌入](../concepts/vector-embeddings_zh-CN.md)了解嵌入兼容性。
