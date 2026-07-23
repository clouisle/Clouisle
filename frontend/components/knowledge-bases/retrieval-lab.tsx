'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { ArrowLeft, ChevronDown, ChevronUp, FileText, Loader2, Search, Send, Settings2 } from 'lucide-react'
import type {
  KnowledgeBase,
  KnowledgeBaseSettings,
  SearchMode,
  SearchParams,
  SearchResponse,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

const MDPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), { ssr: false })

type RetrievalApi = {
  getKnowledgeBase(id: string): Promise<KnowledgeBase>
  search(id: string, params: SearchParams): Promise<SearchResponse>
  updateKnowledgeBase(id: string, data: { settings: KnowledgeBaseSettings }): Promise<KnowledgeBase>
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
  rerank_fail_open: boolean
  rerank_score_threshold: number | null
}

type Preset = { name: string; config: Config }
type Grade = 'relevant' | 'partial' | 'irrelevant'

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
  rerank_enabled: true, rerank_candidate_k: 10, rerank_fail_open: true, rerank_score_threshold: null,
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

function raw(value?: number) {
  return value === undefined ? '—' : String(value)
}

function configParams(query: string, config: Config, hasRerankModel: boolean): SearchParams {
  const rerank = hasRerankModel && config.rerank_enabled
  return {
    query,
    search_mode: config.search_mode,
    top_k: config.top_k,
    threshold: config.threshold,
    dense_weight: config.dense_weight,
    lexical_weight: config.lexical_weight,
    rrf_k: config.rrf_k,
    rerank_enabled: rerank,
    rerank_candidate_k: rerank ? Math.max(config.top_k, config.rerank_candidate_k) : undefined,
    rerank_fail_open: rerank ? config.rerank_fail_open : undefined,
    rerank_score_threshold: rerank ? config.rerank_score_threshold : undefined,
  }
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
  const [error, setError] = React.useState(false)
  const [updateError, setUpdateError] = React.useState(false)
  const [advanced, setAdvanced] = React.useState(false)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())
  const [grades, setGrades] = React.useState<Record<string, Grade>>({})
  const [presets, setPresets] = React.useState<Preset[]>([])
  const [presetName, setPresetName] = React.useState('')
  const [selectedPreset, setSelectedPreset] = React.useState('')

  const storageKey = `retrieval-lab:${knowledgeBaseId}`
  React.useEffect(() => {
    api.getKnowledgeBase(knowledgeBaseId).then(kb => {
      setKnowledgeBase(kb)
      setConfigA({
        ...DEFAULT_CONFIG,
        rerank_enabled: kb.settings?.rerank_enabled ?? true,
        rerank_candidate_k: kb.settings?.rerank_candidate_k ?? 10,
        rerank_fail_open: kb.settings?.rerank_fail_open ?? true,
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
    setError(false)
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
      setError(a.status === 'rejected' || (compare && b.status === 'rejected'))
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
          rerank_fail_open: preset.config.rerank_fail_open,
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
    return <div className="space-y-2">
      {response.timings?.length > 0 && <p className="text-xs text-muted-foreground">{t('stageTimings')}: {response.timings.map(timing => `${timing.stage} ${timing.latency_ms}ms`).join(' · ')}</p>}
      {response.diagnostics?.length > 0 && <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
        <strong>{t('diagnostics')}</strong>: {response.diagnostics.map(item => `${item.code}${item.stage ? ` (${item.stage})` : ''}${item.latency_ms !== undefined ? ` ${item.latency_ms}ms` : ''}${item.detail ? ` — ${item.detail}` : ''}`).join('; ')}
      </div>}
      {response.results.map((result, index) => {
        const open = expanded.has(`${side}:${result.chunk_id}`) || (side === 'a' && expanded.has(result.chunk_id))
        const movement = otherRanks.get(result.chunk_id)
        return <Card key={result.chunk_id}>
          <CardHeader className="cursor-pointer p-3" onClick={() => setExpanded(current => {
            const next = new Set(current)
            const key = `${side}:${result.chunk_id}`
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
          })}>
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="flex min-w-0 items-center gap-2"><Badge variant="outline">#{index + 1}</Badge><FileText className="h-3.5 w-3.5" /><strong className="truncate">{result.document_name}</strong></span>
              <span className="flex items-center gap-2"><Badge>{result.search_type || result.final_score_stage || t('unknownChannel')}</Badge>{movement && <span>{movement - (index + 1) > 0 ? '↑' : movement - (index + 1) < 0 ? '↓' : '→'} {Math.abs(movement - (index + 1))}</span>}{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</span>
            </div>
            {!open && <p className="line-clamp-2 text-xs text-muted-foreground"><Highlight text={result.content} query={query} /></p>}
          </CardHeader>
          {open && <CardContent className="space-y-3 px-3 pb-3">
            <div className="grid grid-cols-2 gap-1 text-[11px] md:grid-cols-5">
              <span>{t('denseStage')}: {raw(result.dense_score)} / #{result.dense_rank ?? '—'}</span>
              <span>{t('lexicalStage')}: {raw(result.lexical_score)} / #{result.lexical_rank ?? '—'}</span>
              <span>{t('fusionStage')}: {raw(result.fusion_score)} / #{result.fusion_rank ?? '—'}</span>
              <span>{t('rerankStage')}: {raw(result.rerank_score)} / #{result.rerank_rank ?? '—'}</span>
              <span>{t('finalStage')}: {raw(result.score)} ({result.final_score_stage ?? '—'})</span>
            </div>
            <div className="rounded bg-muted/50 p-3" data-color-mode={resolvedTheme === 'dark' ? 'dark' : 'light'}>
              {authenticatedMarkdown ? <MDPreview source={result.content} components={{ img: ({ src, alt }) => <AuthenticatedMarkdownImage src={typeof src === 'string' ? src : undefined} alt={alt} /> }} /> : <p className="whitespace-pre-wrap text-xs"><Highlight text={result.content} query={query} /></p>}
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

  const controls = (config: Config, setConfig: React.Dispatch<React.SetStateAction<Config>>, suffix: string) => <div className="grid gap-2 md:grid-cols-3">
    <Label>{t('searchMode')}<select aria-label={`${t('searchMode')} ${suffix}`} className="mt-1 h-9 w-full rounded border bg-background px-2" value={config.search_mode} onChange={event => setConfig(current => ({ ...current, search_mode: event.target.value as SearchMode }))}><option value="hybrid">{t('hybridSearch')}</option><option value="vector">{t('vectorSearch')}</option><option value="fulltext">{t('fulltextSearch')}</option></select></Label>
    <Label>{t('topK')}<Input id={`topK${suffix}`} type="number" min={1} max={20} value={config.top_k} onChange={event => setConfig(current => ({ ...current, top_k: Math.min(20, Math.max(1, Number(event.target.value) || 1)) }))} /></Label>
    <Label className="flex items-center gap-2 pt-6">{t('rerankEnabled')}<Switch checked={Boolean(knowledgeBase?.rerank_model) && config.rerank_enabled} disabled={!knowledgeBase?.rerank_model} onCheckedChange={value => setConfig(current => ({ ...current, rerank_enabled: value }))} /></Label>
    {advanced && <>
      <Label>{t('threshold')}<Input id={`threshold${suffix}`} type="number" min={0} max={1} step="any" value={config.threshold} onChange={event => setConfig(current => ({ ...current, threshold: Math.min(1, Math.max(0, Number(event.target.value) || 0)) }))} /></Label>
      <Label>{t('denseWeight')}<Input id={`denseWeight${suffix}`} type="number" min={0} step="any" value={config.dense_weight} onChange={event => setConfig(current => ({ ...current, dense_weight: Math.max(0, Number(event.target.value) || 0) }))} /></Label>
      <Label>{t('lexicalWeight')}<Input id={`lexicalWeight${suffix}`} type="number" min={0} step="any" value={config.lexical_weight} onChange={event => setConfig(current => ({ ...current, lexical_weight: Math.max(0, Number(event.target.value) || 0) }))} /></Label>
      <Label>{t('rrfK')}<Input id={`rrfK${suffix}`} type="number" min={1} max={1000} value={config.rrf_k} onChange={event => setConfig(current => ({ ...current, rrf_k: Math.min(1000, Math.max(1, Number(event.target.value) || 1)) }))} /></Label>
      <Label>{t('rerankCandidateK')}<Input id={`candidate${suffix}`} type="number" min={1} max={100} value={config.rerank_candidate_k} onChange={event => setConfig(current => ({ ...current, rerank_candidate_k: Math.min(100, Math.max(current.top_k, Number(event.target.value) || current.top_k)) }))} /></Label>
      <Label>{t('rerankScoreThreshold')}<Input id={`rerankThreshold${suffix}`} type="number" min={0} max={1} step="any" value={config.rerank_score_threshold ?? ''} onChange={event => setConfig(current => ({ ...current, rerank_score_threshold: event.target.value === '' ? null : Math.min(1, Math.max(0, Number(event.target.value))) }))} /></Label>
      <Label className="flex items-center gap-2">{t('rerankFailOpen')}<Switch checked={config.rerank_fail_open} onCheckedChange={value => setConfig(current => ({ ...current, rerank_fail_open: value }))} /></Label>
    </>}
  </div>

  return <div className="flex h-full flex-col gap-3 p-4">
    <header className="flex items-center gap-3"><Button render={<a href={backHref} />} variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button><div><h1 className="text-lg font-semibold">{t('retrievalLab')}</h1><p className="text-xs text-muted-foreground">{knowledgeBase?.name}</p></div></header>
    <Card><CardContent className="space-y-3 p-3">
      <div className="flex items-center justify-between"><strong className="text-sm">A</strong><Button variant="ghost" size="sm" onClick={() => setAdvanced(value => !value)}><Settings2 className="mr-1 h-4 w-4" />{t('advancedSettings')}</Button></div>
      {controls(configA, setConfigA, 'A')}
      <div className="flex items-center gap-2"><Switch id="compare" checked={compare} onCheckedChange={setCompare} /><Label htmlFor="compare">{t('compareAB')}</Label></div>
      {compare && <><strong className="text-sm">B</strong>{controls(configB, setConfigB, 'B')}</>}
      <div className="flex flex-wrap gap-2 border-t pt-3"><Input aria-label={t('presetName')} value={presetName} onChange={event => setPresetName(event.target.value)} placeholder={t('presetName')} className="max-w-48" /><Button variant="outline" onClick={savePreset}>{t('savePreset')}</Button><select aria-label={t('presets')} className="h-9 rounded border bg-background px-2" value={selectedPreset} onChange={event => { setSelectedPreset(event.target.value); const preset = presets.find(item => item.name === event.target.value); if (preset) setConfigA(preset.config) }}><option value="">{t('presets')}</option>{presets.map(preset => <option key={preset.name}>{preset.name}</option>)}</select><Button onClick={() => void applyPreset()} disabled={!selectedPreset || !canUpdate}>{t('applyToProduction')}</Button></div>
      {updateError && <p className="text-xs text-destructive">{t('presetUpdateError')}</p>}
    </CardContent></Card>
    <div className="flex gap-2"><div className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={handleKeyDown} placeholder={t('searchPlaceholder')} className="pl-9" /></div><Button aria-label={t('search')} onClick={() => void runSearch()} disabled={!query.trim() || searching}>{searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</Button></div>
    <main className="min-h-0 flex-1 overflow-auto">
      {!searched ? <div className="grid h-full place-content-center text-sm text-muted-foreground">{t('retrievalLabHint')}</div> : searching ? <div className="grid h-full place-content-center"><Loader2 className="animate-spin" /></div> : !responses.a && !responses.b ? <div className="grid h-full place-content-center text-sm text-destructive">{t('searchError')}</div> : responses.a?.results.length === 0 && !responses.b?.results.length ? <div className="grid h-full place-content-center text-sm text-muted-foreground">{t('noResults')}</div> : <>{error && <p className="mb-2 text-xs text-destructive">{t('searchPartialError')}</p>}{compare && responses.a && responses.b && <p className="mb-2 text-xs text-muted-foreground">{t('overlap', { count: overlap, total: Math.max(responses.a.results.length, responses.b.results.length) })}</p>}<div className={cn('grid gap-3', compare && 'lg:grid-cols-2')}><section><h2 className="mb-2 font-medium">A</h2>{responses.a ? renderResults(responses.a, 'a') : <p className="text-xs text-destructive">{t('searchSideError')}</p>}</section>{compare && <section><h2 className="mb-2 font-medium">B</h2>{responses.b ? renderResults(responses.b, 'b') : <p className="text-xs text-destructive">{t('searchSideError')}</p>}</section>}</div></>}
    </main>
  </div>
}
