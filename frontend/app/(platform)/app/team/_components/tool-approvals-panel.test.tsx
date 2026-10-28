import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import type { Tool, ToolApprovalGate, ToolApprovalPolicy } from '@/lib/api/tools'

const toolsApi = {
  list: mock(),
  update: mock(),
}
const toast = { success: mock() }

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api', () => ({ toolsApi }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.ComponentProps<'input'>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.ComponentProps<'label'>) => (
    <label {...props}>{children}</label>
  ),
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.ComponentProps<'span'>) => (
    <span {...props}>{children}</span>
  ),
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/skeleton', () => ({
  Skeleton: () => <div data-skeleton="true" />,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-dialog-open="true">{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h3>{children}</h3>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <span role="alert">{children}</span> : null,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({
    children,
    value,
    onValueChange,
    disabled,
  }: React.PropsWithChildren<{
    value?: string
    onValueChange: (value: string) => void
    disabled?: boolean
  }>) => (
    <select
      value={value ?? ''}
      disabled={disabled}
      onChange={(event) => onValueChange(event.target.value)}
    >
      {children}
    </select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => (
    <option value={value}>{children}</option>
  ),
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('lucide-react', () =>
  Object.fromEntries(
    [
      'AlertTriangle',
      'Loader2',
      'Lock',
      'Pencil',
      'Plus',
      'RefreshCw',
      'Search',
      'Trash2',
    ].map((name) => [
      name,
      (props: Record<string, unknown>) => <i data-icon={name} {...props} />,
    ])
  )
)

// Dynamic import is required: bun module mocks must be registered before the
// panel and the tool policy editor it imports are loaded.
const { TeamToolApprovalsPanel } = await import('./tool-approvals-panel')

const CALLER_GATE: ToolApprovalGate = {
  kind: 'caller',
  user_ids: [],
  roles: [],
  allow_self_approval: false,
}

const ALLOW_POLICY: ToolApprovalPolicy = {
  default_decision: 'allow',
  gates: [],
  operation_overrides: {},
}

const LEGACY_POLICY: ToolApprovalPolicy = {
  default_decision: 'require_approval',
  gates: [{ kind: 'team_role', user_ids: [], roles: ['admin'], allow_self_approval: false }],
  operation_overrides: {},
}

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    name: 'custom_tool',
    display_name: 'Custom Tool',
    description: '',
    type: 'custom',
    category: 'api',
    visibility: 'team',
    parameters: [],
    is_enabled: true,
    requires_config: false,
    config_fields: [],
    is_owned: true,
    created_by_id: 'u-owner',
    approval_policy: ALLOW_POLICY,
    ...overrides,
  }
}

function response(builtin: Tool[] = [], custom: Tool[] = [], mcp: Tool[] = []) {
  return { builtin, custom, mcp }
}

let renderer: ReactTestRenderer | undefined

function element(props: Partial<React.ComponentProps<typeof TeamToolApprovalsPanel>> = {}) {
  return (
    <TeamToolApprovalsPanel
      teamId="team-1"
      enabled
      currentUserId="u-owner"
      isSuperuser={false}
      membershipRole="owner"
      canReadTools
      canUpdateTools
      {...props}
    />
  )
}

async function render(props: Partial<React.ComponentProps<typeof TeamToolApprovalsPanel>> = {}) {
  await act(async () => {
    renderer = create(element(props))
  })
  return renderer
}

function text() {
  return JSON.stringify(renderer!.toJSON())
}

function editButton(toolId: string) {
  return renderer!.root.findAllByProps({ 'data-testid': `edit-tool-approval-${toolId}` })[0]
}

function saveButton() {
  return renderer!.root.findAllByProps({ 'data-testid': 'save-tool-approval' })[0]
}

async function clickEdit(toolId: string) {
  const node = editButton(toolId)
  if (!node) throw new Error(`No edit button for ${toolId}`)
  await act(async () => node.props.onClick())
}

function decisionSelect() {
  return Array.from(document.querySelectorAll('select')).find(
    (item) =>
      Array.from(item.options)
        .map((option) => option.value)
        .join(',') === 'allow,deny,require_approval'
  )!
}

