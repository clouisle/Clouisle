'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { 
  MessageSquare, 
  MessagesSquare, 
  Coins, 
  Timer, 
  Users, 
  Wrench,
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
  type RecentConversationItem,
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
  XAxis,
  YAxis,
  CartesianGrid,
  Cell,
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
  const locale = useLocale()
  const router = useRouter()

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [period, setPeriod] = React.useState('7d')
  
  // Stats data
  const [stats, setStats] = React.useState<AgentStats | null>(null)
  const [trends, setTrends] = React.useState<AgentTrends | null>(null)
  const [toolUsage, setToolUsage] = React.useState<AgentToolUsage | null>(null)
  const [recentConversations, setRecentConversations] = React.useState<RecentConversationItem[]>([])
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
      const [statsData, trendsData, toolUsageData, recentData] = await Promise.all([
        agentStatsApi.getStats(resolvedParams.id, period),
        agentStatsApi.getTrends(resolvedParams.id, period),
        agentStatsApi.getToolUsage(resolvedParams.id, period),
        agentStatsApi.getRecentConversations(resolvedParams.id, 5),
      ])
      setStats(statsData)
      setTrends(trendsData)
      setToolUsage(toolUsageData)
      setRecentConversations(recentData)
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

  // Format datetime
  const formatDateTime = (dateString: string) => {
    const date = new Date(dateString)
    if (locale === 'zh') {
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    }
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

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
                        <ChartTooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltipContent formatter={(value) => [`${(Number(value) / 1000).toFixed(2)}s`, 'Response Time']} />} />
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
                      <ChartContainer config={toolUsageChartConfig} className="h-[250px] w-full">
                        <BarChart data={toolUsage.tools.slice(0, 8)} layout="vertical" margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                          <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                          <XAxis type="number" tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} />
                          <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} tick={{ fill: CHART_AXIS_COLOR, fontSize: 12 }} width={100} />
                          <ChartTooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltipContent />} />
                          <Bar dataKey="count" radius={[0, 8, 8, 0]}>
                            {toolUsage.tools.slice(0, 8).map((tool, index) => (
                              <Cell key={tool.name} fill={CHART_SURFACE_COLORS[index % CHART_SURFACE_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ChartContainer>
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

              {/* Recent Conversations */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">{t('recentConversations')}</CardTitle>
                  <CardDescription>{t('recentConversationsDesc')}</CardDescription>
                </CardHeader>
                <CardContent>
                  {recentConversations.length > 0 ? (
                    <div className="space-y-3">
                      {recentConversations.map((conv) => (
                        <div
                          key={conv.id}
                          className="flex items-center justify-between py-2 border-b last:border-0"
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">
                              {conv.title || t('untitledConversation')}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {conv.user?.username || t('anonymous')} · {conv.message_count} {t('messagesCount')}
                            </p>
                          </div>
                          <div className="text-xs text-muted-foreground shrink-0 ml-4">
                            {formatDateTime(conv.updated_at)}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="py-8 text-center text-muted-foreground">
                      <MessagesSquare className="h-8 w-8 mx-auto mb-2 opacity-30" />
                      <p className="text-sm">{t('noConversations')}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
