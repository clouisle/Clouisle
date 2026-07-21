import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

function MockImage({ alt }: { alt: string }) {
  return <img alt={alt} />
}
mock.module('next/image', () => ({
  default: MockImage,
}))

const push = mock()
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) => {
    if (key === 'pageInfo') return `${values?.page}/${values?.total}`
    if (key === 'bulkDeleted') return `bulk deleted ${values?.count}`
    if (key === 'confirmBulkDelete') return `confirm bulk delete ${values?.count}`
    return `${namespace}.${key}`
  },
}))

mock.module('sonner', () => ({
  toast: { success: mock(), error: mock() },
}))

const icon = (name: string) => {
  function Icon(props: React.SVGProps<SVGSVGElement>) {
    return <svg data-icon={name} {...props} />
  }
  return Icon
}
mock.module('lucide-react', () => ({
  Calculator: icon('Calculator'),
  ChartColumn: icon('ChartColumn'),
  ChevronDown: icon('ChevronDown'),
  ChevronLeft: icon('ChevronLeft'),
  ChevronRight: icon('ChevronRight'),
  ChevronsLeft: icon('ChevronsLeft'),
  ChevronsRight: icon('ChevronsRight'),
  Clock3: icon('Clock3'),
  Code: icon('Code'),
  Copy: icon('Copy'),
  Download: icon('Download'),
  FolderOpen: icon('FolderOpen'),
  Globe: icon('Globe'),
  Link: icon('Link'),
  MoreHorizontal: icon('MoreHorizontal'),
  Pencil: icon('Pencil'),
  Play: icon('Play'),
  Plug: icon('Plug'),
  Plus: icon('Plus'),
  Search: icon('Search'),
  Server: icon('Server'),
  Share2: icon('Share2'),
  ToggleLeft: icon('ToggleLeft'),
  ToggleRight: icon('ToggleRight'),
  Trash2: icon('Trash2'),
  Upload: icon('Upload'),
  Wrench: icon('Wrench'),
  X: icon('X'),
  Zap: icon('Zap'),
}))

mock.module('@/lib/api', () => ({
  isPresetToolCategory: (value: string) => ['time', 'math', 'search', 'web', 'file', 'code', 'sandbox', 'api', 'data', 'other'].includes(value),
}))

mock.module('@/lib/api/admin', () => ({
  adminToolsApi: {},
  teamsApi: { getTeams: mock() },
}))

mock.module('@/lib/api/packages', () => ({
  adminPackagesApi: {},
  downloadBlob: mock(),
}))

mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => ['', mock()],
}))

mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))

const passthrough = (tag = 'div') => {
  function Passthrough({ children, render, ...props }: { children?: React.ReactNode, render?: React.ReactNode }) {
    return React.createElement(tag, props, render ?? children)
  }
  return Passthrough
}

