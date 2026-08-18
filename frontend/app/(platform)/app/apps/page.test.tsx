import { beforeEach, describe, expect, it, mock } from 'bun:test'
import * as ReactActual from 'react'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let agentsResult: { items: Array<Record<string, unknown>> } = { items: [] }
let workflowsResult: { items: Array<Record<string, unknown>> } = { items: [] }
let currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'member' }
let currentUser: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
let allowed = new Set<string>()
let params = new URLSearchParams()
let stateValues: unknown[] = []
const replace = mock(() => {})
const push = mock(() => {})
const setState = mock((value: unknown) => value)
const getAgents = mock(async () => agentsResult)
const getWorkflows = mock(async () => workflowsResult)

mock.module('react', () => ({
  ...ReactActual,
  default: ReactActual,
  useEffect: (effect: () => void) => effect(),
  useState: (initial: unknown) => [stateValues.length ? stateValues.shift() : initial, setState],
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, string>) => values?.name ? `${key} ${values.name}` : key }))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => params,
}))
mock.module('next/link', () => ({ default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a> }))
mock.module('next/image', () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-require-team', () => ({ useRequireTeam: () => undefined }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: currentUser }) }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: (permission: string) => allowed.has(permission) }) }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents, deleteAgent: mock(() => {}), duplicateAgent: mock(() => {}), publishAgent: mock(() => {}), unpublishAgent: mock(() => {}) } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflows, deleteWorkflow: mock(() => {}), duplicateWorkflow: mock(() => {}), publishWorkflow: mock(() => {}), unpublishWorkflow: mock(() => {}) } }))
mock.module('@/lib/api/packages', () => ({ packagesApi: { export: mock(() => {}) }, downloadBlob: mock(() => {}) }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => <div {...props}>{children}</div>,
  CardDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  CardTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: { children: ReactNode; [key: string]: unknown }) => <div {...props}>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ render }: { render: (props: Record<string, unknown>) => ReactNode }) => <>{render({})}</>,
}))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: ReactNode; value: string }) => <button value={value}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  AlertDialogCancel: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))
mock.module('./_components/app-create-dialog', () => ({ AppCreateDialog: ({ open, initialType }: { open: boolean; initialType: string }) => <div data-testid="create-dialog">{open ? initialType : 'closed'}</div> }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: ({ open, expectedResourceType }: { open: boolean; expectedResourceType?: string }) => <div data-testid="import-dialog">{open ? expectedResourceType : 'closed'}</div> }))

const AppsPage = (await import('./page')).default

function renderPage() {
  return renderToStaticMarkup(<AppsPage />)
}

beforeEach(() => {
  agentsResult = { items: [] }
  workflowsResult = { items: [] }
  currentTeam = { id: 'team-1', role: 'member' }
  currentUser = { id: 'user-1' }
  allowed = new Set<string>()
  params = new URLSearchParams()
  stateValues = []
  replace.mockClear()
  push.mockClear()
  setState.mockClear()
  getAgents.mockClear()
  getWorkflows.mockClear()
})

describe('AppsPage', () => {
  it('shows loading before fetch completes and hides create controls without permission', () => {
    const html = renderPage()

    expect(html).toContain('animate-spin')
    expect(html).not.toContain('apps-create-button')
    expect(html).toContain('data-testid="create-dialog"')
    expect(html).toContain('closed')
  })

  it('renders success and filters workflow tab data from state', () => {
    stateValues = ['workflow', '', [
      { id: 'agent-1', name: 'Sales agent', description: 'A', icon: null, status: 'published', type: 'agent', conversation_count: 2, message_count: 3, created_at: '2025-01-01', updated_at: '2025-01-03', created_by_id: 'user-1', created_by_name: 'me' },
      { id: 'workflow-1', name: 'Billing flow', description: 'B', icon: null, status: 'draft', type: 'workflow', run_count: 4, success_count: 3, fail_count: 1, created_at: '2025-01-01', updated_at: '2025-01-02', created_by_id: 'user-2', created_by_name: 'other' },
    ], false]

    const html = renderPage()

    expect(html).not.toContain('Sales agent')
    expect(html).toContain('Billing flow')
    expect(html).toContain('4 runs')
    expect(html).toContain('1 failed')
  })

  it('assigns first onboarding selectors to the first Agent in a mixed list', () => {
    stateValues = ['all', '', [
      { id: 'workflow-1', name: 'Billing flow', description: 'B', icon: null, status: 'draft', type: 'workflow', run_count: 4, success_count: 3, fail_count: 1, created_at: '2025-01-01', updated_at: '2025-01-03', created_by_id: 'user-2', created_by_name: 'other' },
      { id: 'agent-1', name: 'Sales agent', description: 'A', icon: null, status: 'published', type: 'agent', conversation_count: 2, message_count: 3, created_at: '2025-01-01', updated_at: '2025-01-02', created_by_id: 'user-1', created_by_name: 'me' },
    ], false]

    const html = renderPage()

    expect(html).toContain('data-testid="app-card-first"')
    expect(html).toContain('data-testid="app-actions-button-first"')
    expect(html).toContain('data-testid="app-chat-button-first"')
    expect(html).toContain('data-testid="app-card-workflow-1"')
    expect(html).toContain('data-testid="app-actions-button-workflow-1"')
    expect(html).not.toContain('data-testid="app-chat-button-workflow-1"')
  })

  it('opens create dialog from query params and preserves remaining tab query', () => {
    allowed = new Set(['workflow:create'])
    params = new URLSearchParams('action=create&type=workflow&tab=agent')
    globalThis.window = { location: { pathname: '/app/apps' } } as unknown as Window & typeof globalThis

    renderPage()

    expect(setState).toHaveBeenCalledWith('workflow')
    expect(setState).toHaveBeenCalledWith(true)
    expect(replace).toHaveBeenCalledWith('/app/apps?tab=agent', { scroll: false })
    expect(renderPage()).toContain('apps-create-button')
  })

  it('exposes create and admin actions only across permission boundaries', () => {
    currentTeam = { id: 'team-1', role: 'admin' }
    stateValues = ['all', '', [{ id: 'agent-1', name: 'Admin app', description: null, icon: null, status: 'draft', type: 'agent', conversation_count: 0, message_count: 0, created_at: '2025-01-01', updated_at: '2025-01-01', created_by_id: 'user-2', created_by_name: 'other' }], false]

    const html = renderPage()

    expect(html).toContain('apps-create-button')
    expect(html).toContain('configure')
    expect(html).toContain('publish')
    expect(html).toContain('duplicate')
    expect(html).toContain('delete')
  })
})
