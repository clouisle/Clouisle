import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const list = mock(async () => ({ items: [], total: 0, page: 1, page_size: 20 }))
const decide = mock(async () => ({
  execution_status: 'ready',
  remaining_approvals: 0,
  decision: {},
}))
const toastSuccess = mock(() => undefined)
const toastError = mock(() => undefined)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('lucide-react', () => ({
  Check: () => <span data-icon="check" />,
  Loader2: () => <span data-icon="loader" />,
  RefreshCw: () => <span data-icon="refresh" />,
  ShieldCheck: () => <span data-icon="shield" />,
  X: () => <span data-icon="x" />,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span data-badge>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: Record<string, unknown>) => <textarea {...props} />,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{children}</> : null,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/lib/api', () => ({
  toolApprovalsApi: { list, decide },
}))

const { ApprovalsInbox } = await import('./approvals-inbox')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function request(overrides: Record<string, unknown> = {}) {
  return {
    id: 'request-1',
    execution_id: 'execution-1',
    stage_index: 0,
    stage_key: 'caller',
    gate_kind: 'caller',
    approver_user_ids: ['user-1'],
    approver_roles: [],
    allow_self_approval: false,
    masked_display: {
      tool_id: 'tool-1',
      tool_name: 'Calendar',
      operation: 'delete_event',
      parameters: { event_id: 'evt-1', token: '***REDACTED***' },
      entrypoint: 'chat',
      run_kind: 'agent',
      run_id: 'run-1',
      connection: {
        connection_id: 'connection-1',
        scope: 'user',
        account_label: 'work@example.com',
        effective_user_id: 'user-1',
      },
      policy_sources: ['tool'],
      note: 'Approval binds this exact operation.',
    },
    status: 'pending',
    expires_at: '2026-10-27T00:00:00Z',
    resolved_at: null,
    created_at: '2026-10-26T00:00:00Z',
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
  return renderer.root
    .findAllByType('button')
    .find((button) => textOf(button).includes(text))
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('ApprovalsInbox', () => {
  test('loads pending gates, approves the exact request and refetches', async () => {
    list.mockClear()
    decide.mockClear()
    list.mockResolvedValue({ items: [request()], total: 1, page: 1, page_size: 20 })
    const tree = <ApprovalsInbox />
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(tree)
    })
    renderers.push(renderer)
    await flush()

    expect(list).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    expect(JSON.stringify(renderer.toJSON())).toContain('work@example.com')

    act(() => buttonByText(renderer, 'approve')?.props.onClick())
    const reason = renderer.root.findAllByType('textarea')[0]
    act(() => reason.props.onChange({ target: { value: 'approved for audit' } }))
    act(() => buttonByText(renderer, 'confirmApprove')?.props.onClick())
    await flush()

    expect(decide).toHaveBeenCalledTimes(1)
    expect(decide).toHaveBeenCalledWith('request-1', {
      decision: 'approve',
      reason: 'approved for audit',
      idempotency_key: expect.any(String),
    })
    expect(list).toHaveBeenCalledTimes(2)
    expect(toastSuccess).toHaveBeenCalled()
  })

  test('keeps the request when the decision fails', async () => {
    list.mockClear()
    decide.mockClear()
    toastError.mockClear()
    list.mockResolvedValue({ items: [request()], total: 1, page: 1, page_size: 20 })
    decide.mockRejectedValueOnce(new Error('approval expired'))
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<ApprovalsInbox />)
    })
    renderers.push(renderer)
    await flush()

    act(() => buttonByText(renderer, 'reject')?.props.onClick())
    act(() => buttonByText(renderer, 'confirmReject')?.props.onClick())
    await flush()

    expect(decide).toHaveBeenCalledWith('request-1', {
      decision: 'reject',
      reason: null,
      idempotency_key: expect.any(String),
    })
    expect(list).toHaveBeenCalledTimes(1)
    expect(toastError).toHaveBeenCalledWith('approval expired')
    expect(JSON.stringify(renderer.toJSON())).toContain('delete_event')
  })

  test('scans pages for the linked execution and supports clearing the filter', async () => {
    list.mockClear()
    list.mockResolvedValue({
      items: [request(), request({ id: 'request-2', execution_id: 'execution-2' })],
      total: 2,
      page: 1,
      page_size: 100,
    })
    const onClear = mock(() => undefined)
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<ApprovalsInbox executionId="execution-2" onClearExecutionFilter={onClear} />)
    })
    renderers.push(renderer)
    await flush()

    expect(list).toHaveBeenCalledWith({ page: 1, page_size: 100 })
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('approval-request-request-2')
    expect(text).not.toContain('approval-request-request-1')
    act(() => buttonByText(renderer, 'clearFilter')?.props.onClick())
    expect(onClear).toHaveBeenCalled()
  })
})
