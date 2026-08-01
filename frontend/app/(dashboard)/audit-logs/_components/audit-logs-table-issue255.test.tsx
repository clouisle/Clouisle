import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'
import * as React from 'react'
import type { AuditLog } from '@/lib/api/admin/audit-logs'

let stateValues: unknown[] = []
let setters: Array<ReturnType<typeof mock>> = []
let stateIndex = 0
let search = ''
const setSearch = mock(() => {})

mock.module('react', () => ({
  ...React,
  useEffect: () => {},
  useMemo: (factory: () => unknown) => factory(),
  useState: (initial: unknown) => {
    const index = stateIndex++
    return [stateValues[index] ?? initial, setters[index]]
  },
}))

const translate = Object.assign(
  (key: string, values?: { page: number; total: number }) =>
    values ? `${key}:${values.page}/${values.total}` : key,
  { has: (key: string) => key !== 'operationUnknown' },
)

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => [search, setSearch],
}))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({
  WorkflowRunDrawer: ({ open }: { open: boolean }) => (open ? React.createElement('aside', { role: 'dialog', 'aria-label': 'workflow-run' }) : null),
}))

const { AuditLogsTable } = await import('./audit-logs-table')

const log: AuditLog = {
  id: 'log-1',
  created_at: '2026-07-22T10:30:00Z',
  status: 'success',
  action: 'user.created',
  operation: 'create',
  username: null,
  resource_type: 'user',
  resource_name: null,
  ip_address: null,
}

function elements(node: ReactNode): ReactElement[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (node && typeof node === 'object' && 'props' in node) {
    const element = node as ReactElement<{ children?: ReactNode }>
    return [element, ...elements(element.props.children)]
  }
  return []
}

function render(values: unknown[], searchValue = '') {
  stateValues = values
  search = searchValue
  setters = Array.from({ length: 12 }, () => mock(() => {}))
  stateIndex = 0
  return elements(AuditLogsTable())
}

beforeEach(() => {
  setSearch.mockClear()
})

describe('AuditLogsTable', () => {
  test('renders empty and populated table branches', () => {
    const empty = render([[], false, 1, 20, 0, null, false, null, false, [], []])
    expect(empty.some((element) => element.props.children === 'noLogs')).toBe(true)

    const populated = render([[log], false, 1, 20, 2, null, false, null, false, [
      { value: 'user.created', translation_key: 'auditLogs.actionUserCreated', fallback_label: 'Created user' },
    ], []])
    const text = populated.map((element) => element.props.children).flat()

    expect(text).toContain('actionUserCreated')
    expect(text).toContain('system')
    expect(text).toContain('-')
    expect(text).toContain('statusSuccess')
    expect(text).toContain('operationCreate')
  })

  test('updates search and faceted filters and resets them', () => {
    const rendered = render([[], false, 3, 20, 4, null, false, null, false, [], ['failed'], ['user.created']], 'existing')
    const input = rendered.find((element) => element.props.placeholder === 'searchPlaceholder')
    const filters = rendered.filter((element) => typeof element.props.onSelectionChange === 'function')
    const reset = rendered.find((element) => element.props.variant === 'ghost' && element.props.className?.includes('h-8'))

    input?.props.onChange({ target: { value: 'alice' } })
    filters[0].props.onSelectionChange(new Set(['success']))
    filters[1].props.onSelectionChange(new Set(['role.updated']))
    reset?.props.onClick()

    expect(setSearch).toHaveBeenNthCalledWith(1, 'alice')
    expect(setSearch).toHaveBeenNthCalledWith(2, '')
    expect(setters[2]).toHaveBeenCalledWith(1)
    expect(setters[10]).toHaveBeenCalledWith(['success'])
    expect(setters[11]).toHaveBeenCalledWith(['role.updated'])
  })

  test('opens details from a row unless text is selected', () => {
    const rendered = render([[log], false, 1, 20, 2, null, false, null, false, [], []])
    const row = rendered.find((element) => element.props.className === 'cursor-pointer hover:bg-muted/50')

    globalThis.window = { getSelection: () => ({ toString: () => '' }) } as unknown as Window & typeof globalThis
    row?.props.onClick()
    expect(setters[5]).toHaveBeenCalledWith(log)
    expect(setters[6]).toHaveBeenCalledWith(true)

    setters[5].mockClear()
    globalThis.window = { getSelection: () => ({ toString: () => 'selected' }) } as unknown as Window & typeof globalThis
    row?.props.onClick()
    expect(setters[5]).not.toHaveBeenCalled()
  })
})
