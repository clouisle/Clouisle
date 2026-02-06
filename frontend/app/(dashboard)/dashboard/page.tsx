'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter, useSearchParams } from 'next/navigation'
import { Loader2, RefreshCw } from 'lucide-react'
import { dashboardApi, type DashboardStats, type ModelDistribution, type TeamTokenUsage, type TopAgent, type WorkflowSummary } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { TimeRangeSelector, type TimeRange } from '@/components/dashboard/time-range-selector'
import { OverviewTab } from './_components/overview-tab'
import { ModelsTab } from './_components/models-tab'
import { AnalyticsTab } from './_components/analytics-tab'

type TabType = 'overview' | 'models' | 'analytics'

export default function DashboardPage() {
  const t = useTranslations('dashboard')
  const tHome = useTranslations('dashboard.home')
  const router = useRouter()
  const searchParams = useSearchParams()

  const [activeTab, setActiveTab] = React.useState<TabType>('overview')
  const [timeRange, setTimeRange] = React.useState<TimeRange>('7d')

  // Initialize activeTab from URL parameter after mount
  React.useEffect(() => {
    const tabParam = searchParams.get('tab')
    if (tabParam === 'models' || tabParam === 'analytics') {
      setActiveTab(tabParam)
    }
  }, [searchParams])

  // Common data
  const [stats, setStats] = React.useState<DashboardStats | null>(null)
  const [isLoadingStats, setIsLoadingStats] = React.useState(true)

  // Overview tab data
  interface TrendData {
    date: string
    new_users: number
    active_users: number
    new_conversations: number
    messages: number
    tokens: number
  }
  const [trendsData, setTrendsData] = React.useState<TrendData[]>([])
  const [isLoadingOverview, setIsLoadingOverview] = React.useState(false)
  const [overviewDataFetched, setOverviewDataFetched] = React.useState(false)

  // Models tab data
  const [modelDistribution, setModelDistribution] = React.useState<ModelDistribution[]>([])
  const [teamTokenUsage, setTeamTokenUsage] = React.useState<TeamTokenUsage[]>([])
  const [topAgentsByTokens, setTopAgentsByTokens] = React.useState<TopAgent[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  const [modelsDataFetched, setModelsDataFetched] = React.useState(false)

  // Analytics tab data
  const [workflowSummary, setWorkflowSummary] = React.useState<WorkflowSummary | null>(null)
  const [topAgentsByConversations, setTopAgentsByConversations] = React.useState<TopAgent[]>([])
  const [analyticsMetric, setAnalyticsMetric] = React.useState<'conversation_count' | 'message_count' | 'total_tokens'>('conversation_count')
  const [isLoadingAnalytics, setIsLoadingAnalytics] = React.useState(false)
  const [analyticsDataFetched, setAnalyticsDataFetched] = React.useState(false)

  // Fetch common stats (always needed)
  const fetchStats = React.useCallback(async () => {
    try {
      setIsLoadingStats(true)
      const statsResponse = await dashboardApi.getStats()
      setStats(statsResponse)
    } catch (error) {
      console.error('Failed to fetch dashboard stats:', error)
    } finally {
      setIsLoadingStats(false)
    }
  }, [])

  // Fetch Overview tab data
  const fetchOverviewData = React.useCallback(async () => {
    if (overviewDataFetched) return

    try {
      setIsLoadingOverview(true)
      const trendsResponse = await dashboardApi.getTrends(timeRange)
      setTrendsData(trendsResponse.data)
      setOverviewDataFetched(true)
    } catch (error) {
      console.error('Failed to fetch overview data:', error)
    } finally {
      setIsLoadingOverview(false)
    }
  }, [timeRange, overviewDataFetched])

  // Fetch Models tab data
  const fetchModelsData = React.useCallback(async () => {
    if (modelsDataFetched) return

    try {
      setIsLoadingModels(true)
      console.log('[Dashboard] Fetching models data with timeRange:', timeRange)

      const [modelData, teamData, agentsData, trendsResponse] = await Promise.all([
        dashboardApi.getModelDistribution({ time_range: timeRange }),
        dashboardApi.getTeamTokenUsage({ limit: 10, time_range: timeRange }),
        dashboardApi.getTopAgents({ limit: 10, metric: 'total_tokens', time_range: timeRange }),
        dashboardApi.getTrends(timeRange),
      ])

      console.log('[Dashboard] Models data received:', {
        modelData: modelData?.length || 0,
        teamData: teamData?.length || 0,
        agentsData: agentsData?.length || 0,
        trendsData: trendsResponse?.data?.length || 0,
      })
      console.log('[Dashboard] Team token data:', teamData)
      console.log('[Dashboard] Top agents data:', agentsData)

      setModelDistribution(modelData)
      setTeamTokenUsage(teamData)
      setTopAgentsByTokens(agentsData)
      setTrendsData(trendsResponse.data)
      setModelsDataFetched(true)
    } catch (error) {
      console.error('[Dashboard] Failed to fetch models data:', error)
      if (error instanceof Error) {
        console.error('[Dashboard] Error details:', error.message, error.stack)
      }
    } finally {
      setIsLoadingModels(false)
    }
  }, [timeRange, modelsDataFetched])

  // Fetch Analytics tab data
  const fetchAnalyticsData = React.useCallback(async () => {
    if (analyticsDataFetched) return

    try {
      setIsLoadingAnalytics(true)
      const [workflowData, agentsData] = await Promise.all([
        dashboardApi.getWorkflowSummary({ time_range: timeRange }),
        dashboardApi.getTopAgents({ limit: 10, metric: analyticsMetric, time_range: timeRange }),
      ])
      setWorkflowSummary(workflowData)
      setTopAgentsByConversations(agentsData)
      setAnalyticsDataFetched(true)
    } catch (error) {
      console.error('Failed to fetch analytics data:', error)
    } finally {
      setIsLoadingAnalytics(false)
    }
  }, [timeRange, analyticsMetric, analyticsDataFetched])

  // Fetch analytics data when metric changes
  const handleAnalyticsMetricChange = React.useCallback(async (metric: 'conversation_count' | 'message_count' | 'total_tokens') => {
    setAnalyticsMetric(metric)
    try {
      setIsLoadingAnalytics(true)
      const agentsData = await dashboardApi.getTopAgents({ limit: 10, metric, time_range: timeRange })
      setTopAgentsByConversations(agentsData)
    } catch (error) {
      console.error('Failed to fetch agents data:', error)
    } finally {
      setIsLoadingAnalytics(false)
    }
  }, [timeRange])

  // Initial fetch of stats
  React.useEffect(() => {
    fetchStats()
  }, [fetchStats])

  // Fetch data when tab changes
  React.useEffect(() => {
    if (activeTab === 'overview') {
      fetchOverviewData()
    } else if (activeTab === 'models') {
      fetchModelsData()
    } else if (activeTab === 'analytics') {
      fetchAnalyticsData()
    }
  }, [activeTab, fetchOverviewData, fetchModelsData, fetchAnalyticsData])

  // Reset data fetched flags when time range changes
  React.useEffect(() => {
    setOverviewDataFetched(false)
    setModelsDataFetched(false)
    setAnalyticsDataFetched(false)
    fetchStats()
  }, [timeRange, fetchStats])

  const handleRefresh = () => {
    setOverviewDataFetched(false)
    setModelsDataFetched(false)
    setAnalyticsDataFetched(false)
    fetchStats()

    if (activeTab === 'overview') {
      fetchOverviewData()
    } else if (activeTab === 'models') {
      fetchModelsData()
    } else if (activeTab === 'analytics') {
      fetchAnalyticsData()
    }
  }

  // Handle tab change and update URL
  const handleTabChange = (value: string) => {
    const newTab = value as TabType
    setActiveTab(newTab)
    router.push(`?tab=${newTab}`, { scroll: false })
  }

  if (isLoadingStats || !stats) {
    return (
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
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
              <TimeRangeSelector value={timeRange} onChange={setTimeRange} />
              <Button
                variant="outline"
                size="icon"
                onClick={handleRefresh}
                disabled={isLoadingStats || isLoadingOverview || isLoadingModels || isLoadingAnalytics}
              >
                <RefreshCw className={`h-4 w-4 ${(isLoadingStats || isLoadingOverview || isLoadingModels || isLoadingAnalytics) ? 'animate-spin' : ''}`} />
              </Button>
            </div>
          </div>

          {/* Tab Content */}
          {activeTab === 'overview' && (
            <OverviewTab
              stats={stats}
              trendsData={trendsData}
              isLoading={isLoadingOverview}
            />
          )}

          {activeTab === 'models' && (
            <ModelsTab
              stats={stats}
              modelData={modelDistribution}
              teamTokenData={teamTokenUsage}
              topAgentsData={topAgentsByTokens}
              trendsData={trendsData.map(d => ({ date: d.date, tokens: d.tokens }))}
              isLoading={isLoadingModels}
            />
          )}

          {activeTab === 'analytics' && (
            <AnalyticsTab
              stats={stats}
              workflowData={workflowSummary}
              topAgentsData={topAgentsByConversations}
              isLoading={isLoadingAnalytics}
              onMetricChange={handleAnalyticsMetricChange}
              currentMetric={analyticsMetric}
            />
          )}
        </div>
      </div>
    </div>
  )
}
