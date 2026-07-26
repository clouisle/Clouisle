'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { ArrowLeft, ChevronDown, ChevronUp, FileText, HelpCircle, Loader2, Search, Send, Settings2 } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
import type {
  EvaluationCaseInput,
  EvaluationDataset,
  EvaluationRun,
  EvaluationRunConfig,
  KnowledgeBase,
  KnowledgeBaseSettings,
  SearchMode,
  SearchParams,
  SearchResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatDuration } from '@/lib/utils'

const MDPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), { ssr: false })

type RetrievalApi = {
  getKnowledgeBase(id: string): Promise<KnowledgeBase>
  search(id: string, params: SearchParams): Promise<SearchResponse>
  updateKnowledgeBase(id: string, data: { settings: KnowledgeBaseSettings }): Promise<KnowledgeBase>
  listEvaluationDatasets(kbId: string): Promise<EvaluationDataset[]>
  createEvaluationDataset(kbId: string, data: { name: string; description?: string | null; cases?: EvaluationCaseInput[] }): Promise<EvaluationDataset>
  updateEvaluationDataset(kbId: string, datasetId: string, data: { cases: EvaluationCaseInput[] }): Promise<EvaluationDataset>
  importEvaluationDataset(kbId: string, datasetId: string, file: File): Promise<EvaluationDataset>
  startEvaluationRun(kbId: string, datasetId: string, config: EvaluationRunConfig): Promise<EvaluationRun>
  listEvaluationRuns(kbId: string, datasetId: string): Promise<EvaluationRun[]>
  getEvaluationRun(kbId: string, datasetId: string, runId: string): Promise<EvaluationRun>
  cancelEvaluationRun(kbId: string, datasetId: string, runId: string): Promise<EvaluationRun>
}

type Config = {
  search_mode: SearchMode
  top_k: number
  threshold: number
  dense_weight: number
  lexical_weight: number
  rrf_k: number
  rerank_enabled: boolean
  rerank_candidate_k: number
  rerank_score_threshold: number | null
}

type Preset = { name: string; config: Config }
type Grade = 'relevant' | 'partial' | 'irrelevant'
type RetrievalFailure =
  | 'request'
  | 'configuration_mismatch'
  | 'provider_authentication'
  | 'quota_or_rate_limit'
  | 'model_configuration'
  | 'lexical_unavailable'
  | 'provider_unavailable'
  | 'unknown'

const RETRIEVAL_FAILURES = new Set<RetrievalFailure>([
  'configuration_mismatch',
  'provider_authentication',
  'quota_or_rate_limit',
  'model_configuration',
  'lexical_unavailable',
  'provider_unavailable',
  'unknown',
])

function retrievalFailure(reason: unknown): RetrievalFailure {
  if (!(reason instanceof ApiError)) return 'unknown'
  if (reason.code === -1) return 'request'
  if (!reason.data || typeof reason.data !== 'object') return 'unknown'
  const category = (reason.data as Record<string, unknown>).retrieval_error_category
  return typeof category === 'string' && RETRIEVAL_FAILURES.has(category as RetrievalFailure)
    ? category as RetrievalFailure
    : 'unknown'
}

function retrievalStage(reason: unknown): string | null {
  if (!(reason instanceof ApiError)) return null
  if (!reason.data || typeof reason.data !== 'object') return null
  const stage = (reason.data as Record<string, unknown>).stage
  return typeof stage === 'string' ? stage : null
}

// Stage-less keys are camelCase in the catalog, so every snake_case segment is capitalized
function retrievalErrorKey(failure: RetrievalFailure, stage: string | null): string {
  if (stage) return `retrievalError_${stage}_${failure}`
  const suffix = failure.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('')
  return `retrievalError${suffix}`
}

interface RetrievalLabProps {
  knowledgeBaseId: string
  api: RetrievalApi
  backHref: string
  canUpdate: boolean
  authenticatedMarkdown?: boolean
  onLoadError?: () => void
}

const DEFAULT_CONFIG: Config = {
  search_mode: 'hybrid', top_k: 5, threshold: 0,
  dense_weight: 1, lexical_weight: 1, rrf_k: 60,
  rerank_enabled: true, rerank_candidate_k: 10, rerank_score_threshold: null,
}

function AuthenticatedMarkdownImage({ src = '', alt = '' }: { src?: string; alt?: string }) {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null)
  const [failed, setFailed] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    setFailed(false)
    if (!src || src.startsWith('data:') || src.startsWith('javascript:')) {
      setObjectUrl(null)
      setFailed(Boolean(src))
      return
    }
    if (!src.startsWith('/api/v1/knowledge-bases/')) {
      setObjectUrl(src)
      return
    }
    const controller = new AbortController()
    let currentObjectUrl: string | null = null
    const token = localStorage.getItem('access_token')
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : undefined, signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('image_load_failed')
        return response.blob()
      })
      .then(blob => {
        if (cancelled) return
        currentObjectUrl = URL.createObjectURL(blob)
        setObjectUrl(currentObjectUrl)
      })
      .catch(error => {
        if (!cancelled && (error as Error).name !== 'AbortError') setFailed(true)
      })
    return () => {
      cancelled = true
      controller.abort()
      if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl)
    }
  }, [src])

  return failed || !objectUrl
    ? <span className="text-muted-foreground">{alt || src}</span>
    : <img src={objectUrl} alt={alt} loading="lazy" />
}

