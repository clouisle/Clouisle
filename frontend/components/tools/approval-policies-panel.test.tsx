import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { ToolApprovalPolicy } from '@/lib/api/tools'

const list = mock(async () => [])
const createPolicy = mock(async () => ({}))
const updatePolicy = mock(async () => ({}))
const removePolicy = mock(async () => null)
const toastSuccess = mock(() => undefined)
const toastError = mock(() => undefined)
const normalize = mock((policy: ToolApprovalPolicy) => policy)
let team: Record<string, unknown> | null = { id: 'team-1', name: 'Team One', role: 'admin' }
let canUpdateTools = true
let canManageSettings = false

class ApiError extends Error {
  code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('lucide-react', () => ({
  Loader2: () => <span />,
  Pencil: () => <span />,
  Plus: () => <span />,
  RefreshCw: () => <span />,
  ShieldCheck: () => <span />,
  Trash2: () => <span />,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: team }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: { id: 'user-1', is_superuser: false } }) }))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({
    canPerform: (permission: string | string[]) => {
      const permissions = Array.isArray(permission) ? permission : [permission]
      if (permissions.includes('admin:settings:update')) return canManageSettings
      return canUpdateTools
    },
  }),
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span data-badge>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectValue: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{children}</> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{children}</> : null,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  AlertDialogCancel: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/tools/tool-policy-editor', () => ({
  normalizeToolApprovalPolicy: normalize,
  createDefaultApprovalPolicy: () => ({
    default_decision: 'require_approval',
    gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
    operation_overrides: {},
  }),
  ToolApprovalPolicyEditor: ({
    approvalPolicy,
    onApprovalPolicyChange,
  }: {
    approvalPolicy: ToolApprovalPolicy
    onApprovalPolicyChange: (policy: ToolApprovalPolicy) => void
  }) => (
    <div data-testid="policy-editor">
      <button onClick={() => onApprovalPolicyChange({ ...approvalPolicy, default_decision: 'deny', gates: [] })}>
        change-to-deny
      </button>
    </div>
  ),
}))
mock.module('@/lib/api', () => ({
  ApiError,
  toolApprovalPoliciesApi: {
    list,
    create: createPolicy,
    update: updatePolicy,
    remove: removePolicy,
  },
}))

// Dynamic import is required so the module mocks above apply before the panel loads.
const { ApprovalPoliciesPanel } = await import('./approval-policies-panel')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 'policy-1',
    scope: 'site',
    team_id: null,
    entrypoint_kind: null,
    entrypoint_id: null,
    tool_id: null,
    policy: {
      default_decision: 'require_approval',
      gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    },
    policy_hash: 'hash',
    version: 3,
    can_edit: true,
    created_by_id: 'user-1',
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
    ...overrides,
  }
}

function textOfChildren(children: React.ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(textOfChildren).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(children)) {
    return textOfChildren(children.props.children)
  }
  return ''
}

function textOf(node: { props: Record<string, unknown> }): string {
  return textOfChildren(node.props.children as React.ReactNode)
}

function buttonByText(renderer: ReactTestRenderer, text: string) {
  return renderer.root.findAllByType('button').find((button) => textOf(button).includes(text))
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function renderPanel() {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(<ApprovalPoliciesPanel />)
  })
  renderers.push(renderer)
  await flush()
  return renderer
}

