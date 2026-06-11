# 快捷操作跳转后自动弹出新建窗口

## Background & Goals

当前控制台页面的快捷操作（Create Agent / Create Workflow / Create KB / Manage Tools）只是简单跳转到目标页面，用户还需要手动点击"新建"按钮。目标是跳转后自动弹出对应的创建对话框。

## High-Level Design

使用 URL search params 作为信号机制：
- 快捷操作的 `<Link>` 携带 `?action=create` 参数（Agent/Workflow 还需携带 `&type=agent` 或 `&type=workflow`）
- 目标页面的 `useEffect` 读取该参数，自动设置 dialog state 为 open
- 打开 dialog 后清除 URL 参数，避免刷新页面时重复弹出

## Implementation Plan

### Stage 1: 控制台页面 — 快捷操作携带 action 参数

**Files modified**: `frontend/app/(platform)/app/page.tsx`

将 4 个 `<Link href="...">` 改为携带 action 参数：

| 快捷操作 | 当前 href | 新 href |
|---------|----------|---------|
| Create Agent | `/app/apps` | `/app/apps?action=create&type=agent` |
| Create Workflow | `/app/apps` | `/app/apps?action=create&type=workflow` |
| Create Knowledge Base | `/app/kb` | `/app/kb?action=create` |
| Manage Capabilities | `/app/capabilities` | `/app/capabilities?action=create` |

**Validation**: 点击每个快捷操作，检查 URL 是否正确携带参数。

### Stage 2: Apps 页面 — 读取 action 参数自动弹出创建对话框

**Files modified**: `frontend/app/(platform)/app/apps/page.tsx`

在已有的 `useEffect`（读取 `tab` 参数）中扩展，同时读取 `action` 和 `type` 参数：

```ts
React.useEffect(() => {
  const tabParam = searchParams.get('tab')
  if (tabParam === 'agent' || tabParam === 'workflow') {
    setActiveTab(tabParam)
  }

  // 自动弹出创建对话框
  const actionParam = searchParams.get('action')
  if (actionParam === 'create') {
    setCreateDialogOpen(true)
    // 清除 URL 参数
    const url = new URL(window.location.href)
    url.searchParams.delete('action')
    url.searchParams.delete('type')
    window.history.replaceState({}, '', url.toString())
  }
}, [searchParams])
```

将 `initialType` 传递给 `<AppCreateDialog>`：

```tsx
<AppCreateDialog
  open={createDialogOpen}
  onOpenChange={setCreateDialogOpen}
  initialType={searchParams.get('type') === 'workflow' ? 'workflow' : 'agent'}
  onSuccess={() => { ... }}
/>
```

**注意**: 因为 useEffect 在 dialog open 后就清除了 URL params，`initialType` 需要在 dialog 打开前就确定。可以用一个额外的 state 来存储初始类型：

```ts
const [initialCreateType, setInitialCreateType] = React.useState<'agent' | 'workflow'>('agent')

React.useEffect(() => {
  const actionParam = searchParams.get('action')
  if (actionParam === 'create') {
    const typeParam = searchParams.get('type')
    if (typeParam === 'agent' || typeParam === 'workflow') {
      setInitialCreateType(typeParam)
    }
    setCreateDialogOpen(true)
    // 清除 URL 参数
    const url = new URL(window.location.href)
    url.searchParams.delete('action')
    url.searchParams.delete('type')
    window.history.replaceState({}, '', url.toString())
  }
}, [searchParams])
```

然后 `<AppCreateDialog initialType={initialCreateType} .../>`。

**Validation**:
1. 从控制台点击"创建智能体" → 跳转到 Apps 页面，dialog 自动弹出，类型默认为 Agent
2. 从控制台点击"创建工作流" → 跳转到 Apps 页面，dialog 自动弹出，类型默认为 Workflow
3. 直接访问 `/app/apps` → 不弹出 dialog
4. 刷新页面后 → 不弹出 dialog（参数已清除）

### Stage 3: Knowledge Base 页面 — 读取 action 参数自动弹出创建对话框

**Files modified**: `frontend/app/(platform)/app/kb/page.tsx`

在页面组件中添加 `useSearchParams` 和 `useEffect`：

```ts
const searchParams = useSearchParams()

React.useEffect(() => {
  const actionParam = searchParams.get('action')
  if (actionParam === 'create') {
    setDialogOpen(true)
    const url = new URL(window.location.href)
    url.searchParams.delete('action')
    window.history.replaceState({}, '', url.toString())
  }
}, [searchParams])
```

**Validation**:
1. 从控制台点击"创建知识库" → 跳转到 KB 页面，dialog 自动弹出
2. 直接访问 `/app/kb` → 不弹出 dialog

### Stage 4: Capabilities 页面 — 读取 action 参数自动弹出创建对话框

**Files modified**: `frontend/app/(platform)/app/capabilities/page.tsx`

Capabilities 页面有多个创建类型（HTTP / Code / MCP），默认弹出 HTTP 创建对话框：

```ts
React.useEffect(() => {
  const actionParam = searchParams.get('action')
  if (actionParam === 'create') {
    setHttpDialogOpen(true)
    const url = new URL(window.location.href)
    url.searchParams.delete('action')
    window.history.replaceState({}, '', url.toString())
  }
}, [searchParams])
```

**Validation**:
1. 从控制台点击"管理能力" → 跳转到 Capabilities 页面，HTTP Tool 创建 dialog 自动弹出
2. 直接访问 `/app/capabilities` → 不弹出 dialog

## Testing Strategy

- **Happy path**: 从控制台依次点击 4 个快捷操作，验证每个跳转后都自动弹出正确的创建对话框
- **Negative**: 直接访问目标页面 URL（不带 action 参数），确认不会弹出 dialog
- **Refresh safety**: 点击快捷操作跳转后刷新页面，确认不会重复弹出 dialog
- **Back navigation**: 通过浏览器返回按钮回到控制台，再点击快捷操作，确认功能正常

## Risks & Mitigation

- **Risk**: `window.history.replaceState` 在 Next.js App Router 中可能影响路由状态
  - **Mitigation**: 使用 `router.replace` 替代，保持与 Next.js 路由一致
- **Risk**: useEffect 依赖 `searchParams` 可能在 StrictMode 下触发两次
  - **Mitigation**: dialog 的 `setOpen(true)` 是幂等的，多次调用无副作用
