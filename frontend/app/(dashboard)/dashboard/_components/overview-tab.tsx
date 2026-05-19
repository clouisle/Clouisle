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
import { CHART_AXIS_COLOR, CHART_COLOR_ORDER, CHART_GRID_COLOR, CHART_HOVER_CURSOR } from '@/lib/chart-theme'

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

const COLORS = CHART_COLOR_ORDER

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

interface TooltipPayloadItem {
  name: string
  value: number | string
  color: string
  payload: TrendData
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayloadItem[]; label?: string }) {
  if (active && payload && payload.length) {
    return (
      <div className="min-w-[200px] rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
        <p className="mb-2 border-b border-chart-tooltip-border pb-2 text-sm font-semibold text-chart-tooltip-text">
          {label}
        </p>
        <div className="space-y-1.5">
          {payload.map((entry, index: number) => (
            <div key={index} className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <div
                  className="h-3 w-3 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-xs text-chart-tooltip-text/80">
                  {entry.name}
                </span>
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
  const animatedValue = useCountUp(typeof value === 'number' ? value : 0, isLoading)
  const displayValue = typeof value === 'number' ? formatNumber(animatedValue) : value

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="py-0">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <div className="h-9 w-32 bg-muted animate-pulse rounded" />
            ) : (
              <p className="text-3xl font-bold tracking-tight">
                {displayValue}
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
  const passwordExpiration = stats.password_expiration

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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          {/* User Growth Trend */}
          <Card className="flex h-full flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <UserPlus className="h-4 w-4" />
                {t('userGrowth')}
              </CardTitle>
              <CardDescription className="text-xs">{t('userGrowthDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="flex-1 pt-0">
              <div className="h-[180px] min-w-0 w-full">
                <ResponsiveContainer width="100%" height="100%">
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
                  <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: CHART_AXIS_COLOR }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: CHART_AXIS_COLOR }}
                    hide
                  />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<CustomTooltip />} />
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
            </div>
          </CardContent>
        </Card>

        </div>

        <div className="lg:col-span-4">
          {/* Active Users Card */}
          <Card className="h-full">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t('stats.activeUsers')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              <div className="rounded-lg bg-muted/50 p-2.5 text-center">
                <p className="mb-1 text-xs font-medium text-muted-foreground">{t('stats.dau')}</p>
                <p className="text-lg font-bold">{formatNumber(stats.active_users.dau)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('stats.dauDesc')}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-2.5 text-center">
                <p className="mb-1 text-xs font-medium text-muted-foreground">{t('stats.wau')}</p>
                <p className="text-lg font-bold">{formatNumber(stats.active_users.wau)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('stats.wauDesc')}</p>
              </div>
              <div className="rounded-lg bg-muted/50 p-2.5 text-center">
                <p className="mb-1 text-xs font-medium text-muted-foreground">{t('stats.mau')}</p>
                <p className="text-lg font-bold">{formatNumber(stats.active_users.mau)}</p>
                <p className="mt-1 text-xs text-muted-foreground">{t('stats.mauDesc')}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-8">
          {/* Activity Trend */}
          <Card className="flex h-full flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                {t('activityTrend')}
              </CardTitle>
              <CardDescription className="text-xs">{t('activityTrendDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="flex-1 pt-0">
              <div className="h-[180px] min-w-0 w-full">
                <ResponsiveContainer width="100%" height="100%">
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
                  <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: CHART_AXIS_COLOR }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    yAxisId="left"
                    className="text-xs"
                    tick={{ fill: CHART_AXIS_COLOR }}
                    hide
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    className="text-xs"
                    tick={{ fill: CHART_AXIS_COLOR }}
                    hide
                  />
                  <Tooltip cursor={CHART_HOVER_CURSOR} content={<CustomTooltip />} />
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
            </div>
          </CardContent>
        </Card>
        </div>

        <div className="lg:col-span-4">
          <div className="space-y-4">
            {/* Resource Overview */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('resources')}</CardTitle>
                <CardDescription>{t('resourcesDesc')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10">
                      <Building2 className="h-5 w-5 text-blue-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{t('stats.teams')}</p>
                      <p className="text-xs text-muted-foreground">{t('stats.teamsDesc')}</p>
                    </div>
                  </div>
                  <p className="text-xl font-bold">{stats.overview.total_teams}</p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-500/10">
                      <Bot className="h-5 w-5 text-purple-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{t('stats.agents')}</p>
                      <p className="text-xs text-muted-foreground">{t('stats.agentsDesc')}</p>
                    </div>
                  </div>
                  <p className="text-xl font-bold">{stats.overview.total_agents}</p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/10">
                      <Workflow className="h-5 w-5 text-cyan-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{t('stats.workflows')}</p>
                      <p className="text-xs text-muted-foreground">{t('stats.workflowsDesc')}</p>
                    </div>
                  </div>
                  <p className="text-xl font-bold">{stats.overview.total_workflows}</p>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-green-500/10">
                      <Database className="h-5 w-5 text-green-500" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{t('stats.knowledgeBases')}</p>
                      <p className="text-xs text-muted-foreground">{t('stats.knowledgeBasesDesc')}</p>
                    </div>
                  </div>
                  <p className="text-xl font-bold">{stats.overview.total_knowledge_bases}</p>
                </div>
              </CardContent>
            </Card>

            {passwordExpiration && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4 text-yellow-600" />
                    {t('passwordExpiration.title')}
                  </CardTitle>
                  <CardDescription>{t('passwordExpiration.description')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 pt-0">
                  {passwordExpiration.expired_count > 0 && (
                    <div className="flex items-center justify-between rounded-lg border border-destructive/20 bg-destructive/10 p-2.5">
                      <div>
                        <p className="text-sm font-medium text-destructive">{t('passwordExpiration.expired')}</p>
                        <p className="text-xs text-muted-foreground">{t('passwordExpiration.expiredDesc')}</p>
                      </div>
                      <p className="text-2xl font-bold text-destructive">{passwordExpiration.expired_count}</p>
                    </div>
                  )}
                  {passwordExpiration.expiring_soon_count > 0 && (
                    <div className="flex items-center justify-between rounded-lg border border-yellow-500/20 bg-yellow-500/10 p-2.5">
                      <div>
                        <p className="text-sm font-medium text-yellow-700 dark:text-yellow-500">{t('passwordExpiration.expiringSoon')}</p>
                        <p className="text-xs text-muted-foreground">{t('passwordExpiration.expiringSoonDesc')}</p>
                      </div>
                      <p className="text-2xl font-bold text-yellow-700 dark:text-yellow-500">{passwordExpiration.expiring_soon_count}</p>
                    </div>
                  )}
                  {passwordExpiration.force_change_count > 0 && (
                    <div className="flex items-center justify-between rounded-lg border border-orange-500/20 bg-orange-500/10 p-2.5">
                      <div>
                        <p className="text-sm font-medium text-orange-700 dark:text-orange-500">{t('passwordExpiration.forceChange')}</p>
                        <p className="text-xs text-muted-foreground">{t('passwordExpiration.forceChangeDesc')}</p>
                      </div>
                      <p className="text-2xl font-bold text-orange-700 dark:text-orange-500">{passwordExpiration.force_change_count}</p>
                    </div>
                  )}
                  {passwordExpiration.expired_count === 0 &&
                    passwordExpiration.expiring_soon_count === 0 &&
                    passwordExpiration.force_change_count === 0 && (
                      <div className="rounded-lg bg-muted/50 p-3 text-center">
                        <p className="text-sm text-muted-foreground">{t('passwordExpiration.allGood')}</p>
                      </div>
                    )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
