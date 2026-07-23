import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const listProviders = mock()
const deleteProvider = mock()
const testConnection = mock()
const updateProvider = mock()
const success = mock()
const error = mock()
const canPerform = mock(() => true)

let state: unknown[] = []
let stateIndex = 0
let effects: Array<() => void> = []

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: 'fragment' }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: 'fragment' }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (state[index] === undefined) state[index] = initial
    return [state[index], (value: T) => { state[index] = value }]
  },
  useEffect: (effect: () => void) => { effects.push(effect) },
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))
mock.module('@/lib/api/admin/sso', () => ({
  ssoApi: { listProviders, deleteProvider, testConnection, updateProvider },
}))

const component = (name: string) => (props: Record<string, unknown>) => ({ type: name, props })
mock.module('lucide-react', () => ({
  Plus: component('plus'), Pencil: component('pencil'), Trash2: component('trash'),
  TestTube2: component('test-icon'), Power: component('power'), PowerOff: component('power-off'),
}))
mock.module('@/components/ui/button', () => ({ Button: component('button') }))
mock.module('@/components/ui/table', () => ({
  Table: component('table'), TableBody: component('tbody'), TableCell: component('td'),
  TableHead: component('th'), TableHeader: component('thead'), TableRow: component('tr'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: component('alert-dialog'), AlertDialogAction: component('alert-action'),
  AlertDialogCancel: component('alert-cancel'), AlertDialogContent: component('alert-content'),
  AlertDialogDescription: component('alert-description'), AlertDialogFooter: component('alert-footer'),
  AlertDialogHeader: component('alert-header'), AlertDialogTitle: component('alert-title'),
}))
mock.module('@/components/ui/badge', () => ({ Badge: component('badge') }))
mock.module('./_components/provider-dialog', () => ({ ProviderDialog: component('provider-dialog') }))

const { default: SSOSettingsPage } = await import('./page')

type Tree = { type: unknown; props: Record<string, unknown> }
const provider = {
  id: 'provider-1', name: 'corp', display_name: 'Corporate', protocol: 'oidc',
  is_enabled: true, allow_signup: true, icon_url: '/icon.png',
}

function render() {
  stateIndex = 0
  effects = []
  return SSOSettingsPage()
}

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function elements(node: ReactNode): Tree[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const tree = resolved as Tree
  return [tree, ...elements(tree.props.children as ReactNode)]
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

beforeEach(() => {
  state = []
  stateIndex = 0
  effects = []
  for (const fn of [listProviders, deleteProvider, testConnection, updateProvider, success, error]) fn.mockReset()
  canPerform.mockReset()
  canPerform.mockReturnValue(true)
})

describe('SSOSettingsPage', () => {
  test('loads providers and renders their state', async () => {
    listProviders.mockResolvedValue([provider])
    const loading = render()
    expect(elements(loading)).toHaveLength(2)

    effects[0]()
    await flush()
    const tree = render()

    expect(listProviders).toHaveBeenCalledTimes(1)
    expect(elements(tree).some(item => item.type === 'img' && item.props.src === '/icon.png')).toBe(true)
    expect(elements(tree).some(item => item.type === 'badge' && item.props.children === 'OIDC')).toBe(true)
    expect(canPerform).toHaveBeenCalledWith('admin:sso:update')
  })

  test('handles create, edit, dialog success, and dialog close callbacks', async () => {
    state = [[provider], false, null, null, false]
    let tree = render()
    const buttons = elements(tree).filter(item => item.type === 'button')
    ;(buttons[0].props.onClick as () => void)()
    tree = render()
    let dialog = elements(tree).find(item => item.type === 'provider-dialog')!
    expect(dialog.props).toMatchObject({ open: true, provider: null })

    ;(elements(tree).find(item => item.props.title === 'editProvider')!.props.onClick as () => void)()
    tree = render()
    dialog = elements(tree).find(item => item.type === 'provider-dialog')!
    expect(dialog.props.provider).toEqual(provider)

    listProviders.mockResolvedValue([provider])
    ;(dialog.props.onClose as (saved?: boolean) => void)(true)
    await flush()
    expect(listProviders).toHaveBeenCalledTimes(1)

    tree = render()
    dialog = elements(tree).find(item => item.type === 'provider-dialog')!
    ;(dialog.props.onClose as () => void)()
    expect(listProviders).toHaveBeenCalledTimes(1)
  })

  test('reports test outcomes and toggles enabled providers', async () => {
    state = [[provider], false, null, null, false]
    let tree = render()
    const testButton = elements(tree).find(item => item.props.title === 'testConnection')!

    testConnection.mockResolvedValueOnce({ status: 'success', message: 'connected' })
    await (testButton.props.onClick as () => Promise<void>)()
    expect(success).toHaveBeenCalledWith('connected')

    testConnection.mockResolvedValueOnce({ status: 'failed', message: 'rejected' })
    await (testButton.props.onClick as () => Promise<void>)()
    expect(error).toHaveBeenCalledWith('rejected')

    updateProvider.mockResolvedValue(provider)
    listProviders.mockResolvedValue([provider])
    const toggle = elements(tree).find(item => item.props.title === 'disable')!
    await (toggle.props.onClick as () => Promise<void>)()
    await flush()
    expect(updateProvider).toHaveBeenCalledWith('provider-1', { is_enabled: false })
    expect(success).toHaveBeenCalledWith('disableSuccess')
    expect(listProviders).toHaveBeenCalledTimes(1)

    tree = render()
    expect(tree).toBeDefined()
  })

  test('deletes after confirmation and clears canceled deletion', async () => {
    state = [[provider], false, null, null, false]
    let tree = render()
    ;(elements(tree).find(item => item.props.title === 'deleteProvider')!.props.onClick as () => void)()
    tree = render()
    let alert = elements(tree).find(item => item.type === 'alert-dialog')!
    expect(alert.props.open).toBe(true)

    deleteProvider.mockResolvedValue(undefined)
    listProviders.mockResolvedValue([])
    await (elements(tree).find(item => item.type === 'alert-action')!.props.onClick as () => Promise<void>)()
    await flush()
    expect(deleteProvider).toHaveBeenCalledWith('provider-1')
    expect(success).toHaveBeenCalledWith('deleteSuccess')

    tree = render()
    alert = elements(tree).find(item => item.type === 'alert-dialog')!
    expect(alert.props.open).toBe(false)
    ;(alert.props.onOpenChange as () => void)()
  })

  test('swallows API errors without success notifications or external requests', async () => {
    listProviders.mockRejectedValue(new Error('load failed'))
    render()
    effects[0]()
    await flush()
    expect(render()).toBeDefined()

    state = [[provider], false, 'provider-1', null, false]
    deleteProvider.mockRejectedValue(new Error('delete failed'))
    testConnection.mockRejectedValue(new Error('test failed'))
    updateProvider.mockRejectedValue(new Error('update failed'))
    const tree = render()
    await (elements(tree).find(item => item.type === 'alert-action')!.props.onClick as () => Promise<void>)()
    await (elements(tree).find(item => item.props.title === 'testConnection')!.props.onClick as () => Promise<void>)()
    await (elements(tree).find(item => item.props.title === 'disable')!.props.onClick as () => Promise<void>)()

    expect(success).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
    expect(listProviders).toHaveBeenCalledTimes(1)
  })
})
