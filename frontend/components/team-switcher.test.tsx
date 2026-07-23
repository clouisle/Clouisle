import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let teamState: Record<string, unknown> = {}

function Avatar() {}
function AvatarFallback() {}
function AvatarImage() {}
function Button() {}
function DropdownMenu() {}
function DropdownMenuContent() {}
function DropdownMenuItem() {}
function DropdownMenuSeparator() {}
function DropdownMenuTrigger() {}
function Check() {}
function ChevronsUpDown() {}
function Users() {}

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
mock.module('@/contexts/team-context', () => ({ useTeam: () => teamState }))
mock.module('@/components/ui/avatar', () => ({ Avatar, AvatarFallback, AvatarImage }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
}))
mock.module('lucide-react', () => ({ Check, ChevronsUpDown, Users }))

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
  const alpha = { id: 'alpha', name: 'Alpha Team', avatar_url: '' }
  const beta = { id: 'beta', name: 'Beta', avatar_url: '/beta.png' }
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
  const [, items, separator, manage] = content.props.children as Array<unknown>
  const [alphaItem, betaItem] = items as Array<{ props: Record<string, unknown> }>

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
  expect((manage as { type: string }).type).toBe('a')
  expect((manage as { props: Record<string, unknown> }).props.href).toBe('/teams')
})
