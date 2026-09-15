import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const platformTeamsApi = {
  getTeam: mock(),
  updateTeam: mock(),
  addMember: mock(),
  removeMember: mock(),
  updateMember: mock(),
  transferOwnership: mock(),
  leaveTeam: mock(),
}
const teamModelsApi = {
  getTeamModels: mock(),
}
const toast = { success: mock() }
const router = { push: mock() }

let searchParams = new URLSearchParams()

let permissions = new Set<string>()
let currentUser: { id: string; is_superuser?: boolean } | null = { id: 'u-owner', is_superuser: false }
let teamContextState: {
  currentTeam: { id: string; name: string; role: string } | null
  refreshTeams: ReturnType<typeof mock>
  isLoading: boolean
} = {
  currentTeam: { id: 'team-1', name: 'Dev Team', role: 'owner' },
  refreshTeams: mock(),
  isLoading: false,
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api', () => ({
  teamsApi: platformTeamsApi,
  teamModelsApi,
}))
mock.module('@/contexts/team-context', () => ({
  useTeam: () => teamContextState,
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: currentUser,
    hasPermission: (perm: string) => permissions.has(perm),
    loading: false,
  }),
}))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
let lastTabChange: ((value: string | null) => void) | undefined
const tabsRoot = ({
  children,
  value,
  onValueChange,
}: React.PropsWithChildren<{
  value?: string
  onValueChange?: (value: string | null) => void
}>) => {
  lastTabChange = onValueChange
  return <div data-tabs-root data-active-tab={value}>{children}</div>
}

mock.module('@/components/ui/tabs', () => ({
  Tabs: tabsRoot,
  TabsList: passthrough,
  TabsTrigger: ({ children, value }: React.PropsWithChildren<{ value: string }>) => (
    <button data-tab-trigger={value}>{children}</button>
  ),
  TabsContent: ({ children, value }: React.PropsWithChildren<{ value: string }>) => (
    <div data-tab-content={value}>{children}</div>
  ),
}))
mock.module('@/components/ui/card', () => ({
  Card: passthrough,
  CardHeader: passthrough,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardContent: passthrough,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/avatar', () => ({
  Avatar: passthrough,
  AvatarFallback: passthrough,
  AvatarImage: () => null,
}))
mock.module('@/components/ui/skeleton', () => ({
  Skeleton: () => <div data-skeleton="true" />,
}))
mock.module('@/components/ui/scroll-area', () => ({
  ScrollArea: passthrough,
}))
mock.module('@/components/ui/image-upload', () => ({
  ImageUpload: ({ value, disabled }: { value?: string; disabled?: boolean }) => (
    <div data-testid="image-upload" data-value={value} data-disabled={disabled} />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ value, onValueChange, children }: { value?: string; onValueChange?: (v: string) => void; children: React.ReactNode }) => (
    <select value={value} onChange={(e) => onValueChange?.(e.target.value)}>{children}</select>
  ),
  SelectTrigger: passthrough,
  SelectValue: passthrough,
  SelectContent: passthrough,
  SelectItem: ({ value, children }: { value: string; children: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough,
  DropdownMenuTrigger: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) => render({}),
  DropdownMenuContent: passthrough,
  DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
  DropdownMenuSeparator: () => <hr />,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => (open ? <div>{children}</div> : null),
  AlertDialogContent: passthrough,
  AlertDialogHeader: passthrough,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: passthrough,
  AlertDialogCancel: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => (
    <button onClick={onClick}>{children}</button>
  ),
  AlertDialogAction: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => (
    <button onClick={onClick}>{children}</button>
  ),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  DialogFooter: passthrough,
}))
mock.module('lucide-react', () =>
  Object.fromEntries(
    [
      'Users',
      'Cpu',
      'Settings',
      'ShieldAlert',
      'UserPlus',
      'Trash2',
      'ArrowRightLeft',
      'Pencil',
      'Crown',
      'Shield',
      'User',
      'Eye',
      'Search',
      'Check',
      'MoreHorizontal',
      'LogOut',
      'AlertTriangle',
    ].map((name) => [name, (props: Record<string, unknown>) => <i data-icon={name} {...props} />])
  )
)

const { default: PlatformTeamPage } = await import('./page')

const teamPayload = {
  id: 'team-1',
  name: 'Dev Team',
  description: 'Team description',
  avatar_url: '',
  is_default: false,
  members: [
    { user_id: 'u-owner', username: 'OwnerUser', email: 'owner@test.com', role: 'owner' },
    { user_id: 'u-member', username: 'NormalMember', email: 'member@test.com', role: 'member' },
  ],
}

const renderers: ReactTestRenderer[] = []
async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<PlatformTeamPage />)
  })
  renderers.push(renderer!)
  return renderer!
}

