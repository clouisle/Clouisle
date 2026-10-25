import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const item = (id: string, title = id) => ({
  id, scope: 'team', type: 'workflow.run_failed', source: 'system', title, content: 'content',
  level: 'high', status: 'active', created_at: '2026-07-20T12:00:00Z', updated_at: '2026-07-20T12:00:00Z', is_read: false,
})
type ListParams = { page: number; page_size: number; scope?: string; level?: string; search?: string; unread_only: boolean }
type Page = { items: ReturnType<typeof item>[]; total: number; page: number; page_size: number }
const list = mock(async (params: ListParams): Promise<Page> => ({ items: [item('default')], total: 1, page: params.page, page_size: params.page_size }))
const markRead = mock(async () => ({ updated: 1 }))
const toast = { success: mock(), error: mock() }
type ObserverCallback = (entries: Array<{ isIntersecting: boolean }>) => void
class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = []
  constructor(private callback: ObserverCallback) { TestIntersectionObserver.instances.push(this) }
  observe() {}
  unobserve() {}
  disconnect() {}
  trigger(isIntersecting: boolean) { this.callback([{ isIntersecting }]) }
}
globalThis.IntersectionObserver = TestIntersectionObserver as unknown as typeof IntersectionObserver

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }))
mock.module('next/dynamic', () => ({ default: () => () => null }))
mock.module('lucide-react', () => Object.fromEntries(['Check', 'Loader2', 'Megaphone', 'Search', 'ShieldAlert', 'Sparkles', 'X'].map(name => [name, () => null])))
mock.module('@/lib/api', () => ({ notificationsApi: { list, markRead } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getPendingPauseRequest: mock(async () => null), submitPauseRequest: mock(async () => ({})) } }))
mock.module('@/components/chat/pause-request-actions', () => ({ PauseRequestActions: () => null }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/lib/notifications/display', () => ({ getNotificationDisplayMeta: () => ({ kind: 'general', isAnnouncement: false }), getPauseActionMeta: () => null }))
mock.module('@/lib/utils', () => ({ formatDateTime: String, cn: (...values: string[]) => values.filter(Boolean).join(' ') }))
mock.module('sonner', () => ({ toast }))
const element = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: element }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element }))
mock.module('@/components/ui/table', () => ({ Table: element, TableBody: element, TableCell: element, TableHead: element, TableHeader: element, TableRow: element }))
mock.module('@/components/ui/dialog', () => ({ Dialog: element, DialogContent: element, DialogHeader: element, DialogTitle: element }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, options, onSelectionChange }: { title: string; options: { value: string; label: string }[]; onSelectionChange: (next: Set<string>) => void }) => <div data-filter={title}>{options.map(option => <button key={option.value} onClick={() => onSelectionChange(new Set([option.value]))}>{option.value}</button>)}</div>,
}))
const { NotificationsClient } = await import('./notifications-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []
async function renderClient() {
  let renderer!: ReactTestRenderer
  await act(async () => { renderer = create(<NotificationsClient />) })
  renderers.push(renderer)
  return renderer
}
function text(node: ReactTestRenderer['root']): string {
  return node.children.map(child => typeof child === 'string' ? child : text(child as ReactTestRenderer['root'])).join('')
}
function deferred<T>() { return Promise.withResolvers<T>() }

beforeEach(() => {
  TestIntersectionObserver.instances = []
  list.mockReset()
  list.mockImplementation(async params => ({ items: [item(`page-${params.page}`)], total: 60, page: params.page, page_size: 20 }))
})
afterEach(() => { for (const renderer of renderers.splice(0)) act(() => renderer.unmount()) })

test('observer loads page two for a new filter generation and stale completion cannot unlock its append', async () => {
  const staleFirst = deferred<Page>()
  const nextFirst = deferred<Page>()
  const pageTwo = deferred<Page>()
  list.mockImplementationOnce(() => staleFirst.promise)
  const renderer = await renderClient()
  expect(list).toHaveBeenCalledTimes(1)

  const scopeFilter = renderer.root.findByProps({ 'data-filter': 'scope' })
  list.mockImplementationOnce(() => nextFirst.promise)
  // The changed filter starts a new first-page generation while the old request remains pending.
  await act(async () => { scopeFilter.findAllByType('button').find(button => button.props.children === 'user')!.props.onClick() })
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, scope: 'user' }))
  await act(async () => { nextFirst.resolve({ items: [item('user-1')], total: 60, page: 1, page_size: 20 }) })
  await act(async () => {})

  // A single true observer entry is sufficient; no false entry is sent to reset the hook.
  list.mockImplementationOnce(() => pageTwo.promise)
  TestIntersectionObserver.instances.at(-1)!.trigger(true)
  await act(async () => {})
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, scope: 'user' }))

  await act(async () => { staleFirst.resolve({ items: [item('stale')], total: 60, page: 1, page_size: 20 }) })
  await act(async () => {})
  expect(text(renderer.root)).not.toContain('stale')
  expect(text(renderer.root)).toContain('user-1')

  // The stale first-page finalizer must not clear the active append's lock.
  const currentObserver = TestIntersectionObserver.instances.at(-1)!
  currentObserver.trigger(true)
  await act(async () => {})
  expect(list).toHaveBeenCalledTimes(3)
  await act(async () => { pageTwo.resolve({ items: [item('user-2')], total: 60, page: 2, page_size: 20 }) })
  await act(async () => {})
  expect(text(renderer.root)).toContain('user-2')
})

test('a failed observer append can be retried without advancing its page', async () => {
  const renderer = await renderClient()
  list.mockRejectedValueOnce(new Error('page two failed'))
  TestIntersectionObserver.instances.at(-1)!.trigger(true)
  await act(async () => {})
  expect(text(renderer.root)).toContain('loadFailed')
  await act(async () => { renderer.root.findAllByType('button').find(button => button.children.join('') === 'retry')!.props.onClick() })
  await act(async () => {})
  expect(list.mock.calls.map(([params]) => params.page)).toEqual([1, 2, 2])
  expect(text(renderer.root)).toContain('page-2')
})
