import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from './client'
import { toolApprovalsApi, toolExecutionsApi } from './tool-approvals'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
  post.mockRestore()
})

describe('toolApprovalsApi', () => {
  test('lists pending gates with only defined pagination parameters', async () => {
    await toolApprovalsApi.list()
    await toolApprovalsApi.list({ page: 2, page_size: 50 }, { silent: true })

    expect(get).toHaveBeenNthCalledWith(1, '/tool-approvals', {
      params: {},
      silent: undefined,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/tool-approvals', {
      params: { page: 2, page_size: 50 },
      silent: true,
    })
  })

  test('loads one gate and posts an idempotent decision without parameters', async () => {
    const request = { id: 'request-1' }
    const result = { execution_status: 'ready', remaining_approvals: 0 }
    get.mockResolvedValueOnce(request)
    post.mockResolvedValueOnce(result)

    expect(await toolApprovalsApi.get('request-1')).toBe(request)
    await toolApprovalsApi.decide('request-1', {
      decision: 'approve',
      reason: 'looks right',
      idempotency_key: 'approval-1',
    })

    expect(get).toHaveBeenCalledWith('/tool-approvals/request-1')
    expect(post).toHaveBeenCalledWith('/tool-approvals/request-1/decision', {
      decision: 'approve',
      reason: 'looks right',
      idempotency_key: 'approval-1',
    })
  })

  test('forwards API errors instead of masking them', async () => {
    const error = new Error('expired')
    post.mockRejectedValueOnce(error)

    await expect(
      toolApprovalsApi.decide('request-1', {
        decision: 'reject',
        idempotency_key: 'approval-2',
      })
    ).rejects.toBe(error)
  })
})

describe('toolExecutionsApi', () => {
  test('scopes execution lists to a run and status', async () => {
    await toolExecutionsApi.list({
      run_id: 'run-1',
      run_kind: 'agent',
      status: 'awaiting_approval',
      page: 1,
      page_size: 10,
    })
    await toolExecutionsApi.list()

    expect(get).toHaveBeenNthCalledWith(1, '/tool-executions', {
      params: {
        page: 1,
        page_size: 10,
        status: 'awaiting_approval',
        run_kind: 'agent',
        run_id: 'run-1',
      },
      silent: undefined,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/tool-executions', {
      params: {},
      silent: undefined,
    })
  })

  test('loads one secret-safe execution with a silent flag', async () => {
    const execution = { id: 'execution-1', status: 'awaiting_approval' }
    get.mockResolvedValueOnce(execution)

    expect(await toolExecutionsApi.get('execution-1', { silent: true })).toBe(execution)
    expect(get).toHaveBeenCalledWith('/tool-executions/execution-1', { silent: true })
  })
})
