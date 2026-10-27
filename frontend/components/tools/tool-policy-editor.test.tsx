import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import type { ToolApprovalPolicy } from '@/lib/api/tools'
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.ComponentProps<'input'>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) => (children ? <span role="alert">{children}</span> : null),
}))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, id }: { checked: boolean; onCheckedChange: (value: boolean) => void; id?: string }) => (
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />
  ),
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange, id }: { checked?: boolean; onCheckedChange?: (value: boolean) => void; id?: string }) => (
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange?.(event.target.checked)} />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange, disabled }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void; disabled?: boolean }>) => (
    <select value={value ?? ''} disabled={disabled} onChange={(event) => onValueChange(event.target.value)}>{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
const APPROVER_ID = '11111111-1111-4111-8111-111111111111'
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ teams: [], currentTeam: null, isLoading: false }),
}))
mock.module('@/components/ui/combobox', () => ({
  Combobox: ({ children, onValueChange }: React.PropsWithChildren<{ onValueChange?: (value: unknown[]) => void }>) => (
    <div>
      <button type="button" onClick={() => onValueChange?.([{ value: APPROVER_ID, label: APPROVER_ID }])}>
        approver.add
      </button>
      {children}
    </div>
  ),
  ComboboxChips: ({ children }: React.PropsWithChildren) => <>{children}</>,
  ComboboxChip: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  ComboboxChipsInput: () => null,
  ComboboxContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  ComboboxEmpty: ({ children }: React.PropsWithChildren) => <>{children}</>,
  ComboboxList: ({ children }: { children?: React.ReactNode | ((option: unknown) => React.ReactNode) }) => (
    <>{typeof children === 'function' ? null : children}</>
  ),
  ComboboxItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  useComboboxAnchor: () => React.createRef(),
}))

// Dynamic import is required so module mocks above apply before the editor loads.
const {
  ToolApprovalPolicyEditor,
  ToolPolicyEditor,
  getToolApprovalPolicy,
  normalizeConnectionFields,
  normalizeToolApprovalPolicy,
} = await import('./tool-policy-editor')

let renderer: ReactTestRenderer | undefined
let latest: {
  identityPolicy: string
  connectionFields: Array<{ name: string; label: string; required: boolean; secret: boolean }>
  approvalPolicy: ToolApprovalPolicy
} | null = null

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
  latest = null
})

function Harness({
  operationNames,
  initialApprovalPolicy,
  operationTools,
  toolsLoaded,
}: {
  operationNames?: string[]
  initialApprovalPolicy?: ToolApprovalPolicy
  operationTools?: Array<{ name: string; description?: string }>
  toolsLoaded?: boolean
}) {
  const [identityPolicy, setIdentityPolicy] = React.useState<'none' | 'team_only' | 'personal_only' | 'selectable'>('none')
  const [connectionFields, setConnectionFields] = React.useState<Array<{ name: string; label: string; required: boolean; secret: boolean }>>([])
  const [approvalPolicy, setApprovalPolicy] = React.useState(initialApprovalPolicy ?? getToolApprovalPolicy(null))
  React.useEffect(() => {
    latest = { identityPolicy, connectionFields, approvalPolicy }
  }, [identityPolicy, connectionFields, approvalPolicy])
  return (
    <ToolPolicyEditor
      identityPolicy={identityPolicy}
      onIdentityPolicyChange={setIdentityPolicy}
      connectionFields={connectionFields}
      onConnectionFieldsChange={setConnectionFields}
      approvalPolicy={approvalPolicy}
      onApprovalPolicyChange={setApprovalPolicy}
      operationNames={operationNames}
      operationTools={operationTools}
      toolsLoaded={toolsLoaded}
    />
  )
}

async function render(
  operationNames?: string[],
  initialApprovalPolicy?: ToolApprovalPolicy
) {
  await act(async () => {
    renderer = create(
      <Harness
        operationNames={operationNames}
        initialApprovalPolicy={initialApprovalPolicy}
      />
    )
  })
}

function ApprovalOnlyHarness({ initialApprovalPolicy }: { initialApprovalPolicy?: ToolApprovalPolicy }) {
  const [approvalPolicy, setApprovalPolicy] = React.useState(initialApprovalPolicy ?? getToolApprovalPolicy(null))
  React.useEffect(() => {
    latest = { identityPolicy: 'none', connectionFields: [], approvalPolicy }
  }, [approvalPolicy])
  return (
    <ToolApprovalPolicyEditor
      approvalPolicy={approvalPolicy}
      onApprovalPolicyChange={setApprovalPolicy}
      operationNames={['tool:ping']}
    />
  )
}

