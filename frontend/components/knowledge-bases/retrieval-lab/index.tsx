'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { ArrowLeft, ChevronDown, ChevronUp, FileText, HelpCircle, Loader2, Search, Send, Settings2, X } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
import type { KnowledgeBase, SearchMode, SearchParams, SearchResponse, SearchResult } from '@/lib/api'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn, formatDuration } from '@/lib/utils'
import { type Config, type RetrievalApi, runConfig } from './shared'

const MDPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), { ssr: false })
type RetrievalFailure =
  | 'request'
  | 'configuration_mismatch'
  | 'provider_authentication'
  | 'quota_or_rate_limit'
  | 'model_configuration'
  | 'lexical_unavailable'
  | 'provider_unavailable'
  | 'unknown'

const RETRIEVAL_FAILURES: Record<Exclude<RetrievalFailure, 'request'>, true> = {
  configuration_mismatch: true,
  provider_authentication: true,
  quota_or_rate_limit: true,
  model_configuration: true,
  lexical_unavailable: true,
  provider_unavailable: true,
  unknown: true,
}

function retrievalFailure(reason: unknown): RetrievalFailure {
  if (!(reason instanceof ApiError)) return 'unknown'
  if (reason.code === -1) return 'request'
  if (!reason.data || typeof reason.data !== 'object') return 'unknown'
  const category = (reason.data as Record<string, unknown>).retrieval_error_category
  return typeof category === 'string' && category in RETRIEVAL_FAILURES
    ? category as RetrievalFailure
    : 'unknown'
}

function retrievalStage(reason: unknown): string | null {
  if (!(reason instanceof ApiError)) return null
  if (!reason.data || typeof reason.data !== 'object') return null
  const stage = (reason.data as Record<string, unknown>).stage
  return typeof stage === 'string' ? stage : null
}

function batchErrorReason(error: { code: number; retrieval_error_category: string; stage?: string | null }): ApiError {
  return new ApiError(error.code, '', {
    retrieval_error_category: error.retrieval_error_category,
    stage: error.stage,
  })
}

// Stage-less keys are camelCase in the catalog, so every snake_case segment is capitalized
function retrievalErrorKey(failure: RetrievalFailure, stage: string | null): string {
  if (stage) return `retrievalError_${stage}_${failure}`
  const suffix = failure.split('_').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('')
  return `retrievalError${suffix}`
}

function retrievalErrorMessage(
  t: Translate,
  failure: RetrievalFailure,
  stage: string | null
): string {
  const key = retrievalErrorKey(failure, stage)
  return t.has(key) ? t(key) : t(retrievalErrorKey(failure, null))
}

