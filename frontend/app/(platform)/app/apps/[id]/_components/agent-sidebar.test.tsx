import { expect, mock, test } from 'bun:test'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
let pathname = '/custom/agents/agent-1/logs'

function Link() {}
function Image() {}
function LayoutGrid() {}
function Code2() {}
function FileText() {}
function Activity() {}
function ArrowLeft() {}
function Sparkles() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next/link', () => ({ default: Link }))
mock.module('next/image', () => ({ default: Image }))
mock.module('next/navigation', () => ({ usePathname: () => pathname }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => `sidebar.${key}`,
}))
mock.module('lucide-react', () => ({
  LayoutGrid,
  Code2,
  FileText,
  Activity,
  ArrowLeft,
  Sparkles,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { AgentSidebar } = await import('./agent-sidebar')

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

const agent = { id: 'agent-1', name: 'Research Agent', icon: null }

test('renders agent identity and navigates between all sections with exact selection', () => {
  const sidebar = AgentSidebar({
    agent: agent as never,
    backHref: '/custom/agents',
    baseUrl: '/custom/agents/agent-1',
  }) as Node
  const nodes = descendants(sidebar)
  const links = nodes.filter((node) => node.type === Link)
  const navLinks = links.filter((node) => node.props['data-testid'])

  expect(sidebar.props['data-testid']).toBe('agent-sidebar')
  expect(links[0].props.href).toBe('/custom/agents')
  expect(nodes.find((node) => node.type === 'h2')?.props.children).toBe('Research Agent')
  expect(navLinks.map((node) => [node.props['data-testid'], node.props.href, node.props.children])).toEqual([
    ['agent-nav-orchestration', '/custom/agents/agent-1', expect.any(Array)],
    ['agent-nav-api', '/custom/agents/agent-1/api', expect.any(Array)],
    ['agent-nav-logs', '/custom/agents/agent-1/logs', expect.any(Array)],
    ['agent-nav-monitor', '/custom/agents/agent-1/monitor', expect.any(Array)],
  ])
  expect(navLinks.map((node) => (node.props.children as unknown[])[1])).toEqual([
    'sidebar.orchestration',
    'sidebar.api',
    'sidebar.logs',
    'sidebar.monitor',
  ])
  expect(navLinks[2].props.className).toContain('bg-primary text-primary-foreground')
  expect(navLinks[0].props.className).toContain('text-muted-foreground')
})

test('uses default destinations and the empty-icon fallback', () => {
  pathname = '/app/apps/agent-1'
  const sidebar = AgentSidebar({ agent: agent as never }) as Node
  const nodes = descendants(sidebar)
  const links = nodes.filter((node) => node.type === Link)

  expect(links.map((node) => node.props.href)).toEqual([
    '/app/apps',
    '/app/apps/agent-1',
    '/app/apps/agent-1/api',
    '/app/apps/agent-1/logs',
    '/app/apps/agent-1/monitor',
  ])
  expect(nodes.some((node) => node.type === Image)).toBe(false)
  expect(nodes.some((node) => node.type === Sparkles)).toBe(true)
})

test('renders no sidebar at the collapsed boundary', () => {
  expect(AgentSidebar({ agent: agent as never, collapsed: true })).toBeNull()
})
