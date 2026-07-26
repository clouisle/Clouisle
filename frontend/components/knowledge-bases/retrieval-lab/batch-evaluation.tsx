'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { FileText } from 'lucide-react'
import type { EvaluationDataset, EvaluationRun } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { formatDuration } from '@/lib/utils'
import { type Config, type RetrievalApi, runConfig } from './shared'

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
