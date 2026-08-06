import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const adminList = mock()
const adminDelete = mock(async () => {})
const toastSuccess = mock(() => {})
let searchState = ''

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => {
    const t = (key: string, values?: Record<string, unknown>) => values?.count === undefined ? key : `${key}:${values.count}`
    t.has = (key: string) => !key.endsWith('.webhook') && !key.endsWith('.unknown')
    return t
  },
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => Object.fromEntries(['Plus', 'Trash2', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'Search', 'X', 'Mail', 'MessageSquare', 'CheckCircle2', 'XCircle', 'Loader2', 'Clock', 'Eye', 'MoreHorizontal'].map((name) => [name, () => null])))
mock.module('@/lib/api/admin/notifications', () => ({ notificationsApi: { adminList, adminDelete } }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => {
    const [, update] = React.useState(searchState)
    return [searchState, (value: string) => { searchState = value; update(value) }] as const
  },
}))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
const Button = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>
const FacetedFilter = ({ title, options, onSelectionChange }: { title: string; options: unknown[]; onSelectionChange: (values: Set<string>) => void }) => (
  <button data-filter={title} data-options={JSON.stringify(options)} onClick={() => onSelectionChange(new Set())}>{title}</button>
)
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, indeterminate, onCheckedChange }: { checked: boolean; indeterminate?: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} data-indeterminate={indeterminate} onChange={(event) => onCheckedChange(event.target.checked)} /> }))
mock.module('@/components/ui/table', () => ({ Table: passthrough, TableBody: passthrough, TableCell: passthrough, TableHead: passthrough, TableHeader: passthrough, TableRow: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div> }))
mock.module('@/components/ui/select', () => ({ Select: ({ children, onValueChange, ...props }: React.PropsWithChildren<{ onValueChange: (value: string) => void }>) => <select {...props} onChange={(event) => onValueChange(event.target.value)}>{children}</select>, SelectContent: passthrough, SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>, SelectTrigger: passthrough, SelectValue: passthrough }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough, DropdownMenuContent: passthrough, DropdownMenuItem: Button, DropdownMenuTrigger: passthrough }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: FacetedFilter }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough, TooltipContent: passthrough, TooltipTrigger: ({ render, children, ...props }: React.PropsWithChildren<{ render?: React.ReactElement }> & Record<string, unknown>) => render ? React.cloneElement(render, props) : <button {...props}>{children}</button> }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <>{children}</> : null, AlertDialogAction: Button, AlertDialogCancel: passthrough, AlertDialogContent: passthrough, AlertDialogDescription: passthrough, AlertDialogFooter: passthrough, AlertDialogHeader: passthrough, AlertDialogTitle: passthrough }))
mock.module('./create-notification-dialog', () => ({ CreateNotificationDialog: ({ open, onOpenChange, onSuccess }: { open: boolean; onOpenChange: (value: boolean) => void; onSuccess: () => void }) => <div data-testid="create" data-open={open}><button onClick={() => onOpenChange(false)}>close-create</button><button onClick={onSuccess}>created</button></div> }))
mock.module('./notification-detail-dialog', () => ({ NotificationDetailDialog: ({ notification, open, onOpenChange }: { notification: unknown; open: boolean; onOpenChange: (value: boolean) => void }) => <div data-testid="detail" data-open={open} data-selected={notification ? 'yes' : 'no'}><button onClick={() => onOpenChange(false)}>close-detail</button></div> }))

const { NotificationsAdminClient } = await import('./notifications-admin-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const deliveries = [
  { channel: 'email', status: 'success', error_message: null, retry_count: 0 },
  { channel: 'dingtalk', status: 'failed', error_message: 'no route', retry_count: 2 },
  { channel: 'webhook', status: 'sending', error_message: null, retry_count: 0 },
  { channel: 'unknown', status: 'pending', error_message: null, retry_count: 0 },
]
const item = { id: 'n1', title: 'First', scope: 'global', level: 'high', created_at: 'now', deliveries }
const second = { ...item, id: 'n2', title: 'Second', scope: 'custom', level: 'custom', deliveries: [] }
const result = (items = [item, second], total = items.length) => ({ items, total, page: 1, page_size: 10 })
const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  searchState = ''
  adminList.mockReset(); adminList.mockResolvedValue(result())
  adminDelete.mockReset(); adminDelete.mockResolvedValue(undefined)
  toastSuccess.mockClear()
})
afterEach(() => { for (const renderer of renderers) act(() => renderer.unmount()); renderers.length = 0 })

