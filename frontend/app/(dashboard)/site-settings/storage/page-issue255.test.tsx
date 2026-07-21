import { beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void> = []
const success = mock(() => {})
const error = mock(() => {})
const getAll = mock(() => Promise.resolve({}))
const bulkUpdate = mock(() => Promise.resolve({}))
const archiveAuditLogs = mock(() => Promise.resolve({ task_id: 'task-1' }))
const getArchiveTaskStatus = mock(() => Promise.resolve({ status: 'SUCCESS', result: { archived_count: 4 } }))

const components = new Proxy<Record<string, (props: Record<string, unknown>) => ReactElement>>({}, {
  get: (target, key: string) => target[key] ??= (props) => ({ type: key, props, key: null }),
})
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = typeof initial === 'function' ? initial() : initial
    return [states[index], (value: unknown) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: unknown) => unknown)(states[index])
        : value
    }]
  },
  useEffect: (callback: () => void) => effects.push(callback),
  useCallback: (callback: unknown) => callback,
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: { count?: number }) => values ? `${key}:${values.count}` : key }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('lucide-react', () => ({ Loader2: 'loader', Archive: 'archive', Database: 'database', FileText: 'file' }))
mock.module('@/components/ui/card', () => ({ Card: components.Card, CardContent: components.CardContent, CardDescription: components.CardDescription, CardHeader: components.CardHeader, CardTitle: components.CardTitle }))
mock.module('@/components/ui/input', () => ({ Input: components.Input }))
mock.module('@/components/ui/switch', () => ({ Switch: components.Switch }))
mock.module('@/components/ui/select', () => ({ Select: components.Select, SelectContent: components.SelectContent, SelectItem: components.SelectItem, SelectTrigger: components.SelectTrigger, SelectValue: components.SelectValue }))
mock.module('@/components/ui/number-input', () => ({ NumberInput: components.NumberInput }))
mock.module('@/components/ui/label', () => ({ Label: components.Label }))
mock.module('@/components/ui/button', () => ({ Button: components.Button }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: components.Skeleton }))
mock.module('@/components/ui/field', () => ({ FieldError: components.FieldError }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: components.AlertDialog, AlertDialogAction: components.AlertDialogAction, AlertDialogCancel: components.AlertDialogCancel, AlertDialogContent: components.AlertDialogContent, AlertDialogDescription: components.AlertDialogDescription, AlertDialogFooter: components.AlertDialogFooter, AlertDialogHeader: components.AlertDialogHeader, AlertDialogTitle: components.AlertDialogTitle }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getAll, bulkUpdate, archiveAuditLogs, getArchiveTaskStatus },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: (errors: Record<string, string>) => errors,
  normalizeValidationErrors: (value: { errors?: Record<string, string> }) => value.errors ?? {},
  formatValidationSummaryMessage: (field: string, message: string) => `${field}:${message}`,
}))
mock.module('@/lib/constants', () => ({
  KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB: 10,
  KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB: 1,
  KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB: 100,
}))

type Page = typeof import('./page').default
let Page: Page

function render() {
  stateIndex = 0
  effects = []
  return Page()
}

async function load() {
  render()
  for (const effect of effects) effect()
  await Promise.resolve()
  await Promise.resolve()
  return render()
}

function findAll(node: ReactNode, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (!node || typeof node !== 'object') return []
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, type))
  const element = node as ReactElement<Record<string, unknown>>
  return [...(element.type === type ? [element] : []), ...findAll(element.props?.children as ReactNode, type)]
}

beforeAll(async () => {
  ({ default: Page } = await import('./page'))
})

beforeEach(() => {
  states = []
  effects = []
  success.mockClear()
  error.mockClear()
  getAll.mockClear()
  bulkUpdate.mockClear()
  archiveAuditLogs.mockClear()
  getArchiveTaskStatus.mockClear()
  getAll.mockImplementation(() => Promise.resolve({
    audit_log_retention_days: 90,
    audit_log_archive_path: '/archive',
    kb_document_max_upload_size_mb: 20,
    upload_storage_backend: 's3',
    object_storage_endpoint: 'https://storage.test',
    object_storage_bucket: 'bucket',
    object_storage_access_key: 'access',
    object_storage_secret_key: 'secret',
  }))
  bulkUpdate.mockImplementation(() => Promise.resolve({}))
})

describe('SiteSettingsStoragePage', () => {
  test('loads object storage, updates fields, validates, and saves', async () => {
    let tree = await load()
    expect(getAll).toHaveBeenCalledWith('storage')

    const select = findAll(tree, components.Select)[0]
    select.props.onValueChange?.('invalid')
    select.props.onValueChange?.('local')
    tree = render()
    findAll(tree, components.NumberInput)[0].props.onChange?.('')
    findAll(tree, components.NumberInput)[1].props.onChange?.(30)
    findAll(tree, components.Input)[0].props.onChange?.({ target: { value: '' } })
    tree = render()
    await findAll(tree, components.Button).at(-1)?.props.onClick?.()
    expect(bulkUpdate).not.toHaveBeenCalled()

    findAll(tree, components.Input)[0].props.onChange?.({ target: { value: '/new-archive' } })
    tree = render()
    await findAll(tree, components.Button).at(-1)?.props.onClick?.()
    expect(bulkUpdate).toHaveBeenCalledWith(expect.objectContaining({
      audit_log_archive_path: '/new-archive',
      kb_document_max_upload_size_mb: 10,
      upload_storage_backend: 'local',
    }))
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('maps save errors and completes archive polling', async () => {
    bulkUpdate.mockRejectedValueOnce({ errors: { audit_log_archive_path: 'bad path' } })
    let tree = await load()
    await findAll(tree, components.Button).at(-1)?.props.onClick?.()
    tree = render()
    expect(findAll(tree, components.FieldError).some(({ props }) => props.children === 'audit_log_archive_path:bad path')).toBe(true)

    const originalSetInterval = globalThis.setInterval
    const originalSetTimeout = globalThis.setTimeout
    globalThis.setInterval = ((callback: () => void) => { void callback(); return 1 }) as typeof setInterval
    globalThis.setTimeout = (() => 2) as typeof setTimeout
    try {
      findAll(tree, components.Button)[0].props.onClick?.()
      tree = render()
      await findAll(tree, components.AlertDialogAction)[0].props.onClick?.()
      await Promise.resolve()
      expect(archiveAuditLogs).toHaveBeenCalledTimes(1)
      expect(getArchiveTaskStatus).toHaveBeenCalledWith('task-1')
      expect(success).toHaveBeenCalledWith('archiveSuccess:4')
    } finally {
      globalThis.setInterval = originalSetInterval
      globalThis.setTimeout = originalSetTimeout
    }
  })
})
