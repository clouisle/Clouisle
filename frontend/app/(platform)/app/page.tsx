'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import {
  Bot,
  Wrench,
  Grid3x3,
  ArrowRight,
  Loader2,
  Plus,
  Workflow,
  Clock,
  Zap,
  Activity,
  TrendingUp,
  MessageSquare,
  CheckCircle2,
  Coins,
} from 'lucide-react'
import { useTeam } from '@/contexts/team-context'
import { knowledgeBasesApi, teamModelsApi, agentsApi, workflowsApi, type TeamModel } from '@/lib/api'
import { conversationsApi } from '@/lib/api/admin/conversations'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { NoTeamState } from './_components/no-team-state'
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  AreaChart,
  Area,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts'
import { CHART_AXIS_COLOR, CHART_COLOR_ORDER, CHART_GRID_COLOR, CHART_HOVER_CURSOR } from '@/lib/chart-theme'

interface StatsData {
  knowledgeBases: number
  models: number
  agents: number
  workflows: number
  totalConversations: number
  totalMessages: number
  totalTokens: number
  successRate: number
}

interface RecentItem {
  id: string
  name: string
  type: 'agent' | 'workflow'
  icon?: string | null
  updatedAt: string
}

const CHART_COLORS = CHART_COLOR_ORDER

interface UsageTrendTooltipPayloadItem {
  name: string
  value: number | string
  color: string
}

