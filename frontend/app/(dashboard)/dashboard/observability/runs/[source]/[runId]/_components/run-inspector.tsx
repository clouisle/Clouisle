'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { useRouter, useSearchParams } from 'next/navigation'
import { AlertTriangle, ArrowLeft, Clock3, RefreshCw, Search } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { isRecord } from '@/lib/utils'
import {
  observabilityApi,
  type ObservabilitySource,
  type RunDetailResponse,
  type RunSummary,
  type ToolPayloadDetail,
  type TrajectoryEntry,
  type TrajectoryEntryDetail,
} from '@/lib/api/admin/observability'

const SOURCES = ['agent', 'workflow'] as const
const TYPE_OPTIONS = ['all', 'model', 'tool', 'retrieval', 'workflow_node'] as const
const KNOWN_KINDS: Record<string, true> = {
  model: true,
  tool: true,
  retrieval: true,
  workflow_node: true,
}

type Tab = 'summary' | 'preview' | 'raw'

const KIND_STYLE: Record<string, { dot: string; bar: string; badge: string }> = {
  model: { dot: 'bg-sky-500', bar: 'bg-sky-500', badge: 'border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300' },
  tool: { dot: 'bg-amber-500', bar: 'bg-amber-500', badge: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  retrieval: { dot: 'bg-violet-500', bar: 'bg-violet-500', badge: 'border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300' },
  workflow_node: { dot: 'bg-teal-500', bar: 'bg-teal-500', badge: 'border-teal-500/40 bg-teal-500/10 text-teal-700 dark:text-teal-300' },
  unknown: { dot: 'bg-muted-foreground/50', bar: 'bg-muted-foreground/40', badge: 'border-border bg-muted text-muted-foreground' },
}

const kindStyle = (kind: string) => KIND_STYLE[kind] ?? KIND_STYLE.unknown
const isFailed = (status: string) => /fail|error|timeout|abort/i.test(status)
const formatMetric = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat().format(value)
const formatMs = (value: number | null | undefined) => value == null ? '—' : value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`
const formatText = (value: unknown): string => typeof value === 'string' ? value : (JSON.stringify(value, null, 2) ?? String(value))
const hasTiming = (entry: TrajectoryEntry) => Boolean(entry.started_at && Number.isFinite(Date.parse(entry.started_at)))
const entryDuration = (entry: TrajectoryEntry) => {
  if (entry.duration_ms != null) return entry.duration_ms
  if (!entry.started_at || !entry.finished_at) return null
  const started = Date.parse(entry.started_at)
  const finished = Date.parse(entry.finished_at)
  return Number.isFinite(started) && Number.isFinite(finished) ? finished - started : null
}

export function RunInspector({ source, runId }: { source: string; runId: string }) {
  const t = useTranslations('dashboard.observability')
  const sourceValue = (SOURCES as readonly string[]).includes(source) ? source as ObservabilitySource : null
  const [detail, setDetail] = React.useState<RunDetailResponse | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [failed, setFailed] = React.useState(false)
  const [notFound, setNotFound] = React.useState(false)
  const [reloadKey, setReloadKey] = React.useState(0)

  React.useEffect(() => {
    if (!sourceValue) {
      setLoading(false)
      return
    }
    let active = true
    setLoading(true)
    setFailed(false)
    setNotFound(false)
    setDetail((current) => current && current.run.run_id === runId && current.run.source === sourceValue ? current : null)
    observabilityApi.getRun(sourceValue, runId)
      .then((response) => { if (active) setDetail(response) })
      .catch((error: unknown) => {
        if (!active) return
        setNotFound((error as { status?: unknown } | null)?.status === 404)
        setFailed(true)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [sourceValue, runId, reloadKey])

  if (!sourceValue) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <p className="text-sm font-medium">{t('runInspector.invalidSource')}</p>
        <p className="mt-1 text-sm text-muted-foreground">{t('runInspector.invalidSourceHint')}</p>
      </div>
    )
  }

  return (
    <RunInspectorView
      source={sourceValue}
      runId={runId}
      detail={detail}
      loading={loading}
      failed={failed}
      notFound={notFound}
      onReload={() => setReloadKey((value) => value + 1)}
    />
  )
}

function RunInspectorView({
  source,
  runId,
  detail,
  loading,
  failed,
  notFound,
  onReload,
}: {
  source: ObservabilitySource
  runId: string
  detail: RunDetailResponse | null
  loading: boolean
  failed: boolean
  notFound: boolean
  onReload: () => void
}) {
  const t = useTranslations('dashboard.observability')
  const locale = useLocale()
  const router = useRouter()
  const search = useSearchParams()
  const run = detail?.run ?? null
  const entries = React.useMemo(() => detail?.trajectory ?? [], [detail])
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [nameFilter, setNameFilter] = React.useState('')
  const [typeFilter, setTypeFilter] = React.useState<string>('all')
  const [failuresOnly, setFailuresOnly] = React.useState(false)
  const [tab, setTab] = React.useState<Tab>('summary')

  const filtered = React.useMemo(() => {
    const query = nameFilter.trim().toLowerCase()
    return entries.filter((entry) => {
      if (typeFilter !== 'all' && entry.kind !== typeFilter) return false
      if (failuresOnly && !isFailed(entry.status)) return false
      if (!query) return true
      const haystack = [entry.name, entry.kind, entry.model ?? '', entry.preview ?? '', entry.status].join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }, [entries, failuresOnly, nameFilter, typeFilter])

  React.useEffect(() => {
    setSelectedId((current) => {
      if (current && entries.some((entry) => entry.id === current)) return current
      return null
    })
  }, [entries])

  React.useEffect(() => {
    setSelectedId((current) => {
      if (current && filtered.some((entry) => entry.id === current)) return current
      return null
    })
  }, [filtered])

  const selected = entries.find((entry) => entry.id === selectedId) ?? null
  const goBack = () => {
    const params = new URLSearchParams(search.toString())
    params.set('tab', 'runs')
    router.push(`/dashboard/observability?${params.toString()}`)
  }
  const localizedStatus = (status: string) => t.has(`status.${status}`) ? t(`status.${status}`) : status
  const kindLabel = (kind: string) => KNOWN_KINDS[kind] ? t(`runInspector.kinds.${kind}`) : kind
  const selectEntry = (id: string) => {
    if (!filtered.some((entry) => entry.id === id)) {
      setNameFilter('')
      setTypeFilter('all')
      setFailuresOnly(false)
    }
    setSelectedId((current) => current === id ? null : id)
    setTab('summary')
  }

  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <Button variant="ghost" size="sm" className="-ml-2" onClick={goBack}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('runInspector.back')}
        </Button>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {run?.resource_name ?? t('runInspector.title')}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
              <Badge variant="outline">{t(`sources.${source}`)}</Badge>
              <span className="break-all font-mono text-xs">{runId}</span>
              {run?.team_name && <span>· {run.team_name}</span>}
            </div>
          </div>
          <Button variant="outline" onClick={onReload} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('runInspector.refresh')}
          </Button>
        </div>
      </header>

      {loading && !detail ? (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="h-28 animate-pulse rounded-lg bg-muted/40" />
          <div className="h-28 animate-pulse rounded-lg bg-muted/40" />
          <div className="h-48 animate-pulse rounded-lg bg-muted/40 md:col-span-2" />
        </div>
      ) : notFound && !detail ? (
        <div role="alert" className="space-y-3 rounded-lg border p-6">
          <div>
            <p className="text-sm font-medium">{t('runInspector.notFound')}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t('runInspector.notFoundHint')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={goBack}>{t('runInspector.back')}</Button>
        </div>
      ) : failed && !detail ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <div>
            <p className="font-medium">{t('runInspector.loadError')}</p>
            <p className="text-muted-foreground">{t('runInspector.loadErrorHint')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={onReload}>{t('runInspector.retry')}</Button>
        </div>
      ) : detail && run ? (
        <>
          <RunOverview run={run} trace={detail.trace} locale={locale} />
          {failed && <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm"><span>{t('runInspector.loadError')}</span><Button variant="outline" size="sm" onClick={onReload}>{t('runInspector.retry')}</Button></div>}
          <TimelineLanes entries={filtered} allEntries={entries} run={run} source={source} selectedId={selectedId} onSelect={selectEntry} />
          <div className={`grid h-[40rem] max-h-[70dvh] min-h-0 items-stretch gap-4 ${selected ? 'grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'grid-cols-1'}`}>
            <TrajectoryList
              entries={filtered}
              allEntries={entries}
              allCount={entries.length}
              spans={detail.spans}
              selectedId={selectedId}
              onSelect={selectEntry}
              nameFilter={nameFilter}
              setNameFilter={setNameFilter}
              typeFilter={typeFilter}
              setTypeFilter={setTypeFilter}
              failuresOnly={failuresOnly}
              setFailuresOnly={setFailuresOnly}
              localizedStatus={localizedStatus}
              kindLabel={kindLabel}
            />
            {selected && <InspectorPanel
              entry={selected}
              entries={entries}
              source={source}
              runId={runId}
              tab={tab}
              setTab={setTab}
              onSelectEntry={selectEntry}
              localizedStatus={localizedStatus}
              kindLabel={kindLabel}
              emptyDescription={!entries.length && detail.spans.length > 0 ? t('runInspector.inspector.legacyEmpty') : undefined}
            />}
          </div>
        </>
      ) : null}
    </div>
  )
}

