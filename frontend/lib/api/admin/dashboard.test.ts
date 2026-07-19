import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'

import { api } from '../client'
import { dashboardApi } from './dashboard'

afterEach(() => mock.restore())

describe('dashboardApi requests', () => {
  it('requests stats from the exact endpoint', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({})

    await dashboardApi.getStats()

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/admin/dashboard/stats')
  })

  it('requests trends with the default and selected periods', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({})

    await dashboardApi.getTrends()
    await dashboardApi.getTrends('90d')

    expect(get).toHaveBeenNthCalledWith(1, '/admin/dashboard/stats/trends?period=30d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/dashboard/stats/trends?period=90d')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('requests top agents with exact defaults and parameters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await dashboardApi.getTopAgents()
    await dashboardApi.getTopAgents({ limit: 5, metric: 'total_tokens', time_range: 'all' })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/dashboard/stats/agents/top?limit=10&metric=conversation_count&time_range=30d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/dashboard/stats/agents/top?limit=5&metric=total_tokens&time_range=all')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('requests team token usage with exact defaults and parameters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await dashboardApi.getTeamTokenUsage()
    await dashboardApi.getTeamTokenUsage({ limit: 3, time_range: '7d' })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/dashboard/stats/teams/token-usage?limit=10&time_range=30d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/dashboard/stats/teams/token-usage?limit=3&time_range=7d')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('requests workflow summaries with exact defaults and parameters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({})

    await dashboardApi.getWorkflowSummary()
    await dashboardApi.getWorkflowSummary({ time_range: '90d' })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/dashboard/stats/workflows/summary?time_range=30d')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/dashboard/stats/workflows/summary?time_range=90d')
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('requests and normalizes model distribution responses', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({
      items: [
        { model_name: ' claude-sonnet ', usage_count: '4', percentage: 0.25 },
        { model_used: 'unused', token_usage: 0, percentage: 50 },
      ],
    })

    const result = await dashboardApi.getModelDistribution({ time_range: '7d' })

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith('/admin/dashboard/stats/models/distribution?time_range=7d')
    expect(result).toEqual([{ model: 'claude-sonnet', count: 4, percentage: 25 }])
  })

  it('returns an empty model distribution for malformed data', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({ items: 'not-an-array' })

    await expect(dashboardApi.getModelDistribution()).resolves.toEqual([])
    expect(get).toHaveBeenCalledWith('/admin/dashboard/stats/models/distribution?time_range=30d')
  })

  it('maps valid counts while normalizing invalid percentages', async () => {
    spyOn(api, 'get').mockResolvedValue([
      { model: 'model-a', count: 2, percentage: 'not-a-number' },
      { model: 'model-b', count: 3, percentage: 40 },
    ])

    await expect(dashboardApi.getModelDistribution()).resolves.toEqual([
      { model: 'model-a', count: 2, percentage: 0 },
      { model: 'model-b', count: 3, percentage: 40 },
    ])
  })

  it('preserves a meaningful request failure', async () => {
    const failure = new Error('dashboard stats request failed')
    spyOn(api, 'get').mockRejectedValue(failure)

    await expect(dashboardApi.getStats()).rejects.toBe(failure)
  })
})
