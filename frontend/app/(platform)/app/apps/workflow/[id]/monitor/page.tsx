'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  Activity,
  TrendingUp,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Zap,
  ArrowLeft,
  RefreshCw,
  Calendar,
  BarChart3,
  Loader2,
  ExternalLink,
  FileText,
  LayoutGrid,
  GitBranch,
} from 'lucide-react'
import Image from 'next/image'
import { workflowsApi, type Workflow } from '@/lib/api/workflows'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const COLORS = ['#3b82f6', '#10b981', '#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4']

// 格式化数字
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

// 格式化持续时间
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`
  return `${(ms / 3600000).toFixed(1)}h`
}

// 自定义 Tooltip
function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-background/95 backdrop-blur-sm border border-border rounded-lg shadow-lg p-3 min-w-[180px]">
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

// 统计卡片组件
function StatCard({
  title,
  value,
  icon: Icon,
  trend,
  trendLabel,
  color = 'blue',
}: {
  title: string
  value: string | number
  icon: React.ElementType
  trend?: number
  trendLabel?: string
  color?: string
}) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-500',
    green: 'bg-green-500/10 text-green-500',
    red: 'bg-red-500/10 text-red-500',
    orange: 'bg-orange-500/10 text-orange-500',
    purple: 'bg-purple-500/10 text-purple-500',
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <div className={`h-10 w-10 rounded-lg flex items-center justify-center ${colorClasses[color as keyof typeof colorClasses]}`}>
                <Icon className="h-5 w-5" />
              </div>
              {trend !== undefined && (
                <Badge variant={trend >= 0 ? 'default' : 'secondary'} className="text-xs">
                  <TrendingUp className={`h-3 w-3 mr-1 ${trend < 0 ? 'rotate-180' : ''}`} />
                  {Math.abs(trend)}%
                  {trendLabel && <span className="ml-1">{trendLabel}</span>}
                </Badge>
              )}
            </div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold mt-1">
              {typeof value === 'number' ? formatNumber(value) : value}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function WorkflowMonitorPage() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const tMonitor = useTranslations('workflow.monitor_page')
  const workflowId = params.id as string

  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [stats, setStats] = React.useState<any>(null)
  const [trendsData, setTrendsData] = React.useState<any[]>([])
  const [recentRuns, setRecentRuns] = React.useState<any[]>([])
  const [period, setPeriod] = React.useState<'7d' | '30d'>('7d')
  const [isLoading, setIsLoading] = React.useState(true)
  const [isRefreshing, setIsRefreshing] = React.useState(false)

  const fetchData = React.useCallback(async () => {
    try {
      setIsRefreshing(true)

      // 获取工作流信息、统计数据、趋势数据和最近运行记录
      const [workflowData, statsData, trendsData, runsData] = await Promise.all([
        workflowsApi.getWorkflow(workflowId),
        workflowsApi.getWorkflowStats(workflowId, period),
        workflowsApi.getWorkflowTrends(workflowId, period),
        workflowsApi.getWorkflowRuns(workflowId, { page: 1, pageSize: 5 }),
      ])

      setWorkflow(workflowData)
      setStats(statsData)
      setTrendsData(trendsData.data)
      setRecentRuns(runsData.items)
    } catch (error) {
      console.error('Failed to fetch monitor data:', error)
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [workflowId, period])

  React.useEffect(() => {
    fetchData()
  }, [fetchData])

  if (isLoading || !workflow || !stats) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const successRate = stats.total_runs > 0
    ? ((stats.success_count / stats.total_runs) * 100).toFixed(1)
    : '0'

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="absolute top-4 left-4 z-50 flex items-center gap-2">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 bg-card shadow-sm"
          onClick={() => router.push('/app/apps')}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>

        {/* Workflow Dropdown Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 border border-input hover:bg-accent hover:text-accent-foreground h-9 bg-card shadow-sm gap-2 px-2">
            {workflow.icon && (workflow.icon.startsWith('http') || workflow.icon.startsWith('/')) ? (
              <Image
                src={workflow.icon}
                alt={workflow.name || ''}
                width={20}
                height={20}
                className="rounded object-cover"
                unoptimized
              />
            ) : (
              <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10">
                <GitBranch className="h-3 w-3 text-primary" />
              </div>
            )}
            <span className="text-sm font-medium max-w-32 truncate">{workflow.name || t('untitled')}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}`)}
            >
              <LayoutGrid className="h-4 w-4" />
              <span>{t('orchestrate')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}/api`)}
            >
              <ExternalLink className="h-4 w-4" />
              <span>{t('accessApi')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}/logs`)}
            >
              <FileText className="h-4 w-4" />
              <span>{t('logs')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2 bg-primary/10 text-primary">
              <Activity className="h-4 w-4" />
              <span>{t('monitor')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Period Selector */}
        <Select value={period} onValueChange={(v) => setPeriod(v as '7d' | '30d')}>
          <SelectTrigger className="w-[120px] h-9 bg-card shadow-sm">
            <SelectValue>
              {period === '7d' ? tMonitor('last7Days') : tMonitor('last30Days')}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">{tMonitor('last7Days')}</SelectItem>
            <SelectItem value="30d">{tMonitor('last30Days')}</SelectItem>
          </SelectContent>
        </Select>

        {/* Refresh Button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 bg-card shadow-sm"
          onClick={fetchData}
          disabled={isRefreshing}
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto pt-20">
        <div className="mx-auto max-w-7xl px-6 pb-20 space-y-6">
          {/* Page Title */}
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{tMonitor('title')}</h1>
            <p className="text-muted-foreground mt-1">
              {workflow.name}
            </p>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title={tMonitor('stats.totalRuns')}
            value={stats.total_runs}
            icon={Activity}
            color="blue"
          />
          <StatCard
            title={tMonitor('stats.successRate')}
            value={`${successRate}%`}
            icon={CheckCircle2}
            color="green"
          />
          <StatCard
            title={tMonitor('stats.avgDuration')}
            value={formatDuration(stats.avg_duration_ms || 0)}
            icon={Clock}
            color="purple"
          />
          <StatCard
            title={tMonitor('stats.failedRuns')}
            value={stats.failed_count}
            icon={XCircle}
            color="red"
          />
        </div>

        {/* Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Run Trends */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                {tMonitor('runTrends')}
              </CardTitle>
              <CardDescription>{tMonitor('runTrendsDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trendsData}>
                  <defs>
                    <linearGradient id="colorRuns" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={COLORS[0]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={COLORS[0]} stopOpacity={0}/>
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
                  <Area
                    type="monotone"
                    dataKey="runs"
                    stroke={COLORS[0]}
                    fillOpacity={1}
                    fill="url(#colorRuns)"
                    name={tMonitor('stats.runs')}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Success vs Failed */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                {tMonitor('successVsFailed')}
              </CardTitle>
              <CardDescription>{tMonitor('successVsFailedDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={trendsData}>
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
                  <Bar dataKey="success" fill={COLORS[1]} name={tMonitor('stats.success')} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="failed" fill={COLORS[2]} name={tMonitor('stats.failed')} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Performance Trend */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4" />
                {tMonitor('performanceTrend')}
              </CardTitle>
              <CardDescription>{tMonitor('performanceTrendDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={trendsData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: 'hsl(var(--muted-foreground))' }}
                    tickFormatter={(value) => formatDuration(value)}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="avgDuration"
                    stroke={COLORS[4]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    name={tMonitor('stats.avgDuration')}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Status Distribution */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{tMonitor('statusDistribution')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <span className="text-sm font-medium">{tMonitor('stats.success')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{stats.success_count}</span>
                  <span className="text-sm text-muted-foreground">
                    ({((stats.success_count / stats.total_runs) * 100).toFixed(0)}%)
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <XCircle className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-medium">{tMonitor('stats.failed')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{stats.failed_count}</span>
                  <span className="text-sm text-muted-foreground">
                    ({((stats.failed_count / stats.total_runs) * 100).toFixed(0)}%)
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5 text-orange-500" />
                  <span className="text-sm font-medium">{tMonitor('stats.timeout')}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{stats.timeout_count || 0}</span>
                  <span className="text-sm text-muted-foreground">
                    ({(((stats.timeout_count || 0) / stats.total_runs) * 100).toFixed(0)}%)
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">{tMonitor('recentActivity')}</CardTitle>
              <CardDescription>{tMonitor('recentActivityDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              {recentRuns.length > 0 ? (
                <div className="space-y-3">
                  {recentRuns.map((run) => {
                    const statusColor =
                      run.status === 'success' ? 'bg-green-500' :
                      run.status === 'failed' ? 'bg-red-500' :
                      run.status === 'running' ? 'bg-blue-500' :
                      run.status === 'timeout' ? 'bg-orange-500' :
                      'bg-gray-500'

                    const statusVariant =
                      run.status === 'success' ? 'default' :
                      run.status === 'failed' ? 'destructive' :
                      'secondary'

                    const statusLabel =
                      run.status === 'success' ? tMonitor('stats.success') :
                      run.status === 'failed' ? tMonitor('stats.failed') :
                      run.status === 'running' ? tMonitor('stats.running') :
                      run.status === 'timeout' ? tMonitor('stats.timeout') :
                      run.status

                    return (
                      <div key={run.id} className="flex items-center justify-between p-3 rounded-lg border">
                        <div className="flex items-center gap-3">
                          <div className={`h-2 w-2 rounded-full ${statusColor}`} />
                          <div>
                            <p className="text-sm font-medium">
                              {statusLabel}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(run.created_at).toLocaleString()}
                            </p>
                          </div>
                        </div>
                        <Badge variant={statusVariant}>
                          {run.total_duration_ms ? formatDuration(run.total_duration_ms) : '-'}
                        </Badge>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  {tMonitor('noRecentActivity')}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
    </div>
  )
}