function RunOverview({
  run,
  trace,
  locale,
}: {
  run: RunSummary
  trace: RunDetailResponse['trace']
  locale: string
}) {
  const t = useTranslations('dashboard.observability')
  const when = (value: string | null) => {
    if (!value) return '—'
    const parsed = new Date(value)
    return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString(locale) : '—'
  }
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="grid grid-cols-2 gap-x-4 gap-y-3 p-4 sm:grid-cols-3 xl:grid-cols-6">
          <Metric label={t('runInspector.metrics.status')} value={<Badge variant={isFailed(run.status) ? 'destructive' : 'secondary'}>{t.has(`status.${run.status}`) ? t(`status.${run.status}`) : run.status}</Badge>} />
          <Metric label={t('runInspector.metrics.queue')} value={formatMs(run.queue_duration_ms)} />
          <Metric label={t('runInspector.metrics.duration')} value={formatMs(run.total_duration_ms)} />
          <Metric label={t('runInspector.metrics.firstToken')} value={formatMs(run.first_token_ms)} />
          <Metric label={t('runInspector.metrics.tokens')} value={formatMetric(run.total_tokens)} />
          <Metric label={t('runInspector.metrics.team')} value={run.team_name ?? '—'} />
          <Metric label={t('runInspector.metrics.submitted')} value={when(run.submitted_at)} />
          <Metric label={t('runInspector.metrics.started')} value={when(run.started_at)} />
          <Metric label={t('runInspector.metrics.finished')} value={when(run.finished_at)} />
        </CardContent>
      </Card>
      <div className={`rounded-lg border p-3 text-xs ${trace.expired || trace.truncated ? 'border-amber-500/40 bg-amber-500/5 text-amber-800 dark:text-amber-200' : 'text-muted-foreground'}`}>
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5" />
          {t('runInspector.trace.summary', { recorded: trace.recorded_count, complete: trace.complete ? t('runInspector.trace.complete') : t('runInspector.trace.incomplete') })}
        </span>
        {trace.expired && <p className="mt-1">{t('runInspector.trace.expired')}</p>}
        {trace.truncated && <p className="mt-1">{t('runInspector.trace.truncated')}</p>}
      </div>
      {(run.error_category || run.error_code) && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
          <strong>{t('runInspector.trace.error')}:</strong> {[run.error_category, run.error_code].filter(Boolean).join(' · ')}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <div className="mt-0.5 truncate text-sm font-medium" title={typeof value === 'string' ? value : undefined}>{value}</div>
    </div>
  )
}

