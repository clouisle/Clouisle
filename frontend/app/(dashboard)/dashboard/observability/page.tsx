'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Activity, AlertTriangle, Bell, Boxes, CalendarIcon, Check, ChevronDown, ChevronRight, Clock3, Database, ExternalLink, Gauge, RefreshCw, Server, Workflow } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { endOfDay, format, startOfDay } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'
import type { DateRange } from 'react-day-picker'

import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CHART_AXIS_COLOR, CHART_COLOR_ORDER, CHART_GRID_COLOR, CHART_HOVER_CURSOR, CHART_TOOLTIP_STYLE } from '@/lib/chart-theme'
import { formatTime } from '@/lib/utils'
import { usePermissions } from '@/hooks/use-permissions'
import { observabilityApi, type AlertEvent, type AlertRule, type DependenciesResponse, type InfrastructureResponse, type ObservabilityMeta, type ObservabilityPeriod, type QueueRow, type QueuesResponse, type RunDetailResponse, type RunSummary, type SummaryResponse } from '@/lib/api/admin/observability'

const VIEWS = ['overview', 'runs', 'dependencies', 'queues', 'infrastructure', 'alerts'] as const
type View = typeof VIEWS[number]
const PRESETS = ['15m', '1h', '24h'] as const

function customBounds(start: string | null, end: string | null) {
  const aware = /^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/i
  if (!start || !end || !aware.test(start) || !aware.test(end)) return null
  for (const value of [start, end]) {
    const calendarDate = value.slice(0, 10)
    if (new Date(`${calendarDate}T00:00:00Z`).toISOString().slice(0, 10) !== calendarDate) return null
  }
  const from = new Date(start), to = new Date(end)
  if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime())) return null
  const normalize = (value: string, date: Date) => {
    const fraction = value.match(/\.(\d+)/)?.[1]
    return fraction && fraction.length > 3 ? date.toISOString().replace(/\.\d{3}Z$/, `.${fraction}Z`) : date.toISOString()
  }
  const start_time = normalize(start, from), end_time = normalize(end, to)
  const precision = Math.max(start_time.length, end_time.length)
  const ordered = from < to || (from.getTime() === to.getTime() && start_time.slice(0, -1).padEnd(precision, '0') < end_time.slice(0, -1).padEnd(precision, '0'))
  return ordered ? { start_time, end_time } : null
}
type PageData = SummaryResponse | { runs: RunSummary[]; next_cursor: string | null; meta: ObservabilityMeta } | DependenciesResponse | QueuesResponse | InfrastructureResponse | { alerts: AlertEvent[]; next_cursor: string | null; meta: ObservabilityMeta; rules: AlertRule[] }

