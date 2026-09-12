'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { 
  MessageSquare, 
  MessagesSquare, 
  Coins, 
  Timer, 
  Users, 
  Wrench,
  HeartPulse,
  Zap,
  Hand,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'
import {
  agentsApi,
  agentStatsApi,
  type Agent,
  type AgentStats,
  type AgentTrends,
  type AgentToolUsage,
  type ToolUsageItem,
} from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { AgentSidebar } from '../_components/agent-sidebar'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from 'recharts'
import { CHART_AXIS_COLOR, CHART_COLOR_ORDER, CHART_GRID_COLOR, CHART_HOVER_CURSOR, CHART_SURFACE_COLORS } from '@/lib/chart-theme'
import { cn } from '@/lib/utils'

interface MonitorPageProps {
  params: Promise<{ id: string }>
}

// Format large numbers
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

// Format milliseconds to seconds
function formatDuration(ms: number): string {
  if (ms === 0) return '0s'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

// Stat Card Component
interface StatCardProps {
  title: string
  value: string | number
  icon: React.ReactNode
  description?: string
  trend?: number
  className?: string
  color?: 'blue' | 'green' | 'orange' | 'purple' | 'cyan' | 'slate'
}

function StatCard({ title, value, icon, description, trend, className, color = 'blue' }: StatCardProps) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-500',
    green: 'bg-green-500/10 text-green-500',
    orange: 'bg-orange-500/10 text-orange-500',
    purple: 'bg-purple-500/10 text-purple-500',
    cyan: 'bg-cyan-500/10 text-cyan-500',
    slate: 'bg-slate-500/10 text-slate-500',
  }

  return (
    <Card size="sm" className={className}>
      <CardContent className="py-0">
        <div className="flex items-center gap-3">
          <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', colorClasses[color])}>
            {icon}
          </div>
          <div className="min-w-0 flex-1 text-right">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <div className="mt-1 text-2xl font-bold">{value}</div>
            {(description || trend !== undefined) && (
              <div className="mt-1 flex items-center justify-end">
                {trend !== undefined && (
                  <span
                    className={cn(
                      'mr-2 flex items-center text-xs',
                      trend > 0 ? 'text-green-600' : trend < 0 ? 'text-red-600' : 'text-muted-foreground'
                    )}
                  >
                    {trend > 0 ? <TrendingUp className="mr-0.5 h-3 w-3" /> : trend < 0 ? <TrendingDown className="mr-0.5 h-3 w-3" /> : null}
                    {trend > 0 ? '+' : ''}{trend}%
                  </span>
                )}
                {description && <p className="text-xs text-muted-foreground">{description}</p>}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function MonitorPage({ params }: MonitorPageProps) {
  const t = useTranslations('agents.monitor')
  const router = useRouter()

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [period, setPeriod] = React.useState('7d')
  
  // Stats data
  const [stats, setStats] = React.useState<AgentStats | null>(null)
  const [trends, setTrends] = React.useState<AgentTrends | null>(null)
  const [toolUsage, setToolUsage] = React.useState<AgentToolUsage | null>(null)
  const [isLoadingStats, setIsLoadingStats] = React.useState(false)

  // Chart configs with i18n labels
  const conversationChartConfig: ChartConfig = React.useMemo(() => ({
    conversations: {
      label: t('charts.conversations'),
      color: CHART_COLOR_ORDER[2],
    },
    messages: {
      label: t('charts.messages'),
      color: CHART_COLOR_ORDER[4],
    },
  }), [t])

  const tokenChartConfig: ChartConfig = React.useMemo(() => ({
    tokens: {
      label: t('charts.tokens'),
      color: CHART_COLOR_ORDER[5],
    },
  }), [t])

  const responseTimeChartConfig: ChartConfig = React.useMemo(() => ({
    avg_response_time_ms: {
      label: t('charts.avgResponseTime'),
      color: CHART_COLOR_ORDER[4],
    },
  }), [t])

  const toolUsageChartConfig: ChartConfig = React.useMemo(() => ({
    count: {
      label: t('charts.calls'),
      color: CHART_COLOR_ORDER[0],
    },
  }), [t])

  const healthChartConfig: ChartConfig = React.useMemo(() => ({
    completed: { label: t('health.completed'), color: CHART_COLOR_ORDER[0] },
    failed: { label: t('health.failed'), color: CHART_COLOR_ORDER[4] },
    stopped: { label: t('health.stopped'), color: CHART_COLOR_ORDER[3] },
  }), [t])

  const latencyChartConfig: ChartConfig = React.useMemo(() => ({
    first_token_p50_ms: { label: t('firstToken.p50'), color: CHART_COLOR_ORDER[0] },
    first_token_p95_ms: { label: t('firstToken.p95'), color: CHART_COLOR_ORDER[4] },
  }), [t])

  const interventionChartConfig: ChartConfig = React.useMemo(() => ({
    steer: { label: t('interventions.steer'), color: CHART_COLOR_ORDER[2] },
    stop: { label: t('interventions.stop'), color: CHART_COLOR_ORDER[4] },
    followUp: { label: t('interventions.followUp'), color: CHART_COLOR_ORDER[1] },
  }), [t])

  // Terminal run outcomes only; in-flight runs have no outcome to chart.
  const healthSlices = React.useMemo(() => {
    const health = stats?.health
    if (!health) return []
    return [
      { key: 'completed', label: t('health.completed'), value: health.completed, fill: CHART_SURFACE_COLORS[0] },
      { key: 'failed', label: t('health.failed'), value: health.failed, fill: CHART_SURFACE_COLORS[4] },
      { key: 'stopped', label: t('health.stopped'), value: health.stopped, fill: CHART_SURFACE_COLORS[3] },
    ].filter((slice) => slice.value > 0)
  }, [stats, t])

  const health = stats?.health ?? {
    completed: 0,
    failed: 0,
    stopped: 0,
    in_flight: 0,
    total: 0,
    success_rate: 0,
  }
  const latency = stats?.performance.first_token_ms ?? {
    p50: 0,
    p95: 0,
    avg: 0,
    samples: 0,
  }
  const interventions = stats?.interventions ?? {
    steer: 0,
    stop: 0,
    follow_up: 0,
    total: 0,
  }

  const interventionBars = React.useMemo(() => {
    const counts = stats?.interventions
    if (!counts) return []
    return [
      { key: 'steer', label: t('interventions.steer'), value: counts.steer, fill: CHART_SURFACE_COLORS[2] },
      { key: 'stop', label: t('interventions.stop'), value: counts.stop, fill: CHART_SURFACE_COLORS[4] },
      { key: 'followUp', label: t('interventions.followUp'), value: counts.follow_up, fill: CHART_SURFACE_COLORS[1] },
    ].filter((bar) => bar.value > 0)
  }, [stats, t])

  // Interventions per terminal run. Zero runs would make the ratio meaningless
  // rather than infinite, so it reports 0 and the hint omits the denominator.
  const interventionRate =
    health.total > 0 ? interventions.total / health.total : 0

  // The API already returns tools ordered by count descending; cap the slices
  // so the donut and its legend stay readable.
  const topTools = React.useMemo(
    () => (toolUsage?.tools ?? []).slice(0, 8),
    [toolUsage]
  )

  // Unwrap params
  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)

  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])

  // Fetch agent data
  const fetchAgent = React.useCallback(async () => {
    if (!resolvedParams) return

    try {
      setIsLoading(true)
      const data = await agentsApi.getAgent(resolvedParams.id)
      setAgent(data)
    } catch {
      router.push('/app/apps')
    } finally {
      setIsLoading(false)
    }
  }, [resolvedParams, router])

  // Fetch stats data
  const fetchStats = React.useCallback(async () => {
    if (!resolvedParams) return

    try {
      setIsLoadingStats(true)
      const [statsData, trendsData, toolUsageData] = await Promise.all([
        agentStatsApi.getStats(resolvedParams.id, period),
        agentStatsApi.getTrends(resolvedParams.id, period),
        agentStatsApi.getToolUsage(resolvedParams.id, period),
      ])
      setStats(statsData)
      setTrends(trendsData)
      setToolUsage(toolUsageData)
    } catch {
      // Error handled by API client
    } finally {
      setIsLoadingStats(false)
    }
  }, [resolvedParams, period])

  React.useEffect(() => {
    fetchAgent()
  }, [fetchAgent])

  React.useEffect(() => {
    if (agent) {
      fetchStats()
    }
  }, [agent, fetchStats])

  if (isLoading || !agent) {
    return (
      <div className="h-screen flex">
        <div className="w-52 border-r p-4">
          <Skeleton className="h-10 w-full mb-4" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-10 w-64 mb-6" />
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
          <Skeleton className="h-80" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Sidebar - Agent Info & Navigation */}
      <AgentSidebar agent={agent} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b px-6 py-4 shrink-0 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{t('description')}</p>
          <Select value={period} onValueChange={(v) => v && setPeriod(v)}>
            <SelectTrigger className="w-36">
              <SelectValue>
                {period === '24h' && t('period.24h')}
                {period === '7d' && t('period.7d')}
                {period === '30d' && t('period.30d')}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="24h">{t('period.24h')}</SelectItem>
              <SelectItem value="7d">{t('period.7d')}</SelectItem>
              <SelectItem value="30d">{t('period.30d')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {isLoadingStats ? (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-28" />
                ))}
              </div>
              <Skeleton className="h-80" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* Overview Stats */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-4">
                <StatCard
                  title={t('stats.conversations')}
                  value={formatNumber(stats?.overview.total_conversations || 0)}
                  icon={<MessagesSquare className="h-4 w-4" />}
                  color="blue"
                />
                <StatCard
                  title={t('stats.messages')}
                  value={formatNumber(stats?.overview.total_messages || 0)}
                  icon={<MessageSquare className="h-4 w-4" />}
                  color="cyan"
                />
                <StatCard
                  title={t('stats.tokens')}
                  value={formatNumber(stats?.tokens.total_tokens || 0)}
                  icon={<Coins className="h-4 w-4" />}
                  description={`↑${formatNumber(stats?.tokens.prompt_tokens || 0)} ↓${formatNumber(stats?.tokens.completion_tokens || 0)}`}
                  color="purple"
                />
                <StatCard
                  title={t('stats.avgResponseTime')}
                  value={formatDuration(stats?.performance.avg_response_time_ms || 0)}
                  icon={<Timer className="h-4 w-4" />}
                  color="orange"
                />
                <StatCard
                  title={t('stats.activeUsers')}
                  value={stats?.overview.active_users || 0}
                  icon={<Users className="h-4 w-4" />}
                  color="green"
                />
                <StatCard
                  title={t('stats.toolCalls')}
                  value={formatNumber(stats?.tools.tool_call_count || 0)}
                  icon={<Wrench className="h-4 w-4" />}
                  color="slate"
                />
              </div>

              {/* Charts Row 1 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Conversation & Message Trend */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t('charts.conversationTrend')}</CardTitle>
                    <CardDescription>{t('charts.conversationTrendDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={conversationChartConfig} className="h-[250px] w-full">
                      <AreaChart data={trends?.data || []} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="fillConversations" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-conversations)" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="var(--color-conversations)" stopOpacity={0.1}/>
                          </linearGradient>
                          <linearGradient id="fillMessages" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-messages)" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="var(--color-messages)" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} />
                        <YAxis tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} />
                        <ChartTooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltipContent />} />
                        <Area
                          type="monotone"
                          dataKey="conversations"
                          stroke="var(--color-conversations)"
                          fill="url(#fillConversations)"
                          strokeWidth={2}
                        />
                        <Area
                          type="monotone"
                          dataKey="messages"
                          stroke="var(--color-messages)"
                          fill="url(#fillMessages)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ChartContainer>
                  </CardContent>
                </Card>

                {/* Token Usage Trend */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t('charts.tokenUsage')}</CardTitle>
                    <CardDescription>{t('charts.tokenUsageDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={tokenChartConfig} className="h-[250px] w-full">
                      <AreaChart data={trends?.data || []} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="fillTokens" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-tokens)" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="var(--color-tokens)" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} />
                        <YAxis tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} tickFormatter={(v) => formatNumber(v)} />
                        <ChartTooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltipContent />} />
                        <Area
                          type="monotone"
                          dataKey="tokens"
                          stroke="var(--color-tokens)"
                          fill="url(#fillTokens)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ChartContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Charts Row 2 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Response Time Trend */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t('charts.responseTime')}</CardTitle>
                    <CardDescription>{t('charts.responseTimeDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={responseTimeChartConfig} className="h-[250px] w-full">
                      <AreaChart data={trends?.data || []} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="fillResponseTime" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="var(--color-avg_response_time_ms)" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="var(--color-avg_response_time_ms)" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} />
                        <YAxis tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} tickFormatter={(v) => `${(v / 1000).toFixed(1)}s`} />
                        <ChartTooltip
                          cursor={CHART_HOVER_CURSOR}
                          content={
                            <ChartTooltipContent
                              formatter={(value) => (
                                <>
                                  <span className="text-chart-tooltip-text/80">
                                    {t('charts.avgResponseTime')}
                                  </span>
                                  <span className="font-mono font-medium tabular-nums text-chart-tooltip-text">
                                    {`${(Number(value) / 1000).toFixed(2)}s`}
                                  </span>
                                </>
                              )}
                            />
                          }
                        />
                        <Area
                          type="monotone"
                          dataKey="avg_response_time_ms"
                          stroke="var(--color-avg_response_time_ms)"
                          fill="url(#fillResponseTime)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ChartContainer>
                  </CardContent>
                </Card>

                {/* Tool Usage */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t('charts.toolUsage')}</CardTitle>
                    <CardDescription>{t('charts.toolUsageDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {toolUsage && toolUsage.tools.length > 0 ? (
                      <>
                        <ChartContainer config={toolUsageChartConfig} className="h-[200px] w-full">
                          <PieChart>
                            <ChartTooltip
                              content={({ active, payload }) => {
                                if (!active || !payload?.length) return null
                                const tool = payload[0].payload as ToolUsageItem
                                return (
                                  <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                                    <div className="font-semibold mb-1">
                                      {tool.display_name || tool.name}
                                    </div>
                                    <div className="text-sm">
                                      {t('charts.calls')}: {formatNumber(tool.count)}
                                    </div>
                                  </div>
                                )
                              }}
                            />
                            <Pie
                              data={topTools}
                              dataKey="count"
                              nameKey="display_name"
                              cx="50%"
                              cy="50%"
                              innerRadius={55}
                              outerRadius={85}
                              paddingAngle={2}
                            >
                              {topTools.map((tool, index) => (
                                <Cell
                                  key={tool.name}
                                  fill={CHART_SURFACE_COLORS[index % CHART_SURFACE_COLORS.length]}
                                />
                              ))}
                            </Pie>
                          </PieChart>
                        </ChartContainer>
                        {/* Tool names are too long for slice labels, so the
                            legend carries them next to each count. */}
                        <ul className="mt-3 grid grid-cols-1 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
                          {topTools.map((tool, index) => (
                            <li key={tool.name} className="flex min-w-0 items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                                style={{
                                  backgroundColor:
                                    CHART_SURFACE_COLORS[index % CHART_SURFACE_COLORS.length],
                                }}
                              />
                              <span className="truncate" title={tool.display_name || tool.name}>
                                {tool.display_name || tool.name}
                              </span>
                              <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">
                                {formatNumber(tool.count)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                        <div className="text-center">
                          <Wrench className="h-8 w-8 mx-auto mb-2 opacity-30" />
                          <p className="text-sm">{t('noToolUsage')}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Run health, latency quality and user friction. The previous
                  recent-conversations card duplicated the /logs page, which
                  offers the same data with filtering, sorting and pagination. */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Execution Health */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <HeartPulse className="h-4 w-4 text-muted-foreground" />
                      {t('health.title')}
                    </CardTitle>
                    <CardDescription>{t('health.description')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {health.total > 0 ? (
                      <>
                        <ChartContainer config={healthChartConfig} className="h-[160px] w-full">
                          <PieChart>
                            <ChartTooltip
                              content={({ active, payload }) => {
                                if (!active || !payload?.length) return null
                                const item = payload[0].payload as {
                                  key: string
                                  label: string
                                  value: number
                                }
                                return (
                                  <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                                    <div className="font-semibold mb-1">{item.label}</div>
                                    <div className="text-sm">
                                      {`${formatNumber(item.value)} · ${((item.value / health.total) * 100).toFixed(1)}%`}
                                    </div>
                                  </div>
                                )
                              }}
                            />
                            <Pie
                              data={healthSlices}
                              dataKey="value"
                              nameKey="label"
                              cx="50%"
                              cy="50%"
                              innerRadius={42}
                              outerRadius={64}
                              paddingAngle={2}
                            >
                              {healthSlices.map((slice) => (
                                <Cell key={slice.key} fill={slice.fill} />
                              ))}
                            </Pie>
                          </PieChart>
                        </ChartContainer>
                        <dl className="mt-2 space-y-1.5 text-xs">
                          {healthSlices.map((slice) => (
                            <div key={slice.key} className="flex min-w-0 items-center gap-2">
                              <span
                                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                                style={{ backgroundColor: slice.fill }}
                              />
                              <dt className="truncate">{slice.label}</dt>
                              <dd className="ml-auto shrink-0 tabular-nums">{formatNumber(slice.value)}</dd>
                            </div>
                          ))}
                        </dl>
                        <div className="mt-3 border-t pt-3">
                          <div className="flex items-baseline justify-between">
                            <span className="text-xs text-muted-foreground">{t('health.successRate')}</span>
                            <span
                              className={cn(
                                'text-lg font-semibold tabular-nums',
                                health.success_rate >= 0.95
                                  ? 'text-green-600'
                                  : health.success_rate >= 0.8
                                    ? 'text-amber-600'
                                    : 'text-red-600'
                              )}
                            >
                              {`${(health.success_rate * 100).toFixed(1)}%`}
                            </span>
                          </div>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {t('health.rateHint')}
                          </p>
                          {health.in_flight > 0 && (
                            <p className="mt-1 text-[11px] text-muted-foreground">
                              {t('health.inFlight', { count: health.in_flight })}
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <div className="h-[220px] flex items-center justify-center text-muted-foreground">
                        <div className="text-center">
                          <HeartPulse className="h-8 w-8 mx-auto mb-2 opacity-30" />
                          <p className="text-sm">{t('health.empty')}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* First Token Latency */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Zap className="h-4 w-4 text-muted-foreground" />
                      {t('firstToken.title')}
                    </CardTitle>
                    <CardDescription>{t('firstToken.description')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {latency.samples > 0 ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-3 gap-2">
                          {([
                            ['p50', latency.p50],
                            ['p95', latency.p95],
                            ['average', latency.avg],
                          ] as const).map(([key, value]) => (
                            <div key={key} className="rounded-lg bg-muted/50 px-2 py-2 text-center">
                              <p className="text-[11px] text-muted-foreground">{t(`firstToken.${key}`)}</p>
                              <p className="mt-0.5 text-sm font-semibold tabular-nums">
                                {formatDuration(value)}
                              </p>
                            </div>
                          ))}
                        </div>
                        {/* The median and tail as a series: a snapshot cannot
                            show the day a p95 spikes while the median holds. */}
                        <ChartContainer config={latencyChartConfig} className="h-[190px] w-full">
                          <LineChart
                            data={trends?.data || []}
                            margin={{ top: 5, right: 8, left: 0, bottom: 0 }}
                          >
                            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                            <XAxis
                              dataKey="label"
                              tickLine={false}
                              axisLine={false}
                              tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }}
                            />
                            <YAxis
                              tickLine={false}
                              axisLine={false}
                              width={48}
                              tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }}
                              tickFormatter={(value) => `${(Number(value) / 1000).toFixed(0)}s`}
                            />
                            <ChartTooltip
                              cursor={CHART_HOVER_CURSOR}
                              content={
                                <ChartTooltipContent
                                  formatter={(value, name) => (
                                    <>
                                      <span className="text-chart-tooltip-text/80">
                                        {latencyChartConfig[name as string]?.label ?? name}
                                      </span>
                                      <span className="font-mono font-medium tabular-nums text-chart-tooltip-text">
                                        {formatDuration(Number(value))}
                                      </span>
                                    </>
                                  )}
                                />
                              }
                            />
                            <Line
                              type="monotone"
                              dataKey="first_token_p95_ms"
                              stroke={CHART_COLOR_ORDER[4]}
                              strokeWidth={2}
                              dot={{ r: 3 }}
                              connectNulls={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="first_token_p50_ms"
                              stroke={CHART_COLOR_ORDER[0]}
                              strokeWidth={2}
                              dot={{ r: 3 }}
                              connectNulls={false}
                            />
                          </LineChart>
                        </ChartContainer>
                        <ul className="grid grid-cols-2 gap-x-4 text-xs">
                          <li className="flex items-center gap-2">
                            <span
                              className="h-2.5 w-2.5 shrink-0 rounded-sm"
                              style={{ backgroundColor: CHART_SURFACE_COLORS[0] }}
                            />
                            <span className="truncate">{t('firstToken.p50')}</span>
                          </li>
                          <li className="flex items-center gap-2">
                            <span
                              className="h-2.5 w-2.5 shrink-0 rounded-sm"
                              style={{ backgroundColor: CHART_SURFACE_COLORS[4] }}
                            />
                            <span className="truncate">{t('firstToken.p95')}</span>
                          </li>
                        </ul>
                        <p className="text-[11px] text-muted-foreground">
                          {t('firstToken.sampleCount', { count: formatNumber(latency.samples) })}
                        </p>
                      </div>
                    ) : (
                      <div className="h-[220px] flex items-center justify-center text-muted-foreground">
                        <div className="text-center">
                          <Zap className="h-8 w-8 mx-auto mb-2 opacity-30" />
                          <p className="text-sm">{t('firstToken.empty')}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* User Interventions */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Hand className="h-4 w-4 text-muted-foreground" />
                      {t('interventions.title')}
                    </CardTitle>
                    <CardDescription>{t('interventions.description')}</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col">
                    {interventions.total > 0 ? (
                      <div className="flex flex-1 flex-col gap-2">
                        {/* A ranked magnitude comparison: shared baseline, and
                            the category labels fit beside horizontal bars. */}
                        <ChartContainer config={interventionChartConfig} className="min-h-[200px] w-full flex-1">
                          <BarChart
                            data={interventionBars}
                            layout="vertical"
                            margin={{ top: 5, right: 12, left: 0, bottom: 0 }}
                          >
                            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" horizontal={false} />
                            <XAxis
                              type="number"
                              tickLine={false}
                              axisLine={false}
                              allowDecimals={false}
                              tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }}
                            />
                            <YAxis
                              type="category"
                              dataKey="label"
                              tickLine={false}
                              axisLine={false}
                              width={96}
                              tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }}
                            />
                            <ChartTooltip
                              cursor={CHART_HOVER_CURSOR}
                              content={({ active, payload }) => {
                                if (!active || !payload?.length) return null
                                const bar = payload[0].payload as {
                                  label: string
                                  value: number
                                }
                                return (
                                  <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                                    <div className="font-semibold mb-1">{bar.label}</div>
                                    <div className="text-sm tabular-nums">
                                      {formatNumber(bar.value)}
                                    </div>
                                  </div>
                                )
                              }}
                            />
                            <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                              {interventionBars.map((bar) => (
                                <Cell key={bar.key} fill={bar.fill} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ChartContainer>
                        {/* Raw counts grow with traffic, so the rate is what
                            makes two periods comparable. It shares the health
                            card's denominator, so both cards agree. */}
                        <div className="border-t pt-3">
                          <div className="flex items-baseline justify-between">
                            <span className="text-xs text-muted-foreground">
                              {t('interventions.rate')}
                            </span>
                            <span className="text-lg font-semibold tabular-nums">
                              {interventionRate.toFixed(2)}
                            </span>
                          </div>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {t('interventions.rateHint', {
                              runs: formatNumber(health.total),
                            })}
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="h-[220px] flex items-center justify-center text-muted-foreground">
                        <div className="text-center">
                          <Hand className="h-8 w-8 mx-auto mb-2 opacity-30" />
                          <p className="text-sm">{t('interventions.empty')}</p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
