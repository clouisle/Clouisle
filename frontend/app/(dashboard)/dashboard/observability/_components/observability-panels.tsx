'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  AlertTriangle,
  ChevronRight,
  Cpu,
  Database,
  HardDrive,
  Info,
  Server,
  Workflow,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CHART_COLOR_ORDER, CHART_GRID_COLOR, CHART_TOOLTIP_STYLE } from '@/lib/chart-theme'
import {
  observabilityApi,
  type AgentDetailResponse,
  type AgentPerformanceRow,
  type ObservabilityOverview,
  type ObservabilityTrendPoint,
  type SlowQueriesResponse,
  type SystemHealthResponse,
  type SystemTrendResponse,
  type ThroughputResponse,
  type TimeoutEvent,
  type TimeoutResponse,
  type TokenResponse,
  type WorkflowDetailResponse,
  type WorkflowPerformanceRow,
  type WorkerResponse,
} from '@/lib/api/admin/observability'
import type { TimeRange } from '@/components/dashboard/time-range-selector'

type ObservabilityTab = 'overview' | 'health' | 'agents' | 'workflows' | 'timeouts' | 'throughput'
type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'
type ObservabilityTranslator = ReturnType<typeof useTranslations>

const TONE_STYLES: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border',
  success: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20 dark:text-emerald-300',
  warning: 'bg-amber-500/10 text-amber-700 border-amber-500/20 dark:text-amber-300',
  danger: 'bg-destructive/10 text-destructive border-destructive/20',
  info: 'bg-sky-500/10 text-sky-700 border-sky-500/20 dark:text-sky-300',
}

interface OverviewPanelProps {
  overview: ObservabilityOverview | null
  throughput: ThroughputResponse | null
}

interface HealthPanelProps {
  health: SystemHealthResponse | null
  trend: SystemTrendResponse | null
  slowQueries: SlowQueriesResponse | null
  workers: WorkerResponse | null
}

export function ObservabilitySkeleton({ tab }: { tab: ObservabilityTab }) {
  const tableRows = tab === 'agents' || tab === 'workflows' || tab === 'timeouts'
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24 rounded-xl" />
        ))}
      </div>
      {tableRows ? (
        <Skeleton className="h-[420px] rounded-xl" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-12">
          <Skeleton className="h-[360px] rounded-xl lg:col-span-5" />
          <Skeleton className="h-[360px] rounded-xl lg:col-span-7" />
        </div>
      )}
    </div>
  )
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations('dashboard.observability')
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>{t('states.errorTitle')}</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{t('states.errorDescription')}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>{t('actions.retry')}</Button>
      </AlertDescription>
    </Alert>
  )
}