function Highlight({ text, query }: { text: string; query: string }) {
  const terms = query.trim().split(/\s+/).filter(Boolean).sort((a, b) => b.length - a.length)
  if (!terms.length) return text
  const escaped = terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  return <>{text.split(regex).map((part, index) =>
    terms.some(term => term.toLocaleLowerCase() === part.toLocaleLowerCase())
      ? <mark key={index} className="rounded bg-yellow-200 px-0.5 text-inherit dark:bg-yellow-800">{part}</mark>
      : part
  )}</>
}

function formatScore(value?: number | null) {
  return value == null ? '—' : String(Number(value.toFixed(4)))
}

function translateFinalScoreStage(stage: string | undefined | null, t: (key: string) => string): string {
  if (!stage) return '—'
  const key = `finalScoreStage${stage.charAt(0).toUpperCase()}${stage.slice(1)}`
  return t(key)
}

function translateSearchType(type: string | undefined | null, t: (key: string) => string): string {
  if (!type) return ''
  // Handle compound types like "hybrid+rerank"
  const parts = type.split('+')
  const translated = parts.map(part => {
    const key = `searchType${part.charAt(0).toUpperCase()}${part.slice(1)}`
    try {
      return t(key)
    } catch {
      return part
    }
  })
  return translated.join('+')
}

function runConfig(config: Config, hasRerankModel: boolean): EvaluationRunConfig {
  const rerank = hasRerankModel && config.rerank_enabled
  return {
    search_mode: config.search_mode,
    top_k: config.top_k,
    score_threshold: config.threshold,
    dense_weight: config.dense_weight,
    lexical_weight: config.lexical_weight,
    rrf_k: config.rrf_k,
    rerank_enabled: rerank,
    rerank_candidate_k: rerank ? Math.max(config.top_k, config.rerank_candidate_k) : config.top_k,
    rerank_score_threshold: rerank ? config.rerank_score_threshold : null,
  }
}

function configParams(query: string, config: Config, hasRerankModel: boolean): SearchParams {
  const snapshot = runConfig(config, hasRerankModel)
  return {
    query,
    ...snapshot,
    threshold: snapshot.score_threshold,
  }
}

type CaseDraft = { query: string; chunkRelevance: string; documentRelevance: string; expectedEmpty: boolean }
const EMPTY_CASE: CaseDraft = { query: '', chunkRelevance: '{}', documentRelevance: '{}', expectedEmpty: false }

