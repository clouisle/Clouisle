import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const platformTeamsApi = {
  getTeam: mock(),
  addMember: mock(),
  removeMember: mock(),
  updateMember: mock(),
  transferOwnership: mock(),
  leaveTeam: mock(),
}
const adminTeamsApi = { deleteTeam: mock() }
const usersApi = { getUsers: mock() }
const toast = { success: mock() }
let permissions = new Set<string>()

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api', () => ({ teamsApi: platformTeamsApi }))
mock.module('@/lib/api/admin', () => ({ teamsApi: adminTeamsApi }))
mock.module('@/lib/api/admin/users', () => ({ usersApi }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('./team-models-tab', () => ({ TeamModelsTab: ({ teamId }: { teamId: string }) => <section>models:{teamId}</section> }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: React.PropsWithChildren<{ permission: string }>) => permissions.has(permission) ? <>{children}</> : null,
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Crown', 'Shield', 'User', 'Eye', 'MoreHorizontal', 'Pencil', 'Trash2', 'UserPlus', 'LogOut', 'ArrowRightLeft', 'Search', 'Check', 'Users', 'Cpu',
].map((name) => [name, (props: Record<string, unknown>) => <i data-icon={name} {...props} />])))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/avatar', () => ({ Avatar: passthrough, AvatarFallback: passthrough, AvatarImage: () => null }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open, onOpenChange }: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) => open ? <div role="dialog" data-close={() => onOpenChange(false)}>{children}</div> : null,
  DialogContent: passthrough,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  DialogHeader: passthrough,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough, DropdownMenuContent: passthrough, DropdownMenuSeparator: () => <hr />, DropdownMenuItem: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>, DropdownMenuTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => <select value={value} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectContent: passthrough,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: passthrough,
  SelectValue: passthrough,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: React.PropsWithChildren<{ open: boolean }>) => open ? <div role="alertdialog">{children}</div> : null,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogContent: passthrough,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: passthrough,
  AlertDialogHeader: passthrough,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
}))
mock.module('@/components/ui/popover', () => ({ Popover: passthrough, PopoverContent: passthrough, PopoverTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
mock.module('@/components/ui/tabs', () => ({ Tabs: passthrough, TabsContent: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <section data-tab={value}>{children}</section>, TabsList: passthrough, TabsTrigger: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <button data-tab-trigger={value}>{children}</button> }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: passthrough }))
mock.module('@/components/ui/separator', () => ({ Separator: () => <hr /> }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div data-skeleton /> }))

const { TeamDetailDialog } = await import('./team-detail-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const team = {
  id: 'team-1', name: 'Platform', description: 'Shared team', avatar_url: null, is_default: false,
  members: [
    { user_id: 'owner-1', username: 'Owner', email: 'owner@test.dev', avatar_url: null, role: 'owner' },
    { user_id: 'member-1', username: 'Member', email: 'member@test.dev', avatar_url: null, role: 'member' },
  ],
}
const users = [{ id: 'user-2', username: 'Ada', email: 'ada@test.dev', avatar_url: null }]
const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  permissions = new Set(['team:manage', 'team:update', 'team:delete'])
  for (const api of [platformTeamsApi, adminTeamsApi, usersApi]) Object.values(api).forEach((fn) => fn.mockReset())
  toast.success.mockReset()
  platformTeamsApi.getTeam.mockResolvedValue(team)
  usersApi.getUsers.mockResolvedValue({ items: users })
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

async function render(props: Partial<React.ComponentProps<typeof TeamDetailDialog>> = {}) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<TeamDetailDialog open onOpenChange={() => {}} teamId="team-1" {...props} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function text(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

function nodeText(node: ReactTestRenderer['root'] | string | number): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  return node.children.map(nodeText).join('')
}

function buttons(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').filter((node) => nodeText(node).includes(label))
}

function button(renderer: ReactTestRenderer, label: string) {
  return buttons(renderer, label)[0]!
}

describe('TeamDetailDialog', () => {
  test('shows loading, then loaded members, roles, and manager actions', async () => {
    let resolveTeam!: (value: unknown) => void
    platformTeamsApi.getTeam.mockReturnValue(new Promise((resolve) => { resolveTeam = resolve }))
    let renderer: ReactTestRenderer

    await act(() => { renderer = create(<TeamDetailDialog open onOpenChange={() => {}} teamId="team-1" />) })
    expect(renderer!.root.findAllByProps({ 'data-skeleton': true }).length).toBeGreaterThan(0)

    await act(async () => { resolveTeam(team); await Promise.resolve(); await Promise.resolve() })

    expect(text(renderer!)).toContain('Platform')
    expect(text(renderer!)).toContain('Member')
    expect(text(renderer!)).toContain('roles.owner')
    expect(text(renderer!)).toContain('roles.member')
    expect(text(renderer!)).toContain('addMember')
    expect(text(renderer!)).toContain('modelAuth')
    expect(text(renderer!)).toContain('models')
    expect(text(renderer!)).toContain('team-1')
    expect(platformTeamsApi.getTeam).toHaveBeenCalledWith('team-1')
  })

  test('shows not found after detail loading fails', async () => {
    platformTeamsApi.getTeam.mockRejectedValue(new Error('missing'))
    const renderer = await render()

    expect(text(renderer)).toContain('teamNotFound')
  })

  test('adds a searched user, resets selection, and reloads details', async () => {
    platformTeamsApi.addMember.mockResolvedValue({})
    const renderer = await render()

    await act(() => button(renderer, 'Ada').props.onClick())
    await act(() => renderer.root.findByType('select').props.onChange({ target: { value: 'admin' } }))
    await act(async () => buttons(renderer, 'addMember').find((node) => typeof node.props.onClick === 'function')!.props.onClick())

    expect(platformTeamsApi.addMember).toHaveBeenCalledWith('team-1', { user_id: 'user-2', role: 'admin' })
    expect(toast.success).toHaveBeenCalledWith('memberAdded')
    expect(text(renderer)).not.toContain('roles.admin')
    expect(usersApi.getUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 100, search: undefined, excludeUserIds: ['owner-1', 'member-1'] })
  })

  test('changes role, transfers ownership, removes members, leaves, deletes, and edits through exposed actions', async () => {
    for (const fn of [platformTeamsApi.updateMember, platformTeamsApi.transferOwnership, platformTeamsApi.removeMember, platformTeamsApi.leaveTeam, adminTeamsApi.deleteTeam]) fn.mockResolvedValue({})
    const onOpenChange = mock()
    const onDeleted = mock()
    const onEdit = mock()
    const renderer = await render({ onOpenChange, onDeleted, onEdit })

    await act(() => button(renderer, 'changeRole').props.onClick())
    await act(() => renderer.root.findAllByType('select').at(-1)!.props.onChange({ target: { value: 'viewer' } }))
    await act(async () => button(renderer, 'save').props.onClick())
    expect(platformTeamsApi.updateMember).toHaveBeenCalledWith('team-1', 'member-1', { role: 'viewer' })

    await act(() => buttons(renderer, 'transferOwnership').find((node) => typeof node.props.onClick === 'function')!.props.onClick())
    await act(async () => buttons(renderer, 'transfer').at(-1)!.props.onClick())
    expect(platformTeamsApi.transferOwnership).toHaveBeenCalledWith('team-1', 'member-1')

    await act(() => button(renderer, 'removeMember').props.onClick())
    await act(async () => buttons(renderer, 'removeMember').at(-1)!.props.onClick())
    expect(platformTeamsApi.removeMember).toHaveBeenCalledWith('team-1', 'member-1')

    await act(() => button(renderer, 'leaveTeam').props.onClick())
    await act(async () => buttons(renderer, 'leaveTeam').at(-1)!.props.onClick())
    expect(platformTeamsApi.leaveTeam).toHaveBeenCalledWith('team-1')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onDeleted).toHaveBeenCalledTimes(1)

    await act(() => button(renderer, 'delete').props.onClick())
    await act(async () => buttons(renderer, 'delete').at(-1)!.props.onClick())
    expect(adminTeamsApi.deleteTeam).toHaveBeenCalledWith('team-1')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onDeleted).toHaveBeenCalledTimes(2)

    await act(() => button(renderer, 'edit').props.onClick())
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  test('hides manager, update, and delete boundaries without permissions and forwards close', async () => {
    permissions = new Set()
    const onOpenChange = mock()
    const renderer = await render({ onOpenChange })

    expect(text(renderer)).toContain('leaveTeam')
    expect(text(renderer)).not.toContain('addMember')
    expect(text(renderer)).not.toContain('changeRole')
    expect(text(renderer)).not.toContain('modelAuth')
    expect(text(renderer)).not.toContain('delete')
    expect(text(renderer)).not.toContain('edit')

    act(() => renderer.root.findByProps({ role: 'dialog' }).props['data-close']())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