export function OverviewPanel({ overview, throughput }: OverviewPanelProps) {
  const t = useTranslations('dashboard.observability')
  if (!overview) return <ObservabilityEmpty />

  const risk = getRiskLevel(
    overview.rates.timeout_rate,
    overview.rates.overall_success_rate,
    overview.latency.p95_ms,
    overview.ttft?.p95_ms ?? null
  )
  const trafficTotal = overview.totals.agent_requests + overview.totals.workflow_runs
  const distribution = [
    { label: t('overview.agentRequests'), value: overview.totals.agent_requests, tone: 'info' as Tone },
    { label: t('overview.workflowRuns'), value: overview.totals.workflow_runs, tone: 'success' as Tone },
  ]

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-5">
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle>{t('overview.operationalStatus')}</CardTitle>
                <CardDescription>{t('overview.operationalStatusDesc')}</CardDescription>
              </div>
              <StatusPill tone={risk.tone} label={t(`risk.${risk.key}`)} />
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="text-2xl font-semibold tracking-tight">{t(`overview.${risk.summaryKey}`)}</div>
              <div className="mt-2 text-sm text-muted-foreground">{t('states.cacheTtl', { seconds: overview.cache_ttl_seconds })}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ConsoleMetric label={t('metrics.timeoutRate')} value={formatPercent(overview.rates.timeout_rate)} tone={risk.tone} />
              <ConsoleMetric label={t('metrics.successRate')} value={formatPercent(overview.rates.overall_success_rate)} tone="success" />
              <ConsoleMetric label={t('metrics.p95Latency')} value={formatDuration(overview.latency.p95_ms)} />
              <ConsoleMetric label={t('metrics.p95Ttft')} value={formatDuration(overview.ttft?.p95_ms)} />
              <ConsoleMetric label={t('metrics.currentQps')} value={String(overview.throughput.current_qps)} />
            </div>
            <PercentileStrip values={overview.latency} />
          </CardContent>
        </Card>

        <ObservabilityChartCard className="lg:col-span-7" title={t('charts.requestTrend')} description={t('charts.requestTrendDesc')} empty={!throughput?.buckets.length}>
          <ResponsiveContainer width="100%" height={310}>
            <AreaChart data={throughput?.buckets ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
              <XAxis dataKey="bucket" tickFormatter={formatBucket} minTickGap={24} />
              <YAxis />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={formatBucket} />
              <Legend />
              <Area name={t('overview.agentRequests')} type="monotone" dataKey="agent_requests" stackId="requests" stroke={CHART_COLOR_ORDER[0]} fill={CHART_COLOR_ORDER[0]} fillOpacity={0.35} />
              <Area name={t('overview.workflowRuns')} type="monotone" dataKey="workflow_runs" stackId="requests" stroke={CHART_COLOR_ORDER[1]} fill={CHART_COLOR_ORDER[1]} fillOpacity={0.35} />
            </AreaChart>
          </ResponsiveContainer>
        </ObservabilityChartCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ConsoleMetric label={t('metrics.totalRequests')} value={formatNumber(overview.totals.total_requests)} description={t('metrics.agentWorkflowBreakdown', { agents: overview.totals.agent_requests, workflows: overview.totals.workflow_runs })} />
        <ConsoleMetric label={t('metrics.totalTokens')} value={formatCompactNumber(overview.totals.total_tokens)} description={t('metrics.selectedRange')} />
        <ConsoleMetric label={t('metrics.peakHourly')} value={formatNumber(overview.throughput.peak_hourly_requests)} description={t('overview.requestsBySource')} />
        <ConsoleMetric label={t('overview.trafficMix')} value={formatPercent(percentOf(overview.totals.agent_requests, trafficTotal))} description={t('overview.agentRequests')} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('overview.trafficMix')}</CardTitle>
          <CardDescription>{t('overview.requestsBySource')}</CardDescription>
        </CardHeader>
        <CardContent>
          <DistributionBarList items={distribution} total={trafficTotal} />
        </CardContent>
      </Card>
    </div>
  )
}

