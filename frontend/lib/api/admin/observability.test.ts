import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { observabilityApi } from './observability'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let put: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  put = spyOn(api, 'put').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
  post.mockRestore()
  put.mockRestore()
})

describe('observabilityApi', () => {
  test('uses only the summary and diagnostics contract with scoped filters', async () => {
    await observabilityApi.getSummary({ period: '24h', team_id: 'team/a' })
    await observabilityApi.getRuns({ period: '7d', team_id: 'team-1', source: 'workflow', status: 'failed', error_category: 'provider', run_id: 'run 2', cursor: 'opaque:cursor', limit: 25 })
    await observabilityApi.getDependencies({ period: '15m' })
    await observabilityApi.getQueues()
    await observabilityApi.getInfrastructure()

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/summary?period=24h&team_id=team%2Fa')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/runs?period=7d&team_id=team-1&source=workflow&status=failed&error_category=provider&run_id=run+2&cursor=opaque%3Acursor&limit=25')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/observability/dependencies?period=15m')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/observability/queues')
    expect(get).toHaveBeenNthCalledWith(5, '/admin/observability/infrastructure')
  })

  test('loads trace detail separately and safely encodes run identifiers', async () => {
    await observabilityApi.getRun('agent', 'run/id ?')

    expect(get).toHaveBeenCalledWith('/admin/observability/runs/agent/run%2Fid%20%3F')
  })

  test('uses cursor pagination and status filter for alert events and rules', async () => {
    await observabilityApi.getAlerts({ status: 'active', cursor: 'next-page', limit: 25 })
    await observabilityApi.getAlertRules()

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/alerts?status=active&cursor=next-page&limit=25')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/alerts/rules')
  })

  test('sends acknowledge, bounded silence, and complete rule updates', async () => {
    await observabilityApi.acknowledgeAlert('alert/1')
    await observabilityApi.silenceAlert('alert-2', 3600)
    await observabilityApi.updateAlertRule('rule/3', { threshold: 0.9, enabled: false, evaluation_window_seconds: 300, recovery_window_seconds: 600 })

    expect(post).toHaveBeenNthCalledWith(1, '/admin/observability/alerts/alert%2F1/acknowledge', {})
    expect(post).toHaveBeenNthCalledWith(2, '/admin/observability/alerts/alert-2/silence?duration_seconds=3600', {})
    expect(put).toHaveBeenCalledWith('/admin/observability/alerts/rules/rule%2F3', { threshold: 0.9, enabled: false, evaluation_window_seconds: 300, recovery_window_seconds: 600 })
  })

  test('returns response payloads and propagates request failures', async () => {
    const payload = { meta: { state: 'fresh' } }
    const error = new Error('request failed')
    get.mockResolvedValueOnce(payload).mockRejectedValueOnce(error)

    await expect(observabilityApi.getSummary()).resolves.toBe(payload)
    await expect(observabilityApi.getQueues()).rejects.toBe(error)
  })
})
