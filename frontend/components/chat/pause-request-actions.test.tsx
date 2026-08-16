import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getPendingPauseRequest = mock(() => Promise.resolve(null))
const submitPauseRequest = mock(() => Promise.resolve({ pause_request_id: 'p', status: 'submitted' }))
const toastSuccess = mock()
const toastError = mock()
const variableForm = function VariableForm() {}

const tFn = (key: string) => key
mock.module('next-intl', () => ({ useTranslations: () => tFn, useLocale: () => 'en' }))
mock.module('lucide-react', () => ({
  Check: () => null,
  CirclePause: () => null,
  Loader2: () => null,
  X: () => null,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getPendingPauseRequest, submitPauseRequest } }))
mock.module('@/components/chat/variable-form', () => ({ VariableForm: variableForm }))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))

const { PauseRequestActions } = await import('./pause-request-actions')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const approvalRequest = {
  id: 'pr-1', node_id: 'pause-1', node_name: 'Approval', mode: 'approval' as const,
  title: 'Review', description: 'Check the quote', input_variables: [],
  workflow_name: 'Budget Flow', triggered_by_name: 'alice', triggered_at: '2026-01-01T00:00:00Z',
  approver_ids: ['u-1'], approver_names: ['alice'], can_submit: true,
}

const renderers: ReactTestRenderer[] = []
afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  getPendingPauseRequest.mockReset()
  submitPauseRequest.mockReset()
})

async function render(props: Record<string, unknown>) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<PauseRequestActions workflowId="wf-1" runId="run-1" pauseRequestId="pr-1" {...props} />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

function buttons(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('button').map((node) => String(node.children.join('')))
}

test('controlled approval renders content and submits decision with comment', async () => {
  const onSubmit = mock(() => {})
  const renderer = await render({
    request: approvalRequest,
    values: {},
    onValuesChange: mock(),
    onSubmit,
    submitting: false,
    error: null,
  })

  expect(JSON.stringify(renderer.toJSON())).toContain('Check the quote')
  expect(JSON.stringify(renderer.toJSON())).toContain('Budget Flow')
  expect(JSON.stringify(renderer.toJSON())).toContain('pause.typeApproval')
  expect(JSON.stringify(renderer.toJSON())).toContain('pause.triggeredBy')
  expect(buttons(renderer).some((b) => b.includes('pause.approve'))).toBe(true)
  expect(buttons(renderer).some((b) => b.includes('pause.reject'))).toBe(true)

  await act(async () => {
    renderer.root.findAllByType('button').find((b) => String(b.children.join('')).includes('pause.approve'))!.props.onClick()
  })

  expect(onSubmit).toHaveBeenCalledWith({ decision: 'approved' }, '')
})

test('controlled variables mode renders the shared form and empty-variable submit', async () => {
  const onSubmit = mock(() => {})
  const values = { price: 42 }
  const renderer = await render({
    request: { ...approvalRequest, mode: 'variables', input_variables: [{ name: 'price', type: 'number', required: true }] },
    values,
    onValuesChange: mock(),
    onSubmit,
    submitting: false,
    error: null,
  })

  const form = renderer.root.findAllByType(variableForm)[0]
  expect(form.props.values).toEqual(values)
  expect(form.props.submitLabel).toBe('pause.submit')
  await act(async () => { form.props.onSubmit() })
  expect(onSubmit).toHaveBeenCalledWith(values, '')

  const empty = await render({
    request: { ...approvalRequest, mode: 'variables', input_variables: [] },
    values: {},
    onValuesChange: mock(),
    onSubmit,
    submitting: false,
    error: null,
  })
  await act(async () => {
    empty.root.findAllByType('button').find((b) => String(b.children.join('')).includes('pause.submit'))!.props.onClick()
  })
  expect(onSubmit).toHaveBeenLastCalledWith({}, '')
})

test('variables-mode request shows its description like approval', async () => {
  const renderer = await render({
    request: {
      ...approvalRequest,
      mode: 'variables',
      description: '请填写预算金额，并上传支持文件。',
      input_variables: [{ name: 'price', type: 'number', required: true }],
    },
    values: {},
    onValuesChange: mock(),
    onSubmit: mock(),
    submitting: false,
    error: null,
  })

  expect(JSON.stringify(renderer.toJSON())).toContain('请填写预算金额，并上传支持文件。')
  expect(JSON.stringify(renderer.toJSON())).toContain('pause.typeInput')
})

