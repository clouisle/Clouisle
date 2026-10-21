import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'

let sourceFailure: unknown = null
const loadSources = mock(async () => { if (sourceFailure) throw sourceFailure; return sources })
let sources: FeishuKnowledgeSource[] = []
const apiCalls = { update: mock(async (_id: string, _data: unknown) => {}), create: mock(async (_data: unknown) => {}), delete: mock(async (_id: string) => {}), spaces: mock(async () => [{ space_id: 'space-1', name: '工程知识空间' }]), targets: mock(async () => [{ id: 'kb-1', name: '研发 KB', team_name: '研发团队' }]) }
class MockApiError extends Error {}

mock.module('next/link', () => ({ default: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <a {...props}>{children}</a> }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: { is_superuser: true, is_active: true } }) }))
mock.module('@/lib/api/client', () => ({ ApiError: MockApiError }))
mock.module('@/lib/api/admin/feishu-knowledge', () => ({ feishuKnowledgeApi: { sources: loadSources, spaces: apiCalls.spaces, targets: apiCalls.targets, update: apiCalls.update, create: apiCalls.create, delete: apiCalls.delete } }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string | null) => void }>) => <div data-select-value={value} data-on-value-change={onValueChange}>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-select-item={value}>{children}</div>,
  SelectValue: ({ children, placeholder }: React.PropsWithChildren<{ placeholder?: string }>) => <span>{children || placeholder}</span>,
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, defaultOpen = false }: React.PropsWithChildren<{ defaultOpen?: boolean }>) => <div data-collapsible-open={defaultOpen}>{children}</div>,
  CollapsibleTrigger: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('lucide-react', () => ({ ChevronDown: () => null, Loader2: () => <span>spinner</span>, Plus: () => null, RefreshCw: () => null }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/alert', () => ({ Alert: ({ children }: React.PropsWithChildren) => <div role="alert">{children}</div>, AlertDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div> }))
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div>{children}</div> : null, DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>, DialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>, DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>, DialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer> }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>, AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>, AlertDialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>, AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>, AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>, AlertDialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer>, AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>, AlertDialogAction: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button> }))

const { FeishuKnowledgeSync } = await import('./feishu-knowledge-sync')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []
const source: FeishuKnowledgeSource = {
  id: 'source-1', knowledge_base_id: 'kb-1', knowledge_base_name: '研发 KB', space_id: 'space-1', name: '研发',
  interval_minutes: 60, is_enabled: true, status: 'error', last_synced_at: '2026-10-17T00:00:00Z',
  last_error: 'Some documents could not be synchronized. Check the synchronization results.',
  last_result: {
    scanned: 14, indexed: 10, unchanged: 0, failed: 2, unsupported: 1, removed: 0,
    errors: [
      { node_token: 'node-bitable', node_title: '项目数据表', type: 'bitable', error: 'Missing scopes: bitable:app:readonly, base:table:read' },
      { node_token: 'node-embed', error: 'The imported document could not be indexed. Check the knowledge base embedding configuration.' },
    ],
    skipped: [
      { node_token: 'node-mindnote', node_title: 'OKR 制定', type: 'mindnote', reason: 'Mindnote has no public content API.' },
    ],
    warnings: [{ node_token: 'node-warning', blocks: ['unsupported_block:18'] }],
  },
  created_at: '', updated_at: '',
}
afterEach(() => {
  act(() => renderers.splice(0).forEach(renderer => renderer.unmount()))
  sourceFailure = null
  sources = []
  for (const call of Object.values(apiCalls)) call.mockReset()
  apiCalls.spaces.mockImplementation(async () => [{ space_id: 'space-1', name: '工程知识空间' }])
  apiCalls.targets.mockImplementation(async () => [{ id: 'kb-1', name: '研发 KB', team_name: '研发团队' }])
  apiCalls.update.mockImplementation(async () => {})
  apiCalls.create.mockImplementation(async () => {})
  apiCalls.delete.mockImplementation(async () => {})
})

