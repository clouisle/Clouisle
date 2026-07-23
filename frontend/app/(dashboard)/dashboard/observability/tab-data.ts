export type ObservabilityTab = 'overview' | 'health' | 'agents' | 'workflows' | 'timeouts' | 'throughput' | 'tokens' | 'workers' | 'slow-queries'

export type TabData = {
  overview: unknown | null
  health: unknown | null
  agents: unknown[]
  workflows: unknown[]
  timeouts: unknown | null
  throughput: unknown | null
  tokens: unknown | null
  workers: unknown | null
  slowQueries: unknown | null
}

export function hasTabData(tab: ObservabilityTab, data: TabData) {
  if (tab === 'overview') return Boolean(data.overview)
  if (tab === 'health') return Boolean(data.health)
  if (tab === 'agents') return data.agents.length > 0
  if (tab === 'workflows') return data.workflows.length > 0
  if (tab === 'timeouts') return Boolean(data.timeouts)
  if (tab === 'throughput') return Boolean(data.throughput)
  if (tab === 'tokens') return Boolean(data.tokens)
  if (tab === 'workers') return Boolean(data.workers)
  return Boolean(data.slowQueries)
}
