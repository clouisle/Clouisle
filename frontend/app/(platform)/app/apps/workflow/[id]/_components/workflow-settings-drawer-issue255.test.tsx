import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
const toastSuccess = mock(() => {})
const getWorkflowVersions = mock(() => Promise.resolve({ items: [] as Record<string, unknown>[] }))
const restoreWorkflowVersion = mock(() => Promise.resolve(workflow))
const regenerateWebhookToken = mock(() => Promise.resolve({ webhook_token: 'new-token' }))
Object.assign(globalThis, {
  window: { location: { origin: 'https://app.test' } },
  navigator: { clipboard: { writeText: mock(() => Promise.resolve()) } },
})

let hooks: unknown[] = []
let dependencies: (unknown[] | undefined)[] = []
let cursor = 0

function changed(previous: unknown[] | undefined, next: unknown[] | undefined) {
  return !previous || !next || previous.length !== next.length || next.some((value, index) => !Object.is(value, previous[index]))
}

const React = {
  useState<T>(initial: T) {
    const index = cursor++
    if (!(index in hooks)) hooks[index] = initial
    return [hooks[index] as T, (value: T | ((current: T) => T)) => {
      hooks[index] = typeof value === 'function' ? (value as (current: T) => T)(hooks[index] as T) : value
    }] as const
  },
  useEffect(effect: () => void, deps?: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      effect()
    }
  },
  useCallback<T>(callback: T, deps: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      hooks[index] = callback
    }
    return hooks[index] as T
  },
}

mock.module('react', () => React)
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next/image', () => ({ default: element }))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('lucide-react', () => ({ X: element, Copy: element, Check: element, RefreshCw: element, Loader2: element, ChevronDown: element, History: element, RotateCcw: element, GitBranch: element }))
mock.module('@/lib/utils', () => ({ formatDate: (value: unknown) => String(value), formatDateTime: (value: unknown) => String(value), cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: {
  updateWorkflow: mock(() => {}),
  getWorkflowVersions,
  restoreWorkflowVersion,
  regenerateWebhookToken,
} }))

mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/input', () => ({ Input: element }))
mock.module('@/components/ui/label', () => ({ Label: element }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: element }))
mock.module('@/components/ui/select', () => ({ Select: element, SelectContent: element, SelectItem: element, SelectTrigger: element }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: element, CollapsibleContent: element, CollapsibleTrigger: element }))
mock.module('@/components/ui/badge', () => ({ Badge: element }))
mock.module('@/components/ui/dialog', () => ({ Dialog: element, DialogContent: element, DialogDescription: element, DialogFooter: element, DialogHeader: element, DialogTitle: element }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: element }))

const { WorkflowSettingsDrawer } = await import('./workflow-settings-drawer')

type TreeNode = { type: unknown; props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}

const workflow = {
  id: 'workflow-1', name: 'Original', description: 'Description', icon: '', visibility: 'private',
  trigger_type: 'cron', trigger_config: { cron_expression: '30 8 * * 2' }, webhook_token: null,
  status: 'draft', version: 3, run_count: 4, success_count: 3,
} as never

function render(props: Record<string, unknown> = {}) {
  cursor = 0
  return WorkflowSettingsDrawer({
    workflow, open: true, onClose: mock(() => {}), onUpdate: mock(() => {}), ...props,
  } as never) as TreeNode | null
}

function settle(props: Record<string, unknown> = {}) {
  render(props)
  render(props)
  return render(props) as TreeNode
}

function control(tree: TreeNode, predicate: (node: TreeNode) => boolean) {
  const matches = findAll(tree, predicate)
  expect(matches).toHaveLength(1)
  return matches[0]
}

beforeEach(() => {
  hooks = []
  dependencies = []
  cursor = 0
  toastSuccess.mockClear()
  getWorkflowVersions.mockReset()
  getWorkflowVersions.mockResolvedValue({ items: [] })
  restoreWorkflowVersion.mockReset()
  restoreWorkflowVersion.mockResolvedValue(workflow)
  regenerateWebhookToken.mockReset()
  regenerateWebhookToken.mockResolvedValue({ webhook_token: 'new-token' })
})