function TimelineLanes({
  entries,
  allEntries,
  run,
  source,
  selectedId,
  onSelect,
}: {
  entries: TrajectoryEntry[]
  allEntries: TrajectoryEntry[]
  run: RunSummary
  source: ObservabilitySource
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const t = useTranslations('dashboard.observability')
  const kindLabel = (kind: string) => KNOWN_KINDS[kind] ? t(`runInspector.kinds.${kind}`) : kind
  const values: number[] = []
  const add = (value: string | null) => {
    if (!value) return
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) values.push(parsed)
  }
  ;[run.submitted_at, run.started_at, run.finished_at].forEach(add)
  for (const entry of allEntries) {
    add(entry.started_at)
    add(entry.finished_at)
    if (entry.started_at && entry.duration_ms != null) {
      const started = Date.parse(entry.started_at)
      if (Number.isFinite(started)) values.push(started + entry.duration_ms)
    }
  }
  const first = values.length ? Math.min(...values) : 0
  const last = values.length ? Math.max(...values) : 0
  const total = Math.max(1, last - first)
  const timed = values.length > 0
  const untimed = entries.filter((entry) => !hasTiming(entry)).length
  const modelEntries = entries.filter((entry) => entry.kind === 'model')
  const lanes: Array<{ key: string; label: string; items: TrajectoryEntry[]; markers?: TrajectoryEntry[] }> = source === 'workflow'
    ? [
        { key: 'nodes', label: t('runInspector.timeline.nodes'), items: entries.filter((entry) => entry.kind === 'workflow_node') },
        { key: 'model', label: t('runInspector.timeline.model'), items: modelEntries },
        { key: 'tools', label: t('runInspector.timeline.tools'), items: entries.filter((entry) => entry.kind === 'tool' || entry.kind === 'retrieval') },
      ]
    : [
        { key: 'input', label: t('runInspector.timeline.input'), items: [], markers: modelEntries },
        { key: 'model', label: t('runInspector.timeline.model'), items: modelEntries },
        { key: 'tools', label: t('runInspector.timeline.tools'), items: entries.filter((entry) => entry.kind === 'tool' || entry.kind === 'retrieval') },
      ]

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <CardTitle className="text-base">{t('runInspector.timeline.title')}</CardTitle>
            <CardDescription>{t('runInspector.timeline.description')}</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground" aria-hidden>
            {(['model', 'tool', 'retrieval', 'workflow_node'] as const).map((kind) => (
              <span key={kind} className="inline-flex items-center gap-1">
                <span className={`size-2 rounded-full ${kindStyle(kind).dot}`} />
                {kindLabel(kind)}
              </span>
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {lanes.map((lane) => {
          const positioned = lane.items.flatMap((entry) => {
            if (!hasTiming(entry)) return []
            const start = Date.parse(entry.started_at!)
            const end = start + Math.max(1, entryDuration(entry) ?? 0)
            return [{ entry, start, end }]
          }).sort((left, right) => left.start - right.start)
          const trackEnds: number[] = []
          const laidOut = positioned.map((item) => {
            const free = trackEnds.findIndex((end) => end <= item.start)
            const row = free === -1 ? trackEnds.length : free
            trackEnds[row] = item.end
            return { ...item, row }
          })
          const rowCount = Math.max(1, trackEnds.length)
          const laneHeight = Math.max(24, rowCount * 10 + 4)
          return (
            <div key={lane.key} className="flex items-center gap-2">
              <span className="w-14 shrink-0 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{lane.label}</span>
              <div className="relative min-w-0 flex-1 overflow-hidden rounded border border-border/60 bg-muted/20" style={{ height: laneHeight }}>
                {[25, 50, 75].map((tick) => <span key={tick} aria-hidden className="absolute inset-y-0 border-l border-dashed border-border/50" style={{ left: `${tick}%` }} />)}
                {lane.markers?.map((entry) => {
                  if (!hasTiming(entry)) return null
                  const started = Date.parse(entry.started_at!)
                  const left = Math.max(0, Math.min(99, ((started - first) / total) * 100))
                  return (
                    <button
                      key={`input-${entry.id}`}
                      type="button"
                      aria-label={`${t('runInspector.timeline.inputBoundary')}: ${entry.name}`}
                      aria-pressed={entry.id === selectedId}
                      title={`${t('runInspector.timeline.inputBoundary')} · ${entry.name}`}
                      onClick={() => onSelect(entry.id)}
                      className={`absolute inset-y-0 w-1.5 border-l-2 border-dashed bg-transparent ${entry.id === selectedId ? 'border-foreground' : 'border-sky-500/70'}`}
                      style={{ left: `${left}%` }}
                    />
                  )
                })}
                {laidOut.map(({ entry, start, row }) => {
                  const elapsed = Math.max(0, entryDuration(entry) ?? 0)
                  const left = Math.max(0, Math.min(99, ((start - first) / total) * 100))
                  const available = Math.max(0.5, 100 - left)
                  const width = Math.min(available, (elapsed / total) * 100)
                  const tone = kindStyle(entry.kind)
                  return (
                    <button
                      key={entry.id}
                      type="button"
                      aria-label={`${kindLabel(entry.kind)}: ${entry.name}`}
                      aria-pressed={entry.id === selectedId}
                      title={`${entry.name} · ${formatMs(entryDuration(entry))}${entry.model ? ` · ${entry.model}` : ''}`}
                      onClick={() => onSelect(entry.id)}
                      className={`absolute rounded-sm transition-opacity ${tone.bar} ${isFailed(entry.status) ? 'ring-1 ring-destructive' : ''} ${entry.id === selectedId ? 'opacity-100 ring-2 ring-foreground/50' : 'opacity-75 hover:opacity-100'}`}
                      style={{ left: `${left}%`, top: rowCount === 1 ? 9 : 4 + row * 10, height: 6, width: `${width}%`, minWidth: '3px', maxWidth: `${available}%` }}
                    />
                  )
                })}
                {!lane.items.length && !lane.markers?.length && (
                  <span className="absolute inset-0 flex items-center px-2 text-[10px] text-muted-foreground">
                    {lane.key === 'input' ? t('runInspector.timeline.inputHint') : t('runInspector.timeline.emptyLane')}
                  </span>
                )}
              </div>
            </div>
          )
        })}
        <div className="flex items-center justify-between pl-16 text-[10px] tabular-nums text-muted-foreground" aria-hidden={!timed}>
          {timed ? <><span>0</span><span>{formatMs(total / 2)}</span><span>{formatMs(total)}</span></> : <span>{t('runInspector.timeline.emptyLane')}</span>}
        </div>
        {untimed > 0 && <p className="pl-16 text-[11px] text-muted-foreground">{t('runInspector.timeline.untimed', { count: untimed })}</p>}
        {!entries.length && <p className="pt-1 text-xs text-muted-foreground">{t('runInspector.steps.noTrajectory')}</p>}
      </CardContent>
    </Card>
  )
}

function TrajectoryList({
  entries,
  allEntries,
  allCount,
  spans,
  selectedId,
  onSelect,
  nameFilter,
  setNameFilter,
  typeFilter,
  setTypeFilter,
  failuresOnly,
  setFailuresOnly,
  localizedStatus,
  kindLabel,
}: {
  entries: TrajectoryEntry[]
  allEntries: TrajectoryEntry[]
  allCount: number
  spans: RunDetailResponse['spans']
  selectedId: string | null
  onSelect: (id: string) => void
  nameFilter: string
  setNameFilter: (value: string) => void
  typeFilter: string
  setTypeFilter: (value: string) => void
  failuresOnly: boolean
  setFailuresOnly: (value: boolean) => void
  localizedStatus: (status: string) => string
  kindLabel: (kind: string) => string
}) {
  const t = useTranslations('dashboard.observability')
  const selectedType = TYPE_OPTIONS.includes(typeFilter as typeof TYPE_OPTIONS[number]) ? typeFilter : 'all'
  const typeDisplay = selectedType === 'all' ? t('runInspector.steps.allTypes') : kindLabel(selectedType)
  const modelNumbers = new Map<string, number>()
  const toolNumbers = new Map<string, number>()
  const stepNumbers = new Map<string, number>()
  for (const [index, entry] of allEntries.entries()) {
    stepNumbers.set(entry.id, index + 1)
    if (entry.kind === 'model') modelNumbers.set(entry.id, modelNumbers.size + 1)
    if (entry.kind === 'tool') toolNumbers.set(entry.id, toolNumbers.size + 1)
  }
  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <CardHeader className="shrink-0 gap-3 pb-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle className="text-base">{t('runInspector.steps.title')}</CardTitle>
          <span className="text-xs text-muted-foreground">{t('runInspector.steps.count', { count: entries.length })}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-40 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={t('runInspector.steps.filterName')}
              value={nameFilter}
              onChange={(event) => setNameFilter(event.target.value)}
              placeholder={t('runInspector.steps.filterName')}
              className="h-9 pl-8"
            />
          </div>
          <Select value={selectedType} onValueChange={(value) => value && setTypeFilter(value)}>
            <SelectTrigger aria-label={t('runInspector.steps.filterType')} className="w-36">
              <SelectValue>{typeDisplay}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((value) => (
                <SelectItem key={value} value={value}>
                  {value === 'all' ? t('runInspector.steps.allTypes') : kindLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant={failuresOnly ? 'secondary' : 'outline'}
            size="sm"
            aria-pressed={failuresOnly}
            onClick={() => setFailuresOnly(!failuresOnly)}
          >
            <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
            {t('runInspector.steps.failuresOnly')}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto p-0">
        <div className="divide-y">
          {entries.map((entry, index) => {
            const style = kindStyle(entry.kind)
            const duration = entryDuration(entry)
            const tokens = entry.token_usage?.total ?? entry.token_usage?.total_tokens
            const callNumber = modelNumbers.get(entry.id)
            const toolNumber = toolNumbers.get(entry.id)
            return (
              <button
                key={entry.id}
                type="button"
                data-step-id={entry.id}
                aria-pressed={entry.id === selectedId}
                onClick={() => onSelect(entry.id)}
                className={`grid w-full grid-cols-[auto_minmax(0,1fr)] items-start gap-2 px-3 py-2.5 text-left transition-colors hover:bg-muted/40 ${entry.id === selectedId ? 'bg-muted/70' : ''}`}
              >
                <span className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`} />
                <span className="min-w-0 space-y-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="rounded border px-1 py-0.5 font-mono text-[10px] text-muted-foreground">#{stepNumbers.get(entry.id) ?? index + 1}</span>
                    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${style.badge}`}>{kindLabel(entry.kind)}</span>
                    {callNumber != null && <span className="text-[10px] font-medium text-muted-foreground">{t('runInspector.steps.callNumber', { number: callNumber })}</span>}
                    {toolNumber != null && <span className="text-[10px] font-medium text-muted-foreground">{t('runInspector.steps.toolNumber', { number: toolNumber })}</span>}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium" title={entry.name}>{entry.name}</span>
                    {isFailed(entry.status) && <Badge variant="destructive">{localizedStatus(entry.status)}</Badge>}
                    <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">{formatMs(duration)}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                    {entry.parent_id && <span title={t('runInspector.inspector.parent')}>↳</span>}
                    {entry.model && <span className="truncate font-mono">{entry.model}</span>}
                    {tokens != null && <span>{formatMetric(tokens)} tokens</span>}
                    {entry.payload_state === 'partial' && <span className="text-amber-600 dark:text-amber-300">{t('runInspector.steps.previewPartial')}</span>}
                    {entry.payload_state === 'unrecorded' && <span>{t('runInspector.steps.previewUnrecorded')}</span>}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground" title={entry.preview ?? undefined}>
                    {entry.preview ?? '—'}
                  </span>
                </span>
              </button>
            )
          })}
          {!entries.length && allCount === 0 && spans.length > 0 ? (
            <LegacySpans spans={spans} localizedStatus={localizedStatus} kindLabel={kindLabel} />
          ) : !entries.length && (
            <div className="space-y-2 px-4 py-8 text-center">
              <p className="text-sm font-medium">{allCount ? t('runInspector.steps.empty') : t('runInspector.steps.noTrajectory')}</p>
              <p className="text-xs text-muted-foreground">{allCount ? t('runInspector.steps.filterName') : t('runInspector.steps.noTrajectoryHint')}</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function LegacySpans({
  spans,
  localizedStatus,
  kindLabel,
}: {
  spans: RunDetailResponse['spans']
  localizedStatus: (status: string) => string
  kindLabel: (kind: string) => string
}) {
  const t = useTranslations('dashboard.observability')
  const ordered = [...spans].sort((left, right) => {
    const a = left.started_at ? Date.parse(left.started_at) : Number.NaN
    const b = right.started_at ? Date.parse(right.started_at) : Number.NaN
    const rank = (value: number) => Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER
    return rank(a) - rank(b)
  })
  return (
    <div>
      <div className="space-y-1 border-b border-amber-500/30 bg-amber-500/5 px-4 py-2.5 text-xs">
        <p className="font-medium text-amber-800 dark:text-amber-200">{t('runInspector.steps.legacyTitle')}</p>
        <p className="text-muted-foreground">{t('runInspector.steps.legacyNotice')}</p>
      </div>
      {ordered.map((span) => {
        const style = kindStyle(span.kind)
        return (
          <div key={span.span_id} data-legacy-span-id={span.span_id} className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-2 px-3 py-2.5">
            <span className={`mt-1.5 size-2 shrink-0 rounded-full ${style.dot}`} />
            <span className="min-w-0 space-y-1">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${style.badge}`}>{kindLabel(span.kind)}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium" title={span.name}>{span.name}</span>
                <Badge variant={isFailed(span.status) ? 'destructive' : 'secondary'}>{localizedStatus(span.status)}</Badge>
                <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">{formatMs(span.duration_ms)}</span>
              </span>
              <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span>{t('runInspector.steps.legacyUnrecorded')}</span>
                {span.model && <span className="truncate font-mono">{span.model}</span>}
                {span.error_category && <span className="text-destructive">{span.error_category}</span>}
              </span>
            </span>
          </div>
        )
      })}
    </div>
  )
}

function useTrajectoryPayload(source: ObservabilitySource, runId: string, entryId: string | null) {
  const [payload, setPayload] = React.useState<TrajectoryEntryDetail | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [failed, setFailed] = React.useState(false)
  const [retryKey, setRetryKey] = React.useState(0)
  const requestRef = React.useRef(0)

  React.useEffect(() => {
    if (!entryId) {
      setPayload(null)
      setLoading(false)
      setFailed(false)
      return
    }
    let active = true
    const id = ++requestRef.current
    setLoading(true)
    setFailed(false)
    setPayload(null)
    observabilityApi.getTrajectoryEntry(source, runId, entryId)
      .then((response) => { if (active && id === requestRef.current) setPayload(response) })
      .catch(() => { if (active && id === requestRef.current) setFailed(true) })
      .finally(() => { if (active && id === requestRef.current) setLoading(false) })
    return () => { active = false }
  }, [entryId, source, runId, retryKey])

  return { payload, loading, failed, retry: () => setRetryKey((value) => value + 1) }
}

function InspectorPanel({
  entry,
  entries,
  source,
  runId,
  tab,
  setTab,
  onSelectEntry,
  localizedStatus,
  kindLabel,
  emptyDescription,
}: {
  entry: TrajectoryEntry | null
  entries: TrajectoryEntry[]
  source: ObservabilitySource
  runId: string
  tab: Tab
  setTab: (tab: Tab) => void
  onSelectEntry: (id: string) => void
  localizedStatus: (status: string) => string
  kindLabel: (kind: string) => string
  emptyDescription?: string
}) {
  const t = useTranslations('dashboard.observability')
  const locale = useLocale()
  const payloadState = useTrajectoryPayload(source, runId, entry?.id ?? null)
  if (!entry) {
    return (
      <Card className="xl:sticky xl:top-4">
        <CardHeader>
          <CardTitle className="text-base">{t('runInspector.inspector.title')}</CardTitle>
          <CardDescription>{emptyDescription ?? t('runInspector.inspector.empty')}</CardDescription>
        </CardHeader>
      </Card>
    )
  }
  const style = kindStyle(entry.kind)
  const parent = entry.parent_id ? entries.find((candidate) => candidate.id === entry.parent_id) ?? null : null
  const duration = entryDuration(entry)
  const when = (value: string | null) => {
    if (!value) return '—'
    const parsed = new Date(value)
    return Number.isFinite(parsed.getTime()) ? parsed.toLocaleString(locale) : '—'
  }
  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden">
      <CardHeader className="shrink-0 gap-2 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="truncate text-base" title={entry.name}>{entry.name}</CardTitle>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${style.badge}`}>{kindLabel(entry.kind)}</span>
              <Badge variant={isFailed(entry.status) ? 'destructive' : 'secondary'}>{localizedStatus(entry.status)}</Badge>
              {entry.model && <span className="font-mono">{entry.model}</span>}
              <span className="font-mono tabular-nums">{formatMs(duration)}</span>
            </div>
          </div>
        </div>
        <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
          <TabsList>
            <TabsTrigger value="summary">{t('runInspector.inspector.summary')}</TabsTrigger>
            <TabsTrigger value="preview">{t('runInspector.inspector.preview')}</TabsTrigger>
            <TabsTrigger value="raw">{t('runInspector.inspector.raw')}</TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'summary' ? (
          <SummaryView
            entry={entry}
            parent={parent}
            entries={entries}
            when={when}
            localizedStatus={localizedStatus}
            kindLabel={kindLabel}
            onSelectEntry={onSelectEntry}
            payload={payloadState.payload}
            payloadLoading={payloadState.loading}
            payloadFailed={payloadState.failed}
          />
        ) : (
          <PayloadInspector
            entry={entry}
            source={source}
            runId={runId}
            raw={tab === 'raw'}
            payload={payloadState.payload}
            loading={payloadState.loading}
            failed={payloadState.failed}
            onRetry={payloadState.retry}
          />
        )}
      </CardContent>
    </Card>
  )
}

function SummaryView({
  entry,
  parent,
  entries,
  when,
  localizedStatus,
  kindLabel,
  onSelectEntry,
  payload,
  payloadLoading,
  payloadFailed,
}: {
  entry: TrajectoryEntry
  parent: TrajectoryEntry | null
  entries: TrajectoryEntry[]
  when: (value: string | null) => string
  localizedStatus: (status: string) => string
  kindLabel: (kind: string) => string
  onSelectEntry: (id: string) => void
  payload: TrajectoryEntryDetail | null
  payloadLoading: boolean
  payloadFailed: boolean
}) {
  const t = useTranslations('dashboard.observability')
  const tokenEntries = entry.token_usage ? Object.entries(entry.token_usage) : []
  const payloadState = entry.payload_state === 'recorded'
    ? t('runInspector.inspector.recorded')
    : entry.payload_state === 'partial'
      ? t('runInspector.inspector.partialState')
      : t('runInspector.inspector.unrecordedState')
  const linked = (toolCallId: string) => {
    const candidates = entries.filter((candidate) => candidate.id !== entry.id && candidate.tool_call_ids.includes(toolCallId))
    return candidates.find((candidate) => candidate.kind === 'tool' || candidate.kind === 'retrieval') ?? candidates[0] ?? null
  }
  return (
    <dl className="space-y-3 text-sm">
      <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
        <Field label={t('runInspector.inspector.stepId')}><span className="break-all font-mono text-xs">{entry.id}</span></Field>
        <Field label={t('runInspector.inspector.kind')}>{kindLabel(entry.kind)}</Field>
        <Field label={t('runInspector.inspector.status')}>{localizedStatus(entry.status)}</Field>
        <Field label={t('runInspector.inspector.payloadState')}>{payloadState}</Field>
        <Field label={t('runInspector.inspector.started')}>{when(entry.started_at)}</Field>
        <Field label={t('runInspector.inspector.finished')}>{when(entry.finished_at)}</Field>
        <Field label={t('runInspector.inspector.duration')}>{formatMs(entryDuration(entry))}</Field>
        <Field label={t('runInspector.inspector.model')}>{entry.model ?? '—'}</Field>
      </div>
      <Field label={t('runInspector.inspector.parent')}>
        {parent ? (
          <button type="button" title={parent.id} className="text-left font-medium underline-offset-2 hover:underline" onClick={() => onSelectEntry(parent.id)}>
            {parent.name}
          </button>
        ) : t('runInspector.inspector.root')}
      </Field>
      <Field label={t('runInspector.inspector.tokens')}>
        {tokenEntries.length ? (
          <span className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs">
            {tokenEntries.map(([key, value]) => <span key={key}>{key}: {value}</span>)}
          </span>
        ) : '—'}
      </Field>
      <Field label={t('runInspector.inspector.toolCalls')}>
        {entry.tool_call_ids.length ? (
          <span className="flex flex-wrap gap-1.5">
            {entry.tool_call_ids.map((toolCallId) => {
              const target = linked(toolCallId)
              return target ? (
                <button key={toolCallId} type="button" className="rounded border px-1.5 py-0.5 font-mono text-xs hover:bg-muted" onClick={() => onSelectEntry(target.id)}>
                  {toolCallId}
                </button>
              ) : <span key={toolCallId} className="rounded border px-1.5 py-0.5 font-mono text-xs text-muted-foreground">{toolCallId}</span>
            })}
          </span>
        ) : t('runInspector.inspector.noToolCalls')}
      </Field>
      <Field label={t('runInspector.inspector.preview')}>
        <span className="block whitespace-pre-wrap break-words text-xs text-muted-foreground">{entry.preview ?? t('runInspector.inspector.noPreview')}</span>
      </Field>
      <Field label={t('runInspector.inspector.payloadPreview')}>
        {payloadLoading ? (
          <span className="text-xs text-muted-foreground">{t('runInspector.inspector.contextLoading')}</span>
        ) : payloadFailed ? (
          <span className="text-xs text-muted-foreground">{t('runInspector.inspector.contextUnavailable')}</span>
        ) : payload ? (
          <PayloadExcerpt payload={payload} />
        ) : (
          <span className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</span>
        )}
      </Field>
    </dl>
  )
}

function PayloadExcerpt({ payload }: { payload: TrajectoryEntryDetail }) {
  const t = useTranslations('dashboard.observability')
  const input = isRecord(payload.input) ? payload.input : null
  const output = isRecord(payload.output) ? payload.output : null
  const chunks: string[] = []
  if (payload.kind === 'model') {
    const messages = input && Array.isArray(input.messages) ? input.messages : []
    const recent = messages.filter((message) => isRecord(message) && message.content != null).slice(-2)
    for (const message of recent) {
      chunks.push(`${isRecord(message) && typeof message.role === 'string' ? message.role : 'message'}: ${formatText(isRecord(message) ? message.content : message)}`)
    }
    if (output?.content != null) chunks.push(`assistant: ${formatText(output.content)}`)
  } else if (payload.kind === 'tool' || payload.kind === 'retrieval') {
    if (input?.arguments != null) chunks.push(formatText(input.arguments))
    if (output?.model_input != null) chunks.push(formatText(output.model_input))
    else if (output?.display != null) chunks.push(formatText(output.display))
    else if (output) chunks.push(formatText(output))
  } else if (payload.kind === 'workflow_node') {
    if (input?.inputs != null) chunks.push(formatText(input.inputs))
    else if (typeof input?.inputs_storage_key === 'string') chunks.push(`${t('runInspector.inspector.storedUnavailable')}: ${input?.inputs_storage_key}`)
    if (output?.outputs != null) chunks.push(formatText(output.outputs))
    else if (typeof output?.outputs_storage_key === 'string') chunks.push(`${t('runInspector.inspector.storedUnavailable')}: ${output?.outputs_storage_key}`)
  }
  if (!chunks.length) return <span className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</span>
  return <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/20 p-2 text-xs">{chunks.join('\n\n')}</pre>
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 min-w-0 break-words">{children}</dd>
    </div>
  )
}

function PayloadInspector({
  entry,
  source,
  runId,
  raw,
  payload,
  loading,
  failed,
  onRetry,
}: {
  entry: TrajectoryEntry
  source: ObservabilitySource
  runId: string
  raw: boolean
  payload: TrajectoryEntryDetail | null
  loading: boolean
  failed: boolean
  onRetry: () => void
}) {
  const t = useTranslations('dashboard.observability')
  if (loading) return <div className="h-28 animate-pulse rounded bg-muted/40" />
  if (failed) {
    return (
      <div role="alert" className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <p>{t('runInspector.inspector.loadError')}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>{t('runInspector.inspector.retry')}</Button>
      </div>
    )
  }
  if (!payload) return null

  if (raw) {
    const hasPayload = payload.input != null || payload.output != null
    return (
      <div className="space-y-3">
        <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.rawNote')}</p>
        {payload.partial && <PartialNotice />}
        {!payload.recorded && <UnrecordedNotice entry={entry} source={source} runId={runId} />}
        {hasPayload ? (
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/20 p-3 text-xs">
            {JSON.stringify({ input: payload.input ?? null, output: payload.output ?? null }, null, 2)}
          </pre>
        ) : !payload.recorded ? null : <p className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {payload.partial && <PartialNotice />}
      {!payload.recorded && <UnrecordedNotice entry={entry} source={source} runId={runId} />}
      {(payload.recorded || payload.input != null) && (
        <PayloadSection title={t('runInspector.inspector.input')} value={payload.input} kind={entry.kind} direction="input" />
      )}
      {(payload.recorded || payload.output != null) && (
        <PayloadSection title={t('runInspector.inspector.output')} value={payload.output} kind={entry.kind} direction="output" />
      )}
    </div>
  )
}

function PartialNotice() {
  const t = useTranslations('dashboard.observability')
  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2.5 text-xs text-amber-800 dark:text-amber-200">
      {t('runInspector.inspector.partial')}
    </div>
  )
}

function UnrecordedNotice({
  entry,
  source,
  runId,
}: {
  entry: TrajectoryEntry
  source: ObservabilitySource
  runId: string
}) {
  const t = useTranslations('dashboard.observability')
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-dashed p-3 text-sm">
        <p className="font-medium">{t('runInspector.inspector.unrecorded')}</p>
        <p className="mt-1 text-xs text-muted-foreground">{t('runInspector.inspector.unrecordedHint')}</p>
      </div>
      {entry.kind === 'tool' && entry.tool_call_ids.length > 0 && (
        <LegacyToolPayload key={`${source}:${runId}:${entry.tool_call_ids[0]}`} source={source} runId={runId} toolCallId={entry.tool_call_ids[0]} />
      )}
    </div>
  )
}

function LegacyToolPayload({ source, runId, toolCallId }: { source: ObservabilitySource; runId: string; toolCallId: string }) {
  const t = useTranslations('dashboard.observability')
  const [payload, setPayload] = React.useState<ToolPayloadDetail | null>(null)
  const [failed, setFailed] = React.useState(false)
  React.useEffect(() => {
    let active = true
    setPayload(null)
    setFailed(false)
    observabilityApi.getRunToolPayload(source, runId, toolCallId)
      .then((response) => { if (active) setPayload(response) })
      .catch(() => { if (active) setFailed(true) })
    return () => { active = false }
  }, [source, runId, toolCallId])
  if (failed) return <p className="text-xs text-destructive">{t('runInspector.inspector.loadError')}</p>
  if (!payload) return <div className="h-16 animate-pulse rounded bg-muted/40" />
  if (!payload.recorded) return <p className="text-xs text-muted-foreground">{t('runInspector.inspector.legacyUnavailable')}</p>
  return (
    <div className="space-y-2 rounded-md border bg-muted/10 p-3">
      <p className="text-xs font-medium">{t('runInspector.inspector.legacyToolPayload')}</p>
      <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.legacyToolHint')}</p>
      {payload.model_input && <RawBlock label={t('runInspector.inspector.modelResult')} text={payload.model_input} />}
      {payload.display && <RawBlock label={t('runInspector.inspector.displayResult')} text={payload.display} />}
    </div>
  )
}

function PayloadSection({ title, value, kind, direction }: { title: string; value: unknown; kind: string; direction: 'input' | 'output' }) {
  const t = useTranslations('dashboard.observability')
  return (
    <section className="space-y-2">
      <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</h4>
      {value == null ? (
        <p className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</p>
      ) : kind === 'model' && isRecord(value) ? (
        direction === 'input' ? <ModelInputView value={value} /> : <ModelOutputView value={value} />
      ) : kind === 'tool' || kind === 'retrieval' ? (
        <ToolPayloadView value={value} direction={direction} />
      ) : kind === 'workflow_node' && isRecord(value) ? (
        <WorkflowNodeView value={value} direction={direction} />
      ) : (
        <RawBlock text={formatText(value)} />
      )}
    </section>
  )
}

function RawBlock({ label, text }: { label?: React.ReactNode; text: string }) {
  return (
    <div className="space-y-1">
      {label && <p className="text-[11px] text-muted-foreground">{label}</p>}
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/20 p-2.5 text-xs">{text}</pre>
    </div>
  )
}

function ToolDefinitionList({ values }: { values: unknown[] }) {
  const name = (tool: unknown) => {
    if (!isRecord(tool)) return null
    if (typeof tool.name === 'string') return tool.name
    return isRecord(tool.function) && typeof tool.function.name === 'string' ? tool.function.name : null
  }
  return (
    <div className="space-y-1">
      {values.map((tool, index) => typeof tool === 'string' ? (
        <span key={index} className="inline-block rounded border bg-muted/30 px-1.5 py-0.5 font-mono text-[11px]">{tool}</span>
      ) : (
        <details key={index} className="rounded border bg-muted/10 px-2 py-1">
          <summary className="cursor-pointer font-mono text-[11px]">
            {name(tool) ?? `tool ${index + 1}`}
          </summary>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words text-[11px]">{formatText(tool)}</pre>
        </details>
      ))}
    </div>
  )
}

function ModelInputView({ value }: { value: Record<string, unknown> }) {
  const t = useTranslations('dashboard.observability')
  const messages = Array.isArray(value.messages) ? value.messages : null
  const tools = Array.isArray(value.tools) ? value.tools : null
  const options = isRecord(value.options) ? value.options : null
  const limits = isRecord(value.limits) ? value.limits : null
  const meta = [value.model, value.provider, value.streaming === true ? 'streaming' : null].filter((item): item is string => typeof item === 'string')
  return (
    <div className="space-y-3">
      {(typeof value.model_id === 'string' || meta.length > 0 || value.fallback === true) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {typeof value.model_id === 'string' && <Badge variant="outline" className="font-mono text-[10px]">{value.model_id}</Badge>}
          {meta.map((item) => <Badge key={item} variant="outline" className="font-mono text-[10px]">{item}</Badge>)}
          {value.fallback === true && <Badge variant="secondary" className="text-[10px]">{t('runInspector.inspector.fallbackInvocation')}</Badge>}
        </div>
      )}
      {value.scope === 'application' && (
        <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.modelScope')}</p>
      )}
      {messages && (
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium text-muted-foreground">{t('runInspector.inspector.messages')} · {messages.length}</p>
          {messages.map((message, index) => isRecord(message) ? (
            <div key={index} className="rounded border bg-muted/10 p-2">
              <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="rounded bg-foreground/10 px-1.5 py-0.5 font-mono">{typeof message.role === 'string' ? message.role : 'unknown'}</span>
                {typeof message.tool_call_id === 'string' && <span className="font-mono text-muted-foreground">tool_call_id: {message.tool_call_id}</span>}
                {typeof message.name === 'string' && <span className="font-mono text-muted-foreground">name: {message.name}</span>}
              </div>
              {message.content != null && <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs">{formatText(message.content)}</pre>}
              {Array.isArray(message.tool_calls) && message.tool_calls.length > 0 && <RawBlock label={t('runInspector.inspector.toolCalls')} text={formatText(message.tool_calls)} />}
            </div>
          ) : <RawBlock key={index} text={formatText(message)} />)}
        </div>
      )}
      {tools && tools.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground">{t('runInspector.inspector.tools')} · {tools.length}</p>
          <ToolDefinitionList values={tools} />
        </div>
      )}
      {options && Object.keys(options).length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground">{t('runInspector.inspector.options')}</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/20 p-2 text-xs">{formatText(options)}</pre>
        </div>
      )}
      {limits && Object.keys(limits).length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground">{t('runInspector.inspector.limits')}</p>
          <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.limitsNote')}</p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded border bg-muted/20 p-2 text-xs">{formatText(limits)}</pre>
        </div>
      )}
    </div>
  )
}

function ModelOutputView({ value }: { value: Record<string, unknown> }) {
  const t = useTranslations('dashboard.observability')
  const toolCalls = Array.isArray(value.tool_calls) ? value.tool_calls : []
  return (
    <div className="space-y-2">
      {value.error != null && (
        <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs">
          <p className="font-medium text-destructive">{t('runInspector.inspector.modelError')}</p>
          <pre className="mt-1 whitespace-pre-wrap break-words">{formatText(value.error)}</pre>
        </div>
      )}
      {value.content != null && <RawBlock label={t('runInspector.inspector.content')} text={formatText(value.content)} />}
      {value.reasoning != null && <RawBlock label={t('runInspector.inspector.reasoning')} text={formatText(value.reasoning)} />}
      {toolCalls.length > 0 && (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground">{t('runInspector.inspector.toolCalls')} · {toolCalls.length}</p>
          {toolCalls.map((call, index) => isRecord(call) ? (
            <div key={index} className="rounded border bg-muted/10 p-2">
              <div className="flex flex-wrap gap-1.5 text-[11px]">
                <span className="font-mono font-medium">{typeof call.name === 'string' ? call.name : 'unknown'}</span>
                {typeof call.id === 'string' && <span className="font-mono text-muted-foreground">{call.id}</span>}
              </div>
              {call.arguments != null && <RawBlock label={t('runInspector.inspector.toolArguments')} text={formatText(call.arguments)} />}
            </div>
          ) : <RawBlock key={index} text={formatText(call)} />)}
        </div>
      )}
      {value.finish_reason != null && (
        <p className="text-xs text-muted-foreground">{t('runInspector.inspector.finishReason')}: <span className="font-mono">{formatText(value.finish_reason)}</span></p>
      )}
      {value.content == null && value.reasoning == null && !toolCalls.length && value.finish_reason == null && value.error == null && (
        <p className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</p>
      )}
    </div>
  )
}

function ToolPayloadView({ value, direction }: { value: unknown; direction: 'input' | 'output' }) {
  const t = useTranslations('dashboard.observability')
  if (!isRecord(value)) return <RawBlock text={formatText(value)} />
  if (direction === 'input') {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {typeof value.name === 'string' && <Badge variant="outline" className="font-mono">{value.name}</Badge>}
          {typeof value.tool_call_id === 'string' && <span className="font-mono text-muted-foreground">{value.tool_call_id}</span>}
        </div>
        {value.arguments != null && <RawBlock label={t('runInspector.inspector.toolArguments')} text={formatText(value.arguments)} />}
      </div>
    )
  }
  if (typeof value.model_input === 'string' || typeof value.display === 'string') {
    return (
      <div className="space-y-2">
        {typeof value.model_input === 'string' && <RawBlock label={t('runInspector.inspector.modelResult')} text={value.model_input} />}
        {typeof value.display === 'string' && <RawBlock label={t('runInspector.inspector.displayResult')} text={value.display} />}
        {value.partial === true && <PartialNotice />}
      </div>
    )
  }
  return <RawBlock text={formatText(value)} />
}

function WorkflowNodeView({ value, direction }: { value: Record<string, unknown>; direction: 'input' | 'output' }) {
  const t = useTranslations('dashboard.observability')
  if (direction === 'input') {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5 text-xs">
          {typeof value.node_type === 'string' && <Badge variant="outline">{t('runInspector.inspector.nodeType')}: {value.node_type}</Badge>}
          {typeof value.node_name === 'string' && <span className="text-muted-foreground">{value.node_name}</span>}
        </div>
        {typeof value.inputs_storage_key === 'string' && (
          <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.storedUnavailable')}: <span className="break-all font-mono">{value.inputs_storage_key}</span></p>
        )}
        {value.config != null && <RawBlock label={t('runInspector.inspector.config')} text={formatText(value.config)} />}
        {value.inputs != null && <RawBlock label={t('runInspector.inspector.inputs')} text={formatText(value.inputs)} />}
      </div>
    )
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5 text-xs">
        {typeof value.model_used === 'string' && <Badge variant="outline">{t('runInspector.inspector.modelUsed')}: {value.model_used}</Badge>}
        {value.token_usage != null && <span className="text-muted-foreground">{t('runInspector.inspector.tokens')}: {formatText(value.token_usage)}</span>}
        {value.error_type != null && <Badge variant="destructive">{t('runInspector.inspector.errorType')}: {formatText(value.error_type)}</Badge>}
      </div>
      {value.error_message != null && (
        <p className="text-[11px] text-destructive">{t('runInspector.inspector.errorMessage')}: {formatText(value.error_message)}</p>
      )}
      {typeof value.outputs_storage_key === 'string' && (
        <p className="text-[11px] text-muted-foreground">{t('runInspector.inspector.storedUnavailable')}: <span className="break-all font-mono">{value.outputs_storage_key}</span></p>
      )}
      {value.outputs != null ? <RawBlock label={t('runInspector.inspector.outputs')} text={formatText(value.outputs)} /> : <p className="text-xs text-muted-foreground">{t('runInspector.inspector.noData')}</p>}
    </div>
  )
}
