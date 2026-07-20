import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const getAPIKeys = mock()
const getStats = mock()
const deactivateAPIKey = mock()
const activateAPIKey = mock()
const getUsers = mock(() => Promise.resolve({ items: [] }))
const toastSuccess = mock()

function element(tag: string) {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

function Button({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
  return <button {...props}>{children}</button>
}

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  apiKeysApi: { getAPIKeys, getStats, deactivateAPIKey, activateAPIKey },
}))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => value }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('input') }))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('div'), SelectItem: element('option'),
  SelectTrigger: Button, SelectValue: element('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: Button,
  DropdownMenuSeparator: element('hr'), DropdownMenuTrigger: Button,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('div') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element('div'), TooltipContent: element('div'),
  TooltipTrigger: ({ render, ...props }: { render?: React.ReactElement }) => render ? React.cloneElement(render, props) : null,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('div'), AlertDialogAction: Button, AlertDialogCancel: Button,
  AlertDialogContent: element('div'), AlertDialogDescription: element('p'), AlertDialogFooter: element('footer'),
  AlertDialogHeader: element('header'), AlertDialogTitle: element('h2'),
}))
mock.module('lucide-react', () => ({
  Plus: element('svg'), Search: element('svg'), MoreHorizontal: element('svg'), Pencil: element('svg'),
  Trash2: element('svg'), Key: element('svg'), KeyRound: element('svg'), X: element('svg'),
  ChevronLeft: element('svg'), ChevronRight: element('svg'), ChevronsLeft: element('svg'),
  ChevronsRight: element('svg'), Power: element('svg'), PowerOff: element('svg'),
}))
mock.module('./api-key-dialog', () => ({
  APIKeyDialog: ({ open, onSuccess }: { open: boolean, onSuccess?: (key?: string) => void }) =>
    open ? <button onClick={() => onSuccess?.('new-secret')}>complete-create</button> : null,
}))
mock.module('./delete-api-key-dialog', () => ({ DeleteAPIKeyDialog: () => null }))
mock.module('./show-key-dialog', () => ({
  ShowKeyDialog: ({ open, apiKey }: { open: boolean, apiKey: string | null }) => open ? <span>shown:{apiKey}</span> : null,
}))

const { APIKeysClient } = await import('./api-keys-client')

const key = {
  id: 'key-1', name: 'Deploy key', key_prefix: 'clk_test', user_id: 'user-1',
  user: { id: 'user-1', username: 'Ada' }, scopes: [], rate_limit: 0, is_active: true,
  expires_at: null, last_used_at: null, agents: [], workflows: [],
  created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
}
const page = { items: [key], total: 1, page: 1, page_size: 10, pages: 1 }
const renderers: ReactTestRenderer[] = []

function render() {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<APIKeysClient />) })
  renderers.push(renderer!)
  return renderer!
}

async function settle() {
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  getAPIKeys.mockReset()
  getStats.mockReset()
  deactivateAPIKey.mockReset()
  activateAPIKey.mockReset()
  toastSuccess.mockReset()
})

describe('APIKeysClient', () => {
  test('loads and lists API keys', async () => {
    getAPIKeys.mockResolvedValue(page)
    getStats.mockResolvedValue({})

    const renderer = render()
    expect(JSON.stringify(renderer.toJSON())).toContain('loading')
    await settle()

    expect(getAPIKeys).toHaveBeenCalledWith({ page: 1, pageSize: 10, status: undefined, userId: undefined, search: undefined })
    expect(JSON.stringify(renderer.toJSON())).toContain('Deploy key')
    expect(JSON.stringify(renderer.toJSON())).toContain('clk_test')
    expect(JSON.stringify(renderer.toJSON())).toContain('...')
  })

  test('opens the created secret after the dialog succeeds', async () => {
    getAPIKeys.mockResolvedValue(page)
    getStats.mockResolvedValue({})
    const renderer = render()
    await settle()

    act(() => renderer.root.findAllByType('button').find((node) => node.children.includes('createKey'))!.props.onClick())
    act(() => renderer.root.findByProps({ children: 'complete-create' }).props.onClick())
    await settle()

    expect(JSON.stringify(renderer.toJSON())).toContain('shown')
    expect(JSON.stringify(renderer.toJSON())).toContain('new-secret')
    expect(getAPIKeys).toHaveBeenCalledTimes(2)
  })

  test('deactivates an active key and refreshes the list', async () => {
    getAPIKeys.mockResolvedValue(page)
    getStats.mockResolvedValue({})
    deactivateAPIKey.mockResolvedValue(key)
    const renderer = render()
    await settle()

    await act(async () => renderer.root.findAllByType('button').find((node) => node.children.includes('deactivate'))!.props.onClick())

    expect(deactivateAPIKey).toHaveBeenCalledWith('key-1')
    expect(toastSuccess).toHaveBeenCalledWith('keyDeactivated')
    expect(getAPIKeys).toHaveBeenCalledTimes(2)
  })

  test('leaves the empty state after a failed list request', async () => {
    getAPIKeys.mockRejectedValue(new Error('offline'))
    getStats.mockRejectedValue(new Error('offline'))
    const renderer = render()
    await settle()

    expect(JSON.stringify(renderer.toJSON())).toContain('noKeys')
  })
})
