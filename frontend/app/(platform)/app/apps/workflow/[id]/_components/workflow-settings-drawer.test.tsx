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

test('returns no drawer without a workflow and enforces the read-only boundary', () => {
  expect(render({ workflow: null })).toBeNull()

  const tree = settle({ readOnly: true })
  expect(findAll(tree, (node) => node.props.children === 'settings.readOnlyNotice')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.disabled === true).length).toBeGreaterThan(4)
  expect(findAll(tree, (node) => node.props.children === 'settings.save')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.children === 'settings.close')).toHaveLength(1)
})

test('validates the required name and saves a cron generated from the parsed weekly schedule', async () => {
  const updateWorkflow = mock(async (_id: string, data: unknown) => ({ ...workflow, ...(data as object) }))
  const onUpdate = mock(() => {})
  let tree = settle({ updateWorkflow, onUpdate })

  const name = control(tree, (node) => node.props.value === 'Original')
  ;(name.props.onChange as (event: unknown) => void)({ target: { value: '' } })
  tree = settle({ updateWorkflow, onUpdate })
  expect(control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children) === 'settings.save').props.disabled).toBe(true)

  ;(control(tree, (node) => node.props.placeholder === 'settings.namePlaceholder').props.onChange as (event: unknown) => void)({ target: { value: 'Renamed' } })
  tree = settle({ updateWorkflow, onUpdate })
  ;(control(tree, (node) => node.props.type === 'time').props.onChange as (event: unknown) => void)({ target: { value: '09:45' } })
  tree = settle({ updateWorkflow, onUpdate })

  const save = control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children) === 'settings.save')
  expect(save.props.disabled).toBe(false)
  await (save.props.onClick as () => Promise<void>)()

  expect(updateWorkflow).toHaveBeenCalledWith('workflow-1', {
    name: 'Renamed', description: 'Description', icon: null, trigger_type: 'cron',
    trigger_config: { cron_expression: '45 9 * * 2' }, visibility: 'private',
  })
  expect(onUpdate).toHaveBeenCalledTimes(1)
  expect(toastSuccess).toHaveBeenCalledWith('settings.settingsSaved')
})

test('keeps edits retryable when saving fails', async () => {
  const updateWorkflow = mock(() => Promise.reject(new Error('network unavailable')))
  const onUpdate = mock(() => {})
  let tree = settle({ updateWorkflow, onUpdate })
  ;(control(tree, (node) => node.props.value === 'Original').props.onChange as (event: unknown) => void)({ target: { value: 'Retry me' } })
  tree = settle({ updateWorkflow, onUpdate })

  await (control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children) === 'settings.save').props.onClick as () => Promise<void>)()
  tree = settle({ updateWorkflow, onUpdate })

  expect(control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children) === 'settings.save').props.disabled).toBe(false)
  expect(onUpdate).not.toHaveBeenCalled()
  expect(toastSuccess).not.toHaveBeenCalled()
})

test('parses interval, daily, monthly, and custom schedules into save payloads', async () => {
  const cases = [
    ['*/15 * * * *', '*/15 * * * *'],
    ['0 */2 * * *', '0 */2 * * *'],
    ['5 7 * * *', '5 7 * * *'],
    ['30 6 12 * *', '30 6 12 * *'],
    ['1 2 3 4 5', '1 2 * * 5'],
  ]

  for (const [source, expected] of cases) {
    hooks = []
    dependencies = []
    const updateWorkflow = mock(async (_id: string, data: unknown) => ({ ...workflow, ...(data as object) }))
    const configured = { ...workflow, trigger_config: { cron_expression: source } }
    let tree = settle({ workflow: configured, updateWorkflow })
    ;(control(tree, (node) => node.props.value === 'Original').props.onChange as (event: unknown) => void)({ target: { value: 'Changed' } })
    tree = settle({ workflow: configured, updateWorkflow })
    await (control(tree, (node) => text(node.props.children) === 'settings.save').props.onClick as () => Promise<void>)()
    expect(updateWorkflow.mock.calls[0][1]).toMatchObject({ trigger_config: { cron_expression: expected } })
  }
})

test('preserves edits to a custom cron expression', async () => {
  const configured = { ...workflow, trigger_config: { cron_expression: '1/2 3 * * *' } }
  const updateWorkflow = mock(async (_id: string, data: unknown) => ({ ...configured, ...(data as object) }))
  let tree = settle({ workflow: configured, updateWorkflow })

  const cron = control(tree, (node) => node.props.placeholder === '0 0 * * *')
  ;(cron.props.onChange as (event: unknown) => void)({ target: { value: '2/3 4 * * *' } })
  tree = settle({ workflow: configured, updateWorkflow })
  await (control(tree, (node) => text(node.props.children) === 'settings.save').props.onClick as () => Promise<void>)()

  expect(updateWorkflow).toHaveBeenCalledWith('workflow-1', expect.objectContaining({
    trigger_config: { cron_expression: '2/3 4 * * *' },
  }))
})

test('loads version history and restores a selected non-current version', async () => {
  const version = { id: 'version-2', version: 2, description: 'Previous', created_at: new Date().toISOString() }
  getWorkflowVersions.mockResolvedValue({ items: [version] })
  const onUpdate = mock(() => {})
  let tree = settle({ onUpdate })

  const history = control(tree, (node) => typeof node.props.onOpenChange === 'function' && text(node.props.children).includes('settings.versionHistory'))
  ;(history.props.onOpenChange as (open: boolean) => void)(true)
  tree = settle({ onUpdate })
  await Promise.resolve()
  tree = settle({ onUpdate })

  expect(getWorkflowVersions).toHaveBeenCalledWith('workflow-1', { pageSize: 50 })
  const restore = control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children) === 'settings.restore')
  ;(restore.props.onClick as () => void)()
  tree = settle({ onUpdate })
  await (control(tree, (node) => text(node.props.children) === 'settings.confirmRestore').props.onClick as () => Promise<void>)()

  expect(restoreWorkflowVersion).toHaveBeenCalledWith('workflow-1', 2)
  expect(onUpdate).toHaveBeenCalledWith(workflow)
  expect(toastSuccess).toHaveBeenCalledWith('settings.restoredToVersion:2')
})

test('regenerates a webhook token and keeps failed regeneration retryable', async () => {
  const webhook = { ...workflow, trigger_type: 'webhook', webhook_token: null }
  let tree = settle({ workflow: webhook })
  let regenerate = control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children).includes('settings.regenerate'))
  await (regenerate.props.onClick as () => Promise<void>)()
  tree = settle({ workflow: webhook })

  expect(regenerateWebhookToken).toHaveBeenCalledWith('workflow-1')
  expect(findAll(tree, (node) => String(node.props.value).includes('new-token'))).toHaveLength(1)
  expect(toastSuccess).toHaveBeenCalledWith('settings.webhookTokenRegenerated')

  regenerateWebhookToken.mockRejectedValueOnce(new Error('temporary'))
  regenerate = control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children).includes('settings.regenerate'))
  await (regenerate.props.onClick as () => Promise<void>)()
  tree = settle({ workflow: webhook })
  expect(control(tree, (node) => typeof node.props.onClick === 'function' && text(node.props.children).includes('settings.regenerate')).props.disabled).toBe(false)
})
