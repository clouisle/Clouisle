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
function ToolsClient() {}
function AdminSkillsPanel() {}
function Wrench() {}
function PackageOpen() {}

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
  useRouter: () => ({ replace }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Wrench, PackageOpen }))
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard }))
mock.module('@/components/layout/header', () => ({ Header }))
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
