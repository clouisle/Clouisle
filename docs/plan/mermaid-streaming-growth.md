# Mermaid Streaming Growth Design Document

## Background & Goals

当前前端聊天中的 Mermaid 图在流式回复阶段会随着 markdown token 持续重解析，导致图表在 loading、中间态和最终态之间频繁切换。之前的 debounce / freeze / last-good-SVG 方向能减轻闪烁，但不能达到“节点丝滑出现”的目标。

本次目标是在保留现有 Mermaid 展示壳层的前提下，让流式图表只在稳定语义边界推进，并且让新出现的节点和边有轻量入场效果。

### Success criteria

- Mermaid 图只在稳定可渲染前缀推进时更新，而不是跟随每个 token 重绘
- 第一帧成功渲染后，后续流式阶段始终保持上一次成功图表可见
- 新增节点/边有轻量入场动画，已有元素不整体闪烁
- 图表/代码切换、缩放、拖拽、下载、全屏行为保持可用
- 最终完整 Mermaid 仍会做一次全量校验，最终非法代码才展示错误

## High-Level Design

### Stable render frontier

在 `frontend/components/chat/message.tsx` 中为 Mermaid 增加专用前缀提交逻辑：

- 从流式 Mermaid 源码中按行提取“已完成行”
- 对每一行做保守检查：括号/引号配平、边标签 `| |` 配平、箭头不悬空、`subgraph`/`end` 成对、`classDef`/`style`/`linkStyle`/`click`/`class` 指令不截断
- 仅当代码推进到新的稳定 frontier 时才触发 Mermaid render

### Persistent stream session

由于 `Streamdown` 会在 `content_delta` 到达时不断重建 markdown block，需要引入基于 `messageId + partIndex + blockIndex` 的稳定 `streamKey`。

- `TextWithCitations` 生成 Mermaid block 级别的 `streamKey`
- `MermaidBlock` 使用模块级 `mermaidStreamSessions` 记录该 block 最近一次：
  - committed frontier code
  - rendered SVG
  - animated SVG
  - rendered theme
  - final error

这样 Mermaid block 即使因 markdown 重渲染被重新挂载，也能恢复到上一帧稳定图表。

### Selective entry animation

当新的 frontier 成功渲染后：

- 解析前一版 SVG 与新 SVG
- 用节点文本/id 和边 label/path 特征做保守签名
- 只给新增的 `g.node`、`g.edgePath`、`g.edgeLabel` 添加进入动画类
- 在 `frontend/app/globals.css` 中提供节点淡入轻微上移/缩放、边透明度显现动画

## Implementation Plan

### Stage 1: Frontier-based Mermaid rendering
- **Files modified**:
  - `frontend/components/chat/message.tsx`
- **Specific logic**:
  - 移除现有基于 debounce/freeze 的 Mermaid 流式渲染策略
  - 增加 Mermaid 稳定前缀提取 helper
  - 在 `MermaidBlock` 中只对 frontier 或最终完整代码做 render
  - 在已有成功 SVG 存在时，后续渲染失败不清空图表；仅最终完整 Mermaid 失败时展示错误
- **Validation**:
  - 输入 `A -->` 这类未完成边时，图表保持上一帧
  - 完成一整行边定义后，图表推进到新状态

### Stage 2: Stable session identity and visual continuity
- **Files modified**:
  - `frontend/components/chat/message.tsx`
- **Specific logic**:
  - 通过 `Message -> TextWithCitations -> MermaidMarkdownBlock -> MermaidBlock` 传递稳定 `streamKey`
  - 用模块级 session map 保留 block 最近一次成功图和主题信息
  - 保持缩放/拖拽状态不因 frontier 更新而重置
- **Validation**:
  - 流式阶段 markdown 重解析时不回退到 loading
  - 同一条 assistant 消息持续增长时图表保持可见

### Stage 3: Entry animation and docs
- **Files modified**:
  - `frontend/components/chat/message.tsx`
  - `frontend/app/globals.css`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `docs/plan/mermaid-streaming-growth.md`
- **Specific logic**:
  - 对新节点/新边打入场 class
  - 在全局 CSS 中补充 Mermaid streaming keyframes
  - 更新复杂任务计划索引与详细设计文档
- **Validation**:
  - 新增节点/边淡入出现，旧节点不整体闪烁
  - 文档与实现阶段保持一致

## Testing Strategy

### Happy path tests

1. 流式输出 `flowchart TD` 并逐行追加节点和边
2. 第一帧渲染成功后继续追加新节点
3. 最终 fence 闭合后完成最终全量渲染
4. 图表/代码切换、拖拽、缩放、下载、全屏仍正常

### Error path tests

1. `A -->` 这类悬空箭头不触发坏图替换
2. 未闭合 `subgraph` 不触发中间错误 UI
3. 最终完整 Mermaid 依旧非法时展示错误
4. 中途停止或重试后，新流式会话不会复用旧 block 的错误态

### Regression scope

- `frontend/components/chat/message.tsx` 中普通 markdown 渲染
- 聊天消息 citations portal 逻辑
- Mermaid 主题切换（light/dark）
- Mermaid 交互壳层（缩放、拖拽、下载、全屏）

## Risks & Mitigation

### 风险 1：Mermaid layout 每次 frontier 推进仍会重排
- **Mitigation**:
  - 减少 frontier 提交频率，只在稳定行边界推进
  - 仅对新增元素做动画，避免整个容器统一动画造成更强闪烁

### 风险 2：SVG diff 签名不稳定
- **Mitigation**:
  - 优先使用 id/data-id，其次使用 label/title 文本
  - 如果无法可靠识别，则退化为不加动画，而不是错误动画整个图

### 风险 3：Streamdown 重渲染导致 Mermaid state 丢失
- **Mitigation**:
  - 使用 `streamKey` + 模块级 session map 恢复 committed frontier 和上一次成功 SVG

### Rollback plan

若 frontier 渲染逻辑引发回归，可回退为：

- 保留 Mermaid 基础展示与交互壳层
- 移除 session map / frontier prefix / SVG diff 动画逻辑
- 恢复为仅完整 Mermaid fence 渲染的保守模式
