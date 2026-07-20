import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
const toastSuccess = mock(() => {})

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
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('lucide-react', () => ({ X: element, Copy: element, Check: element, RefreshCw: element, Loader2: element, ChevronDown: element, History: element, RotateCcw: element, GitBranch: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: {
  updateWorkflow: mock(() => {}),
  getWorkflowVersions: mock(() => Promise.resolve({ items: [] })),
  restoreWorkflowVersion: mock(() => {}),
  regenerateWebhookToken: mock(() => {}),
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
