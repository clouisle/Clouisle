# Agent Manual Stop State Design Document

## Background & Goals

当前 agent 聊天在用户点击“停止生成”时有三个不完整点：

- 若停止发生在 reasoning 阶段，前端可能因为收不到 `reasoning_end` 而一直显示“思考中”
- 若回复只生成到一半，后端虽然有部分断连保存逻辑，但没有稳定的“手动停止”持久化语义
- 刷新或重新打开会话后，历史消息无法明确区分“手动停止”和“正常完成”

本次目标是做一次最小但完整的前后端联动修复，让“手动停止”成为 assistant message 的一等状态。

### Success criteria

- 点击停止后，当前消息立即退出 loading / streaming / thinking 状态
- 中断前已生成的 reasoning / text 内容会保留
- 当前页面会显示“已手动停止 / Stopped manually”
- 刷新或重新进入历史会话后，仍能看到 stopped 标记
- 正常完整生成路径不出现 stopped 标记

## High-Level Design

### Backend state

在 `Message` 模型上增加 `is_manually_stopped` 布尔字段，默认 `False`。

- 所有因客户端断连而提前退出的 partial save 分支都写入 `is_manually_stopped = True`
- 正常完整结束时写回 `is_manually_stopped = False`
- 历史查询接口通过 `MessageOut` 返回该字段

### Frontend state

前端把“手动停止”作为一个轻量消息 part：`{ type: 'stopped' }`。

- 当前流式消息在 `stop()` 中直接追加 stopped part
- 历史消息在 `message-converter.ts` 中根据 `is_manually_stopped` 追加同一个 stopped part
- 共享 `message.tsx` 负责渲染 stopped 提示条

### Regenerate handling

regenerate 的可见消息行在 `message_end` 之前仍使用旧 message id，而后端会在 `message_start` 提前返回新的 version id。

因此前端流式 ref 需要同时记录：

- 当前页面可见消息 id
- 后端新建 message id

stop 时优先 finalize 可见消息行，避免 regenerate 中途停止后 UI 卡在“思考中”。

## Implementation Plan

### Stage 1: Backend persisted stop state
- **Files modified**:
  - `backend/app/models/agent.py`
  - `backend/app/schemas/agent.py`
  - `backend/app/api/v1/endpoints/chat.py`
  - `backend/app/api/v1/endpoints/chat_helpers/version_utils.py`
  - `backend/app/core/init_data.py`
  - `backend/app/main.py`
- **Specific logic**:
  - 给 `Message` 增加 `is_manually_stopped`
  - 给 `MessageOut` 暴露 `is_manually_stopped`
  - 普通 chat / regenerate 的断连保存分支统一写入 stopped 标记
  - 正常完成保存路径显式写回 `False`
  - 增加启动期 migration helper，确保已有数据库补齐 `messages.is_manually_stopped`
- **Validation**:
  - 手动停止后，查询会话详情返回 `is_manually_stopped = true`
  - 正常完成消息返回 `false`

### Stage 2: Frontend stop finalization
- **Files modified**:
  - `frontend/hooks/use-chat.ts`
  - `frontend/components/chat/types.ts`
  - `frontend/components/chat/message.tsx`
  - `frontend/i18n/en/chat.json`
  - `frontend/i18n/zh/chat.json`
- **Specific logic**:
  - stop 时强制结束 reasoning / task / loading 状态
  - 为消息追加 `stopped` part
  - 修复 regenerate 场景下 visible message id 与 backend message id 不一致的问题
  - 在共享消息渲染器中显示 stopped 提示
- **Validation**:
  - reasoning 阶段停止后不再残留“思考中”
  - regenerate 中途停止后当前可见消息立即 finalize

### Stage 3: History rendering and verification
- **Files modified**:
  - `frontend/lib/utils/message-converter.ts`
  - `frontend/lib/api/agents.ts`
  - `docs/IMPLEMENTATION_PLAN.md`
- **Specific logic**:
  - 读取 `is_manually_stopped`
  - 历史 assistant message 末尾追加 stopped part
  - 为历史 assistant message 写入 `metadata.isManuallyStopped`
  - 保持 tool / RAG 合并逻辑不变
- **Validation**:
  - 刷新会话后，partial 内容与 stopped 标记同时存在
  - 历史版本切换行为保持正常
  - 前端 lint/build 与后端静态检查通过

## Testing Strategy

### Happy path tests

1. 正常聊天，reasoning 阶段停止
2. 正常聊天，正文阶段停止
3. regenerate 中途停止
4. 刷新历史后恢复 stopped 标记
5. 正常完整完成一次 chat 与一次 regenerate

### Error path tests

1. 停止发生在 `message_start` 后但 `reasoning_delta` 前
2. 停止发生在有 tool call 但还没拿到完整正文时
3. 停止后刷新历史，确认不会出现空白 loading 消息

### Regression scope

- 主聊天页面
- run 页面中的 agent chat
- 历史会话加载
- message version 切换

## Risks & Mitigation

### 风险 1：断连被误判为手动停止
- **Mitigation**:
  - 本次最小实现复用现有断连保存链路，不新增 stop endpoint
  - stopped 标记只用于用户可见语义，不影响后续上下文拼装逻辑

### 风险 2：regenerate 停止时命不中当前消息行
- **Mitigation**:
  - 明确拆分 visible message id 与 backend message id
  - stop 时优先命中当前 React state 中仍存在的可见消息

### 风险 3：共享消息渲染影响正常完成消息
- **Mitigation**:
  - 只在 `stopped` part 或 `is_manually_stopped` 为真时渲染 stopped 提示
  - 不改动普通 text / reasoning / tool 的既有渲染顺序

### Rollback plan

若 stopped 语义引发回归，可快速回退为：

- 保留 partial content 保存
- 删除 `is_manually_stopped` 字段透传与前端 stopped marker
- 恢复到当前仅保存 partial content、不额外展示 stopped 状态的行为
