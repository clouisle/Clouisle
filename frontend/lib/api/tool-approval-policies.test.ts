import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from './client'
import { toolApprovalPoliciesApi } from './tool-approval-policies'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let put: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  put = spyOn(api, 'put').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
  post.mockRestore()
  put.mockRestore()
  remove.mockRestore()
})

describe('toolApprovalPoliciesApi', () => {
  test('lists and evaluates policies with only defined filters', async () => {
    await toolApprovalPoliciesApi.list({
      team_id: 'team-1',
      scope: 'team',
      tool_id: 'tool-1',
    })
    await toolApprovalPoliciesApi.list({ scope: 'site' })
    await toolApprovalPoliciesApi.effective({
      team_id: 'team-1',
      entrypoint_kind: 'agent',
      entrypoint_id: 'agent-1',
      tool_id: 'tool-1',
      operation: 'delete_event',
    })

    expect(get).toHaveBeenNthCalledWith(1, '/tool-approval-policies', {
      params: {
        team_id: 'team-1',
        scope: 'team',
        tool_id: 'tool-1',
      },
    })
    expect(get).toHaveBeenNthCalledWith(2, '/tool-approval-policies', {
      params: { scope: 'site' },
    })
    expect(get).toHaveBeenNthCalledWith(3, '/tool-approval-policies/effective', {
      params: {
        team_id: 'team-1',
        entrypoint_kind: 'agent',
        entrypoint_id: 'agent-1',
        tool_id: 'tool-1',
        operation: 'delete_event',
      },
    })
  })

  test('creates, updates with the row version, and deletes a policy', async () => {
    const policy = {
      default_decision: 'require_approval' as const,
      gates: [{ kind: 'caller' as const, user_ids: [], roles: [], allow_self_approval: false }],
      operation_overrides: {},
    }
    await toolApprovalPoliciesApi.create({
      scope: 'team',
      team_id: 'team-1',
      tool_id: 'tool-1',
      policy,
    })
    await toolApprovalPoliciesApi.update('policy-1', { policy, expected_version: 3 })
    await toolApprovalPoliciesApi.remove('policy-1')

    expect(post).toHaveBeenCalledWith('/tool-approval-policies', {
      scope: 'team',
      team_id: 'team-1',
      tool_id: 'tool-1',
      policy,
    })
    expect(put).toHaveBeenCalledWith('/tool-approval-policies/policy-1', {
      policy,
      expected_version: 3,
    })
    expect(remove).toHaveBeenCalledWith('/tool-approval-policies/policy-1')
  })

  test('forwards version conflicts without rewriting them', async () => {
    const error = new Error('tool_approval_policy_version_conflict')
    put.mockRejectedValueOnce(error)

    await expect(
      toolApprovalPoliciesApi.update('policy-1', {
        policy: {
          default_decision: 'allow',
          gates: [],
          operation_overrides: {},
        },
        expected_version: 1,
      })
    ).rejects.toBe(error)
  })
})