test('opens failed sync details and renders per-document causes instead of raw JSON only', async () => {
  sources = [source]
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  const text = renderer!.root.findAll(node => typeof node.type === 'string').map(node => node.children.join('')).join(' ')

  expect(text).toContain(source.last_error)
  expect(text).toContain('resultScanned: 14')
  expect(text).toContain('resultIndexed: 10')
  expect(text).toContain('Missing scopes: bitable:app:readonly, base:table:read')
  expect(text).toContain('项目数据表')
  expect(text).toContain('工程知识空间')
  const namedLink = renderer!.root.findByProps({ href: 'https://feishu.cn/wiki/node-bitable' })
  expect(namedLink.props.target).toBe('_blank')
  expect(namedLink.props.rel).toBe('noopener noreferrer')
  const skippedLink = renderer!.root.findByProps({ href: 'https://feishu.cn/wiki/node-mindnote' })
  expect(skippedLink.children.join('')).toContain('OKR 制定')
  const skippedSection = document.querySelector('a[href="https://feishu.cn/wiki/node-mindnote"]')!.closest('ul')!.parentElement!
  expect(skippedSection.querySelector('h3')!.textContent).toBe('resultSkipped')
  const errorSection = document.querySelector('a[href="https://feishu.cn/wiki/node-bitable"]')!.closest('ul')!.parentElement!
  expect(errorSection.querySelector('h3')!.textContent).toBe('resultErrors')
  expect(errorSection.querySelector('a[href="https://feishu.cn/wiki/node-mindnote"]')).toBeNull()
  expect(text).toContain('The imported document could not be indexed.')
  expect(text).toContain('Mindnote has no public content API.')
  expect(text).toContain('unsupported_block:18')
  expect(renderer!.root.findAllByProps({ 'data-collapsible-open': true })).toHaveLength(1)
})

