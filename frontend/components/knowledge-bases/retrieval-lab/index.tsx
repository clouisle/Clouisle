'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { ArrowLeft, ChevronDown, ChevronUp, FileText, HelpCircle, Loader2, Search, Send, Settings2 } from 'lucide-react'
import { ApiError } from '@/lib/api/client'
import type { KnowledgeBase, SearchMode, SearchParams, SearchResponse } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatDuration } from '@/lib/utils'
import { BatchEvaluation } from './batch-evaluation'
import { type Config, type RetrievalApi, runConfig } from './shared'
import { type Grade, type StorageEnvelope, getDraft, migrateStorage, setGrade as setGradeInDraft } from './labeling'

export { BatchEvaluation } from './batch-evaluation'

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
  canEvaluate: boolean
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

export function RetrievalLab({ knowledgeBaseId, api, backHref, canEvaluate, canUpdate, authenticatedMarkdown = false, onLoadError }: RetrievalLabProps) {
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
  const [storage, setStorage] = React.useState<StorageEnvelope>({ version: 2, presets: [], drafts: {} })
  const [presetName, setPresetName] = React.useState('')
  const [selectedPreset, setSelectedPreset] = React.useState('')
  const [batchMode, setBatchMode] = React.useState(false)
  const [submittedQuery, setSubmittedQuery] = React.useState('')

  const storageKey = `retrieval-lab:${knowledgeBaseId}`
  React.useEffect(() => {
    api.getKnowledgeBase(knowledgeBaseId).then(kb => {
      setKnowledgeBase(kb)
      setConfigA({
        search_mode: kb.settings?.search_mode ?? DEFAULT_CONFIG.search_mode,
        top_k: kb.settings?.top_k ?? DEFAULT_CONFIG.top_k,
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
        const migrated = migrateStorage(local)
        setStorage(migrated ?? { version: 2, presets: [], drafts: {} })
      } catch {
        localStorage.removeItem(storageKey)
      }
    }).catch(() => onLoadError?.()).finally(() => setLoading(false))
  }, [api, knowledgeBaseId, onLoadError, storageKey])

  const persist = (nextStorage: StorageEnvelope) => {
    setStorage(nextStorage)
    localStorage.setItem(storageKey, JSON.stringify(nextStorage))
  }

  // Current draft for the submitted query (not the live input text)
  const currentDraft = getDraft(storage, submittedQuery)
  const grades = currentDraft.grades
  const presets = storage.presets

  const runSearch = async () => {
    const trimmed = query.trim()
    if (!trimmed) return
    setSearching(true)
    setSearched(true)
    setResponses({})
    setSubmittedQuery(trimmed) // Capture submitted query for labeling isolation
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

      const firstA = next.a?.results[0]
      const firstB = next.b?.results[0]
      setExpanded(new Set(
        firstA
          ? [`a:${firstA.chunk_id}`]
          : firstB
            ? [`b:${firstB.chunk_id}`]
            : [],
      ))
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
    const nextPresets = [...presets.filter(preset => preset.name !== name), { name, config: configA }]
    setSelectedPreset(name)
    setPresetName('')
    persist({ ...storage, presets: nextPresets })
  }

  const applyPreset = async () => {
    const preset = presets.find(item => item.name === selectedPreset)
    if (!preset || !canUpdate || !window.confirm(t('applyPresetConfirm', { name: preset.name }))) return
    setUpdateError(false)
    try {
      const cfg = preset.config as Config
      await api.updateKnowledgeBase(knowledgeBaseId, {
        settings: {
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
      toast.success(t('applyPresetSuccess'))
    } catch {
      setUpdateError(true)
    }
  }

  const setGrade = (chunkId: string, grade: Grade) => {
    if (!submittedQuery) return
    persist(setGradeInDraft(storage, submittedQuery, chunkId, grade))
  }

  if (loading) return <div className="flex items-center justify-center p-8"><Loader2 className="h-6 w-6 animate-spin" /></div>

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
              <span className="flex min-w-0 items-center gap-2">
                <Badge variant="outline">#{index + 1}</Badge>
                <FileText className="h-3.5 w-3.5" />
                <strong className="truncate">{result.document_name}</strong>
                <Tooltip>
                  <TooltipTrigger>
                    <button
                      type="button"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={e => {
                        e.stopPropagation()
                        navigator.clipboard.writeText(result.chunk_id)
                        toast.success(t('chunkIdCopied'))
                      }}
                    >
                      <code className="text-[10px]">{result.chunk_id.slice(0, 8)}</code>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>{t('clickToCopyChunkId')}</TooltipContent>
                </Tooltip>
              </span>
              <span className="flex items-center gap-2"><Badge>{translateSearchType(result.search_type, t) || translateFinalScoreStage(result.final_score_stage, t) || t('unknownChannel')}</Badge>{movement && <span>{movement - (index + 1) > 0 ? '↑' : movement - (index + 1) < 0 ? '↓' : '→'} {Math.abs(movement - (index + 1))}</span>}{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</span>
            </div>
            {!open && <p className="line-clamp-2 text-xs text-muted-foreground"><Highlight text={result.content} query={submittedQuery} /></p>}
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
                <p className="whitespace-pre-wrap text-xs"><Highlight text={result.content} query={submittedQuery} /></p>
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
        <BatchEvaluation knowledgeBaseId={knowledgeBaseId} api={api} config={configA} hasRerankModel={Boolean(knowledgeBase?.rerank_model)} canEvaluate={canEvaluate} />
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
                      <Select aria-label={t('presets')} value={selectedPreset || '__none__'} onValueChange={value => { const name = !value || value === '__none__' ? '' : value; setSelectedPreset(name); const preset = presets.find(item => item.name === name); if (preset) setConfigA(preset.config as Config) }}>
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
