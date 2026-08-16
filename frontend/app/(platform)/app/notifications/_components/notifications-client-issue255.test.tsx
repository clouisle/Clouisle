import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const item = {
  id: 'notification-1',
  scope: 'team',
  type: 'workflow.run_failed',
  source: 'system',
  title: 'Workflow failed',
  content: 'The run stopped.',
  level: 'high',
  status: 'active',
  created_at: '2026-07-20T12:00:00Z',
  updated_at: '2026-07-20T12:00:00Z',
  is_read: false,
}
const list = mock(async () => ({ items: [item], total: 41, page: 1, page_size: 20 }))
const markRead = mock(async () => ({ updated: 1 }))
const toastSuccess = mock(() => undefined)

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('next/dynamic', () => ({ default: () => ({ source }: { source: string }) => <article>{source}</article> }))
mock.module('lucide-react', () => ({
  Check: () => null,
  ChevronLeft: () => null,
  ChevronRight: () => null,
  Megaphone: () => null,
  Search: () => null,
  ShieldAlert: () => null,
  Sparkles: () => null,
  X: () => null,
}))
mock.module('@/lib/api', () => ({ notificationsApi: { list, markRead } }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/lib/notifications/display', () => ({
  getNotificationDisplayMeta: () => ({ kind: 'delivery', isAnnouncement: false, priorityScore: 5 }),
  getPauseActionMeta: () => null,
}))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: unknown) => String(value), cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))

const element = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: element }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, onSelectionChange }: { title: string; onSelectionChange: (values: Set<string>) => void }) =>
    <button data-filter={title} onClick={() => onSelectionChange(new Set(['first', 'last']))}>{title}</button>,
}))
mock.module('@/components/ui/table', () => ({
  Table: element,
  TableBody: element,
  TableCell: element,
  TableHead: element,
  TableHeader: element,
  TableRow: element,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => <section data-open={open}>{children}</section>,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}))
mock.module('@/components/chat/pause-request-actions', () => ({
  PauseRequestActions: () => null,
}))

const { NotificationsClient } = await import('./notifications-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  list.mockReset()
  list.mockImplementation(async () => ({ items: [item], total: 41, page: 1, page_size: 20 }))
  markRead.mockReset()
  markRead.mockImplementation(async () => ({ updated: 1 }))
  toastSuccess.mockClear()
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

async function renderClient(onReadUpdated = mock(() => undefined)) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<NotificationsClient onReadUpdated={onReadUpdated} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onReadUpdated }
}

function nodeText(node: { children: Array<unknown> }): string {
  return node.children.map((child) => typeof child === 'string' ? child : child && typeof child === 'object' && 'children' in child
    ? nodeText(child as { children: Array<unknown> })
    : '').join('')
}

function button(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').find((node) => nodeText(node) === label)!
}

describe('notifications client issue 255 callbacks', () => {
  test('applies filters, search, pagination, and opens notification detail', async () => {
    const { renderer } = await renderClient()

    await act(async () => {
      renderer.root.findByProps({ 'data-filter': 'scope' }).props.onClick()
    })
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'last', page: 1 }))

    const search = renderer.root.findByType('input')
    await act(async () => search.props.onChange({ target: { value: 'failed' } }))
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'failed' }))

    const notification = renderer.root.findAllByType('button').find((node) => nodeText(node).includes('Workflow failed'))!
    await act(async () => notification.props.onClick())
    expect(renderer.root.findByProps({ 'data-open': true })).toBeDefined()
    expect(renderer.root.findByType('article').children).toEqual(['The run stopped.'])

    const pagination = renderer.root.findAllByType('button').filter((node) => node.props.className === 'cursor-pointer')
    await act(async () => pagination.at(-1)!.props.onClick())
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    const previous = renderer.root.findAllByType('button').find((node) => node.props.className === 'cursor-pointer' && node.props.disabled === false)!
    await act(async () => previous.props.onClick())
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))
  })

  test('reports list and mark-read failures without firing success callbacks', async () => {
    const listError = new Error('list unavailable')
    const markError = new Error('mark unavailable')
    const consoleError = mock(() => undefined)
    const originalConsoleError = console.error
    console.error = consoleError
    list.mockRejectedValueOnce(listError).mockImplementation(async () => ({ items: [item], total: 1, page: 1, page_size: 20 }))

    const { renderer, onReadUpdated } = await renderClient()
    expect(consoleError).toHaveBeenCalledWith('Failed to fetch notifications:', listError)

    await act(async () => button(renderer, 'scope').props.onClick())
    markRead.mockRejectedValue(markError)
    await act(async () => button(renderer, 'markRead').props.onClick({ stopPropagation: mock(() => undefined) }))
    await act(async () => button(renderer, 'markAllRead').props.onClick())

    expect(consoleError).toHaveBeenCalledWith('Failed to mark read:', markError)
    expect(consoleError).toHaveBeenCalledWith('Failed to mark all read:', markError)
    expect(onReadUpdated).not.toHaveBeenCalled()
    expect(toastSuccess).not.toHaveBeenCalled()
    console.error = originalConsoleError
  })

  test('marks one and all notifications read and refreshes the list', async () => {
    const { renderer, onReadUpdated } = await renderClient()

    await act(async () => button(renderer, 'markRead').props.onClick({ stopPropagation: mock(() => undefined) }))
    await act(async () => button(renderer, 'markAllRead').props.onClick())

    expect(markRead).toHaveBeenNthCalledWith(1, { notification_ids: ['notification-1'] })
    expect(markRead).toHaveBeenNthCalledWith(2, { mark_all: true })
    expect(onReadUpdated).toHaveBeenCalledTimes(2)
    expect(toastSuccess).toHaveBeenCalledTimes(2)
    expect(list).toHaveBeenCalledTimes(3)
  })
})