test('a successful run with unsupported documents shows skips without a failure alert', async () => {
  sources = [{ ...source, status: 'success', last_error: null,
    last_result: { ...source.last_result, failed: 0, errors: [] },
  }]
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  const text = renderer!.root.findAll(node => typeof node.type === 'string').map(node => node.children.join('')).join(' ')
  expect(text).toContain('status.success')
  expect(text).toContain('resultSkipped')
  expect(text).toContain('OKR 制定')
  expect(text).not.toContain('resultErrors')
  expect(text).not.toContain('Some documents could not be synchronized')
  expect(renderer!.root.findAllByProps({ 'data-collapsible-open': true })).toHaveLength(1)
})
test('renders human-readable labels for space and target Select options', async () => {
  sources = []
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  await act(async () => { await renderer!.root.findAllByType('button').find(button => button.children.includes('create'))!.props.onClick() })
  const selects = renderer!.root.findAll(node => node.props['data-select-value'] !== undefined)
  expect(selects.map(select => select.props['data-select-value'])).toEqual(['', ''])
  expect(renderer!.root.findAllByType('span').map(node => node.children.join(''))).toContain('selectSpace')
  expect(renderer!.root.findAllByType('span').map(node => node.children.join(''))).toContain('selectTarget')
  expect(renderer!.root.findAllByProps({ 'data-select-item': 'space-1' }).map(node => node.children.join(''))).toEqual(['工程知识空间'])
  expect(renderer!.root.findAllByProps({ 'data-select-item': 'kb-1' }).map(node => node.children.join(''))).toEqual(['研发团队 / 研发 KB'])
  await act(async () => selects[0].props['data-on-value-change']('space-1'))
  await act(async () => selects[1].props['data-on-value-change']('kb-1'))
  expect(renderer!.root.findAllByType('span').map(node => node.children.join(''))).toContain('工程知识空间')
  expect(renderer!.root.findAllByType('span').map(node => node.children.join(''))).toContain('研发团队 / 研发 KB')
})
test('opens the add-source dialog with a loading indicator before Feishu data resolves', async () => {
  let resolveSpaces!: (spaces: { space_id: string; name: string }[]) => void
  let resolveTargets!: (targets: { id: string; name: string; team_name: string }[]) => void
  const pendingSpaces = new Promise<{ space_id: string; name: string }[]>(resolve => { resolveSpaces = resolve })
  const pendingTargets = new Promise<{ id: string; name: string; team_name: string }[]>(resolve => { resolveTargets = resolve })
  const feishuApi = await import('@/lib/api/admin/feishu-knowledge')
  const spaces = mock(() => pendingSpaces)
  const targets = mock(() => pendingTargets)
  Object.assign(feishuApi.feishuKnowledgeApi, { spaces, targets })
  sources = []
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)

  await act(async () => { renderer!.root.findAllByType('button').find(button => button.children.includes('create'))!.props.onClick() })

  expect(renderer!.root.findAllByProps({ role: 'status' })).toHaveLength(1)
  expect(renderer!.root.findByProps({ role: 'status' }).children.join('')).toContain('loadingOptions')
  expect(renderer!.root.findAllByProps({ 'data-select-value': '' })).toHaveLength(0)

  await act(async () => {
    resolveSpaces([{ space_id: 'space-1', name: '工程知识空间' }])
    resolveTargets([{ id: 'kb-1', name: '研发 KB', team_name: '研发团队' }])
    await Promise.all([pendingSpaces, pendingTargets])
  })

  expect(renderer!.root.findAllByProps({ role: 'status' })).toHaveLength(0)
  expect(renderer!.root.findAllByProps({ 'data-select-value': '' })).toHaveLength(2)
})
test('shows source loading failure and recovers after refresh', async () => {
  sources = [source]
  sourceFailure = new Error('offline')
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  expect(renderer!.root.findAllByProps({ role: 'alert' }).some(node => node.children.join('').includes('loadFailed'))).toBe(true)
  sourceFailure = null
  await act(async () => { await renderer!.root.findByProps({ 'aria-label': 'refresh' }).props.onClick() })
  expect(renderer!.root.findAllByProps({ role: 'alert' }).some(node => node.children.join('').includes('loadFailed'))).toBe(false)
  expect(renderer!.root.findAllByType('h2').some(node => node.children.join('') === source.name)).toBe(true)
  expect(loadSources.mock.calls.length).toBeGreaterThanOrEqual(2)
})

test('edits an existing source and saves the edited values', async () => {
  sources = [source]
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  await act(async () => { await renderer!.root.findAllByType('button').find(button => button.children.includes('edit'))!.props.onClick() })
  await act(async () => { renderer!.root.findByProps({ id: 'source-name' }).props.onChange({ target: { value: 'Updated research' } }); renderer!.root.findByProps({ id: 'source-interval' }).props.onChange({ target: { value: '120' } }) })
  await act(async () => { await renderer!.root.findAllByType('form')[0].props.onSubmit({ preventDefault() {} }) })
  expect(apiCalls.update).toHaveBeenCalledWith('source-1', { name: 'Updated research', interval_minutes: 120, is_enabled: true })
})

test('confirms deletion and calls the delete API', async () => {
  sources = [source]
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  await act(async () => { renderer!.root.findAllByType('button').find(button => button.children.includes('delete'))!.props.onClick() })
  expect(renderer!.root.findAllByType('p').some(node => node.children.join('').includes('deleteConfirm'))).toBe(true)
  await act(async () => { await renderer!.root.findAllByType('button').filter(button => button.children.includes('delete')).at(-1)!.props.onClick({ preventDefault() {} }) })
  expect(apiCalls.delete).toHaveBeenCalledWith('source-1')
})