export function BatchEvaluation({ knowledgeBaseId, api, config, hasRerankModel }: {
  knowledgeBaseId: string
  api: RetrievalApi
  config: Config
  hasRerankModel: boolean
}) {
  const t = useTranslations('knowledgeBases')
  const [datasets, setDatasets] = React.useState<EvaluationDataset[]>([])
  const [datasetId, setDatasetId] = React.useState('')
  const [datasetName, setDatasetName] = React.useState('')
  const [datasetDescription, setDatasetDescription] = React.useState('')
  const [cases, setCases] = React.useState<CaseDraft[]>([])
  const [runs, setRuns] = React.useState<EvaluationRun[]>([])
  const [selectedRun, setSelectedRun] = React.useState<EvaluationRun | null>(null)
  const [failedOnly, setFailedOnly] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  const loadError = t('batchLoadError')

  const selectDataset = React.useCallback((id: string, available: EvaluationDataset[]) => {
    const dataset = available.find(item => item.id === id)
    setDatasetId(id)
    setCases(dataset?.cases.map(item => ({
      query: item.query,
      chunkRelevance: JSON.stringify(item.chunk_relevance),
      documentRelevance: JSON.stringify(item.document_relevance),
      expectedEmpty: item.expected_empty,
    })) ?? [])
    setSelectedRun(null)
    setRuns([])
    if (id) api.listEvaluationRuns(knowledgeBaseId, id).then(setRuns).catch(() => setError(loadError))
  }, [api, knowledgeBaseId, loadError])

  React.useEffect(() => {
    api.listEvaluationDatasets(knowledgeBaseId).then(items => {
      setDatasets(items)
      if (items[0]) selectDataset(items[0].id, items)
    }).catch(() => setError(loadError))
  }, [api, knowledgeBaseId, loadError, selectDataset])

  React.useEffect(() => {
    if (!selectedRun || !['pending', 'running'].includes(selectedRun.status)) return
    const timer = window.setInterval(() => {
      api.getEvaluationRun(knowledgeBaseId, selectedRun.dataset_id, selectedRun.id).then(run => {
        setSelectedRun(run)
        setRuns(current => current.map(item => item.id === run.id ? run : item))
      }).catch(() => setError(loadError))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [api, knowledgeBaseId, loadError, selectedRun])

  const createDataset = async () => {
    const name = datasetName.trim()
    if (!name) return
    setBusy(true); setError('')
    try {
      const dataset = await api.createEvaluationDataset(knowledgeBaseId, { name, description: datasetDescription.trim() || null })
      const next = [dataset, ...datasets]
      setDatasets(next); setDatasetName(''); setDatasetDescription(''); selectDataset(dataset.id, next)
    } catch { setError(t('batchSaveError')) } finally { setBusy(false) }
  }

  const saveCases = async () => {
    if (!datasetId) return
    setBusy(true); setError('')
    try {
      const parseRelevance = (value: string) => {
        const parsed = JSON.parse(value) as unknown
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' || Object.values(parsed).some(grade => !Number.isInteger(grade) || Number(grade) < 0 || Number(grade) > 3)) throw new Error('invalid relevance')
        return parsed as Record<string, number>
      }
      const payload = cases.map(item => ({
        query: item.query.trim(),
        chunk_relevance: parseRelevance(item.chunkRelevance),
        document_relevance: parseRelevance(item.documentRelevance),
        expected_empty: item.expectedEmpty,
      }))
      if (payload.some(item => !item.query || (item.expected_empty && (Object.keys(item.chunk_relevance).length > 0 || Object.keys(item.document_relevance).length > 0)))) throw new Error('invalid case')
      const dataset = await api.updateEvaluationDataset(knowledgeBaseId, datasetId, { cases: payload })
      setDatasets(current => current.map(item => item.id === dataset.id ? dataset : item))
    } catch { setError(t('batchCaseError')) } finally { setBusy(false) }
  }

  const startRun = async () => {
    if (!datasetId || !cases.length) return
    setBusy(true); setError('')
    try {
      const run = await api.startEvaluationRun(knowledgeBaseId, datasetId, runConfig(config, hasRerankModel))
      setRuns(current => [run, ...current]); setSelectedRun(run)
    } catch { setError(t('batchRunError')) } finally { setBusy(false) }
  }

  const active = selectedRun && ['pending', 'running'].includes(selectedRun.status)
  const results = selectedRun?.case_results.filter(result => !failedOnly || Boolean(result.error_message)) ?? []
  const selectedDataset = datasets.find(dataset => dataset.id === datasetId)
  const caseQueries = new Map(selectedDataset?.cases.map(item => [item.id, item.query]))
  const formatMetric = (value: unknown) => typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)

  const downloadTemplate = (format: 'json' | 'csv') => {
    const template = format === 'json'
      ? JSON.stringify([{
          query: "example query",
          chunk_relevance: { "chunk-id-1": 3, "chunk-id-2": 2 },
          document_relevance: { "doc-id-1": 3 },
          expected_empty: false
        }], null, 2)
      : `query,chunk_relevance,document_relevance,expected_empty
"example query","{""chunk-id-1"":3,""chunk-id-2"":2}","{""doc-id-1"":3}",false`
    const blob = new Blob([template], { type: format === 'json' ? 'application/json' : 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `evaluation-template.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return <section className="min-h-0 flex-1 space-y-3 overflow-auto py-4" aria-labelledby="batch-evaluation-heading">
    <h2 id="batch-evaluation-heading" className="mx-4 font-medium">{t('batchEvaluation')}</h2>
    {error && <p role="alert" className="mx-4 text-sm text-destructive">{error}</p>}

    <Card className="mx-4 py-0">
      <CardHeader className="pb-3 pt-3">
        <strong className="text-sm">{t('datasetManagement')}</strong>
      </CardHeader>
      <CardContent className="space-y-3 p-3 pt-0">
        <div className="grid gap-3 md:grid-cols-[1fr,2fr]">
          <div className="space-y-2">
            <Label className="text-xs">{t('datasetName')}</Label>
            <Input value={datasetName} onChange={event => setDatasetName(event.target.value)} placeholder={t('datasetName')} />
          </div>
          <div className="space-y-2">
            <Label className="text-xs">{t('datasetDescription')}</Label>
            <Input value={datasetDescription} onChange={event => setDatasetDescription(event.target.value)} placeholder={t('datasetDescription')} />
          </div>
        </div>
        <Button onClick={() => void createDataset()} disabled={!datasetName.trim() || busy} size="sm">{t('createDataset')}</Button>

        <div className="space-y-2">
          <Label className="text-xs">{t('datasets')}</Label>
          <Select value={datasetId || '__none__'} onValueChange={value => selectDataset(value === '__none__' ? '' : (value ?? ''), datasets)}>
            <SelectTrigger className="w-full">
              <SelectValue>{selectedDataset?.name ?? t('selectDataset')}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">{t('selectDataset')}</SelectItem>
              {datasets.map(dataset => (
                <SelectItem key={dataset.id} value={dataset.id}>
                  <div className="flex flex-col items-start">
                    <span>{dataset.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {t('datasetStats', {
                        cases: dataset.cases.length,
                        date: new Date(dataset.created_at).toLocaleDateString()
                      })}
                    </span>
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {datasetId && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">{t('importDataset')}</Label>
              <Popover>
                <PopoverTrigger className="h-7 rounded px-2 text-xs hover:bg-muted">
                  {t('downloadTemplate')}
                </PopoverTrigger>
                <PopoverContent className="w-56" align="end">
                  <div className="space-y-2">
                    <Button variant="outline" size="sm" className="w-full justify-start text-xs" onClick={() => downloadTemplate('json')}>
                      <FileText className="mr-2 h-3.5 w-3.5" />
                      JSON {t('downloadTemplate')}
                    </Button>
                    <p className="text-xs text-muted-foreground">{t('templateJsonHint')}</p>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <Input
              type="file"
              accept=".json,.csv,application/json,text/csv"
              onChange={event => {
                const file = event.target.files?.[0]
                if (!file) return
                setBusy(true)
                api.importEvaluationDataset(knowledgeBaseId, datasetId, file)
                  .then(dataset => {
                    setDatasets(current => current.map(item => item.id === dataset.id ? dataset : item))
                    selectDataset(dataset.id, datasets.map(item => item.id === dataset.id ? dataset : item))
                  })
                  .catch(() => setError(t('batchImportError')))
                  .finally(() => setBusy(false))
              }}
            />
          </div>
        )}
      </CardContent>
    </Card>

    {datasetId && (
      <Card className="mx-4 py-0">
        <CardHeader className="pb-3 pt-3">
          <div className="flex items-center justify-between">
            <strong className="text-sm">{t('evaluationCases')}</strong>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {t('datasetStats', { cases: cases.length, date: '' }).split('·')[0].trim()}
              </span>
              <Button variant="outline" size="sm" onClick={() => setCases(current => [...current, { ...EMPTY_CASE }])}>
                {t('addCase')}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-3 pt-0">
          {cases.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">{t('noCasesInDataset')}</p>
          ) : (
            cases.map((item, index) => (
              <fieldset key={index} className="space-y-2 rounded border p-3">
                <legend className="px-1 text-sm font-medium">{t('caseNumber', { number: index + 1 })}</legend>
                <Label className="text-xs">
                  {t('caseQuery')}
                  <Input
                    value={item.query}
                    onChange={event => setCases(current => current.map((value, currentIndex) =>
                      currentIndex === index ? { ...value, query: event.target.value } : value
                    ))}
                    className="mt-1"
                  />
                </Label>
                <div className="grid gap-2 md:grid-cols-2">
                  <Label className="text-xs">
                    {t('chunkRelevance')}
                    <Textarea
                      className="mt-1 min-h-20 font-mono text-xs"
                      value={item.chunkRelevance}
                      onChange={event => setCases(current => current.map((value, currentIndex) =>
                        currentIndex === index ? { ...value, chunkRelevance: event.target.value } : value
                      ))}
                    />
                  </Label>
                  <Label className="text-xs">
                    {t('documentRelevance')}
                    <Textarea
                      className="mt-1 min-h-20 font-mono text-xs"
                      value={item.documentRelevance}
                      onChange={event => setCases(current => current.map((value, currentIndex) =>
                        currentIndex === index ? { ...value, documentRelevance: event.target.value } : value
                      ))}
                    />
                  </Label>
                </div>
                <div className="flex items-center justify-between">
                  <Label className="flex items-center gap-2 text-xs">
                    <Checkbox
                      checked={item.expectedEmpty}
                      onCheckedChange={checked => setCases(current => current.map((value, currentIndex) =>
                        currentIndex === index ? { ...value, expectedEmpty: checked } : value
                      ))}
                    />
                    {t('expectedEmpty')}
                  </Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setCases(current => current.filter((_, currentIndex) => currentIndex !== index))}
                  >
                    {t('removeCase')}
                  </Button>
                </div>
              </fieldset>
            ))
          )}
          <Button onClick={() => void saveCases()} disabled={busy || cases.length === 0} size="sm">
            {t('saveCases')}
          </Button>
        </CardContent>
      </Card>
    )}

    {datasetId && (
      <Card className="mx-4 py-0">
        <CardHeader className="pb-3 pt-3">
          <strong className="text-sm">{t('evaluationRuns')}</strong>
        </CardHeader>
        <CardContent className="space-y-3 p-3 pt-0">
          <div className="rounded border bg-muted/50 p-2">
            <div className="mb-1 text-xs font-medium text-muted-foreground">{t('runConfig')}</div>
            <pre className="overflow-auto text-xs">{JSON.stringify(runConfig(config, hasRerankModel), null, 2)}</pre>
          </div>

          <Button onClick={() => void startRun()} disabled={busy || !cases.length} size="sm">
            {t('startRun')}
          </Button>

          <div className="space-y-2">
            <Label className="text-xs">{t('evaluationRuns')}</Label>
            <Select
              aria-label={t('evaluationRuns')}
              value={selectedRun?.id ?? '__none__'}
              onValueChange={value => setSelectedRun(runs.find(run => run.id === value) ?? null)}
            >
              <SelectTrigger className="w-full">
                <SelectValue>
                  {selectedRun
                    ? `${selectedRun.status} · ${new Date(selectedRun.created_at).toLocaleString()}`
                    : t('selectRun')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">{t('selectRun')}</SelectItem>
                {runs.map(run => (
                  <SelectItem key={run.id} value={run.id}>
                    {run.status} · {new Date(run.created_at).toLocaleString()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedRun && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{selectedRun.status}</Badge>
                {active && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void api.cancelEvaluationRun(knowledgeBaseId, datasetId, selectedRun.id)
                      .then(setSelectedRun)
                      .catch(() => setError(t('batchRunError')))}
                  >
                    {t('cancelRun')}
                  </Button>
                )}
              </div>

              {Object.keys(selectedRun.summary_metrics ?? {}).length > 0 && (
                <div className="grid gap-2 sm:grid-cols-3">
                  {Object.entries(selectedRun.summary_metrics ?? {}).map(([name, value]) => (
                    <div key={name} className="rounded border bg-muted/50 p-2">
                      <div className="text-xs text-muted-foreground">{name}</div>
                      <strong className="text-sm">{formatMetric(value)}</strong>
                    </div>
                  ))}
                </div>
              )}

              <Label className="flex items-center gap-2 text-xs">
                <Checkbox checked={failedOnly} onCheckedChange={setFailedOnly} />
                {t('failedCasesOnly')}
              </Label>

              <div className="space-y-2">
                {results.map(result => (
                  <div key={result.id} className="rounded border p-3 text-sm">
                    <div className="mb-1 font-medium">{result.case_snapshot?.query ?? caseQueries.get(result.case_id) ?? result.case_id}</div>
                    {result.error_message && (
                      <p className="mb-1 text-xs text-destructive">{result.error_message}</p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {Object.entries(result.metrics).map(([name, value]) => `${name}: ${formatMetric(value)}`).join(' · ')} · {formatDuration(result.latency_ms)}
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    )}
  </section>
}

export function RetrievalLab({ knowledgeBaseId, api, backHref, canUpdate, authenticatedMarkdown = false, onLoadError }: RetrievalLabProps) {
  const t = useTranslations('knowledgeBases')
  const { resolvedTheme } = useTheme()
  const [knowledgeBase, setKnowledgeBase] = React.useState<KnowledgeBase | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [query, setQuery] = React.useState('')
  const [configA, setConfigA] = React.useState(DEFAULT_CONFIG)
  const [configB, setConfigB] = React.useState({ ...DEFAULT_CONFIG, search_mode: 'vector' as SearchMode, rerank_enabled: false })
  const [compare, setCompare] = React.useState(false)
  const [responses, setResponses] = React.useState<{ a?: SearchResponse; b?: SearchResponse }>({})
  const [searching, setSearching] = React.useState(false)
  const [searched, setSearched] = React.useState(false)
  const [updateError, setUpdateError] = React.useState(false)
  const [showConfig, setShowConfig] = React.useState(false)
  const [advanced, setAdvanced] = React.useState(false)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())
  const [grades, setGrades] = React.useState<Record<string, Grade>>({})
  const [presets, setPresets] = React.useState<Preset[]>([])
  const [presetName, setPresetName] = React.useState('')
  const [selectedPreset, setSelectedPreset] = React.useState('')
  const [batchMode, setBatchMode] = React.useState(false)

  const storageKey = `retrieval-lab:${knowledgeBaseId}`
  React.useEffect(() => {
    api.getKnowledgeBase(knowledgeBaseId).then(kb => {
      setKnowledgeBase(kb)
      setConfigA({
        ...DEFAULT_CONFIG,
        rerank_enabled: kb.settings?.rerank_enabled ?? true,
        rerank_candidate_k: kb.settings?.rerank_candidate_k ?? 10,
        rerank_score_threshold: kb.settings?.rerank_score_threshold ?? null,
      })
      try {
        const local = JSON.parse(localStorage.getItem(storageKey) || '{}') as { presets?: Preset[]; grades?: Record<string, Grade> }
        setPresets(local.presets ?? [])
        setGrades(local.grades ?? {})
      } catch {
        localStorage.removeItem(storageKey)
      }
    }).catch(() => onLoadError?.()).finally(() => setLoading(false))
  }, [api, knowledgeBaseId, onLoadError, storageKey])

  const persist = (nextPresets = presets, nextGrades = grades) =>
    localStorage.setItem(storageKey, JSON.stringify({ presets: nextPresets, grades: nextGrades }))

  const runSearch = async () => {
    const trimmed = query.trim()
    if (!trimmed) return
    setSearching(true)
    setSearched(true)
    setResponses({})
    try {
      const [a, b] = await Promise.allSettled([
        api.search(knowledgeBaseId, configParams(trimmed, configA, Boolean(knowledgeBase?.rerank_model))),
        compare ? api.search(knowledgeBaseId, configParams(trimmed, configB, Boolean(knowledgeBase?.rerank_model))) : Promise.resolve(undefined),
      ])
      const next = {
        a: a.status === 'fulfilled' ? a.value : undefined,
        b: b.status === 'fulfilled' ? b.value : undefined,
      }
      setResponses(next)

      // Handle failures with stage-aware toast notifications
      if (a.status === 'rejected') {
        const failure = retrievalFailure(a.reason)
        const stage = retrievalStage(a.reason)
        const label = compare ? 'A: ' : ''
        toast.error(label + t(retrievalErrorKey(failure, stage)))
      }
      if (compare && b.status === 'rejected') {
        const failure = retrievalFailure(b.reason)
        const stage = retrievalStage(b.reason)
        toast.error('B: ' + t(retrievalErrorKey(failure, stage)))
      }

      const first = next.a?.results[0] ?? next.b?.results[0]
      setExpanded(new Set(first ? [first.chunk_id] : []))
    } finally {
      setSearching(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void runSearch()
    }
  }

  const savePreset = () => {
    const name = presetName.trim()
    if (!name) return
    const next = [...presets.filter(preset => preset.name !== name), { name, config: configA }]
    setPresets(next)
    setSelectedPreset(name)
    setPresetName('')
    persist(next)
  }

  const applyPreset = async () => {
    const preset = presets.find(item => item.name === selectedPreset)
    if (!preset || !canUpdate || !window.confirm(t('applyPresetConfirm', { name: preset.name }))) return
    setUpdateError(false)
    try {
      await api.updateKnowledgeBase(knowledgeBaseId, {
        settings: {
          ...knowledgeBase?.settings,
          rerank_enabled: preset.config.rerank_enabled,
          rerank_candidate_k: preset.config.rerank_candidate_k,
          rerank_score_threshold: preset.config.rerank_score_threshold,
        },
      })
    } catch {
      setUpdateError(true)
    }
  }

  const setGrade = (chunkId: string, grade: Grade) => {
    const next = { ...grades, [chunkId]: grade }
    setGrades(next)
    persist(presets, next)
  }

  if (loading) return <div className="flex h-full items-center justify-center"><Loader2 className="h-8 w-8 animate-spin" /></div>

  const aRanks = new Map(responses.a?.results.map((result, index) => [result.chunk_id, index + 1]))
  const bRanks = new Map(responses.b?.results.map((result, index) => [result.chunk_id, index + 1]))
  const overlap = responses.a && responses.b
    ? responses.a.results.filter(result => bRanks.has(result.chunk_id)).length
    : 0

  const renderResults = (response: SearchResponse | undefined, side: 'a' | 'b') => {
    if (!response) return null
    const otherRanks = side === 'a' ? bRanks : aRanks
    return <div className="min-w-0 space-y-2">
      {response.timings?.length > 0 && <p className="text-xs text-muted-foreground">{t('stageTimings')}: {response.timings.map(timing => `${timing.stage} ${formatDuration(timing.latency_ms)}`).join(' · ')}</p>}
      {response.diagnostics?.length > 0 && <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
        <strong>{t('diagnostics')}</strong>: {response.diagnostics.map(item => `${item.code}${item.stage ? ` (${item.stage})` : ''}${item.latency_ms !== undefined ? ` ${formatDuration(item.latency_ms)}` : ''}${item.detail ? ` — ${item.detail}` : ''}`).join('; ')}
      </div>}
      {response.results.map((result, index) => {
        const key = `${side}:${result.chunk_id}`
        const open = expanded.has(key)
        const movement = otherRanks.get(result.chunk_id)
        return <Card key={result.chunk_id} className="mb-3 last:mb-0 py-0">
          <CardHeader className="cursor-pointer p-3" onClick={() => setExpanded(current => {
            const next = new Set(current)
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
          })}>
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="flex min-w-0 items-center gap-2"><Badge variant="outline">#{index + 1}</Badge><FileText className="h-3.5 w-3.5" /><strong className="truncate">{result.document_name}</strong></span>
              <span className="flex items-center gap-2"><Badge>{translateSearchType(result.search_type, t) || translateFinalScoreStage(result.final_score_stage, t) || t('unknownChannel')}</Badge>{movement && <span>{movement - (index + 1) > 0 ? '↑' : movement - (index + 1) < 0 ? '↓' : '→'} {Math.abs(movement - (index + 1))}</span>}{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</span>
            </div>
            {!open && <p className="line-clamp-2 text-xs text-muted-foreground"><Highlight text={result.content} query={query} /></p>}
          </CardHeader>
          {open && <CardContent className="space-y-3 px-3 pb-3">
            <div className="grid grid-cols-2 gap-1 text-[11px] md:grid-cols-5">
              <span className="flex items-center gap-1">
                {t('denseStage')}: {formatScore(result.dense_score)} / #{result.dense_rank ?? '—'}
                <Tooltip>
                  <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger>
                  <TooltipContent>{t('denseStageHelp')}</TooltipContent>
                </Tooltip>
              </span>
              <span className="flex items-center gap-1">
                {t('lexicalStage')}: {formatScore(result.lexical_score)} / #{result.lexical_rank ?? '—'}
                <Tooltip>
                  <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger>
                  <TooltipContent>{t('lexicalStageHelp')}</TooltipContent>
                </Tooltip>
              </span>
              <span className="flex items-center gap-1">
                {t('fusionStage')}: {formatScore(result.fusion_score)} / #{result.fusion_rank ?? '—'}
                <Tooltip>
                  <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger>
                  <TooltipContent>{t('fusionStageHelp')}</TooltipContent>
                </Tooltip>
              </span>
              <span className="flex items-center gap-1">
                {t('rerankStage')}: {formatScore(result.rerank_score)} / #{result.rerank_rank ?? '—'}
                <Tooltip>
                  <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger>
                  <TooltipContent>{t('rerankStageHelp')}</TooltipContent>
                </Tooltip>
              </span>
              <span className="flex items-center gap-1">
                {t('finalStage')}: {formatScore(result.score)} ({translateFinalScoreStage(result.final_score_stage, t)})
                <Tooltip>
                  <TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger>
                  <TooltipContent>{t('finalStageHelp')}</TooltipContent>
                </Tooltip>
              </span>
            </div>
            <div className="rounded border-2 border-orange-500/30 py-4 pr-4 pl-6" data-color-mode={resolvedTheme === 'dark' ? 'dark' : 'light'}>
              {authenticatedMarkdown ? (
                <div className="w-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_img]:max-w-full [&_img]:h-auto [&_img]:max-h-80 [&_img]:rounded-md [&_img]:object-contain [&_img]:block [&_img]:my-3 [&_a]:break-words [&_p]:text-sm [&_p]:leading-relaxed [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_h4]:text-sm [&_h5]:text-sm [&_h6]:text-sm [&_li]:text-sm [&_pre]:text-xs [&_code]:text-xs [&_table]:text-sm">
                  <MDPreview source={result.content} components={{ img: ({ src, alt }) => <AuthenticatedMarkdownImage src={typeof src === 'string' ? src : undefined} alt={alt} /> }} />
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-xs"><Highlight text={result.content} query={query} /></p>
              )}
            </div>
            {(result.degradation_reasons?.length || result.rerank_reason) && <p className="text-xs text-amber-700 dark:text-amber-300">{t('fallbackReasons')}: {[...(result.degradation_reasons ?? []).map(reason => `${reason.channel}: ${reason.error}`), result.rerank_reason].filter(Boolean).join('; ')}</p>}
            <div className="flex gap-1" aria-label={t('relevance')}>
              {(['relevant', 'partial', 'irrelevant'] as const).map(grade => <Button key={grade} size="sm" variant={grades[result.chunk_id] === grade ? 'default' : 'outline'} onClick={() => setGrade(result.chunk_id, grade)}>{t(grade)}</Button>)}
            </div>
          </CardContent>}
        </Card>
      })}
    </div>
  }

  const controls = (config: Config, setConfig: React.Dispatch<React.SetStateAction<Config>>, suffix: string) => <>
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[200px]">
        <Label className="text-xs text-muted-foreground">{t('searchMode')}</Label>
        <Select value={config.search_mode} onValueChange={value => setConfig(current => ({ ...current, search_mode: value as SearchMode }))}>
          <SelectTrigger aria-label={`${t('searchMode')} ${suffix}`} className="mt-1"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="hybrid">{t('hybridSearch')}</SelectItem>
            <SelectItem value="vector">{t('vectorSearch')}</SelectItem>
            <SelectItem value="fulltext">{t('fulltextSearch')}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">{t('topK')}</Label>
        <Input id={`topK${suffix}`} type="number" min={1} max={20} value={config.top_k} onChange={event => setConfig(current => ({ ...current, top_k: Math.min(20, Math.max(1, Number(event.target.value) || 1)) }))} className="mt-1" />
      </div>
      {knowledgeBase?.rerank_model && (
        <div className="flex items-center gap-2 pb-1">
          <Switch id={`rerank${suffix}`} checked={config.rerank_enabled} onCheckedChange={value => setConfig(current => ({ ...current, rerank_enabled: value }))} />
          <Label htmlFor={`rerank${suffix}`} className="text-sm cursor-pointer">{t('rerankEnabled')}</Label>
        </div>
      )}
    </div>
    {advanced && (
      <div className="space-y-3 pt-3 border-t">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <Label className="text-xs text-muted-foreground">{t('threshold')}</Label>
            <Input id={`threshold${suffix}`} type="number" min={0} max={1} step="0.01" value={config.threshold} onChange={event => setConfig(current => ({ ...current, threshold: Math.min(1, Math.max(0, Number(event.target.value) || 0)) }))} className="mt-1" />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">{t('denseWeight')}</Label>
            <Input id={`denseWeight${suffix}`} type="number" min={0} step="0.1" value={config.dense_weight} onChange={event => setConfig(current => ({ ...current, dense_weight: Math.max(0, Number(event.target.value) || 0) }))} className="mt-1" />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">{t('lexicalWeight')}</Label>
            <Input id={`lexicalWeight${suffix}`} type="number" min={0} step="0.1" value={config.lexical_weight} onChange={event => setConfig(current => ({ ...current, lexical_weight: Math.max(0, Number(event.target.value) || 0) }))} className="mt-1" />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">{t('rrfK')}</Label>
            <Input id={`rrfK${suffix}`} type="number" min={1} max={1000} value={config.rrf_k} onChange={event => setConfig(current => ({ ...current, rrf_k: Math.min(1000, Math.max(1, Number(event.target.value) || 1)) }))} className="mt-1" />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">{t('rerankCandidateK')}</Label>
            <Input id={`candidate${suffix}`} type="number" min={1} max={100} value={config.rerank_candidate_k} onChange={event => setConfig(current => ({ ...current, rerank_candidate_k: Math.min(100, Math.max(current.top_k, Number(event.target.value) || current.top_k)) }))} className="mt-1" />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">{t('rerankScoreThreshold')}</Label>
            <Input id={`rerankThreshold${suffix}`} type="number" min={0} max={1} step="0.01" value={config.rerank_score_threshold ?? ''} onChange={event => setConfig(current => ({ ...current, rerank_score_threshold: event.target.value === '' ? null : Math.min(1, Math.max(0, Number(event.target.value))) }))} placeholder="None" className="mt-1" />
          </div>
        </div>
      </div>
    )}
  </>

  return <div className="flex h-full flex-col">
    <header className="flex items-center gap-3 px-4 py-3 border-b">
      <Button render={<a href={backHref} />} nativeButton={false} variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
      <div className="flex-1">
        <h1 className="text-lg font-semibold">{t('retrievalLab')}</h1>
        <p className="text-xs text-muted-foreground">{knowledgeBase?.name}</p>
      </div>
    </header>

    {batchMode ? (
      <div className="flex-1 min-h-0 overflow-auto">
        <BatchEvaluation knowledgeBaseId={knowledgeBaseId} api={api} config={configA} hasRerankModel={Boolean(knowledgeBase?.rerank_model)} />
      </div>
    ) : (
      <main className="flex-1 min-h-0 overflow-auto p-4">
        {!searched ? (
          <div className="grid h-full place-content-center text-sm text-muted-foreground">{t('retrievalLabHint')}</div>
        ) : searching ? (
          <div className="grid h-full place-content-center"><Loader2 className="animate-spin" /></div>
        ) : !responses.a && !responses.b ? (
          <div className="grid h-full place-content-center text-sm text-muted-foreground">{t('noResults')}</div>
        ) : responses.a?.results.length === 0 && !responses.b?.results.length ? (
          <div className="grid h-full place-content-center text-sm text-muted-foreground">{t('noResults')}</div>
        ) : (
          <>
            {compare && responses.a && responses.b && (
              <p className="mb-2 text-xs text-muted-foreground">
                {t('overlap', { count: overlap, total: Math.max(responses.a.results.length, responses.b.results.length) })}
              </p>
            )}
            <div className={cn('grid gap-3', compare && 'lg:grid-cols-2')}>
              <section className="min-w-0">
                <h2 className="mb-2 font-medium">A</h2>
                {responses.a ? renderResults(responses.a, 'a') : <p className="text-sm text-muted-foreground">{t('noResults')}</p>}
              </section>
              {compare && (
                <section className="min-w-0">
                  <h2 className="mb-2 font-medium">B</h2>
                  {responses.b ? renderResults(responses.b, 'b') : <p className="text-sm text-muted-foreground">{t('noResults')}</p>}
                </section>
              )}
            </div>
          </>
        )}
      </main>
    )}

    <footer className="border-t bg-background">
      <div className="flex items-center gap-2 p-3">
        <div role="tablist" aria-label={t('retrievalLab')} className="flex gap-1">
          <Button role="tab" aria-selected={!batchMode} variant={!batchMode ? 'secondary' : 'ghost'} size="sm" onClick={() => setBatchMode(false)}>
            {t('interactiveSearch')}
          </Button>
          <Button role="tab" aria-selected={batchMode} variant={batchMode ? 'secondary' : 'ghost'} size="sm" onClick={() => setBatchMode(true)}>
            {t('batchEvaluation')}
          </Button>
        </div>
        {!batchMode && (
          <>
            <div className="flex-1 flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={handleKeyDown} placeholder={t('searchPlaceholder')} className="pl-9" />
              </div>
            </div>
            <Popover open={showConfig} onOpenChange={setShowConfig}>
              <PopoverTrigger
                className={cn(
                  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  "disabled:pointer-events-none disabled:opacity-50",
                  "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
                  "h-10 w-10"
                )}
                title={t('settings')}
              >
                <Settings2 className="h-4 w-4" />
              </PopoverTrigger>
              <PopoverContent align="end" side="top" className="w-[500px] max-h-[70vh] overflow-y-auto">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-semibold">A</span>
                      {compare && (
                        <div className="flex items-center gap-2">
                          <Switch id="compare-header" checked={compare} onCheckedChange={setCompare} />
                          <Label htmlFor="compare-header" className="text-sm cursor-pointer">{t('compareAB')}</Label>
                        </div>
                      )}
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => setAdvanced(value => !value)}>
                      <Settings2 className="mr-1.5 h-3.5 w-3.5" />
                      {t('advancedSettings')}
                      {advanced ? <ChevronUp className="ml-1 h-3.5 w-3.5" /> : <ChevronDown className="ml-1 h-3.5 w-3.5" />}
                    </Button>
                  </div>

                  {controls(configA, setConfigA, 'A')}

                  {!compare && (
                    <div className="flex items-center gap-2 pt-2 border-t">
                      <Switch id="compare-toggle" checked={compare} onCheckedChange={setCompare} />
                      <Label htmlFor="compare-toggle" className="text-sm cursor-pointer">{t('compareAB')}</Label>
                    </div>
                  )}

                  {compare && (
                    <div className="space-y-3 pt-3 border-t">
                      <span className="text-sm font-semibold">B</span>
                      {controls(configB, setConfigB, 'B')}
                    </div>
                  )}

                  <div className="space-y-2 pt-3 border-t">
                    <div className="flex items-center gap-2">
                      <Input aria-label={t('presetName')} value={presetName} onChange={event => setPresetName(event.target.value)} placeholder={t('presetName')} className="flex-1" />
                      <Button variant="outline" size="sm" onClick={savePreset}>{t('savePreset')}</Button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select aria-label={t('presets')} value={selectedPreset || '__none__'} onValueChange={value => { const name = !value || value === '__none__' ? '' : value; setSelectedPreset(name); const preset = presets.find(item => item.name === name); if (preset) setConfigA(preset.config) }}>
                        <SelectTrigger className="flex-1"><SelectValue>{selectedPreset || t('presets')}</SelectValue></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">{t('presets')}</SelectItem>
                          {presets.map(preset => <SelectItem key={preset.name} value={preset.name}>{preset.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button size="sm" onClick={() => void applyPreset()} disabled={!selectedPreset || !canUpdate}>{t('applyToProduction')}</Button>
                    </div>
                    {updateError && <p className="text-xs text-destructive">{t('presetUpdateError')}</p>}
                  </div>
                </div>
              </PopoverContent>
            </Popover>
            <Button aria-label={t('search')} onClick={() => void runSearch()} disabled={!query.trim() || searching}>
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </>
        )}
      </div>
    </footer>
  </div>
}
