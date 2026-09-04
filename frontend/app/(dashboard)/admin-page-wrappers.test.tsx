import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import React, { type ReactNode } from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('@/components/auth/permission-guard', () => ({
  RoutePermissionGuard: ({ children }: { children: ReactNode }) => (
    <section aria-label="Restricted administration">{children}</section>
  ),
}))
mock.module('@/components/layout/header', () => ({
  Header: () => <header data-testid="dashboard-header">Administration</header>,
}))
mock.module('./apps/_components/admin-app-edit-providers', () => ({
  AdminAppEditProviders: ({ children }: { children: ReactNode }) => <>{children}</>,
}))
mock.module('./apps/_components/admin-agent-edit-client', () => ({
  AdminAgentEditClient: ({ agentId }: { agentId: string }) => (
    <main data-client="agent-edit" data-agent-id={agentId}><h1>Edit agent</h1></main>
  ),
}))
mock.module('./apps/_components/admin-workflow-edit-client', () => ({
  AdminWorkflowEditClient: ({ workflowId }: { workflowId: string }) => (
    <main data-client="workflow-edit" data-workflow-id={workflowId}><h1>Edit workflow</h1></main>
  ),
}))
mock.module('./audit-logs/_components/audit-logs-client', () => ({
  AuditLogsClient: () => <main data-client="audit-logs"><h1>Audit logs</h1></main>,
}))
mock.module('./permissions/_components', () => ({
  PermissionsClient: () => <main data-client="permissions"><h1>Permissions</h1></main>,
}))
mock.module('./roles/_components', () => ({
  RolesClient: () => <main data-client="roles"><h1>Roles</h1></main>,
}))
mock.module('./users/_components', () => ({
  UsersClient: () => <main data-client="users"><h1>Users</h1></main>,
}))

let AdminAgentEditPage: typeof import('./apps/agents/[id]/edit/page').default
let AdminWorkflowEditPage: typeof import('./apps/workflows/[id]/edit/page').default
let AuditLogsPage: typeof import('./audit-logs/page').default
let PermissionsPage: typeof import('./permissions/page').default
let RolesPage: typeof import('./roles/page').default
let UsersPage: typeof import('./users/page').default

beforeAll(async () => {
  ;({ default: AdminAgentEditPage } = await import('./apps/agents/[id]/edit/page'))
  ;({ default: AdminWorkflowEditPage } = await import('./apps/workflows/[id]/edit/page'))
  ;({ default: AuditLogsPage } = await import('./audit-logs/page'))
  ;({ default: PermissionsPage } = await import('./permissions/page'))
  ;({ default: RolesPage } = await import('./roles/page'))
  ;({ default: UsersPage } = await import('./users/page'))
})

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
})

async function renderPage(element: React.ReactNode | Promise<React.ReactNode>) {
  let renderer!: ReactTestRenderer
  await act(async () => { renderer = create(await element) })
  renderers.push(renderer)
  return renderer
}

function expectRestrictedAdminPage(renderer: ReactTestRenderer, heading: string) {
  expect(renderer.root.findByProps({ 'aria-label': 'Restricted administration' })).toBeDefined()
  expect(renderer.root.findByProps({ 'data-testid': 'dashboard-header' }).children).toEqual(['Administration'])
  expect(renderer.root.findAllByType('main')).toHaveLength(1)
  expect(renderer.root.findByType('h1').children).toEqual([heading])
}

describe('admin dashboard page wrappers', () => {
  test('delegates agent and workflow route ids within restricted editing pages', async () => {
    const agent = await renderPage(AdminAgentEditPage({ params: Promise.resolve({ id: 'agent-42' }) }))
    expectRestrictedAdminPage(agent, 'Edit agent')
    expect(agent.root.findByType('main').props).toMatchObject({
      'data-client': 'agent-edit',
      'data-agent-id': 'agent-42',
    })

    const workflow = await renderPage(AdminWorkflowEditPage({ params: Promise.resolve({ id: 'workflow-84' }) }))
    expectRestrictedAdminPage(workflow, 'Edit workflow')
    expect(workflow.root.findByType('main').props).toMatchObject({
      'data-client': 'workflow-edit',
      'data-workflow-id': 'workflow-84',
    })
  })

  test('exposes guarded administration landmarks for audit and access management', async () => {
    for (const [Page, heading] of [
      [AuditLogsPage, 'Audit logs'],
      [PermissionsPage, 'Permissions'],
      [RolesPage, 'Roles'],
      [UsersPage, 'Users'],
    ] as const) {
      const renderer = await renderPage(<Page />)
      expectRestrictedAdminPage(renderer, heading)
    }
  })
})
