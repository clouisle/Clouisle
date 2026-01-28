'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Users,
  Building2,
  Bot,
  Workflow,
  Database,
  MessageSquare,
  Activity,
  Coins,
  TrendingUp,
  UserPlus,
  Loader2,
} from 'lucide-react'
import { dashboardApi, type DashboardStats } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']

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

// 自定义 Tooltip 组件
function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-background/95 backdrop-blur-sm border border-border rounded-lg shadow-lg p-3 min-w-[200px]">
        <p className="text-sm font-semibold text-foreground mb-2 pb-2 border-b border-border">
          {label}
        </p>
        <div className="space-y-1.5">
          {payload.map((entry: any, index: number) => (
            <div key={index} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-xs text-muted-foreground">
                  {entry.name}
                </span>
              </div>
              <span className="text-sm font-semibold text-foreground">
                {typeof entry.value === 'number' ? formatNumber(entry.value) : entry.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return null
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading,
  change,
  changeLabel,
  color = 'primary',
}: {
  title: string
  value: number | string
  icon: React.ElementType
  isLoading: boolean
  change?: number
  changeLabel?: string
  color?: string
}) {
  const colorClasses = {
    primary: 'bg-primary/10 text-primary',
    blue: 'bg-blue-500/10 text-blue-500',
    purple: 'bg-purple-500/10 text-purple-500',
    green: 'bg-green-500/10 text-green-500',
    orange: 'bg-orange-500/10 text-orange-500',
    cyan: 'bg-cyan-500/10 text-cyan-500',
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${colorClasses[color as keyof typeof colorClasses] || colorClasses.primary}`}>
                <Icon className="h-5 w-5" />
              </div>
              {change !== undefined && (
                <Badge variant={change >= 0 ? 'default' : 'secondary'} className="text-xs">
                  <TrendingUp className={`h-3 w-3 mr-1 ${change < 0 ? 'rotate-180' : ''}`} />
                  {Math.abs(change)}
                  {changeLabel && <span className="ml-1">{changeLabel}</span>}
                </Badge>
              )}
            </div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <div className="h-8 w-20 mt-1 bg-muted animate-pulse rounded" />
            ) : (
              <p className="text-2xl font-bold mt-1">
                {typeof value === 'number' ? formatNumber(value) : value}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const t = useTranslations('dashboard.home')
  const [stats, setStats] = React.useState<DashboardStats | null>(null)
  const [trendsData, setTrendsData] = React.useState<Array<any>>([])
  const [isLoading, setIsLoading] = React.useState(true)

  React.useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true)
        const [statsResponse, trendsResponse] = await Promise.all([
          dashboardApi.getStats(),
          dashboardApi.getTrends('30d'),
        ])
        setStats(statsResponse)
        setTrendsData(trendsResponse.data)
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [])

  if (isLoading || !stats) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="py-6 px-8 flex items-center justify-center min-h-[400px]">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="py-6 px-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title={t('stats.totalUsers')}
          value={stats.overview.total_users}
          icon={Users}
          isLoading={false}
          change={stats.growth.new_users_30d}
          changeLabel="30d"
          color="blue"
        />
        <StatCard
          title={t('stats.dau')}
          value={stats.active_users.dau}
          icon={Activity}
          isLoading={false}
          color="green"
        />
        <StatCard
          title={t('stats.totalConversations')}
          value={stats.overview.total_conversations}
          icon={MessageSquare}
          isLoading={false}
          change={stats.growth.new_conversations_30d}
          changeLabel="30d"
          color="purple"
        />
        <StatCard
          title={t('stats.totalTokens')}
          value={stats.overview.total_tokens}
          icon={Coins}
          isLoading={false}
          color="orange"
        />
      </div>

      {/* Active Users Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.dau')}</p>
              <p className="text-3xl font-bold">{formatNumber(stats.active_users.dau)}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('stats.dauDesc')}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.wau')}</p>
              <p className="text-3xl font-bold">{formatNumber(stats.active_users.wau)}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('stats.wauDesc')}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.mau')}</p>
              <p className="text-3xl font-bold">{formatNumber(stats.active_users.mau)}</p>
              <p className="text-xs text-muted-foreground mt-1">{t('stats.mauDesc')}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content - 2/3 width */}
        <div className="lg:col-span-2 space-y-6">
          {/* User Growth Trend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <UserPlus className="h-4 w-4" />
                {t('userGrowth')}
              </CardTitle>
              <CardDescription>{t('userGrowthDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trendsData}>
                  <defs>
                    <linearGradient id="colorNewUsers" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[0]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[0]} stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorActiveUsers" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[1]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[1]} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="new_users"
                    stroke={COLORS[0]}
                    fillOpacity={1}
                    fill="url(#colorNewUsers)"
                    name={t('stats.newUsers')}
                  />
                  <Area
                    type="monotone"
                    dataKey="active_users"
                    stroke={COLORS[1]}
                    fillOpacity={1}
                    fill="url(#colorActiveUsers)"
                    name={t('stats.activeUsers')}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Activity Trend */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                {t('activityTrend')}
              </CardTitle>
              <CardDescription>{t('activityTrendDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trendsData}>
                  <defs>
                    <linearGradient id="colorConversations" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[2]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[2]} stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[4]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[4]} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <YAxis
                    yAxisId="left"
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="new_conversations"
                    stroke={COLORS[2]}
                    fillOpacity={1}
                    fill="url(#colorConversations)"
                    name={t('stats.conversations')}
                  />
                  <Area
                    yAxisId="right"
                    type="monotone"
                    dataKey="tokens"
                    stroke={COLORS[4]}
                    fillOpacity={1}
                    fill="url(#colorTokens)"
                    name={t('stats.tokens')}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - 1/3 width */}
        <div className="space-y-6">
          {/* Resource Overview */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('resources')}</CardTitle>
              <CardDescription>{t('resourcesDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                    <Users className="h-5 w-5 text-blue-500" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('stats.teams')}</p>
                    <p className="text-xs text-muted-foreground">{t('stats.teamsDesc')}</p>
                  </div>
                </div>
                <p className="text-2xl font-bold">{stats.overview.total_teams}</p>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                    <Bot className="h-5 w-5 text-purple-500" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('stats.agents')}</p>
                    <p className="text-xs text-muted-foreground">{t('stats.agentsDesc')}</p>
                  </div>
                </div>
                <p className="text-2xl font-bold">{stats.overview.total_agents}</p>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                    <Workflow className="h-5 w-5 text-cyan-500" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('stats.workflows')}</p>
                    <p className="text-xs text-muted-foreground">{t('stats.workflowsDesc')}</p>
                  </div>
                </div>
                <p className="text-2xl font-bold">{stats.overview.total_workflows}</p>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                    <Database className="h-5 w-5 text-green-500" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{t('stats.knowledgeBases')}</p>
                    <p className="text-xs text-muted-foreground">{t('stats.knowledgeBasesDesc')}</p>
                  </div>
                </div>
                <p className="text-2xl font-bold">{stats.overview.total_knowledge_bases}</p>
              </div>
            </CardContent>
          </Card>

          {/* System Stats */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('systemStats')}</CardTitle>
              <CardDescription>{t('systemStatsDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">{t('stats.totalMessages')}</span>
                <span className="text-lg font-semibold">{formatNumber(stats.overview.total_messages)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">{t('stats.avgMessagesPerConv')}</span>
                <span className="text-lg font-semibold">
                  {stats.overview.total_conversations > 0
                    ? (stats.overview.total_messages / stats.overview.total_conversations).toFixed(1)
                    : '0'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">{t('stats.avgTokensPerMessage')}</span>
                <span className="text-lg font-semibold">
                  {stats.overview.total_messages > 0
                    ? formatNumber(Math.round(stats.overview.total_tokens / stats.overview.total_messages))
                    : '0'}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
    </div>
  )
}