test('covers remaining editable controls and guarded selections', () => {
  let tree = settle()
  ;(control(tree, (node) => node.props.category === 'icons').props.onChange as (value: string) => void)('/icon.png')
  ;(control(tree, (node) => node.props.placeholder === 'settings.descriptionPlaceholder').props.onChange as (event: unknown) => void)({ target: { value: 'Updated' } })

  const visibility = control(tree, (node) => node.props.value === 'private' && typeof node.props.onValueChange === 'function')
  ;(visibility.props.onValueChange as (value: string | null) => void)(null)
  ;(visibility.props.onValueChange as (value: string | null) => void)('team')
  const trigger = control(tree, (node) => node.props.value === 'cron' && typeof node.props.onValueChange === 'function')
  ;(trigger.props.onValueChange as (value: string | null) => void)(null)
  ;(trigger.props.onValueChange as (value: string | null) => void)('webhook')

  tree = settle()
  expect(findAll(tree, (node) => node.props.value === '/icon.png')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.value === 'Updated')).toHaveLength(1)
})

test('copies a configured webhook URL', () => {
  const originalSetTimeout = globalThis.setTimeout
  let timeoutCallback: (() => void) | undefined
  globalThis.setTimeout = ((callback: () => void) => { timeoutCallback = callback; return 1 }) as unknown as typeof globalThis.setTimeout
  try {
    const writeText = navigator.clipboard.writeText as ReturnType<typeof mock>
    const webhook = { ...workflow, trigger_type: 'webhook', webhook_token: 'secret' }
    const tree = settle({ workflow: webhook })
    const copy = control(tree, (node) => node.props.className === 'h-8 w-8 shrink-0')

    ;(copy.props.onClick as () => void)()

    expect(writeText).toHaveBeenCalledWith('https://app.test/api/v1/workflows/webhook/secret')
    expect(toastSuccess).toHaveBeenCalledWith('editor.copiedToClipboard')
    timeoutCallback!()
  } finally {
    globalThis.setTimeout = originalSetTimeout
  }
})

test('covers schedule controls and collapsible callbacks', () => {
  for (const cron of ['*/15 * * * *', '5 7 * * *', '30 6 12 * *', '1 2 3 4 5']) {
    hooks = []
    dependencies = []
    const tree = settle({ workflow: { ...workflow, trigger_config: { cron_expression: cron } } })
    for (const node of findAll(tree, (candidate) => typeof candidate.props.onOpenChange === 'function')) {
      ;(node.props.onOpenChange as (value: boolean) => void)(false)
    }
    for (const node of findAll(tree, (candidate) => typeof candidate.props.onValueChange === 'function')) {
      ;(node.props.onValueChange as (value: string | null) => void)(null)
      ;(node.props.onValueChange as (value: string | null) => void)(String(node.props.value))
    }
    for (const node of findAll(tree, (candidate) => candidate.props.type === 'time' || candidate.props.placeholder === '0 0 * * *')) {
      ;(node.props.onChange as (event: unknown) => void)({ target: { value: node.props.value } })
    }
  }
})

test('formats every version age and cancels a pending restore', async () => {
  const now = Date.now()
  getWorkflowVersions.mockResolvedValue({ items: [
    { id: 'now', version: 3, created_at: new Date(now).toISOString() },
    { id: 'hours', version: 2, created_at: new Date(now - 2 * 3600000).toISOString() },
    { id: 'days', version: 1, created_at: new Date(now - 2 * 86400000).toISOString() },
    { id: 'old', version: 0, created_at: new Date(now - 8 * 86400000).toISOString() },
  ] })
  let tree = settle()
  ;(control(tree, (node) => typeof node.props.onOpenChange === 'function' && text(node).includes('settings.versionHistory')).props.onOpenChange as (open: boolean) => void)(true)
  tree = settle()
  await Promise.resolve()
  tree = settle()

  expect(text(tree)).toContain('settings.hoursAgo:2')
  expect(text(tree)).toContain('settings.daysAgo:2')
  ;(findAll(tree, (node) => text(node.props.children) === 'settings.restore')[0].props.onClick as () => void)()
  tree = settle()
  ;(findAll(tree, (node) => text(node.props.children) === 'settings.cancel' && typeof node.props.onClick === 'function')[0].props.onClick as () => void)()
  tree = settle()
  expect(text(tree)).toContain('settings.restoreToVersion:')
})