export function HealthPanel({ health, trend, slowQueries, workers }: HealthPanelProps) {
  const t = useTranslations('dashboard.observability')
  if (!health) return <ObservabilityEmpty />

  const worker = workers ?? health.workers
  const dependencies = [
    { label: 'CPU', icon: Cpu, data: health.cpu, valueKey: 'usage_percent', suffix: '%' },
    { label: t('health.memory'), icon: Server, data: health.memory, valueKey: 'usage_percent', suffix: '%' },
    { label: t('health.disk'), icon: HardDrive, data: health.disk, valueKey: 'usage_percent', suffix: '%' },
    { label: t('health.database'), icon: Database, data: health.database, valueKey: 'active_connections', suffix: '' },
    { label: 'Redis', icon: Database, data: health.redis, valueKey: 'ops_per_sec', suffix: ' ops/s' },
    { label: 'Worker', icon: Workflow, data: workerHealthData(worker), valueKey: 'worker_count', suffix: '' },
  ]

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-12">
        <ObservabilityChartCard className="lg:col-span-8" title={t('health.resourceUsage')} description={t('charts.systemTrendDesc')} empty={!trend?.items.length}>
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={trend?.items ?? []}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
              <XAxis dataKey="generated_at" tickFormatter={formatBucket} minTickGap={24} />
              <YAxis />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={formatBucket} />
              <Legend />
              <Line name="CPU" type="monotone" dataKey="cpu_percent" stroke={CHART_COLOR_ORDER[0]} strokeWidth={2} dot={false} />
              <Line name={t('health.memory')} type="monotone" dataKey="memory_percent" stroke={CHART_COLOR_ORDER[1]} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ObservabilityChartCard>

        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>{t('health.dependencies')}</CardTitle>
            <CardDescription>{t('states.autoRefreshHint')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {dependencies.map((item) => (
              <ResourceRow key={item.label} {...item} />
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-5">
          <CardHeader>
            <CardTitle>{t('health.workerQueues')}</CardTitle>
            <CardDescription>{t('health.workerQueuesDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {worker.error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>{t('health.workerError')}</AlertTitle>
                <AlertDescription>{worker.error}</AlertDescription>
              </Alert>
            )}
            <div className="grid grid-cols-3 gap-3">
              <ConsoleMetric label={t('health.activeTasks')} value={formatNumber(worker.active_tasks)} />
              <ConsoleMetric label={t('health.reservedTasks')} value={formatNumber(worker.reserved_tasks)} />
              <ConsoleMetric label={t('health.scheduledTasks')} value={formatNumber(worker.scheduled_tasks)} />
            </div>
            <DistributionBarList items={(worker.queues ?? []).map((queue) => ({ label: queue.queue, value: queue.pending, tone: queue.pending > 0 ? 'warning' : 'neutral' }))} total={Math.max(...(worker.queues ?? []).map((queue) => queue.pending), 1)} valueLabel={t('health.pending')} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-7">
          <CardHeader>
            <CardTitle>{t('health.slowQueries')}</CardTitle>
            <CardDescription>{t('health.slowQueriesDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <SlowQueriesContent slowQueries={slowQueries} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function AgentsPanel({ rows, timeRange }: { rows: AgentPerformanceRow[]; timeRange: TimeRange }) {
  const t = useTranslations('dashboard.observability')
  const [detail, setDetail] = React.useState<AgentDetailResponse | null>(null)
  const [isOpen, setIsOpen] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)

  const openDetail = async (row: AgentPerformanceRow) => {
    setIsOpen(true)
    setIsLoading(true)
    try {
      setDetail(await observabilityApi.getAgentDetail(row.agent_id, timeRange))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      <EntityTable
        empty={rows.length === 0}
        headers={[t('tables.name'), t('tables.team'), t('tables.requests'), t('tables.successRate'), t('tables.timeoutRate'), t('tables.ttftP95'), 'P95', 'P99', t('tables.tokens'), t('tables.avgTokens')]}
        rows={rows.map((row) => ({
          key: row.agent_id,
          onClick: () => openDetail(row),
          cells: [
            <EntityName key="name" name={row.agent_name || row.agent_id} id={row.agent_id} />,
            row.team_name || '-',
            formatNumber(row.request_count),
            <StatusValue key="success" value={formatPercent(row.success_rate)} tone={row.success_rate < 95 ? 'danger' : row.success_rate < 99 ? 'warning' : 'success'} />,
            <StatusValue key="timeout" value={formatPercent(row.timeout_rate)} tone={row.timeout_rate >= 5 ? 'danger' : row.timeout_rate >= 1 ? 'warning' : 'neutral'} />,
            formatDuration(row.ttft_p95_ms),
            formatDuration(row.p95_ms),
            formatDuration(row.p99_ms ?? null),
            formatCompactNumber(row.total_tokens),
            formatNumber(row.avg_tokens),
          ],
        }))}
      />
      <AgentDetailSheet open={isOpen} onOpenChange={setIsOpen} detail={detail} isLoading={isLoading} />
    </>
  )
}

export function WorkflowsPanel({ rows, timeRange }: { rows: WorkflowPerformanceRow[]; timeRange: TimeRange }) {
  const t = useTranslations('dashboard.observability')
  const [detail, setDetail] = React.useState<WorkflowDetailResponse | null>(null)
  const [isOpen, setIsOpen] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)

  const openDetail = async (row: WorkflowPerformanceRow) => {
    setIsOpen(true)
    setIsLoading(true)
    try {
      setDetail(await observabilityApi.getWorkflowDetail(row.workflow_id, timeRange))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      <EntityTable
        empty={rows.length === 0}
        headers={[t('tables.name'), t('tables.team'), t('tables.runs'), t('tables.successRate'), t('tables.timeoutRate'), t('tables.failedNodes'), t('details.avgNodes'), 'P95', t('tables.tokens')]}
        rows={rows.map((row) => ({
          key: row.workflow_id,
          onClick: () => openDetail(row),
          cells: [
            <EntityName key="name" name={row.workflow_name || row.workflow_id} id={row.workflow_id} />,
            row.team_name || '-',
            formatNumber(row.run_count),
            <StatusValue key="success" value={formatPercent(row.success_rate)} tone={row.success_rate < 95 ? 'danger' : row.success_rate < 99 ? 'warning' : 'success'} />,
            <StatusValue key="timeout" value={formatPercent(row.timeout_rate)} tone={row.timeout_rate >= 5 ? 'danger' : row.timeout_rate >= 1 ? 'warning' : 'neutral'} />,
            formatNumber(row.failed_nodes),
            row.avg_nodes == null ? '-' : formatNumber(row.avg_nodes),
            formatDuration(row.p95_ms),
            formatCompactNumber(row.total_tokens),
          ],
        }))}
      />
      <WorkflowDetailSheet open={isOpen} onOpenChange={setIsOpen} detail={detail} isLoading={isLoading} />
    </>
  )
}

export function TimeoutsPanel({ data }: { data: TimeoutResponse | null }) {
  const t = useTranslations('dashboard.observability')
  if (!data) return <ObservabilityEmpty />

  const distribution = Object.entries(data.distribution ?? {}).map(([label, value]) => ({
    label: timeoutTypeLabel(label, t),
    value,
    tone: label === 'workflow' ? 'warning' as Tone : 'info' as Tone,
  }))
  const topType = [...distribution].sort((a, b) => b.value - a.value)[0]

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <ConsoleMetric label={t('timeouts.totalEvents')} value={formatNumber(data.total)} />
        <ConsoleMetric label={t('timeouts.mostFrequentType')} value={topType?.label ?? '-'} />
        <ConsoleMetric label={t('timeouts.typeAvailable')} value={data.agent_timeout_type_available ? t('status.success') : t('status.unknown')} tone={data.agent_timeout_type_available ? 'success' : 'warning'} />
      </div>
      {!data.agent_timeout_type_available && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('timeouts.limitedTitle')}</AlertTitle>
          <AlertDescription>{data.note || t('timeouts.limitedDescription')}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>{t('timeouts.distribution')}</CardTitle>
            <CardDescription>{t('timeouts.distributionDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <DistributionBarList items={distribution} total={data.total || 1} />
          </CardContent>
        </Card>
        <Card className="lg:col-span-8">
          <CardHeader>
            <CardTitle>{t('timeouts.recentEvents')}</CardTitle>
            <CardDescription>{t('timeouts.note')}</CardDescription>
          </CardHeader>
          <CardContent>
            <TimeoutEventsTable rows={data.items} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function ThroughputPanel({ throughput, tokens }: { throughput: ThroughputResponse | null; tokens: TokenResponse | null }) {
  const t = useTranslations('dashboard.observability')
  if (!throughput) return <ObservabilityEmpty />

  const totalTokens = tokens?.total_tokens ?? 0
  const sourceItems = (tokens?.by_source ?? []).map((item) => ({ label: sourceLabel(item.source, t), value: item.tokens, tone: item.source === 'workflow' ? 'success' as Tone : 'info' as Tone }))
  const modelItems = (tokens?.by_model ?? []).slice(0, 8).map((item) => ({ label: item.model, value: item.tokens, tone: 'neutral' as Tone }))

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <ConsoleMetric label={t('metrics.currentQps')} value={String(throughput.current.qps)} description="QPS" />
        <ConsoleMetric label={t('metrics.currentTps')} value={String(throughput.current.tps)} description="TPS" />
        <ConsoleMetric label={t('throughput.runningWorkflows')} value={formatNumber(throughput.current.running_workflows)} tone={throughput.current.running_workflows > 0 ? 'info' : 'neutral'} />
        <ConsoleMetric label={t('metrics.totalTokens')} value={formatCompactNumber(totalTokens)} description={t('metrics.selectedRange')} />
      </div>
      <div className="grid gap-6 lg:grid-cols-12">
        <ObservabilityChartCard className="lg:col-span-8" title={t('throughput.requestVolume')} description={t('charts.throughputTrendDesc')} empty={!throughput.buckets.length}>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={throughput.buckets}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
              <XAxis dataKey="bucket" tickFormatter={formatBucket} minTickGap={24} />
              <YAxis />
              <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={formatBucket} />
              <Legend />
              <Bar name={t('overview.agentRequests')} dataKey="agent_requests" stackId="requests" fill={CHART_COLOR_ORDER[0]} radius={[4, 4, 0, 0]} />
              <Bar name={t('overview.workflowRuns')} dataKey="workflow_runs" stackId="requests" fill={CHART_COLOR_ORDER[1]} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ObservabilityChartCard>
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>{t('throughput.tokenBySource')}</CardTitle>
            <CardDescription>{t('throughput.tokens')}</CardDescription>
          </CardHeader>
          <CardContent>
            {sourceItems.length ? <DistributionBarList items={sourceItems} total={totalTokens || 1} /> : <ObservabilityEmpty description={t('throughput.noTokenData')} />}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('throughput.tokenByModel')}</CardTitle>
          <CardDescription>{t('throughput.share')}</CardDescription>
        </CardHeader>
        <CardContent>
          {modelItems.length ? <DistributionBarList items={modelItems} total={totalTokens || 1} showPercent /> : <ObservabilityEmpty description={t('throughput.noTokenData')} />}
        </CardContent>
      </Card>
    </div>
  )
}

function AgentDetailSheet({ open, onOpenChange, detail, isLoading }: { open: boolean; onOpenChange: (open: boolean) => void; detail: AgentDetailResponse | null; isLoading: boolean }) {
  const t = useTranslations('dashboard.observability')
  const agent = detail?.agent
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="p-0 sm:max-w-2xl">
        <SheetHeader className="border-b px-6 py-4">
          <SheetTitle>{t('details.agentTitle')}</SheetTitle>
          <SheetDescription>{agent ? agent.agent_name || agent.agent_id : t('details.noAgent')}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
          {isLoading ? <DetailSkeleton /> : agent ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <ConsoleMetric label={t('tables.requests')} value={formatNumber(agent.request_count)} />
                <ConsoleMetric label={t('tables.successRate')} value={formatPercent(agent.success_rate)} />
                <ConsoleMetric label={t('tables.timeoutRate')} value={formatPercent(agent.timeout_rate)} />
                <ConsoleMetric label={t('tables.ttftP95')} value={formatDuration(agent.ttft_p95_ms)} />
                <ConsoleMetric label={t('details.avgTokens')} value={formatNumber(agent.avg_tokens)} />
              </div>
              <PercentileStrip values={agent} />
              <DetailTrendChart data={detail?.trend ?? []} countKey="request_count" />
            </>
          ) : <ObservabilityEmpty />}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function WorkflowDetailSheet({ open, onOpenChange, detail, isLoading }: { open: boolean; onOpenChange: (open: boolean) => void; detail: WorkflowDetailResponse | null; isLoading: boolean }) {
  const t = useTranslations('dashboard.observability')
  const workflow = detail?.workflow
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="p-0 sm:max-w-3xl">
        <SheetHeader className="border-b px-6 py-4">
          <SheetTitle>{t('details.workflowTitle')}</SheetTitle>
          <SheetDescription>{workflow ? workflow.workflow_name || workflow.workflow_id : t('details.noWorkflow')}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-4">
          {isLoading ? <DetailSkeleton /> : workflow ? (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <ConsoleMetric label={t('tables.runs')} value={formatNumber(workflow.run_count)} />
                <ConsoleMetric label={t('tables.successRate')} value={formatPercent(workflow.success_rate)} />
                <ConsoleMetric label={t('tables.timeoutRate')} value={formatPercent(workflow.timeout_rate)} />
                <ConsoleMetric label={t('details.avgNodes')} value={workflow.avg_nodes == null ? '-' : formatNumber(workflow.avg_nodes)} />
              </div>
              <DetailTrendChart data={detail?.trend ?? []} countKey="run_count" />
              <NodeBreakdownTable rows={detail?.nodes ?? []} />
            </>
          ) : <ObservabilityEmpty />}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function DetailTrendChart({ data, countKey }: { data: ObservabilityTrendPoint[]; countKey: 'request_count' | 'run_count' }) {
  const t = useTranslations('dashboard.observability')
  return (
    <ObservabilityChartCard title={t('details.performanceTrend')} description={t('details.percentiles')} empty={!data.length}>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
          <XAxis dataKey="bucket" tickFormatter={formatBucket} minTickGap={24} />
          <YAxis />
          <Tooltip contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={formatBucket} />
          <Legend />
          <Line name="P95" type="monotone" dataKey="p95_ms" stroke={CHART_COLOR_ORDER[0]} dot={false} />
          <Line name={t('common.count')} type="monotone" dataKey={countKey} stroke={CHART_COLOR_ORDER[1]} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ObservabilityChartCard>
  )
}

function NodeBreakdownTable({ rows }: { rows: WorkflowDetailResponse['nodes'] }) {
  const t = useTranslations('dashboard.observability')
  if (!rows.length) return <ObservabilityEmpty />
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('details.nodeBreakdown')}</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('details.nodeType')}</TableHead>
              <TableHead className="text-right">{t('details.executionCount')}</TableHead>
              <TableHead className="text-right">{t('details.failedCount')}</TableHead>
              <TableHead className="text-right">{t('details.avgDuration')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.node_type}>
                <TableCell className="font-medium">{row.node_type}</TableCell>
                <TableCell className="text-right">{formatNumber(row.execution_count)}</TableCell>
                <TableCell className="text-right">{formatNumber(row.failed_count)}</TableCell>
                <TableCell className="text-right">{formatDuration(row.avg_duration_ms)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function SlowQueriesContent({ slowQueries }: { slowQueries: SlowQueriesResponse | null }) {
  const t = useTranslations('dashboard.observability')
  if (!slowQueries) return <ObservabilityEmpty />
  if (!slowQueries.available) {
    return (
      <Alert variant="warning">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>{t('health.slowQueriesUnavailable')}</AlertTitle>
        <AlertDescription>{t('health.slowQueriesSetupHint')}</AlertDescription>
      </Alert>
    )
  }
  if (!slowQueries.items.length) return <ObservabilityEmpty description={t('health.noSlowQueries')} />
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('health.query')}</TableHead>
          <TableHead className="text-right">{t('health.calls')}</TableHead>
          <TableHead className="text-right">{t('health.meanTime')}</TableHead>
          <TableHead className="text-right">{t('health.totalTime')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {slowQueries.items.map((row, index) => (
          <TableRow key={index}>
            <TableCell className="max-w-[420px] truncate font-mono text-xs">{readString(row, ['query', 'statement'])}</TableCell>
            <TableCell className="text-right">{formatNumber(readNumber(row, ['calls']))}</TableCell>
            <TableCell className="text-right">{formatDuration(readNumber(row, ['avg_ms', 'mean_exec_time', 'mean_time', 'duration_ms']))}</TableCell>
            <TableCell className="text-right">{formatDuration(readNumber(row, ['total_ms', 'total_exec_time', 'total_time']))}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function TimeoutEventsTable({ rows }: { rows: TimeoutEvent[] }) {
  const t = useTranslations('dashboard.observability')
  if (!rows.length) return <ObservabilityEmpty />
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('tables.source')}</TableHead>
          <TableHead>{t('tables.name')}</TableHead>
          <TableHead>{t('tables.type')}</TableHead>
          <TableHead>{t('tables.status')}</TableHead>
          <TableHead>{t('tables.model')}</TableHead>
          <TableHead className="text-right">{t('tables.duration')}</TableHead>
          <TableHead className="text-right">{t('tables.time')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={`${row.source}-${row.entity_id}-${row.created_at}-${index}`}>
            <TableCell><StatusPill tone={row.source === 'workflow' ? 'success' : 'info'} label={sourceLabel(row.source, t)} /></TableCell>
            <TableCell className="font-medium">{row.entity_name}</TableCell>
            <TableCell>{timeoutTypeLabel(row.timeout_type, t)}</TableCell>
            <TableCell><StatusPill tone={row.status === 'timeout' || row.status === 'error' ? 'warning' : 'neutral'} label={statusLabel(row.status, t)} /></TableCell>
            <TableCell>{row.model || '-'}</TableCell>
            <TableCell className="text-right">{formatDuration(row.duration_ms)}</TableCell>
            <TableCell className="text-right">{formatBucket(row.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function EntityTable({ headers, rows, empty }: { headers: string[]; rows: Array<{ key: string; cells: React.ReactNode[]; onClick?: () => void }>; empty: boolean }) {
  if (empty) return <ObservabilityEmpty />
  return (
    <Card>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              {headers.map((header, index) => (
                <TableHead key={header} className={index > 1 ? 'text-right' : undefined}>{header}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key} role="button" tabIndex={0} className="cursor-pointer" onClick={row.onClick} onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  row.onClick?.()
                }
              }}>
                {row.cells.map((cell, index) => (
                  <TableCell key={index} className={index > 1 ? 'text-right' : undefined}>{cell}</TableCell>
                ))}
                <TableCell className="w-8 text-right"><ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function EntityName({ name, id }: { name: string; id: string }) {
  return (
    <div className="min-w-[180px]">
      <div className="font-medium">{name}</div>
      <div className="text-xs text-muted-foreground">{id.slice(0, 8)}</div>
    </div>
  )
}

function ConsoleMetric({ label, value, description, tone = 'neutral' }: { label: string; value: string; description?: string; tone?: Tone }) {
  return (
    <div className="rounded-lg border bg-card/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        {tone !== 'neutral' && <span className={`h-2 w-2 rounded-full ${toneDotClass(tone)}`} />}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {description && <div className="mt-1 truncate text-xs text-muted-foreground">{description}</div>}
    </div>
  )
}

function ObservabilityChartCard({ title, description, empty, className, children }: { title: string; description?: string; empty?: boolean; className?: string; children: React.ReactNode }) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        {empty ? <ObservabilityEmpty /> : children}
      </CardContent>
    </Card>
  )
}

function PercentileStrip({ values }: { values: { p50_ms: number | null; p90_ms: number | null; p95_ms: number | null; p99_ms?: number | null } }) {
  const items = [
    ['P50', values.p50_ms],
    ['P90', values.p90_ms],
    ['P95', values.p95_ms],
    ['P99', values.p99_ms ?? null],
  ] as const
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-md bg-muted/60 px-3 py-2">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="font-medium">{formatDuration(value)}</div>
        </div>
      ))}
    </div>
  )
}

function ResourceRow({ label, icon: Icon, data, valueKey, suffix }: { label: string; icon: React.ElementType; data: Record<string, unknown>; valueKey: string; suffix: string }) {
  const t = useTranslations('dashboard.observability')
  const status = String(data.status ?? 'unknown')
  const value = readNumber(data, [valueKey])
  const progress = suffix === '%' ? Math.min(Math.max(value, 0), 100) : null
  return (
    <div className="rounded-lg border p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-muted p-2"><Icon className="h-4 w-4" /></div>
          <div>
            <div className="font-medium">{label}</div>
            <div className="text-xs text-muted-foreground">{Number.isFinite(value) ? `${value}${suffix}` : '-'}</div>
          </div>
        </div>
        <StatusPill tone={toneForStatus(status)} label={statusLabel(status, t)} />
      </div>
      {progress !== null && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted"><div className={`h-full ${toneBarClass(toneForStatus(status))}`} style={{ width: `${progress}%` }} /></div>}
    </div>
  )
}

function DistributionBarList({ items, total, valueLabel, showPercent }: { items: Array<{ label: string; value: number; tone?: Tone }>; total: number; valueLabel?: string; showPercent?: boolean }) {
  if (!items.length) return <ObservabilityEmpty />
  return (
    <div className="space-y-4">
      {items.map((item) => {
        const percent = percentOf(item.value, total)
        const tone = item.tone ?? 'neutral'
        return (
          <div key={item.label} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate font-medium">{item.label}</span>
              <span className="text-muted-foreground">{formatCompactNumber(item.value)}{valueLabel ? ` ${valueLabel}` : ''}{showPercent ? ` · ${formatPercent(percent)}` : ''}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div className={`h-full ${toneBarClass(tone)}`} style={{ width: `${Math.max(percent, item.value > 0 ? 2 : 0)}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StatusPill({ tone, label }: { tone: Tone; label: string }) {
  return <Badge variant="outline" className={TONE_STYLES[tone]}>{label}</Badge>
}

function StatusValue({ value, tone }: { value: string; tone: Tone }) {
  return <span className={toneTextClass(tone)}>{value}</span>
}

function ObservabilityEmpty({ description }: { description?: string }) {
  const t = useTranslations('dashboard.observability')
  return (
    <div className="flex min-h-36 flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center">
      <Info className="mb-2 h-5 w-5 text-muted-foreground" />
      <div className="font-medium">{t('states.emptyTitle')}</div>
      <div className="mt-1 text-sm text-muted-foreground">{description ?? t('states.emptyDescription')}</div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-20 rounded-xl" />
      <Skeleton className="h-40 rounded-xl" />
      <Skeleton className="h-52 rounded-xl" />
    </div>
  )
}

function workerHealthData(worker: WorkerResponse): Record<string, unknown> {
  return {
    status: worker.status,
    worker_count: worker.worker_count,
    active_tasks: worker.active_tasks,
    reserved_tasks: worker.reserved_tasks,
    scheduled_tasks: worker.scheduled_tasks,
    error: worker.error,
  }
}

function getRiskLevel(timeoutRate: number, successRate: number, p95: number | null, ttftP95: number | null): { key: 'healthy' | 'warning' | 'critical'; summaryKey: 'healthSummaryHealthy' | 'healthSummaryWarning' | 'healthSummaryCritical'; tone: Tone } {
  if (timeoutRate >= 5 || successRate < 95 || (ttftP95 != null ? ttftP95 >= 10000 : (p95 ?? 0) >= 30000)) {
    return { key: 'critical', summaryKey: 'healthSummaryCritical', tone: 'danger' }
  }
  if (timeoutRate >= 1 || successRate < 99 || (ttftP95 != null ? ttftP95 >= 3000 : (p95 ?? 0) >= 10000)) {
    return { key: 'warning', summaryKey: 'healthSummaryWarning', tone: 'warning' }
  }
  return { key: 'healthy', summaryKey: 'healthSummaryHealthy', tone: 'success' }
}

function toneForStatus(status: string): Tone {
  if (status === 'danger' || status === 'unhealthy' || status === 'failed' || status === 'error') return 'danger'
  if (status === 'warning' || status === 'unknown' || status === 'timeout') return 'warning'
  if (status === 'healthy' || status === 'success') return 'success'
  if (status === 'running') return 'info'
  return 'neutral'
}

function statusLabel(status: string | null | undefined, t: ObservabilityTranslator) {
  const normalized = status || 'unknown'
  const keys = new Set(['healthy', 'warning', 'danger', 'unhealthy', 'unknown', 'success', 'failed', 'running', 'pending', 'cancelled', 'timeout', 'error'])
  return keys.has(normalized) ? t(`status.${normalized}`) : normalized
}

function sourceLabel(source: string | null | undefined, t: ObservabilityTranslator) {
  if (source === 'agent' || source === 'workflow' || source === 'system') return t(`sources.${source}`)
  return t('sources.unknown')
}

function timeoutTypeLabel(type: string | null | undefined, t: ObservabilityTranslator) {
  const normalized = type || 'unknown'
  const keys = new Set(['unknown', 'idle', 'global', 'workflow', 'agent'])
  return keys.has(normalized) ? t(`timeoutTypes.${normalized}`) : normalized
}

function readNumber(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return 0
}

function readString(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return '-'
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value)
}

function formatCompactNumber(value: number) {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`
}

function formatDuration(value: number | null | undefined) {
  if (value == null) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

function formatBucket(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function percentOf(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 1000) / 10
}

function toneDotClass(tone: Tone) {
  return {
    neutral: 'bg-muted-foreground',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-destructive',
    info: 'bg-sky-500',
  }[tone]
}

function toneBarClass(tone: Tone) {
  return {
    neutral: 'bg-muted-foreground/50',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-destructive',
    info: 'bg-sky-500',
  }[tone]
}

function toneTextClass(tone: Tone) {
  return {
    neutral: 'text-foreground',
    success: 'text-emerald-700 dark:text-emerald-300',
    warning: 'text-amber-700 dark:text-amber-300',
    danger: 'text-destructive',
    info: 'text-sky-700 dark:text-sky-300',
  }[tone]
}
