'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Play, X, CheckCircle2, AlertCircle, Loader2, TrendingUp } from 'lucide-react'
import type { EvaluationDataset, EvaluationSweep, EvaluationSweepCreate } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import type { RetrievalApi } from './shared'

interface ParameterSweepProps {
  knowledgeBaseId: string
  datasets: EvaluationDataset[]
  api: RetrievalApi
  canEvaluate: boolean
}

export function ParameterSweep({ knowledgeBaseId, datasets, api, canEvaluate }: ParameterSweepProps) {
  const t = useTranslations('knowledgeBases')
  const [datasetId, setDatasetId] = React.useState(() => datasets[0]?.id ?? '')
  const [sweep, setSweep] = React.useState<EvaluationSweep | null>(null)
  const [objective, setObjective] = React.useState<'ndcg' | 'mrr' | 'recall'>('ndcg')
  const [metricK, setMetricK] = React.useState('5')
  const [servingTopK, setServingTopK] = React.useState('10')
  const [space, setSpace] = React.useState(JSON.stringify({
    dense_weight: [0.5, 1.0, 1.5],
    lexical_weight: [0.5, 1.0, 1.5],
    rrf_k: [30, 60, 90],
  }, null, 2))
  const [guards, setGuards] = React.useState(JSON.stringify({
    min_ndcg_5: 0.3,
    max_latency_p95_ms: 1000,
  }, null, 2))
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')

  // Reset sweep when dataset changes
  React.useEffect(() => { setSweep(null); setError('') }, [datasetId])

  // Poll sweep status while active
  React.useEffect(() => {
    if (!sweep || !datasetId || !['pending', 'running'].includes(sweep.status)) return
    const timer = window.setInterval(() => {
      api.getEvaluationSweep(knowledgeBaseId, datasetId, sweep.id)
        .then(setSweep)
        .catch(() => setError(t('sweepLoadError')))
    }, 3000)
    return () => window.clearInterval(timer)
  }, [api, knowledgeBaseId, datasetId, sweep, t])

  const startSweep = async () => {
    if (!canEvaluate || !datasetId) return
    setBusy(true)
    setError('')
    try {
      const parsedSpace = JSON.parse(space) as Record<string, unknown>
      const parsedGuards = JSON.parse(guards) as Record<string, unknown>
      const payload: EvaluationSweepCreate = {
        objective,
        metric_k: Number.parseInt(metricK, 10),
        serving_top_k: Number.parseInt(servingTopK, 10),
        space: parsedSpace,
        guards: parsedGuards,
      }
      const created = await api.createEvaluationSweep(knowledgeBaseId, datasetId, payload)
      setSweep(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('sweepStartError'))
    } finally {
      setBusy(false)
    }
  }

  const cancelSweep = async () => {
    if (!sweep || !canEvaluate || !datasetId) return
    setBusy(true)
    setError('')
    try {
      await api.cancelEvaluationSweep(knowledgeBaseId, datasetId, sweep.id)
      const updated = await api.getEvaluationSweep(knowledgeBaseId, datasetId, sweep.id)
      setSweep(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('sweepCancelError'))
    } finally {
      setBusy(false)
    }
  }

  const applySweep = async () => {
    if (!sweep || !canEvaluate || !datasetId) return
    setBusy(true)
    setError('')
    try {
      await api.applyEvaluationSweep(knowledgeBaseId, datasetId, sweep.id)
      const updated = await api.getEvaluationSweep(knowledgeBaseId, datasetId, sweep.id)
      setSweep(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('sweepApplyError'))
    } finally {
      setBusy(false)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin" />
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-600" />
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-600" />
      case 'canceled':
        return <X className="h-4 w-4 text-gray-600" />
      default:
        return null
    }
  }

  const getStatusBadge = (status: string) => {
    const variant = status === 'completed' ? 'default' : status === 'failed' ? 'destructive' : 'secondary'
    return (
      <Badge variant={variant} className="gap-1">
        {getStatusIcon(status)}
        {status}
      </Badge>
    )
  }

  const totalProgress = React.useMemo(() => {
    if (!sweep?.progress) return 0
    const stages = Object.values(sweep.progress)
    const totalWork = stages.reduce((sum, stage) => sum + stage.total, 0)
    const completedWork = stages.reduce((sum, stage) => sum + stage.completed, 0)
    return totalWork > 0 ? (completedWork / totalWork) * 100 : 0
  }, [sweep?.progress])

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            {t('parameterSweep')}
          </CardTitle>
          <CardDescription>{t('parameterSweepDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!sweep && (
            <div className="space-y-4">
              {datasets.length > 1 && (
                <div className="space-y-2">
                  <Label>{t('selectDataset')}</Label>
                  <Select value={datasetId} onValueChange={setDatasetId}>
                    <SelectTrigger>
                      <SelectValue placeholder={t('selectDataset')} />
                    </SelectTrigger>
                    <SelectContent>
                      {datasets.map(ds => (
                        <SelectItem key={ds.id} value={ds.id}>{ds.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {!datasetId && (
                <Alert>
                  <AlertDescription>{t('selectDatasetFirst')}</AlertDescription>
                </Alert>
              )}
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>{t('objective')}</Label>
                  <Select value={objective} onValueChange={(v) => setObjective(v as typeof objective)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ndcg">NDCG</SelectItem>
                      <SelectItem value="mrr">MRR</SelectItem>
                      <SelectItem value="recall">Recall</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>{t('metricK')}</Label>
                  <Input
                    type="number"
                    min="1"
                    max="20"
                    value={metricK}
                    onChange={(e) => setMetricK(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>{t('servingTopK')}</Label>
                  <Input
                    type="number"
                    min="1"
                    max="100"
                    value={servingTopK}
                    onChange={(e) => setServingTopK(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>{t('parameterSpace')}</Label>
                <Textarea
                  rows={8}
                  value={space}
                  onChange={(e) => setSpace(e.target.value)}
                  placeholder={t('parameterSpacePlaceholder')}
                  className="font-mono text-sm"
                />
              </div>

              <div className="space-y-2">
                <Label>{t('guards')}</Label>
                <Textarea
                  rows={4}
                  value={guards}
                  onChange={(e) => setGuards(e.target.value)}
                  placeholder={t('guardsPlaceholder')}
                  className="font-mono text-sm"
                />
              </div>

              <Button onClick={startSweep} disabled={busy || !canEvaluate} className="w-full">
                <Play className="mr-2 h-4 w-4" />
                {t('startSweep')}
              </Button>
            </div>
          )}

          {sweep && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{t('sweepStatus')}:</span>
                    {getStatusBadge(sweep.status)}
                  </div>
                  {sweep.stage && (
                    <div className="text-sm text-muted-foreground">
                      {t('currentStage')}: {sweep.stage}
                    </div>
                  )}
                </div>
                {sweep.status === 'running' && (
                  <Button onClick={cancelSweep} disabled={busy} variant="outline" size="sm">
                    <X className="mr-2 h-4 w-4" />
                    {t('cancelSweep')}
                  </Button>
                )}
              </div>

              {['pending', 'running'].includes(sweep.status) && (
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>{t('progress')}</span>
                    <span>{Math.round(totalProgress)}%</span>
                  </div>
                  <Progress value={totalProgress} />
                </div>
              )}

              {sweep.progress && Object.keys(sweep.progress).length > 0 && (
                <div className="space-y-2">
                  <Label>{t('stageProgress')}</Label>
                  {Object.entries(sweep.progress).map(([stage, { total, completed }]) => (
                    <div key={stage} className="flex items-center justify-between text-sm">
                      <span className="font-medium">{stage}</span>
                      <span className="text-muted-foreground">
                        {completed} / {total}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {sweep.error_message && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{sweep.error_message}</AlertDescription>
                </Alert>
              )}

              {sweep.recommendation && sweep.status === 'completed' && (
                <Card className="bg-muted/50">
                  <CardHeader>
                    <CardTitle className="text-base">{t('recommendation')}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-2">
                      <Label>{t('bestConfig')}</Label>
                      <pre className="rounded-md bg-background p-3 text-xs overflow-auto">
                        {JSON.stringify(sweep.recommendation, null, 2)}
                      </pre>
                    </div>

                    {!sweep.applied && (
                      <Button onClick={applySweep} disabled={busy || !canEvaluate} className="w-full">
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        {t('applyRecommendation')}
                      </Button>
                    )}

                    {sweep.applied && (
                      <Alert>
                        <CheckCircle2 className="h-4 w-4" />
                        <AlertDescription>
                          {t('recommendationApplied')} {sweep.applied_at && `at ${new Date(sweep.applied_at).toLocaleString()}`}
                        </AlertDescription>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
