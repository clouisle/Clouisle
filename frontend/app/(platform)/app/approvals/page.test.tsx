import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const pendingRequests = [
  {
    id: 'req-1',
    execution_id: 'exec-1',
    stage_index: 0,
    stage_key: 'caller',
    gate_kind: 'caller',
    approver_user_ids: [],
    approver_roles: [],
    allow_self_approval: false,
    masked_display: {
      tool_name: 'get_current_time',
      operation: 'get_current_time',
      entrypoint: 'workflow',
      run_kind: 'workflow',
      run_id: 'run-1',
      parameters: { timezone_name: 'Asia/Shanghai' },
    },
    status: 'pending',
    expires_at: null,
    resolved_at: null,
    created_at: '2026-01-01T00:00:00Z',
  },
]

const list = mock()
const decide = mock()
const toast = { success: mock(), error: mock() }

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api', () => ({
  toolApprovalsApi: { list, decide },
}))

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

function findButton(tree: ReactTestRenderer, label: string) {
  const matches = tree.root.findAll(
    (node) =>
      node.type === 'button' && String(node.props.children).includes(label)
  )
  if (matches.length === 0) throw new Error(`button ${label} not found`)
  return matches[0]
}

async function renderPage(): Promise<ReactTestRenderer> {  const { default: ApprovalsPage } = await import(
    '@/app/(platform)/app/approvals/page'
  )
  let tree!: ReactTestRenderer
  await act(async () => {
    tree = create(React.createElement(ApprovalsPage))
  })
  await flush()
  return tree
}

describe('approvals inbox page', () => {
  beforeEach(() => {
    list.mockReset()
    decide.mockReset()
    toast.success.mockReset()
    toast.error.mockReset()
    list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
  })

  afterEach(() => {
    mock.restore()
  })

  test('shows the empty state when nothing is pending', async () => {
    const tree = await renderPage()
    const text = JSON.stringify(tree.toJSON())

    expect(list).toHaveBeenCalledTimes(1)
    expect(text).toContain('empty')
    tree.unmount()
  })

  test('lists a pending gate with its run kind and parameters', async () => {
    list.mockResolvedValue({
      items: pendingRequests,
      total: 1,
      page: 1,
      page_size: 50,
    })

    const tree = await renderPage()
    const text = JSON.stringify(tree.toJSON())

    expect(text).toContain('get_current_time')
    expect(text).toContain('runKinds.workflow')
    expect(text).toContain('Asia/Shanghai')
    tree.unmount()
  })

  test('approving drops the row and toasts success', async () => {
    list.mockResolvedValue({
      items: pendingRequests,
      total: 1,
      page: 1,
      page_size: 50,
    })
    decide.mockResolvedValue({
      execution_status: 'ready',
      remaining_approvals: 0,
    })

    const tree = await renderPage()
    const approve = findButton(tree, 'approve')
    await act(async () => {
      approve.props.onClick?.()
    })
    await flush()

    expect(decide).toHaveBeenCalledWith('req-1', {
      decision: 'approve',
      idempotency_key: 'req-1:approve',
    })
    expect(toast.success).toHaveBeenCalledWith('approvedToast')
    tree.unmount()
  })

  test('a failed decision toasts an error and keeps the row', async () => {
    list.mockResolvedValue({
      items: pendingRequests,
      total: 1,
      page: 1,
      page_size: 50,
    })
    decide.mockRejectedValue(new Error('nope'))

    const tree = await renderPage()
    const reject = findButton(tree, 'reject')
    await act(async () => {
      reject.props.onClick?.()
    })
    await flush()

    expect(toast.error).toHaveBeenCalledWith('decisionFailed')
    expect(JSON.stringify(tree.toJSON())).toContain('get_current_time')
    tree.unmount()
  })

  test('a load failure offers a retry that refetches', async () => {
    list.mockRejectedValueOnce(new Error('boom'))

    const tree = await renderPage()
    expect(JSON.stringify(tree.toJSON())).toContain('loadFailed')

    const retry = findButton(tree, 'retry')
    await act(async () => {
      retry.props.onClick?.()
    })
    await flush()

    expect(list).toHaveBeenCalledTimes(2)
    tree.unmount()
  })
})