interface RetrievalLabProps {
  knowledgeBaseId: string
  api: RetrievalApi
  backHref: string
  canTest: boolean
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


function configParams(query: string, config: Config, hasRerankModel: boolean): SearchParams {
  const snapshot = runConfig(config, hasRerankModel)
  return {
    query,
    ...snapshot,
    threshold: snapshot.score_threshold,
  }
}

type ResultSelection = { side: 'a' | 'b'; chunkId: string }
type Translate = {
  (key: string, values?: Record<string, string | number>): string
  has(key: string): boolean
}

function ResultDetail({ result, side, rank, query, authenticatedMarkdown, resolvedTheme, t, onClose }: {
  result: SearchResult
  side: 'a' | 'b'
  rank: number
  query: string
  authenticatedMarkdown: boolean
  resolvedTheme: string | undefined
  t: Translate
  onClose: () => void
}) {
  const stageLabel = translateSearchType(result.search_type, t) || translateFinalScoreStage(result.final_score_stage, t) || t('unknownChannel')
  return <aside id="retrieval-result-detail" aria-labelledby="retrieval-result-detail-title" className="flex h-full min-h-0 flex-col bg-background">
    <div className="flex shrink-0 items-start gap-3 border-b px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">{t('resultConfiguration', { side: side.toUpperCase() })}</Badge>
          <span>#{rank}</span>
          <Badge>{stageLabel}</Badge>
        </div>
        <h2 id="retrieval-result-detail-title" className="truncate text-sm font-semibold">{result.document_name}</h2>
      </div>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={t('closeResultDetails')} onClick={onClose}>
        <X className="h-4 w-4" />
      </Button>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="space-y-4">
        <div className="grid gap-2 text-[11px] sm:grid-cols-2">
          {[
            [t('denseStage'), result.dense_score, result.dense_rank, t('denseStageHelp')],
            [t('lexicalStage'), result.lexical_score, result.lexical_rank, t('lexicalStageHelp')],
            [t('fusionStage'), result.fusion_score, result.fusion_rank, t('fusionStageHelp')],
            [t('rerankStage'), result.rerank_score, result.rerank_rank, t('rerankStageHelp')],
          ].map(([label, score, stageRank, help]) => <span key={String(label)} className="flex items-center gap-1">
            {String(label)}: {formatScore(score as number | null | undefined)} / #{stageRank ?? '—'}
            <Tooltip><TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger><TooltipContent>{String(help)}</TooltipContent></Tooltip>
          </span>)}
          <span className="flex items-center gap-1 sm:col-span-2">
            {t('finalStage')}: {formatScore(result.score)} ({translateFinalScoreStage(result.final_score_stage, t)})
            <Tooltip><TooltipTrigger><HelpCircle className="h-3 w-3 text-muted-foreground" /></TooltipTrigger><TooltipContent>{t('finalStageHelp')}</TooltipContent></Tooltip>
          </span>
        </div>
        <div className="min-w-0 rounded-md border bg-muted/20 p-4" data-color-mode={resolvedTheme === 'dark' ? 'dark' : 'light'}>
          <div className="w-full max-w-[75ch] [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_img]:my-3 [&_img]:block [&_img]:h-auto [&_img]:max-h-80 [&_img]:max-w-full [&_img]:rounded-md [&_img]:object-contain [&_a.anchor]:!ml-0 [&_a]:break-words [&_code]:text-xs [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_h4]:text-sm [&_h5]:text-sm [&_h6]:text-sm [&_li]:text-sm [&_p]:text-sm [&_p]:leading-relaxed [&_pre]:overflow-x-auto [&_pre]:text-xs [&_table]:text-sm">
            <MDPreview source={result.content} components={authenticatedMarkdown ? { img: ({ src, alt }) => <AuthenticatedMarkdownImage src={typeof src === 'string' ? src : undefined} alt={alt} /> } : undefined} />
          </div>
        </div>
        {(result.degradation_reasons?.length || result.rerank_reason) && <p className="text-xs text-amber-700 dark:text-amber-300">{t('fallbackReasons')}: {[...(result.degradation_reasons ?? []).map(reason => `${reason.channel}: ${reason.error}`), result.rerank_reason].filter(Boolean).join('; ')}</p>}
      </div>
    </div>
  </aside>
}

export function RetrievalLab({ knowledgeBaseId, api, backHref, canTest, canUpdate, authenticatedMarkdown = false, onLoadError }: RetrievalLabProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const { resolvedTheme } = useTheme()
  const isMobile = useIsMobile()
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
  const [selection, setSelection] = React.useState<ResultSelection | null>(null)
  const [presets, setPresets] = React.useState<Array<{ name: string; config: Config }>>([])
  const [presetName, setPresetName] = React.useState('')
  const [selectedPreset, setSelectedPreset] = React.useState('')
  const [applyDialogOpen, setApplyDialogOpen] = React.useState(false)
  const [applyingPreset, setApplyingPreset] = React.useState(false)
  const onLoadErrorRef = React.useRef(onLoadError)
  onLoadErrorRef.current = onLoadError
  const [submittedQuery, setSubmittedQuery] = React.useState('')
  const loadGeneration = React.useRef(0)
  const searchGeneration = React.useRef(0)

  const storageKey = `retrieval-lab:${knowledgeBaseId}`
  React.useEffect(() => {
    const generation = ++loadGeneration.current
    setLoading(true)
    api.getKnowledgeBase(knowledgeBaseId).then(kb => {
      if (generation !== loadGeneration.current) return
      setKnowledgeBase(kb)
      setConfigA({
        search_mode: kb.settings?.search_mode ?? DEFAULT_CONFIG.search_mode,
        top_k: Math.min(20, Math.max(1, kb.settings?.top_k ?? DEFAULT_CONFIG.top_k)),
        threshold: kb.settings?.score_threshold ?? DEFAULT_CONFIG.threshold,
        dense_weight: kb.settings?.dense_weight ?? DEFAULT_CONFIG.dense_weight,
        lexical_weight: kb.settings?.lexical_weight ?? DEFAULT_CONFIG.lexical_weight,
        rrf_k: kb.settings?.rrf_k ?? DEFAULT_CONFIG.rrf_k,
        rerank_enabled: kb.settings?.rerank_enabled ?? DEFAULT_CONFIG.rerank_enabled,
        rerank_candidate_k: kb.settings?.rerank_candidate_k ?? DEFAULT_CONFIG.rerank_candidate_k,
        rerank_score_threshold: kb.settings?.rerank_score_threshold ?? DEFAULT_CONFIG.rerank_score_threshold,
      })
      try {
        const local = JSON.parse(localStorage.getItem(storageKey) || '{}')
        setPresets(Array.isArray(local.presets) ? local.presets : [])
      } catch {
        localStorage.removeItem(storageKey)
      }
    }).catch(() => {
      if (generation === loadGeneration.current) onLoadErrorRef.current?.()
    }).finally(() => {
      if (generation === loadGeneration.current) setLoading(false)
    })
    return () => { loadGeneration.current += 1 }
  }, [api, knowledgeBaseId, storageKey])

  const invalidA = configA.search_mode === 'hybrid' && configA.dense_weight === 0 && configA.lexical_weight === 0
  const invalidB = compare && configB.search_mode === 'hybrid' && configB.dense_weight === 0 && configB.lexical_weight === 0
  const invalidConfig = invalidA || invalidB

  const persistPresets = (nextPresets: Array<{ name: string; config: Config }>) => {
    setPresets(nextPresets)
    localStorage.setItem(storageKey, JSON.stringify({ presets: nextPresets }))
  }

  const runSearch = async () => {
    const trimmed = query.trim()
    if (!trimmed || !canTest || invalidConfig) return
    const generation = ++searchGeneration.current
    setSearching(true)
    setSearched(true)
    setResponses({})
    setSelection(null)
    setSubmittedQuery(trimmed)
    try {
      if (compare) {
        const hasRerankModel = Boolean(knowledgeBase?.rerank_model)
        const batch = await api.searchBatch(knowledgeBaseId, trimmed, [
          { id: 'a', ...runConfig(configA, hasRerankModel) },
          { id: 'b', ...runConfig(configB, hasRerankModel) },
        ])
        if (generation !== searchGeneration.current) return
        const outcomes = new Map(batch.outcomes.map(outcome => [outcome.id, outcome]))
        const a = outcomes.get('a')
        const b = outcomes.get('b')
        setResponses({
          a: a?.status === 'fulfilled' ? a.response : undefined,
          b: b?.status === 'fulfilled' ? b.response : undefined,
        })
        for (const [id, outcome] of [['A', a], ['B', b]] as const) {
          if (outcome?.status !== 'rejected') continue
          const reason = batchErrorReason(outcome.error)
          toast.error(`${id}: ${retrievalErrorMessage(t, retrievalFailure(reason), retrievalStage(reason))}`)
        }
      } else {
        const response = await api.search(knowledgeBaseId, configParams(trimmed, configA, Boolean(knowledgeBase?.rerank_model)))
        if (generation === searchGeneration.current) setResponses({ a: response })
      }
    } catch (reason) {
      if (generation === searchGeneration.current) {
        toast.error(retrievalErrorMessage(t, retrievalFailure(reason), retrievalStage(reason)))
      }
    } finally {
      if (generation === searchGeneration.current) setSearching(false)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter' && !event.shiftKey && !searching && canTest) {
      event.preventDefault()
      void runSearch()
    }
  }

  const savePreset = () => {
    const name = presetName.trim()
    if (!name || invalidA) return
    const nextPresets = [...presets.filter(preset => preset.name !== name), { name, config: configA }]
    setSelectedPreset(name)
    setPresetName('')
    persistPresets(nextPresets)
  }

  const applyPreset = async () => {
    const preset = presets.find(item => item.name === selectedPreset)
    if (!preset || !canUpdate || applyingPreset || invalidA) return
    setUpdateError(false)
    setApplyingPreset(true)
    try {
      const cfg = configA
      const updatedKnowledgeBase = await api.updateKnowledgeBase(knowledgeBaseId, {
        settings: {
          ...(knowledgeBase?.settings ?? {}),
          search_mode: cfg.search_mode,
          top_k: cfg.top_k,
          score_threshold: cfg.threshold,
          dense_weight: cfg.dense_weight,
          lexical_weight: cfg.lexical_weight,
          rrf_k: cfg.rrf_k,
          rerank_enabled: cfg.rerank_enabled,
          rerank_candidate_k: cfg.rerank_candidate_k,
          rerank_score_threshold: cfg.rerank_score_threshold,
        },
      })
      setKnowledgeBase(updatedKnowledgeBase)
      setApplyDialogOpen(false)
      toast.success(t('applyPresetSuccess'))
    } catch {
      setUpdateError(true)
    } finally {
      setApplyingPreset(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center p-8"><Loader2 className="h-6 w-6 animate-spin" /></div>

  const aRanks = new Map(responses.a?.results.map((result, index) => [result.chunk_id, index + 1]))
  const bRanks = new Map(responses.b?.results.map((result, index) => [result.chunk_id, index + 1]))
  const overlap = responses.a && responses.b
    ? responses.a.results.filter(result => bRanks.has(result.chunk_id)).length
    : 0

  const selectedResponse = selection ? responses[selection.side] : undefined
  const selectedIndex = selection ? selectedResponse?.results.findIndex(result => result.chunk_id === selection.chunkId) ?? -1 : -1
  const selectedResult = selectedIndex >= 0 ? selectedResponse?.results[selectedIndex] : undefined

  const renderResults = (response: SearchResponse | undefined, side: 'a' | 'b') => {
    if (!response) return null
    const otherRanks = side === 'a' ? bRanks : aRanks
    return <div className="min-w-0 space-y-2">
      {response.timings?.length > 0 && <p className="text-xs text-muted-foreground">{t('stageTimings')}: {response.timings.map(timing => `${timing.stage} ${formatDuration(timing.latency_ms)}`).join(' · ')}</p>}
      {response.diagnostics?.length > 0 && <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
        <strong>{t('diagnostics')}</strong>: {response.diagnostics.map(item => `${item.code}${item.stage ? ` (${item.stage})` : ''}${item.latency_ms !== undefined ? ` ${formatDuration(item.latency_ms)}` : ''}${item.detail ? ` — ${item.detail}` : ''}`).join('; ')}
      </div>}
      {response.results.map((result, index) => {
        const selected = selection?.side === side && selection.chunkId === result.chunk_id
        const movement = otherRanks.get(result.chunk_id)
        const movementDelta = movement === undefined ? null : movement - (index + 1)
        const stageLabel = translateSearchType(result.search_type, t) || translateFinalScoreStage(result.final_score_stage, t) || t('unknownChannel')
        return <Card key={result.chunk_id} className={cn('py-0 transition-colors', selected && 'border-primary bg-accent/60 ring-1 ring-primary/30')}>
          <button
            type="button"
            className="w-full rounded-xl p-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-label={t('selectResult', { side: side.toUpperCase(), rank: index + 1, document: result.document_name })}
            aria-pressed={selected}
            aria-expanded={selected}
            aria-controls="retrieval-result-detail"
            onClick={() => setSelection({ side, chunkId: result.chunk_id })}
          >
            <span className="flex min-w-0 items-center gap-2 text-xs">
              <Badge variant="outline">#{index + 1}</Badge>
              <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <strong className="min-w-0 flex-1 truncate">{result.document_name}</strong>
              {movementDelta !== null && <Badge variant="outline" className={cn(
                'shrink-0 border-transparent font-medium tabular-nums',
                movementDelta > 0 && 'bg-emerald-500/15 text-emerald-700 dark:bg-emerald-400/20 dark:text-emerald-300',
                movementDelta < 0 && 'bg-red-500/15 text-red-700 dark:bg-red-400/20 dark:text-red-300',
                movementDelta === 0 && 'bg-muted text-muted-foreground'
              )}>{movementDelta > 0 ? '↑' : movementDelta < 0 ? '↓' : '→'} {Math.abs(movementDelta)}</Badge>}
              <Badge className="shrink-0">{stageLabel}</Badge>
            </span>
            <span className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground"><Highlight text={result.content} query={submittedQuery} /></span>
          </button>
        </Card>
      })}
    </div>
  }

  const resultsView = <div className="space-y-4 p-4">
    {compare && responses.a && responses.b && (
      <p className="text-xs text-muted-foreground">
        {t('overlap', { count: overlap, total: Math.max(responses.a.results.length, responses.b.results.length) })}
      </p>
    )}
    <div className={cn('grid gap-3', compare && 'lg:grid-cols-2')}>
      <section className="min-w-0" aria-labelledby="retrieval-results-a">
        <h2 id="retrieval-results-a" className="mb-2 font-medium">A</h2>
        {responses.a ? renderResults(responses.a, 'a') : <p className="text-sm text-muted-foreground">{t('noResults')}</p>}
      </section>
      {compare && (
        <section className="min-w-0" aria-labelledby="retrieval-results-b">
          <h2 id="retrieval-results-b" className="mb-2 font-medium">B</h2>
          {responses.b ? renderResults(responses.b, 'b') : <p className="text-sm text-muted-foreground">{t('noResults')}</p>}
        </section>
      )}
    </div>
  </div>

  const detail = selectedResult && selection ? <ResultDetail
    result={selectedResult}
    side={selection.side}
    rank={selectedIndex + 1}
    query={submittedQuery}
    authenticatedMarkdown={authenticatedMarkdown}
    resolvedTheme={resolvedTheme}
    t={t}
    onClose={() => setSelection(null)}
  /> : null

  const controls = (config: Config, setConfig: React.Dispatch<React.SetStateAction<Config>>, suffix: string, invalid: boolean) => <>
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[200px]">
        <Label className="text-xs text-muted-foreground">{t('searchMode')}</Label>
        <Select value={config.search_mode} onValueChange={value => setConfig(current => ({ ...current, search_mode: value as SearchMode }))}>
          <SelectTrigger aria-label={`${t('searchMode')} ${suffix}`} className="mt-1">
            <SelectValue>
              {config.search_mode === 'hybrid' ? t('hybridSearch') : config.search_mode === 'vector' ? t('vectorSearch') : t('fulltextSearch')}
            </SelectValue>
          </SelectTrigger>
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
        <div className="flex h-14 flex-col justify-between">
          <Label htmlFor={`rerank${suffix}`} className="text-xs text-muted-foreground cursor-pointer">{t('rerankEnabled')}</Label>
          <div className="flex h-9 items-center">
            <Switch id={`rerank${suffix}`} checked={config.rerank_enabled} onCheckedChange={value => setConfig(current => ({ ...current, rerank_enabled: value }))} />
          </div>
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
            <Input id={`rerankThreshold${suffix}`} type="number" min={0} max={1} step="0.01" value={config.rerank_score_threshold ?? ''} onChange={event => setConfig(current => ({ ...current, rerank_score_threshold: event.target.value === '' ? null : Math.min(1, Math.max(0, Number(event.target.value))) }))} placeholder={t('rerankScoreThresholdPlaceholder')} className="mt-1" />
          </div>
        </div>
        {invalid && <p role="alert" className="text-xs text-destructive">{t('hybridWeightsRequired', { side: suffix })}</p>}
      </div>
    )}
  </>

  return <div className="relative flex h-full flex-col">
    <Button
      render={<a href={backHref} />}
      nativeButton={false}
      variant="outline"
      size="icon"
      className="absolute left-3 top-3 z-20 rounded-md bg-background shadow-sm"
      aria-label={t('retrievalLab')}
    >
      <ArrowLeft className="h-4 w-4" />
    </Button>

    <main className="min-h-0 flex-1 overflow-hidden pt-14">
      {!searched ? (
        <div className="grid h-full place-content-center p-4 text-sm text-muted-foreground">{t('retrievalLabHint')}</div>
      ) : searching ? (
        <div className="grid h-full place-content-center"><Loader2 className="animate-spin" /></div>
      ) : !responses.a && !responses.b ? (
        <div className="grid h-full place-content-center p-4 text-sm text-muted-foreground">{t('noResults')}</div>
      ) : responses.a?.results.length === 0 && !responses.b?.results.length ? (
        <div className="grid h-full place-content-center p-4 text-sm text-muted-foreground">{t('noResults')}</div>
      ) : isMobile ? (
        <div className="h-full overflow-y-auto">{resultsView}</div>
      ) : (
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          <ResizablePanel defaultSize={detail ? '62%' : '100%'} minSize="40%">
            <div className="h-full min-w-0 overflow-y-auto">{resultsView}</div>
          </ResizablePanel>
          {detail && <>
            <ResizableHandle withHandle aria-label={t('resizeResultDetails')} />
            <ResizablePanel defaultSize="38%" minSize="25%" maxSize="60%">
              {detail}
            </ResizablePanel>
          </>}
        </ResizablePanelGroup>
      )}
    </main>

    {isMobile && <Sheet open={Boolean(detail)} onOpenChange={open => { if (!open) setSelection(null) }}>
      <SheetContent side="right" className="w-full max-w-none gap-0 p-0 sm:max-w-none" showCloseButton={false}>
        <SheetHeader className="sr-only">
          <SheetTitle>{t('resultDetails')}</SheetTitle>
          <SheetDescription>{selectedResult ? t('resultDetailsDescription', { side: selection?.side.toUpperCase() ?? '', document: selectedResult.document_name }) : t('resultDetails')}</SheetDescription>
        </SheetHeader>
        {detail}
      </SheetContent>
    </Sheet>}

    <footer className="border-t bg-background">
      <div className="flex items-center gap-2 p-3">
        <div className="flex-1 flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={handleKeyDown} placeholder={t('searchPlaceholder')} className="pl-9" disabled={!canTest} />
              </div>
        </div>
        <Popover open={showConfig} onOpenChange={setShowConfig}>
              <PopoverTrigger
                className={cn(
                  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  "disabled:pointer-events-none disabled:opacity-50",
                  "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
                  "h-9 w-9"
                )}
                title={t('settings')}
              >
                <Settings2 className="h-4 w-4" />
              </PopoverTrigger>
              <PopoverContent align="end" side="top" className="w-[min(500px,calc(100vw-1rem))] max-h-[calc(100dvh-1rem)] overflow-y-auto">
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
                    <Button variant="ghost" onClick={() => setAdvanced(value => !value)}>
                      <Settings2 className="mr-1.5 h-3.5 w-3.5" />
                      {t('advancedSettings')}
                      {advanced ? <ChevronUp className="ml-1 h-3.5 w-3.5" /> : <ChevronDown className="ml-1 h-3.5 w-3.5" />}
                    </Button>
                  </div>

                  {controls(configA, setConfigA, 'A', invalidA)}

                  {!compare && (
                    <div className="flex items-center gap-2 pt-2 border-t">
                      <Switch id="compare-toggle" checked={compare} onCheckedChange={setCompare} />
                      <Label htmlFor="compare-toggle" className="text-sm cursor-pointer">{t('compareAB')}</Label>
                    </div>
                  )}

                  {compare && (
                    <div className="space-y-3 pt-3 border-t">
                      <span className="text-sm font-semibold">B</span>
                      {controls(configB, setConfigB, 'B', invalidB)}
                    </div>
                  )}

                  <div className="space-y-2 pt-3 border-t">
                    <div className="flex items-center gap-2">
                      <Input aria-label={t('presetName')} value={presetName} onChange={event => setPresetName(event.target.value)} placeholder={t('presetName')} className="flex-1" />
                      <Button variant="outline" onClick={savePreset} disabled={invalidA}>{t('savePreset')}</Button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select aria-label={t('presets')} value={selectedPreset || '__none__'} onValueChange={value => {
                        const name = !value || value === '__none__' ? '' : value
                        setSelectedPreset(name)
                        const preset = presets.find(item => item.name === name)
                        if (preset) setConfigA(current => ({ ...current, ...preset.config }))
                      }}>
                        <SelectTrigger className="flex-1"><SelectValue>{selectedPreset || t('presets')}</SelectValue></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">{t('presets')}</SelectItem>
                          {presets.map(preset => <SelectItem key={preset.name} value={preset.name}>{preset.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Button onClick={() => setApplyDialogOpen(true)} disabled={!selectedPreset || !canUpdate || invalidA}>{t('applyToProduction')}</Button>
                    </div>
                    {updateError && <p className="text-xs text-destructive">{t('presetUpdateError')}</p>}
                  </div>
                </div>
              </PopoverContent>
        </Popover>
        <AlertDialog open={applyDialogOpen} onOpenChange={open => { if (!applyingPreset) setApplyDialogOpen(open) }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('applyToProduction')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('applyPresetConfirm', { name: selectedPreset })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={applyingPreset}>{commonT('cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={() => void applyPreset()} disabled={applyingPreset || invalidA}>
                {applyingPreset && <Loader2 className="h-4 w-4 animate-spin" />}
                {commonT('confirm')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <Button aria-label={t('search')} onClick={() => void runSearch()} disabled={!canTest || !query.trim() || searching || invalidConfig}>
          {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </footer>
  </div>
}
