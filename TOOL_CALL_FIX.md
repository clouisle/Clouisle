# 工具调用展示修复说明

## 问题描述

之前所有工具调用都被放入"思考过程"（ChainOfThought）中显示，但这不符合实际使用场景：
- 当模型有 `reasoning_content`（思考链）时，工具调用应该显示在思考过程中
- 当模型没有 `reasoning_content`（直接返回结果）时，工具调用应该显示在消息正文中

## 解决方案

### 修改文件
- `frontend/components/chat/message.tsx`

### 核心逻辑

1. **判断是否有 reasoning**
   ```typescript
   const hasReasoning = reasoningParts.length > 0
   const hasTasks = taskParts.length > 0
   const hasChainOfThought = hasReasoning || hasTasks
   ```

2. **工具调用渲染逻辑**
   - 如果 `hasReasoning === true`：工具调用在 ChainOfThought 中渲染
   - 如果 `hasReasoning === false`：工具调用在消息内容中正常渲染

3. **ChainOfThought 步骤构建**
   ```typescript
   // 只有在有 reasoning 时，才将工具调用添加到 ChainOfThought
   if (hasReasoning) {
     // 处理工具调用和 reasoning parts
   }
   ```

## 测试场景

### 场景 1：有 reasoning 的模型（如 DeepSeek）
- **预期**：工具调用显示在"思考过程"折叠面板中
- **验证**：
  1. 使用支持 reasoning 的模型（DeepSeek）
  2. 发送需要工具调用的消息
  3. 确认工具调用显示在思考过程中

### 场景 2：无 reasoning 的模型（如 GPT-4、Claude）
- **预期**：工具调用直接显示在消息内容中
- **验证**：
  1. 使用不支持 reasoning 的模型
  2. 发送需要工具调用的消息
  3. 确认工具调用显示在消息正文中，而不是思考过程中

### 场景 3：只有 RAG 任务
- **预期**：显示 ChainOfThought，但只包含 RAG 步骤
- **验证**：
  1. 使用启用了知识库的 Agent
  2. 发送消息触发 RAG
  3. 确认 ChainOfThought 显示 RAG 步骤

## 技术细节

### 修改点 1：`renderDefaultPart` 函数
```typescript
// 之前：所有工具调用都跳过
if (isToolCallPart(part) || isMcpToolCallPart(part)) {
  return null
}

// 之后：根据是否有 reasoning 决定
if (isToolCallPart(part) || isMcpToolCallPart(part)) {
  if (hasReasoning) {
    return null // 在 ChainOfThought 中渲染
  }
  // 没有 reasoning - 在消息内容中渲染
  return <Tool>...</Tool>
}
```

### 修改点 2：`buildChainOfThoughtSteps` 函数
```typescript
// 之前：总是处理所有工具调用
otherParts.forEach((part, index) => {
  if (isToolCallPart(part)) {
    // 添加到 ChainOfThought
  }
})

// 之后：只在有 reasoning 时处理工具调用
if (hasReasoning) {
  otherParts.forEach((part, index) => {
    if (isToolCallPart(part)) {
      // 添加到 ChainOfThought
    }
  })
}
```

### 修改点 3：`hasChainOfThought` 判断
```typescript
// 之前：有任务、reasoning 或工具调用就显示
const hasChainOfThought = taskParts.length > 0 || reasoningParts.length > 0 || toolCallParts.length > 0

// 之后：只有任务或 reasoning 时显示
const hasChainOfThought = hasReasoning || hasTasks
```

## 影响范围

- ✅ Agent 调试页面（`/app/apps/[id]`）
- ✅ Chat 页面（`/chat/[id]`）
- ✅ 所有使用 `Message` 组件的地方

## 构建验证

```bash
cd frontend
bun run lint    # ✅ 通过
bun run build   # ✅ 通过
```

## 后续优化建议

1. 考虑在后端 SSE 事件中添加 `in_reasoning` 标记，明确标识工具调用是否在 reasoning 期间
2. 添加单元测试覆盖不同场景
3. 考虑添加用户配置选项，允许用户选择工具调用的展示方式