describe('ApprovalPoliciesPanel', () => {
  test('shows server-computed editability and saves edits with the row version', async () => {
    list.mockClear(); updatePolicy.mockClear(); normalize.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    canUpdateTools = true
    list.mockResolvedValue([
      row(),
      row({ id: 'policy-2', scope: 'team', team_id: 'team-1', can_edit: false }),
    ])
    const renderer = await renderPanel()

    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('policy-row-policy-1')
    expect(text).toContain('readOnly')
    expect(renderer.root.findAllByProps({ 'data-testid': 'policy-row-policy-2' })[0]
      .findAllByType('button')).toHaveLength(0)

    const edit = buttonByText(renderer, 'approvals.policy.edit')
    act(() => edit?.props.onClick())
    act(() => buttonByText(renderer, 'change-to-deny')?.props.onClick())
    act(() => buttonByText(renderer, 'approvals.policy.save')?.props.onClick())
    await flush()

    expect(normalize).toHaveBeenCalled()
    expect(updatePolicy).toHaveBeenCalledWith('policy-1', {
      policy: expect.objectContaining({ default_decision: 'deny', gates: [] }),
      expected_version: 3,
    })
    expect(toastSuccess).toHaveBeenCalledWith('approvals.policy.saved')
    expect(list).toHaveBeenCalledTimes(2)
  })

  test('creates a team policy with the selected team and no optimistic row', async () => {
    list.mockClear(); createPolicy.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    canUpdateTools = true
    list.mockResolvedValue([])
    const renderer = await renderPanel()

    act(() => buttonByText(renderer, 'approvals.policy.addTeam')?.props.onClick())
    act(() => buttonByText(renderer, 'approvals.policy.save')?.props.onClick())
    await flush()

    expect(createPolicy).toHaveBeenCalledWith({
      scope: 'team',
      team_id: 'team-1',
      policy: expect.objectContaining({ default_decision: 'require_approval' }),
      tool_id: null,
    })
    expect(list).toHaveBeenCalledTimes(2)
  })

  test('deletes only after the dialog confirms and refreshes from the server', async () => {
    list.mockClear(); removePolicy.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    list.mockResolvedValue([row()])
    const renderer = await renderPanel()

    act(() => buttonByText(renderer, 'approvals.policy.delete')?.props.onClick())
    act(() => buttonByText(renderer, 'approvals.policy.confirmDelete')?.props.onClick())
    await flush()

    expect(removePolicy).toHaveBeenCalledWith('policy-1')
    expect(list).toHaveBeenCalledTimes(2)
  })

  test('creates an entry point policy only with an explicit referenced id', async () => {
    list.mockClear(); createPolicy.mockClear(); toastError.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    canUpdateTools = true
    list.mockResolvedValue([])
    const renderer = await renderPanel()

    act(() => buttonByText(renderer, 'approvals.policy.addEntrypoint')?.props.onClick())
    act(() => buttonByText(renderer, 'approvals.policy.save')?.props.onClick())
    await flush()
    expect(createPolicy).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith('approvals.policy.entrypointIdRequired')

    const entrypointId = renderer.root.findAllByType('input').find((input) => input.props.id === 'policy-entrypoint-id')
    act(() => entrypointId?.props.onChange({ target: { value: 'agent-1' } }))
    act(() => buttonByText(renderer, 'approvals.policy.save')?.props.onClick())
    await flush()

    expect(createPolicy).toHaveBeenCalledWith({
      scope: 'entrypoint',
      team_id: 'team-1',
      entrypoint_kind: 'agent',
      entrypoint_id: 'agent-1',
      policy: expect.objectContaining({ default_decision: 'require_approval' }),
      tool_id: null,
    })
  })

  test('reports a version conflict without overwriting the policy', async () => {
    list.mockClear(); updatePolicy.mockClear(); toastError.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    canUpdateTools = true
    list.mockResolvedValue([row()])
    updatePolicy.mockRejectedValueOnce(new ApiError(409, 'tool_approval_policy_version_conflict'))
    const renderer = await renderPanel()

    act(() => buttonByText(renderer, 'approvals.policy.edit')?.props.onClick())
    act(() => buttonByText(renderer, 'approvals.policy.save')?.props.onClick())
    await flush()

    expect(toastError).toHaveBeenCalledWith('approvals.policy.versionConflict')
    expect(list).toHaveBeenCalledTimes(1)
  })

  test('renders generic and tool-specific rows for the same scope independently', async () => {
    list.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'admin' }
    canUpdateTools = true
    canManageSettings = false
    list.mockResolvedValue([
      row(),
      row({ id: 'policy-tool', tool_id: 'tool-1' }),
      row({ id: 'policy-team', scope: 'team', team_id: 'team-1' }),
      row({ id: 'policy-team-tool', scope: 'team', team_id: 'team-1', tool_id: 'tool-1' }),
    ])
    const renderer = await renderPanel()

    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('policy-row-policy-1')
    expect(text).toContain('policy-row-policy-tool')
    expect(text).toContain('policy-row-policy-team')
    expect(text).toContain('policy-row-policy-team-tool')
  })

  test('shows site creation only with the settings write permission', async () => {
    list.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'member' }
    canUpdateTools = false
    canManageSettings = false
    list.mockResolvedValue([])
    let renderer = await renderPanel()
    expect(buttonByText(renderer, 'approvals.policy.addSite')).toBeUndefined()

    act(() => renderer.unmount())
    renderers.length = 0
    canManageSettings = true
    renderer = await renderPanel()
    expect(buttonByText(renderer, 'approvals.policy.addSite')).toBeDefined()
  })

  test('hides creation controls without team tool permission', async () => {
    list.mockClear()
    team = { id: 'team-1', name: 'Team One', role: 'member' }
    canUpdateTools = false
    list.mockResolvedValue([])
    const renderer = await renderPanel()

    expect(buttonByText(renderer, 'approvals.policy.addTeam')).toBeUndefined()
    expect(buttonByText(renderer, 'approvals.policy.addEntrypoint')).toBeUndefined()
  })
})