mock.module('@/components/ui/button', () => ({ Button: passthrough('button') }))
mock.module('@/components/ui/input', () => ({ Input: passthrough('input') }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough('span') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: passthrough('input') }))
mock.module('@/components/ui/table', () => ({
  Table: passthrough('table'),
  TableBody: passthrough('tbody'),
  TableCell: passthrough('td'),
  TableHead: passthrough('th'),
  TableHeader: passthrough('thead'),
  TableRow: passthrough('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: passthrough(),
  SelectContent: passthrough(),
  SelectItem: passthrough(),
  SelectTrigger: passthrough('button'),
  SelectValue: passthrough('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough(),
  DropdownMenuContent: passthrough(),
  DropdownMenuItem: passthrough('button'),
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: passthrough('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title }: { title: string }) => <button>{title}</button>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: passthrough(),
  TooltipContent: passthrough(),
  TooltipTrigger: passthrough('button'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: passthrough(),
  AlertDialogAction: passthrough('button'),
  AlertDialogCancel: passthrough('button'),
  AlertDialogContent: passthrough(),
  AlertDialogDescription: passthrough('p'),
  AlertDialogFooter: passthrough(),
  AlertDialogHeader: passthrough(),
  AlertDialogTitle: passthrough('h2'),
}))

mock.module('@/app/(platform)/app/capabilities/_components/http-tool-dialog', () => ({ HttpToolDialog: () => null }))
mock.module('@/app/(platform)/app/capabilities/_components/mcp-tool-dialog', () => ({ McpToolDialog: () => null }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-test-panel', () => ({ ToolTestPanel: () => null }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-config-dialog', () => ({ ToolConfigDialog: () => null }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: () => null }))
mock.module('./delete-tool-dialog', () => ({ DeleteToolDialog: () => null }))
mock.module('./tool-share-dialog', () => ({ ToolShareDialog: () => null }))

const { ToolsClient } = await import('./tools-client')

const tools = [
  {
    id: undefined,
    name: 'builtin_time',
    display_name: 'Time Tool',
    type: 'builtin',
    category: 'time',
    is_enabled: true,
    requires_config: true,
    team_id: undefined,
    created_by_name: undefined,
  },
  {
    id: 'http-tool',
    name: 'weather',
    display_name: 'Weather Tool',
    type: 'custom',
    custom_type: 'http',
    category: 'web',
    is_enabled: false,
    team_id: 'team-2',
    created_by_name: 'Alice',
  },
]

const teams = [
  { id: 'team-1', name: 'Alpha' },
  { id: 'team-2', name: 'Beta' },
]

function renderWithState(overrides: Record<number, unknown> = {}) {
  const consoleError = spyOn(console, 'error').mockImplementation(() => {})
  const values = [
    tools,
    teams,
    'team-1',
    [{ value: 'web', label: 'Web' }],
    [{ value: 'alice', label: 'Alice' }],
    [{ value: 'team-1', label: 'Alpha' }, { value: 'team-2', label: 'Beta' }],
    false,
    1,
    10,
    { total: tools.length, items: tools },
    new Set(),
    new Set(),
    new Set(),
    new Set(),
    new Set(),
    new Set(),
    false,
    false,
    null,
    null,
    false,
    false,
    null,
    false,
    null,
    false,
    null,
    null,
    false,
  ]
  const useState = spyOn(React, 'useState').mockImplementation((initial: unknown) => {
    const index = useState.mock.calls.length - 1
    return [overrides[index] ?? values[index] ?? initial, mock()] as never
  })

  try {
    return renderToStaticMarkup(<ToolsClient />)
  } finally {
    useState.mockRestore()
    consoleError.mockRestore()
  }
}

afterEach(() => {
  push.mockClear()
})

describe('dashboard ToolsClient', () => {
  test('renders server-provided tools with type, category, team, creator, status, and actions', () => {
    const html = renderWithState()

    expect(html).toContain('Time Tool')
    expect(html).toContain('Weather Tool')
    expect(html).toContain('tools.filters.builtin')
    expect(html).toContain('tools.filters.custom')
    expect(html).toContain('tools.categories.time')
    expect(html).toContain('tools.categories.web')
    expect(html).toContain('Beta')
    expect(html).toContain('Alice')
    expect(html).toContain('tools.enabled')
    expect(html).toContain('tools.disabled')
    expect(html).toContain('tools.runTest')
    expect(html).toContain('common.edit')
    expect(html).toContain('tools.duplicate')
    expect(html).toContain('packages.export')
    expect(html).toContain('tools.share.title')
    expect(html).toContain('tools.enable')
    expect(html).toContain('common.delete')
  })

  test('shows bulk delete toolbar only when non-builtin tools are selected', () => {
    expect(renderWithState()).not.toContain('1 tools.toolsSelected')

    const html = renderWithState({ 15: new Set(['http-tool']) })

    expect(html).toContain('1 tools.toolsSelected')
    expect(html).toContain('confirm bulk delete 1')
  })
})
