import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let teamState: Record<string, unknown> = {}

function Button() {}
function DropdownMenu() {}
function DropdownMenuContent() {}
function DropdownMenuItem() {}
function DropdownMenuSeparator() {}
function DropdownMenuTrigger() {}
function Check() {}
function ChevronsUpDown() {}
function Users() {}
function Settings() {}
function Link() {}
mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({ default: Link }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => teamState }))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({
    hasPermission: (perm: string) => perm === 'team:manage',
    isSuperuser: false,
  }),
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
}))
mock.module('lucide-react', () => ({ Check, ChevronsUpDown, Users, Settings }))

const { TeamSwitcher } = await import('./team-switcher')

test('renders loading and no-current-team states', () => {
  teamState = { isLoading: true }
  const loading = TeamSwitcher() as { props: Record<string, unknown> }

  expect((loading.type as { name?: string }).name).toBe('Button')
  expect(loading.props.disabled).toBe(true)
  expect(JSON.stringify(loading.props.children)).toContain('animate-pulse')

  teamState = { isLoading: false, currentTeam: null }
  expect(TeamSwitcher()).toBeNull()
})

test('renders teams, initials, selection, and team-switch behavior', () => {
  const setCurrentTeam = mock(() => {})
  const alpha = { id: 'alpha', name: 'Alpha Team', avatar_url: '', role: 'admin' }
  const beta = { id: 'beta', name: 'Beta', avatar_url: '/beta.png', role: 'member' }
  teamState = {
    isLoading: false,
    teams: [alpha, beta],
    currentTeam: alpha,
    setCurrentTeam,
  }
  const tree = TeamSwitcher() as { props: Record<string, unknown> }
  const [trigger, content] = tree.props.children as Array<{ props: Record<string, unknown> }>
  const triggerButton = (trigger.props.render as (props: Record<string, unknown>) => unknown)(
    {},
  ) as {
    props: Record<string, unknown>
  }
  const children = content.props.children as Array<unknown>
  const items = children[1] as Array<{ props: Record<string, unknown> }>
  const [separator, manageCurrentTeam, manageAllTeams] = children.slice(2) as Array<unknown>
  const [alphaItem, betaItem] = items

  expect((tree.type as { name?: string }).name).toBe('DropdownMenu')
  expect(triggerButton.props.className).toContain('cursor-pointer')
  expect(JSON.stringify(triggerButton.props.children)).toContain('Alpha Team')
  expect(JSON.stringify(triggerButton.props.children)).toContain('AT')
  expect(content.props.align).toBe('start')
  expect(((alphaItem.props.children as unknown[])[2] as { type: { name?: string } }).type.name).toBe('Check')
  expect((betaItem.props.children as unknown[])[2]).toBe(false)
  expect(JSON.stringify(betaItem.props.children)).toContain('/beta.png')
  alphaItem.props.onClick()
  betaItem.props.onClick()
  expect(setCurrentTeam).toHaveBeenNthCalledWith(1, alpha)
  expect(setCurrentTeam).toHaveBeenNthCalledWith(2, beta)
  expect((separator as { type: { name?: string } }).type.name).toBe('DropdownMenuSeparator')
  expect((manageCurrentTeam as { type: { name?: string } }).type.name).toBe('DropdownMenuItem')
  const manageLink = (manageCurrentTeam as { props: { render: (props: Record<string, unknown>) => { props: Record<string, unknown> } } }).props.render({
    className: 'flex items-center gap-2 px-2 py-1.5 text-sm',
  })
  expect(manageLink.props.className).toContain('flex')
  expect(manageLink.props.className).toContain('items-center')
  expect(manageLink.props.className).toContain('gap-2')
  expect(manageAllTeams).toBe(false)
})

test('hides team management link when user only has member teams', () => {
  const team = { id: 'member-team', name: 'Member Team', avatar_url: '', role: 'member' }
  teamState = {
    isLoading: false,
    teams: [team],
    currentTeam: team,
    setCurrentTeam: mock(() => {}),
  }

  const tree = TeamSwitcher() as { props: Record<string, unknown> }
  const [, content] = tree.props.children as Array<{ props: Record<string, unknown> }>
  const children = content.props.children as Array<unknown>
  expect(children.slice(2).every((item) => !item)).toBe(true)
})