export default function ObservabilityPage() {
  const t = useTranslations('dashboard.observability')
  const { hasPermission } = usePermissions()
  const canManageObservability = hasPermission('admin:observability:manage')
  const locale = useLocale()
  const calendarLocale = locale.startsWith('zh') ? zhCN : enUS
  const router = useRouter()
  const pathname = usePathname()
  const search = useSearchParams()
  const searchString = search.toString()
  const view = (VIEWS as readonly string[]).includes(search.get('tab') ?? '') ? search.get('tab') as View : 'overview'
  const period = [...PRESETS, '7d', 'custom'].includes(search.get('period') ?? '') ? search.get('period') as ObservabilityPeriod : '1h'
  const bounds = period === 'custom' ? customBounds(search.get('start_time'), search.get('end_time')) : null
  const startTime = bounds?.start_time
  const endTime = bounds?.end_time
  const invalidRange = period === 'custom' && !bounds
  const [rangeOpen, setRangeOpen] = React.useState(false)
  const [rangeDraft, setRangeDraft] = React.useState<DateRange | undefined>()
  const validDraft = Boolean(rangeDraft?.from && rangeDraft.to && Number.isFinite(rangeDraft.from.getTime()) && Number.isFinite(rangeDraft.to.getTime()) && startOfDay(rangeDraft.from) <= startOfDay(rangeDraft.to))
  const teamId = search.get('team_id') ?? ''
  const [teamDraft, setTeamDraft] = React.useState(teamId)
  const [data, setData] = React.useState<PageData | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState(false)
  const [lastUpdated, setLastUpdated] = React.useState<Date | null>(null)
  const [runFilter, setRunFilter] = React.useState({ source: 'all', status: '', error_category: '', run_id: '' })
  const [cursor, setCursor] = React.useState<string | undefined>()
  const [runPages, setRunPages] = React.useState<Array<{ items: RunSummary[]; next_cursor: string | null }>>([])
  const [alertStatus, setAlertStatus] = React.useState<'active' | 'resolved' | 'all'>('active')
  const [alertPages, setAlertPages] = React.useState<Array<{ items: AlertEvent[]; next_cursor: string | null }>>([])
  const [detail, setDetailState] = React.useState<RunDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = React.useState(false)
  const [detailError, setDetailError] = React.useState(false)
  const [silenceDuration, setSilenceDuration] = React.useState(3600)
  const [mutationBusy, setMutationBusy] = React.useState<string | null>(null)
  const [expandedSpans, setExpandedSpans] = React.useState<Set<string>>(new Set())
  const requestId = React.useRef(0)
  const busy = React.useRef(false)
  const pendingLoad = React.useRef(false)
  const cursorRef = React.useRef<string | undefined>(undefined)
  const loadRef = React.useRef<((manual?: boolean) => Promise<void>) | null>(null)
  const detailRequestId = React.useRef(0)
  const setDetail = React.useCallback((next: RunDetailResponse | null) => {
    if (next === null) {
      detailRequestId.current++
      setDetailLoading(false)
      setDetailError(false)
    }
    setDetailState(next)
  }, [])

  const updateQuery = React.useCallback((updates: Record<string, string | null>) => {
    const params = new URLSearchParams(searchString)
    Object.entries(updates).forEach(([key, value]) => value ? params.set(key, value) : params.delete(key))
    router.replace(`${pathname}?${params.toString()}`, { scroll: false })
  }, [pathname, router, searchString])
  React.useEffect(() => setTeamDraft(teamId), [teamId])

  const openRange = () => {
    const meta = data && 'meta' in data ? data.meta : null
    const end = bounds ? new Date(bounds.end_time) : meta ? new Date(meta.window_end) : new Date()
    const duration = period === '15m' ? 900000 : period === '24h' ? 86400000 : period === '7d' ? 604800000 : 3600000
    const start = bounds ? new Date(bounds.start_time) : meta ? new Date(meta.window_start) : new Date(end.getTime() - duration)
    setRangeDraft(invalidRange ? undefined : { from: start, to: end })
    setRangeOpen(true)
  }
  const applyRange = () => {
    if (!validDraft || !rangeDraft?.from || !rangeDraft.to) return
    updateQuery({ period: 'custom', start_time: startOfDay(rangeDraft.from).toISOString(), end_time: endOfDay(rangeDraft.to).toISOString().replace('.999Z', '.999999Z') })
    setRangeOpen(false)
  }

  const load = React.useCallback(async (manual = false) => {
    if (invalidRange && (view === 'overview' || view === 'runs' || view === 'dependencies')) { setLoading(false); return }
    if (busy.current) { pendingLoad.current = true; return }
    if (document.visibilityState === 'hidden' && !manual) return
    busy.current = true
    const id = ++requestId.current
    setLoading(true)
    setError(false)
    try {
      let result: PageData
      if (view === 'overview') result = await observabilityApi.getSummary({ period, ...(startTime && endTime ? { start_time: startTime, end_time: endTime } : {}), team_id: teamId || undefined })
      else if (view === 'runs') {
        const response = await observabilityApi.getRuns({ period, ...(startTime && endTime ? { start_time: startTime, end_time: endTime } : {}), team_id: teamId || undefined, source: runFilter.source as 'all' | 'agent' | 'workflow', status: runFilter.status || undefined, error_category: runFilter.error_category || undefined, run_id: runFilter.run_id || undefined, cursor: cursorRef.current, limit: 25 })
        result = { runs: response.items, next_cursor: response.next_cursor, meta: response.meta }
      } else if (view === 'dependencies') result = await observabilityApi.getDependencies({ period, ...(startTime && endTime ? { start_time: startTime, end_time: endTime } : {}), team_id: teamId || undefined })
      else if (view === 'queues') result = await observabilityApi.getQueues()
      else if (view === 'infrastructure') result = await observabilityApi.getInfrastructure()
      else {
        const [response, rules] = await Promise.all([observabilityApi.getAlerts({ status: alertStatus, limit: 25, cursor: cursorRef.current }), observabilityApi.getAlertRules()])
        result = { alerts: response.items, next_cursor: response.next_cursor, meta: response.meta, rules }
      }
      if (id !== requestId.current) return
      setData(result)
      if (view === 'runs') setRunPages((pages) => cursorRef.current ? [...pages, { items: (result as Extract<PageData, { runs: RunSummary[] }>).runs, next_cursor: (result as Extract<PageData, { runs: RunSummary[] }>).next_cursor }] : [{ items: (result as Extract<PageData, { runs: RunSummary[] }>).runs, next_cursor: (result as Extract<PageData, { runs: RunSummary[] }>).next_cursor }])
      if (view === 'alerts') setAlertPages((pages) => cursorRef.current ? [...pages, { items: (result as Extract<PageData, { alerts: AlertEvent[] }>).alerts, next_cursor: (result as Extract<PageData, { alerts: AlertEvent[] }>).next_cursor }] : [{ items: (result as Extract<PageData, { alerts: AlertEvent[] }>).alerts, next_cursor: (result as Extract<PageData, { alerts: AlertEvent[] }>).next_cursor }])
      setLastUpdated(new Date())
    } catch {
      if (id === requestId.current) setError(true)
    } finally {
      if (id === requestId.current) setLoading(false)
      busy.current = false
      if (pendingLoad.current) { pendingLoad.current = false; window.setTimeout(() => loadRef.current?.(), 0) }
    }
  }, [alertStatus, period, startTime, endTime, invalidRange, runFilter, teamId, view])

  const refresh = React.useCallback((manual = false) => {
    requestId.current++
    cursorRef.current = undefined
    setCursor(undefined)
    setRunPages([])
    setAlertPages([])
    return load(manual)
  }, [load])

  React.useEffect(() => { loadRef.current = refresh }, [refresh])
  React.useEffect(() => {
    requestId.current++
    cursorRef.current = undefined
    setCursor(undefined)
    setRunPages([])
    setAlertPages([])
    setData(null)
    setLastUpdated(null)
    void load()
  }, [load])

  React.useEffect(() => { if (cursor && cursor === cursorRef.current) void load() }, [cursor, load])

  React.useEffect(() => {
    const requestIdRef = requestId
    const detailRequestIdRef = detailRequestId
    const loadRefRef = loadRef
    const pendingLoadRef = pendingLoad
    const timer = window.setInterval(() => { if (!busy.current && document.visibilityState === 'visible') void refresh() }, 30000)
    const visibility = () => { if (document.visibilityState === 'visible') void refresh() }
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', visibility)
      requestIdRef.current++
      detailRequestIdRef.current++
      pendingLoadRef.current = false
      loadRefRef.current = null
    }
  }, [refresh])

  const openRun = async (run: RunSummary) => {
    setDetail(null); setDetailError(false); setDetailLoading(true)
    const id = ++detailRequestId.current
    try {
      const response = await observabilityApi.getRun(run.source, run.run_id)
      if (id === detailRequestId.current) setDetail(response)
    } catch {
      if (id === detailRequestId.current) setDetailError(true)
    } finally { if (id === detailRequestId.current) setDetailLoading(false) }
  }

  const mutateAlert = async (alert: AlertEvent, action: 'acknowledge' | 'silence') => {
    setMutationBusy(`${alert.id}:${action}`)
    try {
      if (action === 'acknowledge') await observabilityApi.acknowledgeAlert(alert.id)
      else await observabilityApi.silenceAlert(alert.id, silenceDuration)
      await refresh(true)
    } catch { setError(true) } finally { setMutationBusy(null) }
  }

  const saveRule = async (rule: AlertRule, patch: Partial<Pick<AlertRule, 'threshold' | 'enabled' | 'evaluation_window_seconds' | 'recovery_window_seconds'>>) => {
    setMutationBusy(rule.id)
    try {
      await observabilityApi.updateAlertRule(rule.id, { threshold: patch.threshold ?? rule.threshold, enabled: patch.enabled ?? rule.enabled, evaluation_window_seconds: patch.evaluation_window_seconds ?? rule.evaluation_window_seconds, recovery_window_seconds: patch.recovery_window_seconds ?? rule.recovery_window_seconds })
      await refresh(true)
    } catch { setError(true) } finally { setMutationBusy(null) }
  }

  const currentMeta = data && 'meta' in data ? data.meta : null
  const dependencyData = data && 'models' in data ? data : null
  const queueData = data && 'queues' in data ? data : null
  const infrastructureData = data && 'instances' in data ? data : null
  const alertData = data && 'alerts' in data ? data : null

  return <RoutePermissionGuard><div className="flex h-full flex-col"><Header /><main className="flex-1 overflow-auto bg-muted/20 p-4 md:p-6"><div className="mx-auto max-w-[1600px] space-y-5">
    <header className="flex flex-col justify-between gap-4 xl:flex-row xl:items-end">
      <div><h1 className="text-2xl font-semibold tracking-tight">{t('title')}</h1><div className="mt-1 flex max-w-3xl flex-wrap items-baseline gap-x-2 gap-y-1"><p className="text-sm text-muted-foreground">{t('consoleDescription')}</p>{lastUpdated && <span className="inline-flex items-center rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground">{t('states.lastUpdated', { time: formatTime(lastUpdated, locale) })}</span>}</div></div>
      <div className="flex flex-wrap items-end gap-2">
        <form className="flex items-end gap-2" onSubmit={(event) => { event.preventDefault(); updateQuery({ team_id: teamDraft.trim() || null }) }}>
          <div><label className="sr-only" htmlFor="obs-team">{t('filters.team')}</label><Input id="obs-team" value={teamDraft} onChange={(event) => setTeamDraft(event.target.value)} placeholder={t('filters.teamId')} className="w-48"/></div>
          <Button variant="outline" type="submit" disabled={loading || teamDraft.trim() === teamId}>{t('actions.apply')}</Button>
        </form>
        <Field className="w-auto gap-1.5">
          <FieldLabel htmlFor="obs-range" className="sr-only">{t('filters.period')}</FieldLabel>
          <Popover open={rangeOpen} onOpenChange={(open) => { if (open) openRange(); else setRangeOpen(false) }}>
            <PopoverTrigger render={<Button id="obs-range" variant="outline" className="w-auto justify-start font-normal" aria-invalid={invalidRange} />}>
              <CalendarIcon className="mr-2 h-4 w-4" />
              {bounds ? `${format(new Date(bounds.start_time), 'PPP', { locale: calendarLocale })} – ${format(new Date(bounds.end_time), 'PPP', { locale: calendarLocale })}` : period === 'custom' ? t('customRange.pickDate') : t(`periods.${period}`)}
            </PopoverTrigger>
            <PopoverContent className="w-auto max-w-[calc(100vw-2rem)] overflow-x-auto p-0" align="end" aria-describedby="obs-range-description">
              <p id="obs-range-description" className="px-4 pt-4 text-sm text-muted-foreground">{t('customRange.description')}</p>
              <Calendar mode="range" selected={rangeDraft} onSelect={setRangeDraft} defaultMonth={rangeDraft?.from} numberOfMonths={2} locale={calendarLocale} />
              {rangeDraft?.from && !validDraft && <p role="alert" className="px-4 text-sm text-destructive">{t('customRange.invalid')}</p>}
              <div className="flex justify-end gap-2 px-4 pb-4">
                <Button type="button" variant="outline" onClick={() => setRangeOpen(false)}>{t('customRange.cancel')}</Button>
                <Button type="button" onClick={applyRange} disabled={!validDraft}>{t('actions.apply')}</Button>
              </div>
              <div className="space-y-2 border-t p-4">
                <p className="text-xs font-medium text-muted-foreground">{t('customRange.presets')}</p>
                <div className="flex flex-wrap gap-2">{PRESETS.map((value) => <Button key={value} type="button" variant={period === value ? 'secondary' : 'outline'} size="sm" onClick={() => { updateQuery({ period: value, start_time: null, end_time: null }); setRangeOpen(false) }}>{t(`periods.${value}`)}</Button>)}</div>
              </div>
            </PopoverContent>
          </Popover>
          {invalidRange && <p role="alert" className="text-sm text-destructive">{t('customRange.invalid')}</p>}
        </Field>
        <Button variant="outline" onClick={() => void refresh(true)} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />{t('actions.refresh')}</Button>
      </div>
    </header>
    <Tabs value={view} onValueChange={(value) => updateQuery({ tab: value === 'overview' ? null : value })}><TabsList className="max-w-full overflow-x-auto">{VIEWS.map((item) => <TabsTrigger key={item} value={item} className="gap-2"><ViewIcon view={item}/>{t(`tabs.${item}`)}</TabsTrigger>)}</TabsList></Tabs>
    {error && <div role="alert" className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"><span>{t('states.errorDescription')}</span><Button variant="outline" size="sm" onClick={() => void refresh(true)}>{t('actions.retry')}</Button></div>}
    {currentMeta && <QualityState meta={currentMeta} />}
    {loading && !data ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><Card className="h-32 animate-pulse bg-muted/40"/><Card className="h-32 animate-pulse bg-muted/40"/><Card className="h-32 animate-pulse bg-muted/40"/><Card className="h-32 animate-pulse bg-muted/40"/></div> : <>
      {view === 'overview' && data && 'agents' in data && <Overview data={data} />}
      {view === 'runs' && <RunDiagnostics items={runPages.flatMap((page) => page.items)} nextCursor={runPages.at(-1)?.next_cursor ?? null} loading={loading} onFilter={(next) => { setRunFilter(next); cursorRef.current = undefined; setCursor(undefined); setRunPages([]) }} filter={runFilter} onNext={(next) => { cursorRef.current = next; setCursor(next) }} onOpen={openRun} />}
      {view === 'dependencies' && dependencyData && <Dependencies data={dependencyData} />}
      {view === 'queues' && queueData && <Queues data={queueData} />}
      {view === 'infrastructure' && infrastructureData && <Infrastructure data={infrastructureData} />}
      {view === 'alerts' && alertData && <Alerts canManage={canManageObservability} data={alertData} status={alertStatus} setStatus={(status) => { setAlertStatus(status); cursorRef.current = undefined; setCursor(undefined); setAlertPages([]) }} pages={alertPages} nextCursor={alertPages.at(-1)?.next_cursor ?? null} onNext={(next) => { cursorRef.current = next; setCursor(next) }} onMutate={mutateAlert} onSaveRule={saveRule} busy={mutationBusy} silenceDuration={silenceDuration} setSilenceDuration={setSilenceDuration} />}
    </>}
  </div></main><RunDetail detail={detail} loading={detailLoading} error={detailError} onClose={() => setDetail(null)} expanded={expandedSpans} setExpanded={setExpandedSpans} /></div></RoutePermissionGuard>
}