async function chooseDecision(value: string) {
  const select = decisionSelect()
  await act(async () => {
    select.value = value
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function clickSave() {
  const node = saveButton()
  await act(async () => node.props.onClick())
}

beforeEach(() => {
  toolsApi.list.mockReset().mockResolvedValue(response())
  toolsApi.update.mockReset()
  toast.success.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
})

describe('TeamToolApprovalsPanel', () => {
  test('loads every tool available to the team and shows its real policy decision', async () => {
    toolsApi.list.mockResolvedValue(
      response(
        [makeTool({ id: 'builtin-1', name: 'web_search', display_name: 'Web Search', type: 'builtin' })],
        [
          makeTool({
            id: 'custom-1',
            name: 'deploy',
            display_name: 'Deploy',
            approval_policy: { default_decision: 'deny', gates: [], operation_overrides: {} },
          }),
        ],
        [
          makeTool({
            id: 'mcp-1',
            name: 'github',
            display_name: 'GitHub',
            type: 'mcp',
            visibility: 'private',
            approval_policy: {
              default_decision: 'require_approval',
              gates: [CALLER_GATE],
              operation_overrides: {},
            },
          }),
        ]
      )
    )

    await render()
    const content = text()

    expect(toolsApi.list).toHaveBeenCalledWith('team-1')
    expect(content).toContain('Web Search')
    expect(content).toContain('Deploy')
    expect(content).toContain('GitHub')
    expect(content).toContain('decisions.deny')
    expect(content).toContain('decisions.require_approval')
    expect(content).toContain('types.mcp')
    expect(content).toContain('visibility.private')
    expect(editButton('builtin-1')).toBeDefined()
  })

  test('never renders another member private tool', async () => {
    toolsApi.list.mockResolvedValue(
      response([], [
        makeTool({
          id: 'private-other',
          name: 'other_secret',
          display_name: 'Other Secret',
          visibility: 'private',
          created_by_id: 'u-other',
        }),
        makeTool({
          id: 'private-own',
          name: 'own_secret',
          display_name: 'Own Secret',
          visibility: 'private',
          created_by_id: 'u-owner',
        }),
      ])
    )

    await render()
    const content = text()

    expect(content).not.toContain('Other Secret')
    expect(content).toContain('Own Secret')
  })

  test('saves an explicit deny decision on a team tool', async () => {
    toolsApi.list.mockResolvedValue(response([], [makeTool()]))
    toolsApi.update.mockResolvedValue(makeTool())
    await render({ membershipRole: 'admin' })

    await clickEdit('tool-1')
    await chooseDecision('deny')
    await clickSave()

    expect(toolsApi.update).toHaveBeenCalledWith('tool-1', {
      approval_policy: { default_decision: 'deny', gates: [], operation_overrides: {} },
    })
    expect(toast.success).toHaveBeenCalledWith('saved')
    expect(text()).toContain('decisions.deny')
  })

  test('edits MCP operation overrides without dropping the saved ones', async () => {
    const overridePolicy: ToolApprovalPolicy = {
      default_decision: 'require_approval',
      gates: [CALLER_GATE],
      operation_overrides: {
        'tool:delete_repo': {
          default_decision: 'deny',
          gates: [],
          operation_overrides: {},
        },
      },
    }
    toolsApi.list.mockResolvedValue(
      response([], [], [
        makeTool({
          id: 'mcp-1',
          name: 'github',
          display_name: 'GitHub',
          type: 'mcp',
          approval_policy: overridePolicy,
        }),
      ])
    )
    toolsApi.update.mockResolvedValue(makeTool())
    await render()

    await clickEdit('mcp-1')
    expect(text()).toContain('operations.title')
    expect(text()).toContain('tool:delete_repo')

    const operationInput = renderer!.root.findByProps({
      placeholder: 'operations.operationPlaceholder',
    })
    await act(async () => operationInput.props.onChange({ target: { value: 'tool:create_issue' } }))
    const addOperation = Array.from(document.querySelectorAll('button')).find(
      (button) => button.textContent === 'operations.addOperation'
    )!
    await act(async () => addOperation.click())

    await chooseDecision('allow')
    await clickSave()

    expect(toolsApi.update).toHaveBeenCalledWith('mcp-1', {
      approval_policy: {
        default_decision: 'allow',
        gates: [],
        operation_overrides: {
          ...overridePolicy.operation_overrides,
          'tool:create_issue': {
            default_decision: 'require_approval',
            gates: [CALLER_GATE],
            operation_overrides: {},
          },
        },
      },
    })
  })

  test('treats builtin definitions as team-scoped for their owner and admins', async () => {
    toolsApi.list.mockResolvedValue(
      response([
        makeTool({
          id: 'builtin-team',
          name: 'web_search',
          display_name: 'Builtin Team',
          type: 'builtin',
          // `/tools/legacy` does not copy the definition's TEAM visibility;
          // the default serialized value must not make this look private.
          visibility: 'private',
          created_by_id: null,
        }),
      ])
    )

    await render({ membershipRole: 'admin' })
    const content = text()

    expect(content).toContain('Builtin Team')
    expect(content).toContain('visibility.team')
    expect(editButton('builtin-team')).toBeDefined()
  })

  test('shows an unmaterialized builtin as unavailable instead of hiding it', async () => {
    toolsApi.list.mockResolvedValue(
      response([
        makeTool({
          id: undefined,
          name: 'ghost_builtin',
          display_name: 'Ghost Builtin',
          type: 'builtin',
          visibility: 'private',
          created_by_id: null,
        }),
      ])
    )

    await render()
    const content = text()

    expect(content).toContain('Ghost Builtin')
    expect(content).toContain('visibility.team')
    expect(content).toContain('policyUnavailable')
    expect(content).toContain('readOnly.policyUnavailable')
    // The registry default policy is not the saved policy.
    expect(content).not.toContain('decisions.')
    expect(editButton('ghost_builtin')).toBeUndefined()

    const reload = renderer!.root.findAllByProps({
      'data-testid': 'reload-tool-approval-ghost_builtin',
    })[0]
    await act(async () => reload.props.onClick())
    expect(toolsApi.list).toHaveBeenCalledTimes(2)
  })

  test('does not synthesize a decision for an unsaved tool policy', async () => {
    toolsApi.list.mockResolvedValue(
      response([], [
        makeTool({
          id: 'no-policy',
          name: 'no_policy',
          display_name: 'No Policy Tool',
          approval_policy: undefined,
        }),
      ])
    )

    await render()
    const content = text()

    expect(content).toContain('policyUnavailable')
    expect(content).toContain('readOnly.policyUnavailable')
    expect(content).not.toContain('decisions.')
    expect(editButton('no-policy')).toBeUndefined()
  })

  test('ignores a stale response after the team changes', async () => {
    const firstTeam = Promise.withResolvers<unknown>()
    const secondTeam = Promise.withResolvers<unknown>()
    toolsApi.list
      .mockImplementationOnce(() => firstTeam.promise)
      .mockImplementationOnce(() => secondTeam.promise)

    await render({ teamId: 'team-1' })
    await act(async () => {
      renderer!.update(element({ teamId: 'team-2' }))
    })

    await act(async () => {
      secondTeam.resolve(
        response([], [makeTool({ id: 'team-2-tool', display_name: 'Team Two Tool' })])
      )
    })
    expect(text()).toContain('Team Two Tool')

    await act(async () => {
      firstTeam.resolve(
        response([], [makeTool({ id: 'team-1-tool', display_name: 'Team One Tool' })])
      )
    })
    expect(text()).not.toContain('Team One Tool')
    expect(toolsApi.list).toHaveBeenNthCalledWith(1, 'team-1')
    expect(toolsApi.list).toHaveBeenNthCalledWith(2, 'team-2')
  })

  test('treats shared tools as read-only and never reveals the owning team', async () => {
    toolsApi.list.mockResolvedValue(
      response([], [
        makeTool({
          id: 'shared-1',
          display_name: 'Shared Search',
          is_owned: false,
          owner_team_id: 'team-secret',
          owner_team_name: 'Secret Owner Team',
          share_permission: 'read_execute',
        }),
      ])
    )

    await render({ membershipRole: 'admin' })
    const content = text()

    expect(content).toContain('readOnly.sharedTool')
    expect(content).not.toContain('Secret Owner Team')
    expect(editButton('shared-1')).toBeUndefined()
  })

  test('members can edit their own tool but not another member team tool', async () => {
    toolsApi.list.mockResolvedValue(
      response(
        [
          makeTool({
            id: 'builtin-1',
            name: 'web_search',
            display_name: 'Builtin Search',
            type: 'builtin',
            created_by_id: null,
          }),
        ],
        [
          makeTool({ id: 'other-team', display_name: 'Other Team Tool', created_by_id: 'u-other' }),
          makeTool({ id: 'own-team', display_name: 'Own Team Tool', created_by_id: 'u-member' }),
        ]
      )
    )

    await render({ currentUserId: 'u-member', membershipRole: 'member' })
    const content = text()

    expect(content).toContain('readOnly.teamAdminOnly')
    expect(editButton('builtin-1')).toBeUndefined()
    expect(editButton('other-team')).toBeUndefined()
    expect(editButton('own-team')).toBeDefined()
  })

  test('viewers and users without tool:update cannot change policies', async () => {
    toolsApi.list.mockResolvedValue(response([], [makeTool()]))

    await render({ membershipRole: 'viewer' })
    expect(text()).toContain('readOnly.viewerOnly')

    await act(async () => {
      renderer!.unmount()
      renderer = undefined
    })
    await render({ canUpdateTools: false })
    expect(text()).toContain('readOnly.permissionDenied')
    expect(editButton('tool-1')).toBeUndefined()
  })

  test('superusers may edit shared tools, matching backend authorization', async () => {
    toolsApi.list.mockResolvedValue(
      response([], [makeTool({ id: 'shared-1', is_owned: false })])
    )

    await render({ isSuperuser: true, currentUserId: 'u-root', membershipRole: undefined })

    expect(editButton('shared-1')).toBeDefined()
  })

  test('blocks saving a legacy audience until the administrator resets it', async () => {
    toolsApi.list.mockResolvedValue(
      response([], [makeTool({ approval_policy: LEGACY_POLICY })])
    )
    toolsApi.update.mockResolvedValue(makeTool())
    await render()

    expect(text()).toContain('legacyBadge')
    await clickEdit('tool-1')

    expect(text()).toContain('approval.legacyTitle')
    expect(saveButton().props.disabled).toBe(true)

    const reset = Array.from(document.querySelectorAll('button')).find(
      (button) => button.textContent === 'approval.legacyReset'
    )!
    await act(async () => reset.click())

    expect(saveButton().props.disabled).toBe(false)
    await clickSave()

    expect(toolsApi.update).toHaveBeenCalledWith('tool-1', {
      approval_policy: {
        default_decision: 'require_approval',
        gates: [CALLER_GATE],
        operation_overrides: {},
      },
    })
  })

  test('keeps the dialog open and reports a failed save', async () => {
    toolsApi.list.mockResolvedValue(response([], [makeTool()]))
    toolsApi.update.mockRejectedValue(new Error('forbidden'))
    await render()

    await clickEdit('tool-1')
    await clickSave()

    expect(text()).toContain('saveFailed')
    expect(saveButton()).toBeDefined()
    expect(toast.success).not.toHaveBeenCalled()
  })

  test('renders loading, failure, retry, empty, and no-match states', async () => {
    const pending = Promise.withResolvers<unknown>()
    toolsApi.list.mockImplementationOnce(() => pending.promise)
    await render()

    expect(renderer!.root.findAllByProps({ 'data-skeleton': 'true' }).length).toBe(6)
    await act(async () => pending.resolve(response()))
    expect(text()).toContain('empty')
    expect(text()).toContain('emptyHint')

    await act(async () => {
      renderer!.unmount()
      renderer = undefined
    })
    toolsApi.list.mockRejectedValueOnce(new Error('network'))
    const retryable = (await render())!
    await act(async () => {})
    expect(JSON.stringify(retryable.toJSON())).toContain('loadFailed')

    toolsApi.list.mockResolvedValueOnce(response([], [makeTool({ display_name: 'Search Me' })]))
    const retryButton = retryable.root
      .findAllByType('button')
      .find((button) => button.props.children === 'retry')!
    await act(async () => retryButton.props.onClick())
    expect(JSON.stringify(retryable.toJSON())).toContain('Search Me')

    const search = retryable.root.findByProps({ placeholder: 'searchPlaceholder' })
    await act(async () => search.props.onChange({ target: { value: 'no-such-tool' } }))
    expect(JSON.stringify(retryable.toJSON())).toContain('noMatches')
  })

  test('does not fetch or reveal tools without tool:read', async () => {
    await render({ canReadTools: false })

    expect(toolsApi.list).not.toHaveBeenCalled()
    expect(text()).toContain('readDenied')
  })

  test('does not fetch until the approvals tab is active', async () => {
    await render({ enabled: false })

    expect(toolsApi.list).not.toHaveBeenCalled()
    expect(renderer!.toJSON()).toBeNull()
  })
})
