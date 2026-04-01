'use client'

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
  UserPlus,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type { DashboardStats } from '@/lib/api/admin/dashboard'
import type { TOTPStatsResponse } from '@/lib/api/admin/users'

interface TrendData {
  date: string
  new_users: number
  active_users: number
  new_conversations: number
  messages: number
  tokens: number
}

interface OverviewTabProps {
  stats: DashboardStats
  trendsData: TrendData[]
  isLoading: boolean
  totpStats: TOTPStatsResponse | null
}

const COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

interface TooltipPayloadItem {
  name: string
  value: number | string
  color: string
  payload: TrendData
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayloadItem[]; label?: string }) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-background/95 backdrop-blur-sm border border-border rounded-lg shadow-lg p-3 min-w-[200px]">
        <p className="text-sm font-semibold text-foreground mb-2 pb-2 border-b border-border">
          {label}
        </p>
        <div className="space-y-1.5">
          {payload.map((entry, index: number) => (
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
  color = 'primary',
}: {
  title: string
  value: number | string
  icon: React.ElementType
  isLoading: boolean
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
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <div className="h-9 w-32 bg-muted animate-pulse rounded" />
            ) : (
              <p className="text-3xl font-bold tracking-tight">
                {typeof value === 'number' ? formatNumber(value) : value}
              </p>
            )}
          </div>
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${colorClasses[color as keyof typeof colorClasses] || colorClasses.primary}`}>
            <Icon className="h-6 w-6" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function OverviewTab({ stats, trendsData, isLoading, totpStats }: OverviewTabProps) {
  const t = useTranslations('dashboard.home')

  return (
    <div className="space-y-6">
      {/* Top Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title={t('stats.totalUsers')}
          value={stats.overview.total_users}
          icon={Users}
          isLoading={isLoading}
          color="blue"
        />
        <StatCard
          title={t('stats.dau')}
          value={stats.active_users.dau}
          icon={Activity}
          isLoading={isLoading}
          color="green"
        />
        <StatCard
          title={t('stats.totalConversations')}
          value={stats.overview.total_conversations}
          icon={MessageSquare}
          isLoading={isLoading}
          color="purple"
        />
        <StatCard
          title={t('stats.totalTokens')}
          value={stats.overview.total_tokens}
          icon={Coins}
          isLoading={isLoading}
          color="orange"
        />
      </div>

      {/* 2FA Stats */}
      {totpStats && (
        <Card className="border-green-200 dark:border-green-900">
          <CardContent className="pt-6">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground">{t('stats.twoFactorAuth')}</p>
                <div className="flex items-baseline gap-2">
                  <p className="text-3xl font-bold tracking-tight">{totpStats.totp_enabled}</p>
                  <p className="text-sm text-muted-foreground">/ {totpStats.total_users} {t('stats.users')}</p>
                </div>
                <p className="text-sm text-green-600 dark:text-green-400 font-medium">
                  {totpStats.adoption_rate.toFixed(1)}% {t('stats.adoptionRate')}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl flex items-center justify-center bg-green-500/10 text-green-500">
                <ShieldCheck className="h-6 w-6" />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

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
                      <stop offset="5%" stopColor={COLORS[2]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[2]} stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorActiveUsers" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[4]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[4]} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: 'var(--muted-foreground)' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: 'var(--muted-foreground)' }}
                    hide
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="new_users"
                    stroke={COLORS[2]}
                    fillOpacity={1}
                    fill="url(#colorNewUsers)"
                    name={t('stats.newUsers')}
                  />
                  <Area
                    type="monotone"
                    dataKey="active_users"
                    stroke={COLORS[4]}
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
                    tick={{ fill: 'var(--muted-foreground)' }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="left"
                    className="text-xs"
                    tick={{ fill: 'var(--muted-foreground)' }}
                    hide
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    className="text-xs"
                    tick={{ fill: 'var(--muted-foreground)' }}
                    hide
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
          {/* Password Expiration Stats */}
          {stats.password_expiration && (
            <Card className="border-yellow-500/50">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-yellow-600" />
                  {t('passwordExpiration.title')}
                </CardTitle>
                <CardDescription>{t('passwordExpiration.description')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {stats.password_expiration.expired_count > 0 && (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                    <div>
                      <p className="text-sm font-medium text-destructive">{t('passwordExpiration.expired')}</p>
                      <p className="text-xs text-muted-foreground">{t('passwordExpiration.expiredDesc')}</p>
                    </div>
                    <p className="text-2xl font-bold text-destructive">{stats.password_expiration.expired_count}</p>
                  </div>
                )}
                {stats.password_expiration.expiring_soon_count > 0 && (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                    <div>
                      <p className="text-sm font-medium text-yellow-700 dark:text-yellow-500">{t('passwordExpiration.expiringSoon')}</p>
                      <p className="text-xs text-muted-foreground">{t('passwordExpiration.expiringSoonDesc')}</p>
                    </div>
                    <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-500">{stats.password_expiration.expiring_soon_count}</p>
                  </div>
                )}
                {stats.password_expiration.force_change_count > 0 && (
                  <div className="flex items-center justify-between p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
                    <div>
                      <p className="text-sm font-medium text-orange-700 dark:text-orange-500">{t('passwordExpiration.forceChange')}</p>
                      <p className="text-xs text-muted-foreground">{t('passwordExpiration.forceChangeDesc')}</p>
                    </div>
                    <p className="text-2xl font-bold text-orange-700 dark:text-orange-500">{stats.password_expiration.force_change_count}</p>
                  </div>
                )}
                {stats.password_expiration.expired_count === 0 &&
                  stats.password_expiration.expiring_soon_count === 0 &&
                  stats.password_expiration.force_change_count === 0 && (
                    <div className="text-center p-4 rounded-lg bg-muted/50">
                      <p className="text-sm text-muted-foreground">{t('passwordExpiration.allGood')}</p>
                    </div>
                  )}
              </CardContent>
            </Card>
          )}

          {/* Active Users Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t('stats.activeUsers')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.dau')}</p>
                <p className="text-3xl font-bold">{formatNumber(stats.active_users.dau)}</p>
                <p className="text-xs text-muted-foreground mt-1">{t('stats.dauDesc')}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.wau')}</p>
                <p className="text-3xl font-bold">{formatNumber(stats.active_users.wau)}</p>
                <p className="text-xs text-muted-foreground mt-1">{t('stats.wauDesc')}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-muted/50">
                <p className="text-sm font-medium text-muted-foreground mb-2">{t('stats.mau')}</p>
                <p className="text-3xl font-bold">{formatNumber(stats.active_users.mau)}</p>
                <p className="text-xs text-muted-foreground mt-1">{t('stats.mauDesc')}</p>
              </div>
            </CardContent>
          </Card>

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
                    <Building2 className="h-5 w-5 text-blue-500" />
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
        </div>
      </div>
    </div>
  )
}