test('require-all approval shows progress, submitted state and hides actions once submitted', async () => {
  const renderer = await render({
    request: {
      ...approvalRequest,
      require_all: true,
      approver_ids: ['u-a', 'u-b'],
      approver_names: ['alice', 'bob'],
      approvals: [
        { approver_id: 'u-a', username: 'alice', decision: 'approved', comment: null, submitted_at: null },
      ],
      already_submitted: true,
    },
    values: {},
    onValuesChange: mock(),
    onSubmit: mock(),
    submitting: false,
    error: null,
    canSubmit: false,
  })

  const json = JSON.stringify(renderer.toJSON())
  expect(json).toContain('pause.approvalProgress')
  expect(json).toContain('pause.alreadySubmitted')
  expect(json).toContain('pause.approverStatusApproved')
  expect(json).toContain('pause.approverStatusPending')
  // 当前用户已提交后，不再渲染操作按钮（审批未全部完成时由他人继续处理）
  expect(buttons(renderer).some((b) => b.includes('pause.approve'))).toBe(false)
  expect(buttons(renderer).some((b) => b.includes('pause.reject'))).toBe(false)

  // 未提交时仍显示通过/拒绝操作
  const actionable = await render({
    request: {
      ...approvalRequest,
      require_all: true,
      approver_ids: ['u-a', 'u-b'],
      approver_names: ['alice', 'bob'],
      approvals: [],
      already_submitted: false,
    },
    values: {},
    onValuesChange: mock(),
    onSubmit: mock(),
    submitting: false,
    error: null,
    canSubmit: true,
  })
  expect(buttons(actionable).some((b) => b.includes('pause.approve'))).toBe(true)
  expect(buttons(actionable).some((b) => b.includes('pause.reject'))).toBe(true)
  expect(JSON.stringify(actionable.toJSON())).toContain('pause.approvalProgress')
})

test('disables controls for non-approvers and shows the notice', async () => {
  const renderer = await render({
    request: approvalRequest,
    values: {},
    onValuesChange: mock(),
    onSubmit: mock(),
    submitting: false,
    error: null,
    canSubmit: false,
    approverNames: ['alice'],
  })

  for (const button of renderer.root.findAllByType('button')) {
    expect(button.props.disabled).toBe(true)
  }
  expect(JSON.stringify(renderer.toJSON())).toContain('pause.approversOnly')
})

test('self-managed full mode loads, submits and resolves', async () => {
  getPendingPauseRequest.mockImplementationOnce(async () => approvalRequest)
  submitPauseRequest.mockImplementationOnce(async () => ({ pause_request_id: 'pr-1', status: 'submitted' }))
  const onResolved = mock(() => {})
  const renderer = await render({ onResolved })

  await act(async () => { await Promise.resolve() })
  await act(async () => { await Promise.resolve() })
  expect(buttons(renderer).some((b) => b.includes('pause.approve'))).toBe(true)

  await act(async () => {
    renderer.root.findAllByType('button').find((b) => String(b.children.join('')).includes('pause.approve'))!.props.onClick()
  })
  await act(async () => { await Promise.resolve() })

  expect(submitPauseRequest).toHaveBeenCalledWith('wf-1', 'run-1', 'pr-1', { decision: 'approved' }, '')
  expect(toastSuccess).toHaveBeenCalledWith('pause.submitted')
  expect(onResolved).toHaveBeenCalled()
})

test('self-managed compact approval shows buttons and submits', async () => {
  getPendingPauseRequest.mockImplementationOnce(async () => approvalRequest)
  submitPauseRequest.mockImplementationOnce(async () => ({ pause_request_id: 'pr-1', status: 'submitted' }))
  const renderer = await render({ variant: 'compact' })

  await act(async () => { await Promise.resolve() })
  await act(async () => { await Promise.resolve() })
  expect(buttons(renderer).some((b) => b.includes('pause.approve'))).toBe(true)

  await act(async () => {
    renderer.root.findAllByType('button').find((b) => String(b.children.join('')).includes('pause.approve'))!.props.onClick({ stopPropagation: mock() })
  })
  await act(async () => { await Promise.resolve() })

  expect(submitPauseRequest).toHaveBeenCalledWith('wf-1', 'run-1', 'pr-1', { decision: 'approved' }, '')
})

test('self-managed compact variables routes to the run page', async () => {
  getPendingPauseRequest.mockImplementationOnce(async () => ({
    ...approvalRequest, mode: 'variables', input_variables: [{ name: 'price', type: 'number', required: true }],
  }))
  const renderer = await render({ variant: 'compact' })

  await act(async () => { await Promise.resolve() })
  await act(async () => { await Promise.resolve() })

  const link = renderer.root.findAll((node) => node.type === 'a')[0]
  expect(link).toBeDefined()
  expect(link.props.href).toBe('/run/wf-1?run=run-1')
})