function selects(): HTMLSelectElement[] {
  return Array.from(document.querySelectorAll('select'))
}

function button(text: string): HTMLButtonElement {
  return Array.from(document.querySelectorAll('button')).find((item) => item.textContent === text)!
}

function alerts(): string[] {
  return Array.from(document.querySelectorAll('[role="alert"]')).map((node) => node.textContent ?? '')
}

async function change(element: HTMLSelectElement, value: string) {
  await act(async () => {
    element.value = value
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

describe('ToolPolicyEditor', () => {
  test('switches identity mode and writes declared connection fields', async () => {
    await render()
    const identitySelect = selects().find((item) => item.value === 'none')!
    await change(identitySelect, 'personal_only')
    expect(latest?.identityPolicy).toBe('personal_only')

    await act(async () => button('connectionFields.add').click())
    expect(latest?.connectionFields).toHaveLength(1)

    const nameInput = renderer!.root.findByProps({ placeholder: 'connectionFields.namePlaceholder' })
    const labelInput = renderer!.root.findByProps({ placeholder: 'connectionFields.labelPlaceholder' })
    await act(async () => nameInput.props.onChange({ target: { value: 'api_key' } }))
    await act(async () => labelInput.props.onChange({ target: { value: 'API key' } }))
    expect(latest?.connectionFields[0]).toMatchObject({ name: 'api_key', label: 'API key', required: true, secret: true })

    const checkboxes = renderer!.root.findAll((node) => node.type === 'input' && node.props.type === 'checkbox')
    const secretToggle = checkboxes.at(-1)!
    await act(async () => secretToggle.props.onChange({ target: { checked: false } }))
    expect(latest?.connectionFields[0].secret).toBe(false)
  })

  test('keeps approval gates while switching decisions and normalizes non-approval decisions', async () => {
    await render(undefined, {
      default_decision: 'require_approval',
      gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    })
    expect(latest?.approvalPolicy.default_decision).toBe('require_approval')
    expect(latest?.approvalPolicy.gates).toEqual([
      { kind: 'caller', user_ids: [], roles: [], allow_self_approval: false },
    ])

    const decisionSelect = selects().find((item) => item.value === 'require_approval')!
    await change(decisionSelect, 'allow')
    expect(latest?.approvalPolicy.default_decision).toBe('allow')
    expect(latest?.approvalPolicy.gates).toHaveLength(1)

    const normalized = normalizeToolApprovalPolicy(latest!.approvalPolicy)
    expect(normalized.default_decision).toBe('allow')
    expect(normalized.gates).toEqual([])

    const allowSelect = selects().find((item) => item.value === 'allow')!
    await change(allowSelect, 'require_approval')
    expect(latest?.approvalPolicy.default_decision).toBe('require_approval')
    expect(latest?.approvalPolicy.gates).toHaveLength(1)
  })

  test('stores exact MCP operation overrides and removes them when inherited', async () => {
    await render(['tool:search_issues'])
    const operationSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'inherit')
    )!
    expect(operationSelect.value).toBe('inherit')

    await change(operationSelect, 'require_approval')
    expect(latest?.approvalPolicy.operation_overrides['tool:search_issues']).toEqual({
      default_decision: 'require_approval',
      gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    })

    const configuredSelect = selects().find((item) => item.value === 'require_approval')
    expect(configuredSelect).toBeTruthy()
    const overrideSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'inherit')
    )!
    await change(overrideSelect, 'inherit')
    expect(latest?.approvalPolicy.operation_overrides['tool:search_issues']).toBeUndefined()
  })

  test('combines descriptions with policies and retains rules after discovery changes', async () => {
    const policy: ToolApprovalPolicy = {
      default_decision: 'allow', gates: [],
      operation_overrides: {
        'tool:removed': { default_decision: 'deny', gates: [], operation_overrides: {} },
      },
    }
    await act(async () => {
      renderer = create(<Harness operationTools={[{ name: 'search', description: 'Search project records' }]} toolsLoaded initialApprovalPolicy={policy} />)
    })
    expect(document.querySelector('details')).toBeNull()
    const description = document.querySelector('p[data-slot="tooltip-trigger"]') as HTMLElement
    expect(description.textContent).toBe('Search project records')
    expect(description.hasAttribute('title')).toBe(false)
    const rows = selects().filter(item => Array.from(item.options).some(option => option.value === 'inherit'))
    await change(rows[0], 'require_approval')
    expect(latest?.approvalPolicy.operation_overrides['tool:search'].default_decision).toBe('require_approval')
    expect(latest?.approvalPolicy.operation_overrides['tool:removed'].default_decision).toBe('deny')
    await act(async () => renderer!.update(<Harness operationTools={[]} toolsLoaded initialApprovalPolicy={policy} />))
    expect(document.body.textContent).toContain('operations.otherTitle')
    expect(document.body.textContent).toContain('operations.notDiscovered')
    expect(document.body.textContent).toContain('tool:search')
    expect(document.body.textContent).toContain('tool:removed')
    expect(latest?.approvalPolicy.operation_overrides['tool:search'].default_decision).toBe('require_approval')
  })

  test('normalizes invalid approvers and invalid connection fields', () => {
    const normalized = normalizeToolApprovalPolicy({
      default_decision: 'require_approval',
      gates: [
        { kind: 'user', user_ids: ['not-a-uuid'], roles: [], allow_self_approval: false },
        { kind: 'team_role', user_ids: [], roles: ['admin', 'unknown'], allow_self_approval: true },
      ],
      operation_overrides: {
        'tool:send': {
          default_decision: 'deny',
          gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
          operation_overrides: {},
        },
      },
    })
    expect(normalized.gates).toEqual([
      { kind: 'team_role', user_ids: [], roles: ['admin'], allow_self_approval: true },
    ])
    expect(normalized.operation_overrides['tool:send']).toEqual({
      default_decision: 'deny',
      gates: [],
      operation_overrides: {},
    })

    expect(normalizeConnectionFields([
      { name: 'api_key', label: 'API key', required: true, secret: true },
      { name: 'api_key', label: 'Duplicate', required: false, secret: false },
      { name: 'bad-name', label: 'Bad', required: false, secret: false },
      { name: 'account', label: '', required: false, secret: false },
      { name: '', label: '', required: false, secret: false },
    ])).toEqual([{ name: 'api_key', label: 'API key', required: true, secret: true }])

    expect(normalizeToolApprovalPolicy({
      default_decision: 'unexpected' as ToolApprovalPolicy['default_decision'],
      gates: [],
      operation_overrides: { '*': { default_decision: 'deny', gates: [], operation_overrides: {} } },
    })).toEqual({
      default_decision: 'require_approval',
      gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    })
  })

  test('scopes gates to team roles and removes audiences without errors', async () => {
    await render(undefined, { default_decision: 'require_approval', gates: [], operation_overrides: {} })
    expect(document.body.textContent).toContain('approval.noGates')

    await act(async () => button('approval.addGate').click())
    expect(latest?.approvalPolicy.gates).toEqual([
      { kind: 'caller', user_ids: [], roles: [], allow_self_approval: false },
    ])

    const gateKind = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'team_role')
    )!
    await change(gateKind, 'team_role')
    expect(latest?.approvalPolicy.gates).toEqual([
      { kind: 'team_role', user_ids: [], roles: [], allow_self_approval: false },
    ])
    expect(alerts()).toContain('approval.rolesRequired')

    const adminLabel = Array.from(document.querySelectorAll('label'))
      .find((item) => item.textContent === 'approval.roleOptions.admin')!
    await act(async () => (adminLabel.querySelector('input') as HTMLInputElement).click())
    expect(latest?.approvalPolicy.gates[0].roles).toEqual(['admin'])
    expect(alerts()).not.toContain('approval.rolesRequired')

    const selfApproval = document.getElementById('approval-gate-self-0') as HTMLInputElement
    await act(async () => selfApproval.click())
    expect(latest?.approvalPolicy.gates[0].allow_self_approval).toBe(true)
    expect(document.body.textContent).not.toContain('approval.selfApprovalUnavailable')

    await act(async () => (document.querySelector('button[aria-label="approval.removeGate"]') as HTMLButtonElement).click())
    expect(latest?.approvalPolicy.gates).toEqual([])
    expect(document.body.textContent).toContain('approval.noGates')
  })

  test('requires approvers for user gates and resets audiences when the gate kind changes', async () => {
    await render(undefined, {
      default_decision: 'require_approval',
      gates: [{ kind: 'user', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    })
    expect(alerts()).toContain('approval.userIdsRequired')

    await act(async () => button('approver.add').click())
    expect(latest?.approvalPolicy.gates[0].user_ids).toEqual([APPROVER_ID])
    expect(alerts()).not.toContain('approval.userIdsRequired')
    expect(document.body.textContent).toContain(APPROVER_ID)

    const gateKind = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'team_role')
    )!
    await change(gateKind, 'caller')
    expect(latest?.approvalPolicy.gates).toEqual([
      { kind: 'caller', user_ids: [], roles: [], allow_self_approval: false },
    ])
    expect(document.body.textContent).toContain('approval.callerHint')
  })

  test('rejects invalid or duplicate manual operations and adds on Enter', async () => {
    await render(['tool:search'])
    const operationInput = () => renderer!.root.findByProps({ placeholder: 'operations.operationPlaceholder' })
    const setOperation = async (value: string) => {
      await act(async () => operationInput().props.onChange({ target: { value } }))
    }

    await setOperation('*')
    await act(async () => button('operations.addOperation').click())
    expect(alerts()).toContain('operations.invalidOperation')
    expect(latest?.approvalPolicy.operation_overrides).toEqual({})

    await setOperation('send email')
    await act(async () => button('operations.addOperation').click())
    expect(alerts()).toContain('operations.invalidOperation')

    await setOperation('tool:search')
    await act(async () => button('operations.addOperation').click())
    expect(alerts()).toContain('operations.duplicate')
    expect(latest?.approvalPolicy.operation_overrides).toEqual({})

    await setOperation('tool:new')
    expect(alerts()).toEqual([])
    await act(async () => {
      operationInput().props.onKeyDown({ key: 'Enter', preventDefault: () => {} })
    })
    expect(latest?.approvalPolicy.operation_overrides['tool:new']).toEqual({
      default_decision: 'require_approval',
      gates: [{ kind: 'caller', user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    })
    expect(operationInput().props.value).toBe('')
  })

  test('flags invalid, duplicate, and incomplete connection fields in place', async () => {
    await render()
    await act(async () => button('connectionFields.add').click())
    const name = () => document.getElementById('connection-field-name-0') as HTMLInputElement
    const setField = async (id: string, value: string) => {
      await act(async () =>
        renderer!.root.findByProps({ id }).props.onChange({ target: { value } })
      )
    }

    await setField('connection-field-name-0', 'bad-name')
    await setField('connection-field-label-0', 'Bad name')
    expect(name().getAttribute('aria-invalid')).toBe('true')
    expect(alerts()).toContain('connectionFields.invalidName')

    await setField('connection-field-name-0', 'account')
    await setField('connection-field-label-0', '')
    expect(alerts()).toContain('connectionFields.labelRequired')

    await setField('connection-field-name-0', '')
    await setField('connection-field-label-0', 'Account')
    expect(alerts()).toContain('connectionFields.nameRequired')

    await setField('connection-field-name-0', 'api_key')
    await setField('connection-field-label-0', 'API key')
    expect(alerts()).toEqual([])
    expect(name().getAttribute('aria-invalid')).not.toBe('true')

    await act(async () => button('connectionFields.add').click())
    await setField('connection-field-name-1', 'api_key')
    await setField('connection-field-label-1', 'Second key')
    expect(alerts()).toContain('connectionFields.duplicate')
    expect((document.getElementById('connection-field-name-1') as HTMLInputElement).getAttribute('aria-invalid')).toBe('true')

    await act(async () => (document.querySelector('button[aria-label="connectionFields.remove"]') as HTMLButtonElement).click())
    expect(latest?.connectionFields).toHaveLength(1)
    expect(alerts()).toEqual([])
  })

  test('keeps the approval-only surface scoped away from identity and connection settings', async () => {
    await act(async () => {
      renderer = create(
        <ApprovalOnlyHarness initialApprovalPolicy={{ default_decision: 'allow', gates: [], operation_overrides: {} }} />
      )
    })
    expect(document.getElementById('tool-identity-policy')).toBeNull()
    expect(document.querySelector('input[placeholder="connectionFields.namePlaceholder"]')).toBeNull()
    expect(document.body.textContent).not.toContain('identity.label')
    expect(document.body.textContent).not.toContain('connectionFields.add')
    expect(document.body.textContent).toContain('operations.title')

    const decision = selects().find((item) => item.value === 'allow')!
    await change(decision, 'require_approval')
    expect(latest?.approvalPolicy.default_decision).toBe('require_approval')
    expect(latest?.approvalPolicy.gates).toEqual([
      { kind: 'caller', user_ids: [], roles: [], allow_self_approval: false },
    ])
    expect(document.body.textContent).toContain('approval.gates')
  })
})