describe('PlatformTeamPage', () => {
  beforeEach(() => {
    permissions = new Set(['team:manage', 'team:update'])
    currentUser = { id: 'u-owner', is_superuser: false }
    teamContextState = {
      currentTeam: { id: 'team-1', name: 'Dev Team', role: 'owner' },
      refreshTeams: mock(),
      isLoading: false,
    }
    platformTeamsApi.getTeam.mockReset().mockResolvedValue(teamPayload)
    platformTeamsApi.updateTeam.mockReset().mockResolvedValue(teamPayload)
    platformTeamsApi.addMember.mockReset().mockResolvedValue({})
    platformTeamsApi.removeMember.mockReset().mockResolvedValue({})
    platformTeamsApi.updateMember.mockReset().mockResolvedValue({})
    platformTeamsApi.transferOwnership.mockReset().mockResolvedValue(teamPayload)
    platformTeamsApi.leaveTeam.mockReset().mockResolvedValue({})
    teamModelsApi.getTeamModels.mockReset().mockResolvedValue([
      {
        id: 'tm-1',
        model: {
          name: 'Claude 3.5 Sonnet',
          model_type: 'chat',
          provider: 'Anthropic',
          model_id: 'claude-3-5',
        },
        is_enabled: true,
        daily_token_limit: 100000,
        daily_tokens_used: 25000,
      },
    ])
    searchParams = new URLSearchParams()
    lastTabChange = undefined
    toast.success.mockReset()
    router.push.mockReset()
  })

  afterEach(() => {
    for (const renderer of renderers) act(() => renderer.unmount())
    renderers.length = 0
  })

  test('loads team details, members, authorized models, and settings', async () => {
    const renderer = await render()
    const text = JSON.stringify(renderer.toJSON())

    expect(text).toContain('Dev Team')
    expect(text).toContain('OwnerUser')
    expect(text).toContain('NormalMember')
    expect(text).toContain('Claude 3.5 Sonnet')
  })
  test('restores the selected tab from the URL and updates it on change', async () => {
    searchParams = new URLSearchParams('tab=settings')
    const renderer = await render()
    const tabs = renderer.root.findByProps({ 'data-tabs-root': true })

    expect(tabs.props['data-active-tab']).toBe('settings')

    await act(async () => {
      lastTabChange?.('models')
    })

    expect(router.push).toHaveBeenCalledWith('?tab=models', { scroll: false })
  })

  test('allows owner/admin to manage team settings and updates successfully', async () => {
    const renderer = await render()
    const form = renderer.root.findByType('form')

    await act(async () => {
      form.props.onSubmit({ preventDefault: () => {} })
    })

    expect(platformTeamsApi.updateTeam).toHaveBeenCalledWith('team-1', {
      name: 'Dev Team',
      description: 'Team description',
      avatar_url: undefined,
    })
    expect(toast.success).toHaveBeenCalled()
  })

  test('adds a member with the selected role', async () => {
    const renderer = await render()
    const addBtn = renderer.root.findAll((node) => node.type === 'button' && String(node.props.children).includes('addMember'))[0]
    expect(addBtn).toBeDefined()

    act(() => addBtn.props.onClick())
    const identifier = renderer.root.findByProps({ id: 'member-identifier' })
    act(() => identifier.props.onChange({ target: { value: '  new@example.com  ' } }))
    const roleSelect = renderer.root.findAllByType('select').at(-1)!
    act(() => roleSelect.props.onChange({ target: { value: 'admin' } }))

    const addForm = renderer.root.findAllByType('form').at(-1)!
    await act(async () => addForm.props.onSubmit({ preventDefault: () => {} }))

    expect(platformTeamsApi.addMember).toHaveBeenCalledWith('team-1', {
      identifier: 'new@example.com',
      role: 'admin',
    })
    expect(toast.success).toHaveBeenCalledWith('memberAdded')
  })

  test('changes and removes a member, then transfers ownership', async () => {
    const renderer = await render()
    const memberRow = renderer.root.findAll((node) => node.props.className === 'flex items-center justify-between p-4 hover:bg-muted/40 transition-colors')[1]
    const menuActions = memberRow.findAllByType('button')

    act(() => menuActions.find((button) => String(button.props.children).includes('changeRole'))!.props.onClick())
    const roleSelect = renderer.root.findAllByType('select').at(-1)!
    act(() => roleSelect.props.onChange({ target: { value: 'viewer' } }))
    await act(async () => renderer.root.findAllByType('button').filter((button) => String(button.props.children).includes('save')).at(-1)!.props.onClick())
    expect(platformTeamsApi.updateMember).toHaveBeenCalledWith('team-1', 'u-member', { role: 'viewer' })

    const refreshedRow = renderer.root.findAll((node) => node.props.className === 'flex items-center justify-between p-4 hover:bg-muted/40 transition-colors')[1]
    const refreshedActions = refreshedRow.findAllByType('button')
    act(() => refreshedActions.find((button) => String(button.props.children).includes('removeMember'))!.props.onClick())
    await act(async () => renderer.root.findAllByType('button').filter((button) => String(button.props.children).includes('removeMember')).at(-1)!.props.onClick())
    expect(platformTeamsApi.removeMember).toHaveBeenCalledWith('team-1', 'u-member')

    const transferRow = renderer.root.findAll((node) => node.props.className === 'flex items-center justify-between p-4 hover:bg-muted/40 transition-colors')[1]
    act(() => transferRow.findAllByType('button').find((button) => String(button.props.children).includes('transferOwnership'))!.props.onClick())
    await act(async () => renderer.root.findAllByType('button').filter((button) => String(button.props.children).includes('confirm')).at(-1)!.props.onClick())
    expect(platformTeamsApi.transferOwnership).toHaveBeenCalledWith('team-1', 'u-member')
  })

  test('renders model loading and empty states', async () => {
    let resolveModels: ((models: never[]) => void) | undefined
    teamModelsApi.getTeamModels.mockImplementationOnce(() => new Promise((resolve) => { resolveModels = resolve }))
    searchParams = new URLSearchParams('tab=models')
    const renderer = await render()

    expect(renderer.root.findAllByProps({ 'data-skeleton': 'true' })).toHaveLength(9)
    resolveModels!([])
    await act(async () => {})
    expect(JSON.stringify(renderer.toJSON())).toContain('noModelsAuthorized')
  })
  test('filters members and models and edits settings fields', async () => {
    teamModelsApi.getTeamModels.mockResolvedValueOnce([
      {
        id: 'tm-1',
        model: { name: 'Claude 3.5 Sonnet', model_type: 'chat', provider: 'Anthropic', model_id: 'claude-3-5' },
        is_enabled: true,
        daily_token_limit: 100000,
        daily_tokens_used: 25000,
      },
      {
        id: 'tm-2',
        model: { name: 'GPT-5', model_type: 'chat', provider: 'OpenAI', model_id: 'gpt-5' },
        is_enabled: false,
        daily_token_limit: null,
        daily_tokens_used: 0,
      },
    ])
    const renderer = await render()

    act(() => renderer.root.findByProps({ placeholder: 'searchUsers' }).props.onChange({ target: { value: 'member@test.com' } }))
    expect(JSON.stringify(renderer.toJSON())).toContain('NormalMember')
    expect(JSON.stringify(renderer.toJSON())).not.toContain('OwnerUser')

    await act(async () => lastTabChange?.('models'))
    expect(JSON.stringify(renderer.toJSON())).toContain('GPT-5')
    act(() => renderer.root.findByProps({ placeholder: 'searchModels' }).props.onChange({ target: { value: 'anthropic' } }))
    expect(JSON.stringify(renderer.toJSON())).toContain('Claude 3.5 Sonnet')
    expect(JSON.stringify(renderer.toJSON())).not.toContain('GPT-5')

    await act(async () => lastTabChange?.('settings'))
    act(() => renderer.root.findByProps({ id: 'team-name' }).props.onChange({ target: { value: 'Renamed Team' } }))
    act(() => renderer.root.findByProps({ id: 'team-desc' }).props.onChange({ target: { value: 'Updated description' } }))
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault: () => {} }))
    expect(platformTeamsApi.updateTeam).toHaveBeenCalledWith('team-1', {
      name: 'Renamed Team',
      description: 'Updated description',
      avatar_url: undefined,
    })
  })

  test('allows a non-owner to leave a team', async () => {
    currentUser = { id: 'u-member', is_superuser: false }
    searchParams = new URLSearchParams('tab=settings')
    const renderer = await render()
    const leaveButton = renderer.root.findAllByType('button').find((button) => String(button.props.children).includes('leaveTeam'))!

    act(() => leaveButton.props.onClick())
    await act(async () => renderer.root.findAllByType('button').filter((button) => String(button.props.children).includes('leaveTeam')).at(-1)!.props.onClick())

    expect(platformTeamsApi.leaveTeam).toHaveBeenCalledWith('team-1')
    expect(router.push).toHaveBeenCalledWith('/app')
  })

  test('returns to the app when no team is selected', async () => {
    teamContextState = { ...teamContextState, currentTeam: null }
    const renderer = await render()
    const backButton = renderer.root.findAllByType('button').find((button) => String(button.props.children).includes('back'))!

    act(() => backButton.props.onClick())
    expect(router.push).toHaveBeenCalledWith('/app')
  })
})
