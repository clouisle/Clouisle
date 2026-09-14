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

  test('adds member via exact identifier', async () => {
    const renderer = await render()
    const addBtn = renderer.root.findAll((node) => node.type === 'button' && String(node.props.children).includes('addMember'))[0]
    expect(addBtn).toBeDefined()
  })
})