function render() {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<NotificationsAdminClient />) })
  renderers.push(renderer!)
  return renderer!
}
async function settle() { await act(async () => {}) }
function buttons(renderer: ReactTestRenderer, text: string) { return renderer.root.findAllByType('button').filter((button) => button.findAll((node) => node.children.includes(text)).length > 0) }
function checkboxes(renderer: ReactTestRenderer) { return renderer.root.findAllByProps({ type: 'checkbox' }) }
function selectedRows(renderer: ReactTestRenderer) { return renderer.root.findAllByProps({ 'data-state': 'selected' }).filter((node) => typeof node.type === 'string') }

 describe('notifications admin client issue 255 coverage', () => {
  test('loads rows and covers delivery icons, translated labels, and fallbacks', async () => {
    const renderer = render()
    expect(JSON.stringify(renderer.toJSON())).toContain('loading')
    await settle()
    expect(adminList).toHaveBeenCalledWith({ page: 1, page_size: 10, scope: undefined, level: undefined, search: undefined })
    const output = JSON.stringify(renderer.toJSON())
    expect(output).toContain('retryCount:2')
    expect(output).toContain('no route')
    expect(output).toContain('custom')
    expect(output).toContain('date:now')
  })

  test('shows empty state after a failed fetch', async () => {
    adminList.mockRejectedValueOnce(new Error('offline'))
    const renderer = render(); await settle()
    expect(JSON.stringify(renderer.toJSON())).toContain('empty')
  })

  test('applies search and both filters, then resets all filters', async () => {
    const renderer = render(); await settle()
    act(() => renderer.root.findByProps({ placeholder: 'searchPlaceholder' }).props.onChange({ target: { value: '  urgent  ' } }))
    const filters = renderer.root.findAllByType(FacetedFilter)
    act(() => filters[0].props.onSelectionChange(new Set(['team'])))
    act(() => filters[1].props.onSelectionChange(new Set(['low'])))
    await settle()
    expect(adminList).toHaveBeenLastCalledWith({ page: 1, page_size: 10, scope: ['team'], level: ['low'], search: 'urgent' })
    await act(async () => buttons(renderer, 'reset')[0].props.onClick())
    await settle()
    expect(adminList).toHaveBeenLastCalledWith({ page: 1, page_size: 10, scope: undefined, level: undefined, search: undefined })
  })

  test('selects all, deselects all, toggles one, and clears the bulk toolbar', async () => {
    const renderer = render(); await settle()
    act(() => checkboxes(renderer)[0].props.onChange({ target: { checked: true } }))
    expect(selectedRows(renderer)).toHaveLength(2)
    act(() => checkboxes(renderer)[0].props.onChange({ target: { checked: false } }))
    act(() => checkboxes(renderer)[1].props.onChange({ target: { checked: true } }))
    expect(selectedRows(renderer)).toHaveLength(1)
    act(() => checkboxes(renderer)[1].props.onChange({ target: { checked: false } }))
    expect(selectedRows(renderer)).toHaveLength(0)
  })

  test('opens detail from a row, ignores interactive row targets, and closes detail', async () => {
    const renderer = render(); await settle()
    const row = renderer.root.findAll((node) => node.props.className === 'cursor-pointer')[0]
    act(() => row.props.onClick({ target: { closest: () => null } }))
    expect(renderer.root.findByProps({ 'data-testid': 'detail' }).props).toMatchObject({ 'data-open': true, 'data-selected': 'yes' })
    act(() => buttons(renderer, 'close-detail')[0].props.onClick())
    act(() => row.props.onClick({ target: { closest: () => ({}) } }))
    expect(renderer.root.findByProps({ 'data-testid': 'detail' }).props['data-open']).toBe(false)
  })

  test('opens create, closes it, and refreshes after success', async () => {
    const renderer = render(); await settle()
    act(() => buttons(renderer, 'admin.create')[0].props.onClick())
    expect(renderer.root.findByProps({ 'data-testid': 'create' }).props['data-open']).toBe(true)
    act(() => buttons(renderer, 'close-create')[0].props.onClick())
    await act(async () => buttons(renderer, 'created')[0].props.onClick())
    expect(adminList.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  test('deletes one notification and closes after a request failure', async () => {
    const renderer = render(); await settle()
    await act(async () => buttons(renderer, 'delete')[0].props.onClick())
    await act(async () => buttons(renderer, 'delete')[buttons(renderer, 'delete').length - 1].props.onClick())
    expect(adminDelete).toHaveBeenCalledWith('n1')
    expect(toastSuccess).toHaveBeenCalledWith('toast.deleted')

    adminDelete.mockRejectedValueOnce(new Error('delete'))
    await act(async () => buttons(renderer, 'delete')[0].props.onClick())
    await act(async () => buttons(renderer, 'delete')[buttons(renderer, 'delete').length - 1].props.onClick())
  })

  test('bulk deletes selected notifications and covers the failure path', async () => {
    const renderer = render(); await settle()
    act(() => checkboxes(renderer)[0].props.onChange({ target: { checked: true } }))
    const bulkTrigger = renderer.root.findAllByType('button').find((button) => button.props.className?.includes('hover:bg-destructive'))!
    await act(async () => bulkTrigger.props.onClick())
    await act(async () => buttons(renderer, 'admin.delete')[0].props.onClick())
    expect(adminDelete).toHaveBeenCalledWith('n1')
    expect(adminDelete).toHaveBeenCalledWith('n2')
    expect(toastSuccess).toHaveBeenCalledWith('toast.bulkDeleted:2')

    act(() => checkboxes(renderer)[0].props.onChange({ target: { checked: true } }))
    adminDelete.mockRejectedValueOnce(new Error('bulk'))
    await act(async () => renderer.root.findAllByType('button').find((button) => button.props.className?.includes('hover:bg-destructive'))!.props.onClick())
    await act(async () => buttons(renderer, 'admin.delete')[0].props.onClick())
  })

  test('changes page size and exercises every pagination callback', async () => {
    adminList.mockResolvedValue(result([item], 45))
    const renderer = render(); await settle()
    act(() => renderer.root.findByType('select').props.onChange({ target: { value: '20' } })); await settle()
    expect(adminList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))
    const paging = renderer.root.findAllByType('button').filter((button) => button.props.className === 'h-8 w-8')
    act(() => paging[2].props.onClick()); await settle()
    expect(adminList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    act(() => paging[1].props.onClick()); await settle()
    act(() => paging[3].props.onClick()); await settle()
    expect(adminList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    act(() => paging[0].props.onClick()); await settle()
    expect(adminList).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))
  })
})
