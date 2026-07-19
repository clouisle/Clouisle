import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { observabilityApi } from './observability'

let get: ReturnType<typeof spyOn>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
})

afterEach(() => {
  get.mockRestore()
})

describe('observabilityApi', () => {
  test('constructs default and public system requests', async () => {
    await observabilityApi.getOverview()
    await observabilityApi.getAgents()
    await observabilityApi.getWorkflows()
    await observabilityApi.getTimeouts()
    await observabilityApi.getThroughput()
    await observabilityApi.getTokens()
    await observabilityApi.getSystemHealth()
    await observabilityApi.getSystemTrend()
    await observabilityApi.getSlowQueries()
    await observabilityApi.getWorkers()

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/overview?time_range=30d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/agents')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/observability/workflows')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/observability/timeouts')
    expect(get).toHaveBeenNthCalledWith(5, '/admin/observability/throughput')
    expect(get).toHaveBeenNthCalledWith(6, '/admin/observability/tokens?time_range=30d')
    expect(get).toHaveBeenNthCalledWith(7, '/admin/observability/system/health')
    expect(get).toHaveBeenNthCalledWith(8, '/admin/observability/system/trend')
    expect(get).toHaveBeenNthCalledWith(9, '/admin/observability/system/slow-queries')
    expect(get).toHaveBeenNthCalledWith(10, '/admin/observability/system/workers')
  })

  test('serializes detail routes and explicit time ranges', async () => {
    await observabilityApi.getOverview('7d')
    await observabilityApi.getAgentDetail('agent/id', '90d')
    await observabilityApi.getWorkflowDetail('workflow-1', 'all')
    await observabilityApi.getTokens('7d')

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/overview?time_range=7d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/agent/agent/id?time_range=90d')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/observability/workflow/workflow-1?time_range=all')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/observability/tokens?time_range=7d')
  })

  test('serializes optional query parameters and preserves falsey values', async () => {
    await observabilityApi.getAgents({ time_range: '7d', page: 0, page_size: 25, sort_by: 'requests', sort_order: 'asc' })
    await observabilityApi.getWorkflows({ time_range: '90d', page: 2, page_size: 0, sort_by: 'latency', sort_order: 'desc' })
    await observabilityApi.getTimeouts({ time_range: 'all', source: 'workflow', page: 3, page_size: 50 })
    await observabilityApi.getThroughput({ time_range: '30d', granularity: 'day' })
    await observabilityApi.getSlowQueries({ threshold_ms: 0, page: 4, page_size: 10 })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/agents?time_range=7d&page=0&page_size=25&sort_by=requests&sort_order=asc')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/workflows?time_range=90d&page=2&page_size=0&sort_by=latency&sort_order=desc')
    expect(get).toHaveBeenNthCalledWith(3, '/admin/observability/timeouts?time_range=all&source=workflow&page=3&page_size=50')
    expect(get).toHaveBeenNthCalledWith(4, '/admin/observability/throughput?time_range=30d&granularity=day')
    expect(get).toHaveBeenNthCalledWith(5, '/admin/observability/system/slow-queries?threshold_ms=0&page=4&page_size=10')
  })

  test('returns response payloads and propagates errors', async () => {
    const payload = { status: 'healthy' }
    const error = new Error('request failed')
    get.mockResolvedValueOnce(payload).mockRejectedValueOnce(error)

    await expect(observabilityApi.getSystemHealth()).resolves.toBe(payload)
    await expect(observabilityApi.getWorkers()).rejects.toBe(error)

    expect(get).toHaveBeenNthCalledWith(1, '/admin/observability/system/health')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/observability/system/workers')
  })
})