function UsageTrendTooltip({ active, payload, label }: { active?: boolean; payload?: UsageTrendTooltipPayloadItem[]; label?: string }) {
  if (!active || !payload?.length) {
    return null
  }

  return (
    <div className="min-w-[200px] rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
      <p className="mb-2 border-b border-chart-tooltip-border pb-2 text-sm font-semibold text-chart-tooltip-text">
        {label}
      </p>
      <div className="space-y-1.5">
        {payload.map((entry, index) => (
          <div key={index} className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full" style={{ backgroundColor: entry.color }} />
              <span className="text-xs text-chart-tooltip-text/80">{entry.name}</span>
            </div>
            <span className="text-sm font-semibold text-chart-tooltip-text">
              {typeof entry.value === 'number' ? formatNumber(entry.value) : entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// 格式化大数字
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function useCountUp(value: number, isLoading: boolean) {
  const [displayValue, setDisplayValue] = React.useState(0)

  React.useEffect(() => {
    if (isLoading) {
      setDisplayValue(0)
      return
    }

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || value === 0) {
      setDisplayValue(value)
      return
    }

    const duration = 900
    const startedAt = performance.now()
    let frameId = 0

    const tick = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1)
      const easedProgress = 1 - Math.pow(1 - progress, 3)
      setDisplayValue(Math.round(value * easedProgress))

      if (progress < 1) {
        frameId = requestAnimationFrame(tick)
      }
    }

    frameId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameId)
  }, [isLoading, value])

  return displayValue
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading,
  change,
  suffix,
  href,
}: {
  title: string
  value: number | string
  icon: React.ElementType
  isLoading: boolean
  change?: number
  suffix?: string
  href?: string
}) {
  const animatedValue = useCountUp(typeof value === 'number' ? value : 0, isLoading)
  const displayValue = typeof value === 'number' ? formatNumber(animatedValue) : value
  const trendBadgeClassName = change === undefined
    ? ''
    : change >= 0
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300'
      : 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-300'

  const content = (
    <Card size="sm" className={href ? 'cursor-pointer hover:shadow-md transition-all' : ''}>
      <CardContent className="py-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 self-start">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Icon className="h-5 w-5 text-primary" />
            </div>
            {change !== undefined && (
              <Badge variant="outline" className={`gap-1 rounded-full px-2 py-0.5 text-xs font-medium shadow-none ${trendBadgeClassName}`}>
                <TrendingUp className={`h-3 w-3 ${change < 0 ? 'rotate-180' : ''}`} />
                {Math.abs(change)}%
              </Badge>
            )}
          </div>
          <div className="min-w-0 flex-1 text-right">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <Skeleton className="mt-1 ml-auto h-8 w-20" />
            ) : (
              <p className="mt-1 text-2xl font-bold">
                {displayValue}
                {suffix && <span className="ml-1 text-sm font-normal text-muted-foreground">{suffix}</span>}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )

  if (href) {
    return <Link href={href}>{content}</Link>
  }

  return content
}

function RecentItemCard({ item }: { item: RecentItem }) {
  const t = useTranslations('platform.home')
  const href = item.type === 'agent' ? `/app/apps/${item.id}` : `/app/apps/workflow/${item.id}`
  const Icon = item.type === 'agent' ? Bot : Workflow

  return (
    <Link href={href}>
      <div className="group flex items-center gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer">
        <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
          {item.icon ? (
            item.icon.startsWith('http') || item.icon.startsWith('/') ? (
              <img src={item.icon} alt={item.name} className="size-full rounded object-cover" />
            ) : (
              <span className="text-base">{item.icon}</span>
            )
          ) : (
            <Icon className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate group-hover:text-primary transition-colors">
            {item.name}
          </p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
            <Badge variant="outline" className="text-xs px-1.5 py-0 h-4">
              {t(`recentItemTypes.${item.type}`)}
            </Badge>
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {new Date(item.updatedAt).toLocaleDateString()}
            </span>
          </div>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all shrink-0" />
      </div>
    </Link>
  )
}

export default function PlatformHomePage() {
  const t = useTranslations('platform.home')

  // Chart 配置 - 使用 i18n
  const usageTrendChartConfig = {
    conversations: {
      label: t('stats.conversations'),
      color: 'var(--chart-1)',
    },
    tokens: {
      label: t('stats.tokens'),
      color: 'var(--chart-2)',
    },
  } satisfies ChartConfig

  const resourceChartConfig = {
    value: {
      label: t('charts.count'),
    },
    agents: {
      label: t('stats.agents'),
      color: 'var(--chart-1)',
    },
    workflows: {
      label: t('stats.workflows'),
      color: 'var(--chart-2)',
    },
    knowledgeBases: {
      label: t('stats.knowledgeBases'),
      color: 'var(--chart-3)',
    },
    models: {
      label: t('stats.models'),
      color: 'var(--chart-4)',
    },
  } satisfies ChartConfig
  const { currentTeam, isLoading: isTeamLoading } = useTeam()
  const [stats, setStats] = React.useState<StatsData>({
    knowledgeBases: 0,
    models: 0,
    agents: 0,
    workflows: 0,
    totalConversations: 0,
    totalMessages: 0,
    totalTokens: 0,
    successRate: 0,
  })
  const [recentItems, setRecentItems] = React.useState<RecentItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [usageTrendData, setUsageTrendData] = React.useState<Array<{
    date: string
    conversations: number
    tokens: number
  }>>([])

  // 加载统计数据和最近项目
  const fetchData = React.useCallback(async () => {
    if (!currentTeam) return

    try {
      setIsLoading(true)

      // 并行请求
      const [kbResponse, modelsResponse, agentsResponse, workflowsResponse, trendsResponse] = await Promise.all([
        knowledgeBasesApi.getKnowledgeBases({ pageSize: 1, teamId: currentTeam.id }),
        teamModelsApi.getTeamModels(currentTeam.id),
        agentsApi.getAgents({ pageSize: 8, teamId: currentTeam.id }),
        workflowsApi.getWorkflows({ pageSize: 8, teamId: currentTeam.id }),
        conversationsApi.getTrends({ team_id: currentTeam.id, period: '7d' }),
      ])

      // 计算总的对话数和消息数
      const totalConversations = agentsResponse.items.reduce((sum, agent) => sum + (agent.conversation_count || 0), 0)
      const totalMessages = agentsResponse.items.reduce((sum, agent) => sum + (agent.message_count || 0), 0)

      // 计算总的 token 消耗（从趋势数据中累加）
      const totalTokens = trendsResponse.data.reduce((sum, item) => sum + (item.tokens || 0), 0)

      // 计算工作流成功率
      const totalRuns = workflowsResponse.items.reduce((sum, wf) => sum + (wf.run_count || 0), 0)
      const successRuns = workflowsResponse.items.reduce((sum, wf) => sum + (wf.success_count || 0), 0)
      const successRate = totalRuns > 0 ? Math.round((successRuns / totalRuns) * 100) : 0

      setStats({
        knowledgeBases: kbResponse.total,
        models: modelsResponse.filter((m: TeamModel) => m.is_enabled).length,
        agents: agentsResponse.total,
        workflows: workflowsResponse.total,
        totalConversations,
        totalMessages,
        totalTokens,
        successRate,
      })

      // 设置趋势数据
      setUsageTrendData(trendsResponse.data)

      // 合并最近的 agents 和 workflows
      const recent: RecentItem[] = [
        ...agentsResponse.items.map(agent => ({
          id: agent.id,
          name: agent.name,
          type: 'agent' as const,
          icon: agent.icon || agent.avatar_url,
          updatedAt: agent.updated_at,
        })),
        ...workflowsResponse.items.map(workflow => ({
          id: workflow.id,
          name: workflow.name,
          type: 'workflow' as const,
          icon: workflow.icon,
          updatedAt: workflow.updated_at,
        })),
      ]

      // 按更新时间排序，取前8个
      recent.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
      setRecentItems(recent.slice(0, 8))
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam])

  React.useEffect(() => {
    if (currentTeam) {
      fetchData()
    }
  }, [currentTeam, fetchData])

  // 等待团队加载
  if (isTeamLoading) {
    return (
      <div className="py-6 px-8 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // 没有团队时显示提示页面
  if (!currentTeam) {
    return <NoTeamState />
  }

  return (
    <div className="py-6 px-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title={t('stats.totalConversations')}
          value={stats.totalConversations}
          icon={MessageSquare}
          isLoading={isLoading}
          change={15}
        />
        <StatCard
          title={t('stats.totalMessages')}
          value={stats.totalMessages}
          icon={Activity}
          isLoading={isLoading}
          change={23}
        />
        <StatCard
          title={t('stats.totalTokens')}
          value={stats.totalTokens}
          icon={Coins}
          isLoading={isLoading}
          change={-5}
        />
        <StatCard
          title={t('stats.successRate')}
          value={stats.successRate}
          suffix="%"
          icon={CheckCircle2}
          isLoading={isLoading}
          change={3}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content - 2/3 width */}
        <div className="space-y-6 lg:col-span-2">
          {/* Usage Trend Chart */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                {t('usageTrend')}
              </CardTitle>
              <CardDescription>{t('usageTrendDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="h-[220px] flex items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <ChartContainer config={usageTrendChartConfig} className="h-[220px] w-full aspect-auto">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={usageTrendData} margin={{ left: 12, right: 12 }}>
                      <defs>
                        <linearGradient id="platformUsageConversations" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={CHART_COLORS[2]} stopOpacity={0.3} />
                          <stop offset="95%" stopColor={CHART_COLORS[2]} stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="platformUsageTokens" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={CHART_COLORS[4]} stopOpacity={0.3} />
                          <stop offset="95%" stopColor={CHART_COLORS[4]} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        className="text-xs"
                        tick={{ fill: CHART_AXIS_COLOR }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis yAxisId="left" className="text-xs" tick={{ fill: CHART_AXIS_COLOR }} hide />
                      <YAxis yAxisId="right" orientation="right" className="text-xs" tick={{ fill: CHART_AXIS_COLOR }} hide />
                      <Tooltip cursor={CHART_HOVER_CURSOR} content={<UsageTrendTooltip />} />
                      <Legend wrapperStyle={{ color: 'var(--chart-label)' }} />
                      <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="conversations"
                        stroke={CHART_COLORS[2]}
                        fillOpacity={1}
                        fill="url(#platformUsageConversations)"
                        name={t('stats.conversations')}
                      />
                      <Area
                        yAxisId="right"
                        type="monotone"
                        dataKey="tokens"
                        stroke={CHART_COLORS[4]}
                        fillOpacity={1}
                        fill="url(#platformUsageTokens)"
                        name={t('stats.tokens')}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </ChartContainer>
              )}
            </CardContent>
          </Card>

          {/* Resource Overview */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Grid3x3 className="h-4 w-4" />
                {t('resourceOverview')}
              </CardTitle>
              <CardDescription>{t('resourceOverviewDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="h-[250px] flex items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <ChartContainer config={resourceChartConfig} className="h-[250px] w-full aspect-auto">
                  <BarChart
                    accessibilityLayer
                    data={[
                      { category: t('stats.agents'), value: stats.agents },
                      { category: t('stats.workflows'), value: stats.workflows },
                      { category: t('stats.knowledgeBases'), value: stats.knowledgeBases },
                      { category: t('stats.models'), value: stats.models },
                    ]}
                    margin={{
                      left: 12,
                      right: 12,
                    }}
                  >
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="category"
                      tickLine={false}
                      axisLine={false}
                      tickMargin={8}
                    />
                    <ChartTooltip
                      cursor={CHART_HOVER_CURSOR}
                      content={<ChartTooltipContent />}
                    />
                    <Bar dataKey="value" radius={8}>
                      <Cell fill="var(--chart-1)" />
                      <Cell fill="var(--chart-2)" />
                      <Cell fill="var(--chart-3)" />
                      <Cell fill="var(--chart-4)" />
                    </Bar>
                  </BarChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - 1/3 width */}
        <div className="space-y-6">
          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4" />
                {t('quickActions')}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Link href="/app/apps" className="block">
                <Button variant="outline" className="w-full justify-start" size="sm">
                  <Plus className="mr-2 h-4 w-4" />
                  {t('actions.createAgent.title')}
                </Button>
              </Link>
              <Link href="/app/apps" className="block">
                <Button variant="outline" className="w-full justify-start" size="sm">
                  <Plus className="mr-2 h-4 w-4" />
                  {t('actions.createWorkflow.title')}
                </Button>
              </Link>
              <Link href="/app/kb" className="block">
                <Button variant="outline" className="w-full justify-start" size="sm">
                  <Plus className="mr-2 h-4 w-4" />
                  {t('actions.createKB.title')}
                </Button>
              </Link>
              <Link href="/app/capabilities" className="block">
                <Button variant="outline" className="w-full justify-start" size="sm">
                  <Wrench className="mr-2 h-4 w-4" />
                  {t('actions.manageTools.title')}
                </Button>
              </Link>
            </CardContent>
          </Card>

          {/* Recent Items */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  {t('recentItems')}
                </span>
                <Link href="/app/apps">
                  <Button variant="ghost" size="sm" className="h-7 text-xs">
                    {t('viewAll')}
                  </Button>
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex items-center gap-3">
                      <Skeleton className="h-10 w-10 rounded-lg" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : recentItems.length > 0 ? (
                <div className="space-y-1">
                  {recentItems.map((item) => (
                    <RecentItemCard key={item.id} item={item} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <div className="h-12 w-12 rounded-lg bg-muted flex items-center justify-center mx-auto mb-3">
                    <Grid3x3 className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">
                    {t('noRecentItems')}
                  </p>
                  <Link href="/app/apps">
                    <Button size="sm" variant="outline">
                      <Plus className="mr-2 h-4 w-4" />
                      {t('createFirst')}
                    </Button>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
