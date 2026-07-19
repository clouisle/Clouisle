import { describe, expect, test } from 'bun:test'

import { hasTabData, type ObservabilityTab } from './tab-data'

const emptyData = {
  overview: null,
  health: null,
  agents: [],
  workflows: [],
  timeouts: null,
  throughput: null,
  tokens: null,
  workers: null,
  slowQueries: null,
}

describe('hasTabData', () => {
  test('recognizes cached data for every tab', () => {
    const cases: Array<[ObservabilityTab, Partial<typeof emptyData>]> = [
      ['overview', { overview: {} }],
      ['health', { health: {} }],
      ['agents', { agents: [{}] }],
      ['workflows', { workflows: [{}] }],
      ['timeouts', { timeouts: {} }],
      ['throughput', { throughput: {} }],
      ['tokens', { tokens: {} }],
      ['workers', { workers: {} }],
      ['slow-queries', { slowQueries: {} }],
    ]

    for (const [tab, data] of cases) {
      expect(hasTabData(tab, emptyData)).toBe(false)
      expect(hasTabData(tab, { ...emptyData, ...data })).toBe(true)
    }
  })
})
