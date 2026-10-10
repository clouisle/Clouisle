'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter, useSearchParams } from 'next/navigation'
import { Loader2, RefreshCw } from 'lucide-react'
import { dashboardApi, type DashboardActivitySummary, type DashboardStats, type DashboardTrends, type ModelDistribution, type TeamTokenUsage, type TopAgent, type WorkflowSummary } from '@/lib/api/admin/dashboard'
import { adminTOTPApi, type TOTPStatsResponse } from '@/lib/api/admin/users'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { TimeRangeSelector, type TimeRange } from '@/components/dashboard/time-range-selector'
import { OverviewTab } from './_components/overview-tab'
import { ModelsTab } from './_components/models-tab'
import { AnalyticsTab } from './_components/analytics-tab'

type TabType = 'overview' | 'models' | 'analytics'
type AnalyticsMetric = 'conversation_count' | 'message_count' | 'total_tokens'

function readTimeRange(period: string | null, start: string | null, end: string | null): { value: TimeRange; invalid: boolean } {
  if (period !== 'custom') {
    const validPreset = period === null || period === '7d' || period === '30d' || period === '90d' || period === 'all'
    return { value: validPreset && period ? period as TimeRange : '30d', invalid: !validPreset || start !== null || end !== null }
  }
  const invalid = { value: '30d' as const, invalid: true }
  const aware = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/i
  if (!start || !end || !aware.test(start) || !aware.test(end)) return invalid
  for (const value of [start, end]) {
    const date = value.slice(0, 10)
    if (date.startsWith('0000') || new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) !== date) return invalid
  }
  const from = new Date(start), to = new Date(end)
  if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime())) return invalid
  const startRemainder = Number((start.match(/\.(\d+)/)?.[1] ?? '').padEnd(6, '0').slice(3))
  const endRemainder = Number((end.match(/\.(\d+)/)?.[1] ?? '').padEnd(6, '0').slice(3))
  const ordered = from < to || (from.getTime() === to.getTime() && startRemainder < endRemainder)
  return ordered ? { value: { start_time: start, end_time: end }, invalid: false } : invalid
}

function summarizeDashboardActivity(data: DashboardTrends['data']): DashboardActivitySummary {
  const summary: DashboardActivitySummary = { conversations: 0, messages: 0, tokens: 0 }
  for (const point of data) {
    summary.conversations += point.new_conversations
    summary.messages += point.messages
    summary.tokens += point.tokens
  }
  return summary
}

