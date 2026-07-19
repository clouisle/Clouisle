import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const replace = mock(() => {})
const setActiveTab = mock(() => {})
let searchParams = new URLSearchParams()

function RoutePermissionGuard() {}
function Header() {}
function Tabs() {}
function TabsContent() {}
function TabsList() {}
function TabsTrigger() {}
function AdminAgentsPanel() {}
function AdminWorkflowsPanel() {}
function Bot() {}
function GitBranch() {}

mock.module('react', () => ({
  useEffect: (effect: () => void) => effect(),
  useState: () => ['agents', setActiveTab],
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Bot, GitBranch }))
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard }))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('@/components/ui/tabs', () => ({ Tabs, TabsContent, TabsList, TabsTrigger }))
mock.module('./_components', () => ({ AdminAgentsPanel, AdminWorkflowsPanel }))

const { default: AppsManagementPage } = await import('./page')

test('defaults to agents and renders both guarded app panels', () => {
  searchParams = new URLSearchParams()
  const tree = AppsManagementPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const [header, content] = page.props.children as Array<{ props: Record<string, unknown> }>
  const [, tabs] = content.props.children as Array<{ props: Record<string, unknown> }>
  const [, agentsPanel, workflowsPanel] = tabs.props.children as Array<{
    props: Record<string, unknown>
  }>

  expect((tree.type as Function).name).toBe('RoutePermissionGuard')
  expect((header.type as Function).name).toBe('Header')
  expect(tabs.props.value).toBe('agents')
  expect((agentsPanel.props.children as { type: Function }).type.name).toBe('AdminAgentsPanel')
  expect((workflowsPanel.props.children as { type: Function }).type.name).toBe(
    'AdminWorkflowsPanel',
  )
})

test('selects workflows from the URL and updates its shallow route', () => {
  searchParams = new URLSearchParams('tab=workflows')
  const tree = AppsManagementPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const content = (page.props.children as Array<{ props: Record<string, unknown> }>)[1]
  const tabs = (content.props.children as Array<{ props: Record<string, unknown> }>)[1]

  tabs.props.onValueChange('workflows')

  expect(setActiveTab).toHaveBeenCalledWith('workflows')
  expect(replace).toHaveBeenCalledWith('/apps?tab=workflows', { scroll: false })
})