test('create option errors show API detail or fallback without corrupting editor state', async () => {
  for (const failure of [new MockApiError('Localized API message'), new Error('opaque')]) {
    sources = [source]
    let renderer: ReactTestRenderer
    await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
    renderers.push(renderer!)
    apiCalls.spaces.mockRejectedValueOnce(failure)
    await act(async () => { await renderer!.root.findAllByType('button').find(button => button.children.includes('create'))!.props.onClick() })
    expect(renderer!.root.findByProps({ id: 'source-name' }).props.value).toBe('')
    expect(renderer!.root.findAllByProps({ role: 'alert' }).some(node => node.children.join('').includes(failure instanceof MockApiError ? 'Localized API message' : 'loadFailed'))).toBe(true)
    expect(renderer!.root.findAll(node => typeof node.type === 'string').map(node => node.children.join('')).join(' ')).toContain(source.name)
    expect(apiCalls.create).not.toHaveBeenCalled()
  }
})
test('shows the empty state and loads sync sources and Feishu spaces on entry', async () => {
  sources = []
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)

  expect(loadSources).toHaveBeenCalledTimes(1)
  expect(apiCalls.spaces).toHaveBeenCalledTimes(1)
  expect(apiCalls.targets).not.toHaveBeenCalled()
  expect(renderer!.root.findAllByType('p').some(node => node.children.join('') === 'empty')).toBe(true)
})

test('prevents saving a new source until all required values are provided, then creates it', async () => {
  sources = []
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  await act(async () => { await renderer!.root.findAllByType('button').find(button => button.children.includes('create'))!.props.onClick() })
  const submit = renderer!.root.findAllByType('button').find(button => button.children.includes('save'))!
  expect(submit.props.disabled).toBe(true)

  await act(async () => renderer!.root.findByProps({ id: 'source-name' }).props.onChange({ target: { value: '  Product docs  ' } }))
  expect(renderer!.root.findAllByType('button').find(button => button.children.includes('save'))!.props.disabled).toBe(true)
  const selects = renderer!.root.findAll(node => node.props['data-select-value'] !== undefined)
  await act(async () => selects[0].props['data-on-value-change']('space-1'))
  await act(async () => selects[1].props['data-on-value-change']('kb-1'))
  expect(renderer!.root.findAllByType('button').find(button => button.children.includes('save'))!.props.disabled).toBe(false)

  apiCalls.create.mockImplementationOnce(async () => {})
  await act(async () => renderer!.root.findAllByType('form')[0].props.onSubmit({ preventDefault() {} }))
  expect(apiCalls.create).toHaveBeenCalledWith({ name: 'Product docs', interval_minutes: 60, is_enabled: true, knowledge_base_id: 'kb-1', space_id: 'space-1' })
  expect(loadSources).toHaveBeenCalledTimes(2)
})

test('blocks sync while queued or running and allows syncing an idle source', async () => {
  sources = [{ ...source, status: 'queued' }, { ...source, id: 'running', status: 'running' }, { ...source, id: 'idle', status: 'success' }]
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  const syncButtons = renderer!.root.findAllByType('button').filter(button => button.children.includes('sync'))
  expect(syncButtons.map(button => button.props.disabled)).toEqual([true, true, false])

  await act(async () => syncButtons[2].props.onClick())
  expect(apiCalls.update).not.toHaveBeenCalled()
  expect(loadSources).toHaveBeenCalledTimes(2)
})

test('reports an API failure when add options cannot be loaded', async () => {
  sources = []
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuKnowledgeSync />) })
  renderers.push(renderer!)
  apiCalls.targets.mockRejectedValueOnce(new MockApiError('Target access denied'))
  await act(async () => { await renderer!.root.findAllByType('button').find(button => button.children.includes('create'))!.props.onClick() })
  expect(renderer!.root.findAllByProps({ role: 'alert' }).some(node => node.children.join('').includes('Target access denied'))).toBe(true)
  expect(renderer!.root.findAllByProps({ id: 'source-name' })).toHaveLength(0)
  expect(apiCalls.spaces).toHaveBeenCalledTimes(2)
  expect(apiCalls.targets).toHaveBeenCalledTimes(1)
  expect(apiCalls.create).not.toHaveBeenCalled()
})