export default function DashboardPage() {
  const t = useTranslations('dashboard')
  const tHome = useTranslations('dashboard.home')
  const router = useRouter()
  const searchParams = useSearchParams()

  const searchString = searchParams.toString()
  const tabParam = searchParams.get('tab')
  const activeTab: TabType = tabParam === 'models' || tabParam === 'analytics' ? tabParam : 'overview'
  const period = searchParams.get('time_range')
  const startTime = searchParams.get('start_time')
  const endTime = searchParams.get('end_time')
  const { value: timeRange, invalid: invalidRange } = React.useMemo(() => readTimeRange(period, startTime, endTime), [period, startTime, endTime])
  const [refreshVersion, setRefreshVersion] = React.useState(0)
  const rangeKey = JSON.stringify(timeRange)
  const scopeKey = `${rangeKey}:${refreshVersion}`
  const fetched = React.useRef({ overview: '', models: '', analytics: '', agents: '' })
  const fetchedScope = React.useRef(scopeKey)

  const [stats, setStats] = React.useState<DashboardStats | null>(null)
  const [isLoadingStats, setIsLoadingStats] = React.useState(true)
  const [totpStats, setTotpStats] = React.useState<TOTPStatsResponse | null>(null)
  const [trendsData, setTrendsData] = React.useState<DashboardTrends['data']>([])
  const [modelTrendsData, setModelTrendsData] = React.useState<DashboardTrends['data']>([])
  const [analyticsTrendsData, setAnalyticsTrendsData] = React.useState<DashboardTrends['data']>([])
  const [isLoadingOverview, setIsLoadingOverview] = React.useState(false)
  const [modelDistribution, setModelDistribution] = React.useState<ModelDistribution[]>([])
  const [teamTokenUsage, setTeamTokenUsage] = React.useState<TeamTokenUsage[]>([])
  const [topAgentsByTokens, setTopAgentsByTokens] = React.useState<TopAgent[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  const [workflowSummary, setWorkflowSummary] = React.useState<WorkflowSummary | null>(null)
  const [topAgentsByConversations, setTopAgentsByConversations] = React.useState<TopAgent[]>([])
  const [analyticsMetric, setAnalyticsMetric] = React.useState<AnalyticsMetric>('conversation_count')
  const [isLoadingAnalytics, setIsLoadingAnalytics] = React.useState(false)
  const [isLoadingAnalyticsAgents, setIsLoadingAnalyticsAgents] = React.useState(false)
  const activityTrendsData = activeTab === 'overview' ? trendsData : activeTab === 'models' ? modelTrendsData : analyticsTrendsData
  const activitySummary: DashboardActivitySummary = React.useMemo(() => summarizeDashboardActivity(activityTrendsData), [activityTrendsData])

  React.useEffect(() => {
    let current = true
    setIsLoadingStats(true)
    void Promise.all([
      dashboardApi.getStats(),
      adminTOTPApi.getStats().catch(() => null),
    ]).then(([statsResponse, totpStatsResponse]) => {
      if (!current) return
      setStats(statsResponse)
      if (totpStatsResponse) setTotpStats(totpStatsResponse)
    }).catch((error) => {
      if (current) console.error('Failed to fetch dashboard stats:', error)
    }).finally(() => {
      if (current) setIsLoadingStats(false)
    })
    return () => { current = false }
  }, [refreshVersion])

  React.useEffect(() => {
    let current = true
    if (fetchedScope.current !== scopeKey) {
      fetched.current = { overview: '', models: '', analytics: '', agents: '' }
      fetchedScope.current = scopeKey
    }
    setIsLoadingOverview(false)
    setIsLoadingModels(false)
    setIsLoadingAnalytics(false)
    if (invalidRange) {
      fetched.current = { overview: '', models: '', analytics: '', agents: '' }
      setTrendsData([])
      setModelTrendsData([])
      setModelDistribution([])
      setTeamTokenUsage([])
      setTopAgentsByTokens([])
      setAnalyticsTrendsData([])
      setWorkflowSummary(null)
      return
    }
    if (fetched.current[activeTab] === scopeKey) return

    if (activeTab === 'overview') {
      setTrendsData([])
      setIsLoadingOverview(true)
      void dashboardApi.getTrends(timeRange).then((response) => {
        if (!current) return
        setTrendsData(response.data)
        fetched.current.overview = scopeKey
      }).catch((error) => {
        if (current) console.error('Failed to fetch overview data:', error)
      }).finally(() => {
        if (current) setIsLoadingOverview(false)
      })
    } else if (activeTab === 'models') {
      setModelDistribution([])
      setTeamTokenUsage([])
      setTopAgentsByTokens([])
      setModelTrendsData([])
      setIsLoadingModels(true)
      void Promise.allSettled([
        dashboardApi.getModelDistribution({ time_range: timeRange }),
        dashboardApi.getTeamTokenUsage({ limit: 10, time_range: timeRange }),
        dashboardApi.getTopAgents({ limit: 10, metric: 'total_tokens', time_range: timeRange }),
        dashboardApi.getTrends(timeRange),
      ]).then(([models, teams, agents, trends]) => {
        if (!current) return
        setModelDistribution(models.status === 'fulfilled' ? models.value : [])
        setTeamTokenUsage(teams.status === 'fulfilled' ? teams.value : [])
        setTopAgentsByTokens(agents.status === 'fulfilled' ? agents.value : [])
        setModelTrendsData(trends.status === 'fulfilled' ? trends.value.data : [])
        fetched.current.models = scopeKey
        for (const result of [models, teams, agents, trends]) {
          if (result.status === 'rejected') console.error('[Dashboard] Failed to fetch models data:', result.reason)
        }
      }).finally(() => {
        if (current) setIsLoadingModels(false)
      })
    } else {
      setWorkflowSummary(null)
      setAnalyticsTrendsData([])
      setIsLoadingAnalytics(true)
      void Promise.allSettled([
        dashboardApi.getWorkflowSummary({ time_range: timeRange }),
        dashboardApi.getTrends(timeRange),
      ]).then(([workflow, trends]) => {
        if (!current) return
        setWorkflowSummary(workflow.status === 'fulfilled' ? workflow.value : null)
        setAnalyticsTrendsData(trends.status === 'fulfilled' ? trends.value.data : [])
        fetched.current.analytics = scopeKey
        if (workflow.status === 'rejected') console.error('[Dashboard] Failed to fetch analytics data:', workflow.reason)
        if (trends.status === 'rejected') console.error('[Dashboard] Failed to fetch analytics activity data:', trends.reason)
      }).finally(() => {
        if (current) setIsLoadingAnalytics(false)
      })
    }
    return () => { current = false }
  }, [activeTab, invalidRange, scopeKey, timeRange])

  React.useEffect(() => {
    let current = true
    setIsLoadingAnalyticsAgents(false)
    if (invalidRange) { setTopAgentsByConversations([]); return }
    const agentsKey = `${scopeKey}:${analyticsMetric}`
    if (activeTab !== 'analytics' || fetched.current.agents === agentsKey) return
    fetched.current.agents = ''
    setTopAgentsByConversations([])
    setIsLoadingAnalyticsAgents(true)
    void dashboardApi.getTopAgents({ limit: 10, metric: analyticsMetric, time_range: timeRange }).then((response) => {
      if (!current) return
      setTopAgentsByConversations(response)
      fetched.current.agents = agentsKey
    }).catch((error) => {
      if (current) console.error('Failed to fetch agents data:', error)
    }).finally(() => {
      if (current) setIsLoadingAnalyticsAgents(false)
    })
    return () => { current = false }
  }, [activeTab, analyticsMetric, invalidRange, scopeKey, timeRange])

  const handleRefresh = () => {
    fetched.current = { overview: '', models: '', analytics: '', agents: '' }
    setRefreshVersion((version) => version + 1)
  }

  const handleTabChange = (tab: string) => {
    const params = new URLSearchParams(searchString)
    params.set('tab', tab)
    router.push(`?${params}`, { scroll: false })
  }

  const handleTimeRangeChange = (range: TimeRange) => {
    const params = new URLSearchParams(searchString)
    params.set('time_range', typeof range === 'string' ? range : 'custom')
    if (typeof range === 'object') {
      params.set('start_time', range.start_time)
      params.set('end_time', range.end_time)
    } else {
      params.delete('start_time')
      params.delete('end_time')
    }
    router.push(`?${params}`, { scroll: false })
  }

  if (!stats) {
    return (
      <RoutePermissionGuard>
        <div className="flex h-full flex-col">
          <Header />
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </div>
      </RoutePermissionGuard>
    )
  }

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex-1 overflow-auto p-4">
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold tracking-tight">{tHome('title')}</h1>
                <p className="text-muted-foreground mt-1">{tHome('description')}</p>
              </div>
            </div>

            {/* Filters */}
            <div className="flex items-center gap-4 mb-6">
              <Tabs value={activeTab} onValueChange={handleTabChange}>
                <TabsList>
                  <TabsTrigger value="overview">{t('tabs.overview')}</TabsTrigger>
                  <TabsTrigger value="models">{t('tabs.models')}</TabsTrigger>
                  <TabsTrigger value="analytics">{t('tabs.analytics')}</TabsTrigger>
                </TabsList>
              </Tabs>

              <div className="flex items-center gap-2 ml-auto">
                <TimeRangeSelector value={timeRange} onChange={handleTimeRangeChange} invalid={invalidRange} />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={handleRefresh}
                  aria-label={t('actions.refresh')}
                  disabled={isLoadingStats || isLoadingOverview || isLoadingModels || isLoadingAnalytics || isLoadingAnalyticsAgents}
                >
                  <RefreshCw className={`h-4 w-4 ${(isLoadingStats || isLoadingOverview || isLoadingModels || isLoadingAnalytics || isLoadingAnalyticsAgents) ? 'animate-spin' : ''}`} />
                </Button>
              </div>
            </div>

            {/* Tab Content */}
            {activeTab === 'overview' && (
              <OverviewTab
                activitySummary={activitySummary}
                stats={stats}
                trendsData={trendsData}
                isLoading={isLoadingOverview}
                totpStats={totpStats}
              />
            )}

            {activeTab === 'models' && (
              <ModelsTab
                modelData={modelDistribution}
                teamTokenData={teamTokenUsage}
                topAgentsData={topAgentsByTokens}
                trendsData={modelTrendsData}
                activitySummary={activitySummary}
                isLoading={isLoadingModels}
              />
            )}

            {activeTab === 'analytics' && (
              <AnalyticsTab
                activitySummary={activitySummary}
                workflowData={workflowSummary}
                topAgentsData={topAgentsByConversations}
                isLoading={isLoadingAnalytics}
                isLoadingAgents={isLoadingAnalyticsAgents}
                onMetricChange={setAnalyticsMetric}
                currentMetric={analyticsMetric}
              />
            )}
          </div>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
