# Agent Context Loop Fix Design Document

状态：Superseded。

本文件描述的确定性工具步骤压缩、保留区预算、emergency fallback 和两阶段 prepare 已不再是当前实现。当前方案改为请求前完整 payload 预检：超过模型上下文长度 90% 时调用一次摘要模型，并用系统提示词、摘要和当前用户消息替换旧历史。

当前设计与验证入口：`docs/plan/agent-simple-context-summary.md`。
