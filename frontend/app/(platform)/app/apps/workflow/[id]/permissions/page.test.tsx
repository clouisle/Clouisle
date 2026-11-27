import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const push = mock(() => {})
const getWorkflow = mock(() => Promise.resolve(workflow))

mock.module('next/navigation', () => ({
  useParams: () => ({ id: 'workflow-1' }),
  useRouter: () => ({ push }),
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))

let currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'owner' }
let currentUser: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
let editorProps: Record<string, unknown> | undefined

mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: currentUser }) }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflow } }))
mock.module('../_components/access-policy-editor', () => ({
  AccessPolicyEditor: (props: Record<string, unknown>) => {
    editorProps = props
    return React.createElement('div', { 'data-policy-editor': 'true' })
  },
}))

const workflow = {
  id: 'workflow-1',
  name: 'Coverage Flow',
  team_id: 'team-1',
  created_by_id: 'user-1',
}

const { default: WorkflowPermissionsPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
let renderer: ReactTestRenderer | undefined

afterEach(() => {
  if (renderer) {
    act(() => {
      renderer?.unmount()
    })
    renderer = undefined
  }
  push.mockClear()
  getWorkflow.mockClear()
  editorProps = undefined
  currentTeam = { id: 'team-1', role: 'owner' }
  currentUser = { id: 'user-1' }
})

async function renderPage() {
  await act(async () => {
    renderer = create(React.createElement(WorkflowPermissionsPage))
  })
  return renderer!
}

test('loads the workflow and grants editing to its owner', async () => {
  await renderPage()

  expect(getWorkflow).toHaveBeenCalledWith('workflow-1')
  expect(editorProps).toMatchObject({
    workflowId: 'workflow-1',
    teamId: 'team-1',
    readOnly: false,
  })
})

test('a plain team member sees a read-only policy editor', async () => {
  currentTeam = { id: 'team-1', role: 'member' }
  currentUser = { id: 'user-2' }

  await renderPage()

  expect(editorProps).toMatchObject({ readOnly: true })
})

test('a superuser keeps editing rights outside the owning team', async () => {
  currentTeam = null
  currentUser = { id: 'user-9', is_superuser: true }

  await renderPage()

  expect(editorProps).toMatchObject({ readOnly: false })
})

test('shows the not-found state and returns to the workflow list', async () => {
  getWorkflow.mockImplementationOnce(() => Promise.resolve(null as never) as never)

  const tree = await renderPage()
  expect(editorProps).toBeUndefined()
  expect(JSON.stringify(tree.toJSON())).toContain('workflowNotFound')

  const back = tree.root.findAll(
    node => typeof node.props?.onClick === 'function',
  )[0]
  act(() => {
    back.props.onClick()
  })
  expect(push).toHaveBeenCalledWith('/app/apps/workflow')
})

