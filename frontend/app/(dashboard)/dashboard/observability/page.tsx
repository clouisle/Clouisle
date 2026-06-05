'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter, useSearchParams } from 'next/navigation'
import { RefreshCw } from 'lucide-react'

import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { TimeRangeSelector, type TimeRange } from '@/components/dashboard/time-range-selector'
import { Header } from '@/components/layout/header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  observabilityApi,
  type AgentPerformanceRow,
  type ObservabilityOverview,
  type SlowQueriesResponse,
  type SystemHealthResponse,
  type SystemTrendResponse,
  type ThroughputResponse,
  type TimeoutResponse,
  type TokenResponse,
  type WorkflowPerformanceRow,
  type WorkerResponse,
} from '@/lib/api/admin/observability'
import {
  AgentsPanel,
  ErrorState,
  HealthPanel,
  ObservabilitySkeleton,
  OverviewPanel,
  ThroughputPanel,
  TimeoutsPanel,
  WorkflowsPanel,
} from './_components/observability-panels'

type ObservabilityTab = 'overview' | 'health' | 'agents' | 'workflows' | 'timeouts' | 'throughput'

const TAB_VALUES: ObservabilityTab[] = ['overview', 'health', 'agents', 'workflows', 'timeouts', 'throughput']

export default function ObservabilityPage() {
  const t = useTranslations('dashboard.observability')
  const router = useRouter()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = React.useState<ObservabilityTab>('overview')
  const [timeRange, setTimeRange] = React.useState<TimeRange>('30d')
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = React.useState<Date | null>(null)
  const [overview, setOverview] = React.useState<ObservabilityOverview | null>(null)
  const [throughput, setThroughput] = React.useState<ThroughputResponse | null>(null)
  const [tokens, setTokens] = React.useState<TokenResponse | null>(null)
  const [agents, setAgents] = React.useState<AgentPerformanceRow[]>([])
  const [workflows, setWorkflows] = React.useState<WorkflowPerformanceRow[]>([])
  const [timeouts, setTimeouts] = React.useState<TimeoutResponse | null>(null)
  const [health, setHealth] = React.useState<SystemHealthResponse | null>(null)
  const [systemTrend, setSystemTrend] = React.useState<SystemTrendResponse | null>(null)
  const [slowQueries, setSlowQueries] = React.useState<SlowQueriesResponse | null>(null)
  const [workers, setWorkers] = React.useState<WorkerResponse | null>(null)

  React.useEffect(() => {
    const tab = searchParams.get('tab') as ObservabilityTab | null
    if (tab && TAB_VALUES.includes(tab)) {
      setActiveTab(tab)
    }
  }, [searchParams])

  const fetchCurrentTab = React.useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      if (activeTab === 'overview') {
        const [overviewData, throughputData] = await Promise.all([
          observabilityApi.getOverview(timeRange),
          observabilityApi.getThroughput({ time_range: timeRange }),
        ])
        setOverview(overviewData)
        setThroughput(throughputData)
      } else if (activeTab === 'health') {
        const [healthData, trendData, slowQueryData, workerData] = await Promise.all([
          observabilityApi.getSystemHealth(),
          observabilityApi.getSystemTrend(),
          observabilityApi.getSlowQueries({ page_size: 10 }),
          observabilityApi.getWorkers(),
        ])
        setHealth(healthData)
        setSystemTrend(trendData)
        setSlowQueries(slowQueryData)
        setWorkers(workerData)
      } else if (activeTab === 'agents') {
        const data = await observabilityApi.getAgents({ time_range: timeRange, page_size: 20 })
        setAgents(data.items)
      } else if (activeTab === 'workflows') {
        const data = await observabilityApi.getWorkflows({ time_range: timeRange, page_size: 20 })
        setWorkflows(data.items)
      } else if (activeTab === 'timeouts') {
        const data = await observabilityApi.getTimeouts({ time_range: timeRange, page_size: 20 })
        setTimeouts(data)
      } else if (activeTab === 'throughput') {
        const [throughputData, tokenData] = await Promise.all([
          observabilityApi.getThroughput({ time_range: timeRange }),
          observabilityApi.getTokens(timeRange),
        ])
        setThroughput(throughputData)
        setTokens(tokenData)
      }
      setLastUpdatedAt(new Date())
    } catch (fetchError) {
      console.error('[Observability] Failed to fetch data:', fetchError)
      setError(t('states.errorDescription'))
    } finally {
      setIsLoading(false)
    }
  }, [activeTab, timeRange, t])

  React.useEffect(() => {
    fetchCurrentTab()
  }, [fetchCurrentTab])

  React.useEffect(() => {
    if (activeTab !== 'health') return
    const timer = window.setInterval(fetchCurrentTab, 30000)
    return () => window.clearInterval(timer)
  }, [activeTab, fetchCurrentTab])

  const handleTabChange = (value: string) => {
    const newTab = value as ObservabilityTab
    setActiveTab(newTab)
    router.push(`/dashboard/observability?tab=${newTab}`, { scroll: false })
  }

  const showSkeleton = isLoading && !hasTabData(activeTab, { overview, health, agents, workflows, timeouts, throughput })

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex-1 overflow-auto p-4">
          <div className="space-y-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="max-w-3xl">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
                  {activeTab === 'health' && <Badge variant="outline">{t('states.autoRefreshHint')}</Badge>}
                </div>
                <p className="text-muted-foreground mt-1">{t('description')}</p>
                {lastUpdatedAt && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {t('states.lastUpdated', { time: lastUpdatedAt.toLocaleTimeString() })}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {activeTab !== 'health' && <TimeRangeSelector value={timeRange} onChange={setTimeRange} />}
                <Button variant="outline" size="icon" onClick={fetchCurrentTab} disabled={isLoading} aria-label={t('actions.refresh')}>
                  <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>

            <Tabs value={activeTab} onValueChange={handleTabChange}>
              <TabsList className="flex h-auto w-full flex-wrap justify-start">
                {TAB_VALUES.map((tab) => (
                  <TabsTrigger key={tab} value={tab}>{t(`tabs.${tab}`)}</TabsTrigger>
                ))}
              </TabsList>
            </Tabs>

            {error && <ErrorState onRetry={fetchCurrentTab} />}
            {showSkeleton && <ObservabilitySkeleton tab={activeTab} />}
            {!showSkeleton && activeTab === 'overview' && <OverviewPanel overview={overview} throughput={throughput} />}
            {!showSkeleton && activeTab === 'health' && (
              <HealthPanel health={health} trend={systemTrend} slowQueries={slowQueries} workers={workers} />
            )}
            {!showSkeleton && activeTab === 'agents' && <AgentsPanel rows={agents} timeRange={timeRange} />}
            {!showSkeleton && activeTab === 'workflows' && <WorkflowsPanel rows={workflows} timeRange={timeRange} />}
            {!showSkeleton && activeTab === 'timeouts' && <TimeoutsPanel data={timeouts} />}
            {!showSkeleton && activeTab === 'throughput' && <ThroughputPanel throughput={throughput} tokens={tokens} />}
          </div>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}

function hasTabData(
  tab: ObservabilityTab,
  data: {
    overview: ObservabilityOverview | null
    health: SystemHealthResponse | null
    agents: AgentPerformanceRow[]
    workflows: WorkflowPerformanceRow[]
    timeouts: TimeoutResponse | null
    throughput: ThroughputResponse | null
  }
) {
  if (tab === 'overview') return Boolean(data.overview)
  if (tab === 'health') return Boolean(data.health)
  if (tab === 'agents') return data.agents.length > 0
  if (tab === 'workflows') return data.workflows.length > 0
  if (tab === 'timeouts') return Boolean(data.timeouts)
  return Boolean(data.throughput)
}
