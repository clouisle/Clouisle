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

// Dynamic import is required so module mocks above apply before the editor loads.
const {
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

function selects(): HTMLSelectElement[] {
  return Array.from(document.querySelectorAll('select'))
}

function button(text: string): HTMLButtonElement {
  return Array.from(document.querySelectorAll('button')).find((item) => item.textContent === text)!
}

async function change(element: HTMLSelectElement | HTMLInputElement, value: string) {
  await act(async () => {
    element.value = value
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
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
    expect(document.querySelectorAll('details')).toHaveLength(1)
    expect(document.querySelector('summary')?.textContent).toBe('Search project records')
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
  })
})
