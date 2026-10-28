import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const replace = mock(() => {})
const push = mock(() => {})
let canManagePolicies = false
const setActiveTab = mock(() => {})
let searchParams = new URLSearchParams()

function RoutePermissionGuard() {}
function Header() {}
function Tabs() {}
function TabsContent() {}
function TabsList() {}
function TabsTrigger() {}
function ToolsClient() {}
function AdminSkillsPanel() {}
function Wrench() {}
function PackageOpen() {}
function ShieldCheck() {}
function Button() {}

mock.module('react', () => ({
  useEffect: (effect: () => void) => effect(),
  useState: () => ['tools', setActiveTab],
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Wrench, PackageOpen, ShieldCheck }))
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard }))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canManagePolicies }),
}))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/tabs', () => ({ Tabs, TabsContent, TabsList, TabsTrigger }))
mock.module('./_components', () => ({ ToolsClient, AdminSkillsPanel }))

const { default: CapabilitiesPage } = await import('./page')

test('defaults to tools and renders both guarded capability panels', () => {
  searchParams = new URLSearchParams()
  const tree = CapabilitiesPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const [header, content] = page.props.children as Array<{ props: Record<string, unknown> }>
  const [, tabs] = content.props.children as Array<{ props: Record<string, unknown> }>
  const [, toolsPanel, skillsPanel] = tabs.props.children as Array<{
    props: Record<string, unknown>
  }>

  expect((tree.type as { name?: string }).name).toBe('RoutePermissionGuard')
  expect((header.type as { name?: string }).name).toBe('Header')
  expect(tabs.props.value).toBe('tools')
  expect((toolsPanel.props.children as { type: { name?: string } }).type.name).toBe('ToolsClient')
  expect((skillsPanel.props.children as { type: { name?: string } }).type.name).toBe('AdminSkillsPanel')
})

test('selects the skills tab from the URL and updates its shallow route', () => {
  searchParams = new URLSearchParams('tab=skills')
  const tree = CapabilitiesPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const content = (page.props.children as Array<{ props: Record<string, unknown> }>)[1]
  const tabs = (content.props.children as Array<{ props: Record<string, unknown> }>)[1]

  tabs.props.onValueChange('skills')

  expect(setActiveTab).toHaveBeenCalledWith('skills')
  expect(replace).toHaveBeenCalledWith('/capabilities?tab=skills', { scroll: false })
})

test('links administrators to the approval policy page', () => {
  canManagePolicies = true
  searchParams = new URLSearchParams()
  push.mockClear()
  const tree = CapabilitiesPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const content = (page.props.children as Array<{ props: Record<string, unknown> }>)[1]
  const headerBlock = (content.props.children as Array<{ props: Record<string, unknown> }>)[0]
  const link = (headerBlock.props.children as Array<{ props: Record<string, unknown> }>)[1]

  expect(link.props['data-testid']).toBe('admin-capabilities-policies-link')
  ;(link.props.onClick as () => void)()
  expect(push).toHaveBeenCalledWith('/capabilities/policies')
  canManagePolicies = false
})
