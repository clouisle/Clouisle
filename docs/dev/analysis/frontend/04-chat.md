# 聊天页面

路由分组: `(chat)`
布局: 聊天专用布局

## /chat/[id] - 公开聊天界面

**文件位置**: `frontend/app/(chat)/chat/[id]/page.tsx`

**页面作用**: Agent 公开聊天界面，用户与 Agent 进行对话

**使用的 API**:

| API | 方法 | 说明 |
|-----|------|------|
| `publicAgentsApi.getPublicAgent()` | GET `/agents/{id}` | 获取 Agent 信息 |
| `publicAgentsApi.getConversations()` | GET `/agents/{id}/conversations/my` | 获取用户对话列表 |
| `publicAgentsApi.getConversation()` | GET `/agents/conversations/{id}` | 获取对话详情 |
| `publicAgentsApi.deleteConversation()` | DELETE `/agents/conversations/{id}` | 删除对话 |
| `publicAgentsApi.updateConversation()` | PATCH `/agents/conversations/{id}` | 更新对话（重命名） |
| `publicAgentsApi.chatStream()` | POST `/chat/{agentId}/chat` | 发送消息（SSE） |
| `uploadApi.uploadFileWithProgress()` | POST `/chat/{agentId}/chat/upload` | 上传文件 |

**主要组件**:

### ChatContainer

主聊天容器，包含：
- 对话列表侧边栏
- 消息展示区域
- 输入框

### MessageList

消息列表组件：
- 用户消息
- AI 回复
- 工具调用展示
- 思考过程展示（如有）

### ChatInput

输入组件：
- 文本输入
- 文件上传（如启用）
- 发送按钮
- 停止生成按钮

### ConversationSidebar

对话侧边栏：
- 对话列表
- 新建对话
- 对话重命名
- 删除对话

---

## 主要功能

### 消息发送

```typescript
// 使用 useChat hook
const { sendMessage, isLoading, stopGeneration } = useChat({
  agentId,
  conversationId,
  onMessage: (message) => {
    // 处理新消息
  },
  onError: (error) => {
    // 处理错误
  }
})

// 发送消息
await sendMessage({
  content: 'Hello',
  files: [] // 可选文件
})
```

### 流式响应

使用 Server-Sent Events (SSE) 接收流式响应：

```typescript
// 事件类型
type StreamEvent =
  | { type: 'message_start', data: { conversation_id, message_id } }
  | { type: 'content_delta', data: { delta: string } }
  | { type: 'tool_call_start', data: { tool_call_id, name } }
  | { type: 'tool_call_delta', data: { delta: string } }
  | { type: 'tool_call_end', data: { tool_call_id } }
  | { type: 'message_end', data: { usage } }
```

### 文件上传

支持上传文件用于对话：

```typescript
const { uploadFile, progress } = useFileUpload()

const file = await uploadFile(selectedFile, {
  onProgress: (percent) => {
    // 更新进度
  }
})

// 发送带文件的消息
await sendMessage({
  content: 'Analyze this image',
  files: [{ type: 'image', url: file.url }]
})
```

### 工具调用展示

当 Agent 调用工具时，展示：
- 工具名称
- 调用参数
- 执行结果
- 执行状态

### 消息版本

支持消息版本切换：
- 重新生成会创建新版本
- 可以查看历史版本
- 切换到不同版本

---

## 访问控制

| Agent 状态 | Agent 可见性 | 访问规则 |
|------------|--------------|----------|
| DRAFT | - | 仅创建者 |
| PUBLISHED | PRIVATE | 仅创建者 |
| PUBLISHED | TEAM | 团队成员 |
| PUBLISHED | PUBLIC | 所有登录用户 |

---

## 响应式设计

- 桌面端：左侧对话列表 + 右侧聊天区域
- 移动端：可折叠的对话列表抽屉

---

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Shift + Enter` | 换行 |
| `Escape` | 停止生成 |
| `Ctrl/Cmd + N` | 新建对话 |