function ViewIcon({ view }: { view: View }) {
  const props = { className: 'h-4 w-4' }
  if (view === 'overview') return <Gauge {...props}/>
  if (view === 'runs') return <Activity {...props}/>
  if (view === 'dependencies') return <Boxes {...props}/>
  if (view === 'queues') return <Workflow {...props}/>
  if (view === 'infrastructure') return <Server {...props}/>
  return <Bell {...props}/>
}

function QualityState({ meta }: { meta: ObservabilityMeta }) {
  const t = useTranslations('dashboard.observability')
  const state = meta.state
  const sampleTime = t('quality.lastSample', { time: new Date(meta.sampled_at).toLocaleString() })
  const window = t('quality.window', { start: new Date(meta.window_start).toLocaleString(), end: new Date(meta.window_end).toLocaleString() })
  if (state === 'fresh') return <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="h-2 w-2 rounded-full bg-emerald-500"/>{t('quality.fresh', { samples: meta.sample_count })}<span>·</span>{window}<span>·</span>{sampleTime}</div>
  return <div role="status" className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${state === 'stale' || state === 'unavailable' ? 'border-amber-500/30 bg-amber-500/5' : 'border-border bg-muted/30'}`}><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"/><div><strong>{t(`quality.${state}`, { samples: meta.sample_count })}</strong><p className="mt-0.5 text-muted-foreground">{window} · {sampleTime}</p></div></div>
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) { return <Card><CardContent className="p-4"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>{hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}</CardContent></Card> }
const number = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat().format(value)
const duration = (value: number | null | undefined) => value == null ? '—' : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const percentage = (value: number | null) => value == null ? '—' : `${value.toFixed(1)}%`

function Overview({ data }: { data: SummaryResponse }) {
  const t = useTranslations('dashboard.observability')
  const locale = useLocale()
  return <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label={t('metrics.agentSubmitted')} value={number(data.agents.submitted)} hint={t('metrics.completedFailed', { completed: number(data.agents.completed), failed: number(data.agents.failed) })}/><Metric label={t('metrics.agentSuccessRate')} value={percent(data.agents.success_rate)}/><Metric label={t('metrics.agentP95')} value={duration(data.agents.p95_ms)} hint={t('metrics.firstTokenP95', { value: duration(data.agents.first_token_p95_ms) })}/><Metric label={t('metrics.agentTokens')} value={number(data.agents.tokens)}/><Metric label={t('metrics.workflowSubmitted')} value={number(data.workflows.submitted)} hint={t('metrics.completedFailed', { completed: number(data.workflows.completed), failed: number(data.workflows.failed) })}/><Metric label={t('metrics.workflowSuccessRate')} value={percent(data.workflows.success_rate)}/><Metric label={t('metrics.workflowP95')} value={duration(data.workflows.p95_ms)}/><Metric label={t('metrics.workflowTokens')} value={number(data.workflows.tokens)}/></div>
  <Card><CardHeader><CardTitle>{t('charts.runTrend')}</CardTitle><CardDescription>{t('charts.runTrendDesc')}</CardDescription></CardHeader><CardContent><div className="h-[300px]">{data.trend.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={data.trend} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}><CartesianGrid stroke={CHART_GRID_COLOR} vertical={false}/><XAxis dataKey="bucket" tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }} tickFormatter={(value) => new Date(value).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}/><YAxis tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }}/><Tooltip cursor={CHART_HOVER_CURSOR} contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={(value) => new Date(String(value)).toLocaleString(locale)} formatter={(value, name, item) => [`${value == null ? '—' : number(Number(value))} · ${t('charts.sampleCoverage', { samples: number(item.payload.submitted) })}`, String(name)]}/><Area type="monotone" dataKey="completed" name={t('charts.completed')} stackId="outcomes" stroke={CHART_COLOR_ORDER[0]} fill={CHART_COLOR_ORDER[0]} fillOpacity={0.18}/><Area type="monotone" dataKey="failed" name={t('charts.failed')} stackId="outcomes" stroke={CHART_COLOR_ORDER[1]} fill={CHART_COLOR_ORDER[1]} fillOpacity={0.2}/><Line type="monotone" dataKey="submitted" name={t('charts.submitted')} stroke={CHART_COLOR_ORDER[2]} strokeWidth={2} dot={false} connectNulls={false}/></AreaChart></ResponsiveContainer> : <Empty text={t('states.noSamples')}/>}</div></CardContent></Card>
  <div className="grid gap-4 xl:grid-cols-2"><Card><CardHeader><CardTitle>{t('charts.latencyTrend')}</CardTitle><CardDescription>{t('charts.latencyTrendDesc')}</CardDescription></CardHeader><CardContent><div className="h-[260px]">{data.trend.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={data.trend} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}><CartesianGrid stroke={CHART_GRID_COLOR} vertical={false}/><XAxis dataKey="bucket" tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }} tickFormatter={(value) => new Date(value).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}/><YAxis tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }}/><Tooltip cursor={CHART_HOVER_CURSOR} contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={(value) => new Date(String(value)).toLocaleString(locale)} formatter={(value, name, item) => [`${value == null ? '—' : duration(Number(value))} · ${t('charts.sampleCoverage', { samples: number(item.payload.submitted) })}`, String(name)]}/><Line type="monotone" dataKey="p95_ms" name={t('charts.p95')} stroke={CHART_COLOR_ORDER[0]} strokeWidth={2} dot={false} connectNulls={false}/><Line type="monotone" dataKey="first_token_p95_ms" name={t('charts.firstTokenP95')} stroke={CHART_COLOR_ORDER[2]} strokeWidth={2} dot={false} connectNulls={false}/></LineChart></ResponsiveContainer> : <Empty text={t('states.noSamples')}/>}</div></CardContent></Card><Card><CardHeader><CardTitle>{t('charts.tokenTrend')}</CardTitle><CardDescription>{t('charts.tokenTrendDesc')}</CardDescription></CardHeader><CardContent><div className="h-[260px]">{data.trend.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={data.trend} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}><CartesianGrid stroke={CHART_GRID_COLOR} vertical={false}/><XAxis dataKey="bucket" tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }} tickFormatter={(value) => new Date(value).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}/><YAxis tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }}/><Tooltip cursor={CHART_HOVER_CURSOR} contentStyle={CHART_TOOLTIP_STYLE} labelFormatter={(value) => new Date(String(value)).toLocaleString(locale)} formatter={(value, name, item) => [`${number(Number(value))} · ${t('charts.sampleCoverage', { samples: number(item.payload.submitted) })}`, String(name)]}/><Bar dataKey="tokens" name={t('charts.tokens')} fill={CHART_COLOR_ORDER[1]} radius={[4, 4, 0, 0]}/></BarChart></ResponsiveContainer> : <Empty text={t('states.noSamples')}/>}</div></CardContent></Card></div>
  <div className="grid gap-4 xl:grid-cols-2">{data.issues.map((issue) => <Card key={`${issue.kind}:${issue.title}`} className="border-l-4" style={{ borderLeftColor: issue.severity === 'critical' ? 'hsl(var(--destructive))' : issue.severity === 'warning' ? 'hsl(var(--chart-2))' : 'hsl(var(--primary))' }}><CardContent className="flex items-start justify-between gap-3 p-4"><div><div className="flex items-center gap-2"><Badge variant={issue.severity === 'critical' ? 'destructive' : 'secondary'}>{t(`severity.${issue.severity}`)}</Badge><strong>{issue.title}</strong></div><p className="mt-2 text-sm text-muted-foreground">{issue.detail}</p><p className="mt-2 text-xs text-muted-foreground">{t('issues.affected', { count: issue.affected_count })}</p></div>{issue.href && <a href={issue.href} aria-label={t('actions.openIssue')}><ExternalLink className="h-4 w-4"/></a>}</CardContent></Card>)}</div>{!data.issues.length && <Card><CardContent className="p-4 text-sm text-muted-foreground">{t('issues.none')}</CardContent></Card>}</div>
}

function RunDiagnostics({ items, nextCursor, loading, onFilter, filter, onNext, onOpen }: { items: RunSummary[]; nextCursor: string | null; loading: boolean; filter: { source: string; status: string; error_category: string; run_id: string }; onFilter: (filter: { source: string; status: string; error_category: string; run_id: string }) => void; onNext: (cursor: string) => void; onOpen: (run: RunSummary) => void }) {
  const t = useTranslations('dashboard.observability')
  const [draftFilter, setDraftFilter] = React.useState(filter)
  React.useEffect(() => setDraftFilter(filter), [filter])
  const changeFilter = (key: keyof typeof draftFilter, value: string) => setDraftFilter((current) => ({ ...current, [key]: value }))
  const submitFilter = (event: React.FormEvent<HTMLFormElement>) => { event.preventDefault(); onFilter(draftFilter) }
  const sourceOptions = [
    { value: 'all', label: t('filters.allSources') },
    { value: 'agent', label: t('sources.agent') },
    { value: 'workflow', label: t('sources.workflow') },
  ]
  const statusOptions = [
    { value: 'all', label: t('filters.allStatuses') },
    ...(['completed', 'failed', 'running', 'queued', 'cancelled'] as const).map((value) => ({
      value,
      label: t(`status.${value}`),
    })),
  ]
  const selectedSourceLabel =
    sourceOptions.find((option) => option.value === draftFilter.source)?.label ??
    sourceOptions[0].label
  const selectedStatus = draftFilter.status || 'all'
  const selectedStatusLabel =
    statusOptions.find((option) => option.value === selectedStatus)?.label ??
    statusOptions[0].label
  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>{t('runs.title')}</CardTitle>
          <CardDescription>{t('runs.description')}</CardDescription>
        </div>
        <form className="flex flex-wrap items-end gap-2" onSubmit={submitFilter}>
          <Select
            value={draftFilter.source}
            onValueChange={(value) => value && changeFilter('source', value)}
          >
            <SelectTrigger aria-label={t('filters.source')} className="w-36">
              <SelectValue>{selectedSourceLabel}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {sourceOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={selectedStatus}
            onValueChange={(value) =>
              changeFilter('status', !value || value === 'all' ? '' : value)
            }
          >
            <SelectTrigger aria-label={t('filters.status')} className="w-36">
              <SelectValue>{selectedStatusLabel}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {statusOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            aria-label={t('filters.errorCategory')}
            value={draftFilter.error_category}
            onChange={(event) => changeFilter('error_category', event.target.value)}
            placeholder={t('filters.errorCategory')}
            className="w-36"
          />
          <Input
            aria-label={t('filters.runId')}
            value={draftFilter.run_id}
            onChange={(event) => changeFilter('run_id', event.target.value)}
            placeholder={t('filters.runId')}
            className="w-36"
          />
          <Button type="submit" disabled={loading}>
            {t('actions.apply')}
          </Button>
        </form>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-muted-foreground">
                {['source', 'name', 'team', 'status', 'submitted', 'queue', 'duration', 'tokens', 'error', 'trace'].map((key) => (
                  <th key={key} className="px-3 py-2 font-medium">
                    {t(`runs.columns.${key}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((run) => (
                <tr
                  key={`${run.source}:${run.run_id}`}
                  className="cursor-pointer border-b transition-colors hover:bg-muted/50"
                  onClick={() => onOpen(run)}
                >
                  <td className="px-3 py-3">
                    <Badge variant="outline">{t(`sources.${run.source}`)}</Badge>
                  </td>
                  <td className="max-w-48 truncate px-3 py-3 font-medium">
                    {run.resource_name}
                  </td>
                  <td className="px-3 py-3">{run.team_name ?? '—'}</td>
                  <td className="px-3 py-3">
                    <Badge variant={run.status === 'failed' ? 'destructive' : 'secondary'}>
                      {t.has(`status.${run.status}`) ? t(`status.${run.status}`) : run.status}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">
                    {run.submitted_at ? new Date(run.submitted_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-3">{duration(run.queue_duration_ms)}</td>
                  <td className="px-3 py-3">{duration(run.total_duration_ms)}</td>
                  <td className="px-3 py-3">{number(run.total_tokens)}</td>
                  <td className="px-3 py-3">{run.error_category ?? run.error_code ?? '—'}</td>
                  <td className="px-3 py-3">
                    {run.trace_available ? (
                      run.trace_complete ? (
                        <Check className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <Clock3 className="h-4 w-4 text-amber-600" />
                      )
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!items.length && !loading && <Empty text={t('states.noSamples')} />}
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            disabled={!nextCursor || loading}
            onClick={() => nextCursor && onNext(nextCursor)}
          >
            {loading ? t('states.loading') : t('actions.loadMore')}
            <ChevronDown className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function Dependencies({ data }: { data: DependenciesResponse }) {
  const t = useTranslations('dashboard.observability')
  return <div className="grid gap-4 xl:grid-cols-3">{(['models', 'tools', 'retrieval'] as const).map((group) => (
    <Card key={group}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Database className="h-4 w-4"/>{t(`dependencies.${group}`)}</CardTitle>
        <CardDescription>{t('dependencies.description')}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {data[group].map((row) => (
            <div key={'id' in row ? row.id : row.name} className="rounded-lg border p-3">
              <strong className="block truncate">{row.name || t('status.unavailable')}</strong>
              {'provider_display_name' in row && row.provider_display_name && (
                <div className="mt-1 truncate text-xs text-muted-foreground">{row.provider_display_name}</div>
              )}
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                <span>{t('dependencies.requests')}: {number(row.requests)}</span>
                <span>{t('dependencies.samples')}: {number(row.sample_count)}</span>
                <span>{t('dependencies.successRate')}: {percent(row.success_rate)}</span>
                <span>{t('dependencies.completedFailed', { completed: number(row.completed), failed: number(row.failed) })}</span>
                <span>{t('dependencies.p50')}: {duration(row.p50_ms)}</span>
                <span>{t('dependencies.p95')}: {duration(row.p95_ms)}</span>
                <span>{t('dependencies.firstTokenP95')}: {duration(row.first_token_p95_ms)}</span>
                <span>{t('dependencies.tokens')}: {number(row.tokens)}</span>
              </div>
            </div>
          ))}
          {!data[group].length && <Empty text={t('states.noSamples')}/>}
        </div>
      </CardContent>
    </Card>
  ))}</div>
}

function Queues({ data }: { data: QueuesResponse }) {
  const t = useTranslations('dashboard.observability')
  return <div className="space-y-4"><Card><CardHeader><CardTitle>{t('queues.workers')}</CardTitle><CardDescription>{t('queues.workersDescription')}</CardDescription></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.workers.map((worker) => <div key={worker.worker_id} className="rounded-lg border p-4"><div className="flex min-w-0 justify-between gap-2"><strong className="min-w-0 flex-1 truncate">{worker.worker_id}</strong><Badge variant={worker.status === 'healthy' ? 'secondary' : 'outline'}>{worker.status}</Badge></div><p className="mt-3 text-sm text-muted-foreground">{t('queues.active')}: {number(worker.active_tasks)} · {t('queues.reserved')}: {number(worker.reserved_tasks)} · {t('queues.scheduled')}: {number(worker.scheduled_tasks)}</p><p className="mt-2 break-words text-xs text-muted-foreground">{t('queues.workerQueues')}: {worker.queues.join(', ') || '—'}</p><p className="mt-2 text-xs text-muted-foreground">{t('queues.lastHeartbeat')}: {worker.last_heartbeat ? new Date(worker.last_heartbeat).toLocaleString() : '—'}</p></div>)}</div>{!data.workers.length && <Empty text={t('states.unavailableDetail')}/>}</CardContent></Card><Card><CardHeader><CardTitle>{t('queues.queues')}</CardTitle><CardDescription>{t('queues.queuesDescription')}</CardDescription></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.queues.map((queue) => <QueueCard key={queue.name} queue={queue}/>)}</div>{!data.queues.length && <Empty text={t('states.unavailableDetail')}/>}</CardContent></Card></div>
}

function QueueCard({ queue }: { queue: QueueRow }) {
  const t = useTranslations('dashboard.observability')
  return <div className="rounded-lg border p-4"><div className="flex items-center justify-between gap-2"><strong className="min-w-0 flex-1 break-words">{queue.name}</strong><Badge variant={queue.state === 'unavailable' || queue.state === 'warning' ? 'destructive' : 'outline'}>{t(`status.${queue.state}`)}</Badge></div><div className="mt-3 grid grid-cols-2 gap-2 text-sm text-muted-foreground"><span>{t('queues.consumers')}: {number(queue.consumers)}</span><span>{t('queues.pending')}: {number(queue.pending)}</span><span>{t('queues.oldestWait')}: {duration(queue.oldest_wait_ms)}</span><span>{t('queues.observedAt')}: {queue.observed_at ? new Date(queue.observed_at).toLocaleTimeString() : '—'}</span></div>{queue.trend.length ? <div className="mt-3 h-20" aria-label={t('queues.pendingTrend', { name: queue.name })}><ResponsiveContainer width="100%" height="100%"><LineChart data={queue.trend}><XAxis dataKey="bucket" hide/><YAxis hide/><Tooltip cursor={CHART_HOVER_CURSOR} contentStyle={CHART_TOOLTIP_STYLE} formatter={(value) => [number(value == null ? null : Number(value)), t('queues.pending')]}/><Line type="monotone" dataKey="pending" stroke={CHART_COLOR_ORDER[0]} strokeWidth={2} dot={false} connectNulls={false}/></LineChart></ResponsiveContainer></div> : <p className="mt-3 text-xs text-muted-foreground">{t('states.noSamples')}</p>}</div>
}

function Infrastructure({ data }: { data: InfrastructureResponse }) {
  const t = useTranslations('dashboard.observability')
  return <div className="space-y-4"><Card><CardHeader><CardTitle>{t('infrastructure.instances')}</CardTitle></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.instances.map((instance) => {
    const retained = instance.state === 'stale' || instance.state === 'offline'
    return <article key={instance.instance_id} aria-label={instance.name} className={`rounded-lg border p-4 ${instance.state === 'offline' ? 'border-destructive/40 bg-destructive/5' : instance.state === 'stale' ? 'border-dashed bg-muted/40' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0"><strong className="block truncate" title={instance.name}>{instance.name}</strong><span className="block break-all text-xs text-muted-foreground">{instance.instance_id}</span></div>
        <Badge variant={instance.state === 'warning' || instance.state === 'offline' ? 'destructive' : instance.state === 'healthy' ? 'secondary' : 'outline'}>{t(`status.${instance.state}`)}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t(`infrastructure.roles.${instance.role}`)} · {t(`infrastructure.scope.${instance.metric_scope}`)}</p>
      {retained && <p className="mt-2 text-xs font-medium">{t('infrastructure.retainedSample')}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-muted-foreground"><span>{t('infrastructure.metric.cpu_percent')}: {percentage(instance.cpu_percent)}</span><span>{t('infrastructure.metric.memory_percent')}: {percentage(instance.memory_percent)}</span></div>
      <p className="mt-2 text-xs text-muted-foreground">{t('infrastructure.lastObservedAt')}: {instance.observed_at ? new Date(instance.observed_at).toLocaleString() : '—'}</p>
    </article>
  })}</div>{!data.instances.length && <Empty text={t('states.unavailableDetail')}/>}</CardContent></Card><Card><CardHeader><CardTitle>{t('infrastructure.dependencies')}</CardTitle></CardHeader><CardContent><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.dependencies.map((dep) => <div key={dep.name} className="rounded-lg border p-4"><div className="flex items-center justify-between"><strong>{dep.name}</strong><Badge variant={dep.status === 'unhealthy' ? 'destructive' : 'outline'}>{t(`status.${dep.status}`)}</Badge></div><p className="mt-2 text-sm text-muted-foreground">{t('infrastructure.latency')}: {duration(dep.latency_ms)}</p>{dep.detail && <p className="mt-2 text-xs text-muted-foreground">{dep.detail}</p>}</div>)}</div>{!data.dependencies.length && <Empty text={t('states.unavailableDetail')}/>}</CardContent></Card><Card><CardHeader><CardTitle>{t('infrastructure.slowQueries')}</CardTitle><CardDescription>{data.slow_queries.reset_at ? t('infrastructure.queryReset', { time: new Date(data.slow_queries.reset_at).toLocaleString() }) : t('infrastructure.safeQueryNotice')}</CardDescription></CardHeader><CardContent>{data.slow_queries.available && data.slow_queries.items.length ? <div className="space-y-3">{data.slow_queries.items.map((query) => <div key={query.query_id} className="rounded-lg border p-3"><code className="block max-h-20 overflow-auto whitespace-pre-wrap break-all text-xs">{query.query}</code><div className="mt-2 flex flex-wrap gap-x-4 text-xs text-muted-foreground"><span>{t('infrastructure.calls')}: {number(query.calls)}</span><span>{t('infrastructure.mean')}: {duration(query.mean_ms)}</span><span>{t('infrastructure.max')}: {duration(query.max_ms)}</span><span>{t('infrastructure.total')}: {duration(query.total_ms)}</span></div></div>)}</div> : <Empty text={t(data.slow_queries.available ? 'states.noSamples' : 'states.unavailableDetail')}/>}</CardContent></Card></div>
}

function Alerts({ data, canManage, status, setStatus, pages, nextCursor, onNext, onMutate, onSaveRule, busy, silenceDuration, setSilenceDuration }: { data: { alerts: AlertEvent[]; rules: AlertRule[] }; canManage: boolean; status: 'active' | 'resolved' | 'all'; setStatus: (status: 'active' | 'resolved' | 'all') => void; pages: Array<{ items: AlertEvent[]; next_cursor: string | null }>; nextCursor: string | null; onNext: (cursor: string) => void; onMutate: (alert: AlertEvent, action: 'acknowledge' | 'silence') => void; onSaveRule: (rule: AlertRule, patch: Partial<Pick<AlertRule, 'threshold' | 'enabled' | 'evaluation_window_seconds' | 'recovery_window_seconds'>>) => void; busy: string | null; silenceDuration: number; setSilenceDuration: (value: number) => void }) {
  const t = useTranslations('dashboard.observability')
  const alerts = pages.flatMap((page) => page.items)
  const alertStatusOptions = (['active', 'resolved', 'all'] as const).map((value) => ({
    value,
    label: t(`alerts.${value}`),
  }))
  const selectedAlertStatusLabel =
    alertStatusOptions.find((option) => option.value === status)?.label ??
    alertStatusOptions[0].label
  const silenceDurationOptions = [900, 3600, 14400, 86400].map((seconds) => ({
    value: String(seconds),
    label: t('alerts.seconds', { count: seconds }),
  }))
  const selectedSilenceDuration = String(silenceDuration)
  const selectedSilenceDurationLabel =
    silenceDurationOptions.find((option) => option.value === selectedSilenceDuration)?.label ??
    silenceDurationOptions[0].label
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>{t('alerts.events')}</CardTitle>
            <CardDescription>{t('alerts.eventsDescription')}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Select
              value={status}
              onValueChange={(value) => value && setStatus(value as typeof status)}
            >
              <SelectTrigger aria-label={t('filters.alertStatus')} className="w-36">
                <SelectValue>{selectedAlertStatusLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {alertStatusOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {canManage && <Select
              value={selectedSilenceDuration}
              onValueChange={(value) => value && setSilenceDuration(Number(value))}
            >
              <SelectTrigger aria-label={t('alerts.silenceDuration')} className="w-40">
                <SelectValue>{selectedSilenceDurationLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {silenceDurationOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {alerts.map((alert) => (
            <div key={alert.id} className="rounded-lg border p-4">
              <div className="flex flex-col justify-between gap-3 md:flex-row">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={alert.severity === 'critical' ? 'destructive' : 'secondary'}>
                      {t(`severity.${alert.severity}`)}
                    </Badge>
                    <Badge variant="outline">{t(`alerts.${alert.status}`)}</Badge>
                    <strong>{alert.title}</strong>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{alert.detail}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {t('alerts.started', { time: new Date(alert.opened_at).toLocaleString() })}
                    {' · '}
                    {t('issues.affected', { count: alert.affected_count })}
                  </p>
                  {alert.silenced_until && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('alerts.silencedUntil', { time: new Date(alert.silenced_until).toLocaleString() })}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  {canManage && alert.status === 'active' && !alert.acknowledged_at && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === `${alert.id}:acknowledge`}
                      onClick={() => onMutate(alert, 'acknowledge')}
                    >
                      <Check className="mr-1 h-4 w-4" />
                      {t('alerts.acknowledge')}
                    </Button>
                  )}
                  {canManage && alert.status === 'active' && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === `${alert.id}:silence`}
                      onClick={() => onMutate(alert, 'silence')}
                    >
                      {t('alerts.silence')}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
          {!alerts.length && <Empty text={t('alerts.noEvents')} />}
          <div className="flex justify-end">
            <Button
              variant="outline"
              size="sm"
              disabled={!nextCursor}
              onClick={() => nextCursor && onNext(nextCursor)}
            >
              {t('actions.loadMore')}
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('alerts.rules')}</CardTitle>
          <CardDescription>{t('alerts.rulesDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {canManage && data.rules.map((rule) => (
            <RuleEditor key={rule.id} rule={rule} busy={busy === rule.id} onSave={onSaveRule} />
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
function RuleEditor({ rule, busy, onSave }: { rule: AlertRule; busy: boolean; onSave: (rule: AlertRule, patch: Partial<Pick<AlertRule, 'threshold' | 'enabled' | 'evaluation_window_seconds' | 'recovery_window_seconds'>>) => void }) {
  const t = useTranslations('dashboard.observability')
  const [threshold, setThreshold] = React.useState(String(rule.threshold))
  const [evaluationWindow, setEvaluationWindow] = React.useState(String(rule.evaluation_window_seconds))
  const [recoveryWindow, setRecoveryWindow] = React.useState(String(rule.recovery_window_seconds))
  React.useEffect(() => { setThreshold(String(rule.threshold)); setEvaluationWindow(String(rule.evaluation_window_seconds)); setRecoveryWindow(String(rule.recovery_window_seconds)) }, [rule.threshold, rule.evaluation_window_seconds, rule.recovery_window_seconds])
  const changed = Number(threshold) !== rule.threshold || Number(evaluationWindow) !== rule.evaluation_window_seconds || Number(recoveryWindow) !== rule.recovery_window_seconds
  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3 md:flex-row md:items-center">
      <div className="min-w-0 flex-1"><strong>{rule.name}</strong></div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={rule.enabled}
          disabled={busy}
          onChange={(event) => onSave(rule, { enabled: event.target.checked })}
        />
        {t('alerts.enabled')}
      </label>
      <label className="flex items-center gap-2 text-sm">
        {t('alerts.threshold')}
        <Input
          type="number"
          min="0"
          max="1"
          step="any"
          value={threshold}
          onChange={(event) => setThreshold(event.target.value)}
          className="w-24"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        {t('alerts.evaluationWindow', { count: Number(evaluationWindow) || rule.evaluation_window_seconds })}
        <Input
          aria-label={t('alerts.evaluationWindow', { count: Number(evaluationWindow) || rule.evaluation_window_seconds })}
          type="number"
          min="60"
          max="604800"
          step="1"
          value={evaluationWindow}
          onChange={(event) => setEvaluationWindow(event.target.value)}
          className="w-24"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        {t('alerts.recoveryWindow', { count: Number(recoveryWindow) || rule.recovery_window_seconds })}
        <Input
          aria-label={t('alerts.recoveryWindow', { count: Number(recoveryWindow) || rule.recovery_window_seconds })}
          type="number"
          min="60"
          max="604800"
          step="1"
          value={recoveryWindow}
          onChange={(event) => setRecoveryWindow(event.target.value)}
          className="w-24"
        />
      </label>
      <Button
        disabled={busy || !threshold || !evaluationWindow || !recoveryWindow || Number(threshold) < 0 || Number(threshold) > 1 || Number(evaluationWindow) < 60 || Number(evaluationWindow) > 604800 || Number(recoveryWindow) < 60 || Number(recoveryWindow) > 604800 || !changed}
        onClick={() => onSave(rule, { threshold: Number(threshold), evaluation_window_seconds: Number(evaluationWindow), recovery_window_seconds: Number(recoveryWindow) })}
      >
        {t('actions.save')}
      </Button>
    </div>
  )
}

function RunDetail({ detail, loading, error, onClose, expanded, setExpanded }: { detail: RunDetailResponse | null; loading: boolean; error: boolean; onClose: () => void; expanded: Set<string>; setExpanded: React.Dispatch<React.SetStateAction<Set<string>>> }) {
  const t = useTranslations('dashboard.observability')
  const run = detail?.run
  const spans = detail?.spans ?? []
  const children = new Map<string | null, RunDetailResponse['spans']>()
  const timelineValues: number[] = []
  for (const span of spans) {
    const started = span.started_at ? Date.parse(span.started_at) : Number.NaN
    const finished = span.finished_at ? Date.parse(span.finished_at) : Number.NaN
    if (Number.isFinite(started)) timelineValues.push(started)
    if (Number.isFinite(finished)) timelineValues.push(finished)
    else if (Number.isFinite(started) && span.duration_ms != null) timelineValues.push(started + span.duration_ms)
    const key = span.parent_span_id
    children.set(key, [...(children.get(key) ?? []), span])
  }
  const timelineStart = timelineValues.length ? Math.min(...timelineValues) : 0
  const timelineDuration = Math.max(1, (timelineValues.length ? Math.max(...timelineValues) : timelineStart) - timelineStart)
  const toggle = (id: string) =>
    setExpanded((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  return <Sheet open={Boolean(run || loading || error)} onOpenChange={(open) => !open && onClose()}><SheetContent className="w-full overflow-y-auto sm:max-w-3xl"><SheetHeader><SheetTitle>{run?.resource_name ?? t('details.runTitle')}</SheetTitle><SheetDescription>{run ? `${t(`sources.${run.source}`)} · ${run.run_id}` : t('details.traceDescription')}</SheetDescription></SheetHeader>{loading ? <div className="space-y-3 p-6"><div className="h-16 animate-pulse rounded bg-muted"/><div className="h-32 animate-pulse rounded bg-muted"/></div> : error ? <p role="alert" className="p-6 text-sm text-destructive">{t('states.errorDescription')}</p> : detail && run ? <div className="space-y-5 p-1"><div className="grid grid-cols-2 gap-3 sm:grid-cols-4"><Metric label={t('runs.columns.status')} value={run.status}/><Metric label={t('runs.columns.queue')} value={duration(run.queue_duration_ms)}/><Metric label={t('runs.columns.duration')} value={duration(run.total_duration_ms)}/><Metric label={t('runs.columns.tokens')} value={number(run.total_tokens)}/></div><div className="rounded-lg border p-3 text-xs text-muted-foreground">{t('details.traceStatus', { recorded: detail.trace.recorded_count, complete: detail.trace.complete ? t('details.complete') : t('details.incomplete') })}{detail.trace.expired && ` · ${t('details.traceExpired')}`}{detail.trace.truncated && ` · ${t('details.traceTruncated')}`}</div><div className="space-y-1"><h3 className="mb-3 font-medium">{t('details.waterfall')}</h3>{spans.length ? (children.get(null) ?? spans.filter((span) => !spans.some((other) => other.span_id === span.parent_span_id))).map((span) => <SpanTree key={span.span_id} span={span} childrenMap={children} depth={0} timelineStart={timelineStart} timelineDuration={timelineDuration} expanded={expanded} toggle={toggle}/>) : <Empty text={t('details.traceUnavailable')}/>}</div>{run.error_category && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm"><strong>{t('details.errorCategory')}:</strong> {run.error_category}{run.error_code && ` · ${run.error_code}`}</div>}</div> : null}</SheetContent></Sheet>
}
function SpanTree({
  span,
  childrenMap,
  depth,
  timelineStart,
  timelineDuration,
  expanded,
  toggle,
}: {
  span: RunDetailResponse['spans'][number]
  childrenMap: Map<string | null, RunDetailResponse['spans']>
  depth: number
  timelineStart: number
  timelineDuration: number
  expanded: Set<string>
  toggle: (id: string) => void
}) {
  const children = childrenMap.get(span.span_id) ?? []
  const open = expanded.has(span.span_id)
  const started = span.started_at ? Date.parse(span.started_at) : timelineStart
  const offset = Number.isFinite(started) ? Math.max(0, started - timelineStart) : 0
  const elapsed =
    span.duration_ms ??
    (span.finished_at && span.started_at
      ? Date.parse(span.finished_at) - Date.parse(span.started_at)
      : 0)
  const left = Math.min(100, (offset / timelineDuration) * 100)
  const width = Math.max(
    elapsed > 0 ? 1 : 0.5,
    Math.min(100 - left, (Math.max(0, elapsed) / timelineDuration) * 100),
  )

  return (
    <div>
      <button
        type="button"
        aria-expanded={children.length ? open : undefined}
        disabled={!children.length}
        onClick={() => toggle(span.span_id)}
        className="flex w-full items-center gap-2 rounded-md border-b px-2 py-2 text-left hover:bg-muted/50"
        style={{ paddingLeft: `${8 + depth * 18}px` }}
      >
        {children.length ? (
          open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )
        ) : (
          <span className="w-3.5" />
        )}
        <Badge variant="outline">{span.kind}</Badge>
        <span className="min-w-0 flex-1 truncate text-sm">{span.name}</span>
        <span className="text-xs text-muted-foreground">
          {duration(span.duration_ms)}
        </span>
        <Badge variant={span.status === 'failed' ? 'destructive' : 'secondary'}>
          {span.status}
        </Badge>
      </button>
      <div className="relative ml-6 mt-1 h-2 overflow-hidden rounded bg-muted">
        <div
          className="absolute inset-y-0 rounded bg-primary/70"
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      </div>
      {open &&
        children.map((child) => (
          <SpanTree
            key={child.span_id}
            span={child}
            childrenMap={childrenMap}
            depth={depth + 1}
            timelineStart={timelineStart}
            timelineDuration={timelineDuration}
            expanded={expanded}
            toggle={toggle}
          />
        ))}
    </div>
  )
}
function Empty({ text }: { text: string }) { return <div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed px-4 text-center text-sm text-muted-foreground">{text}</div> }
