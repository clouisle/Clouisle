'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Play, X, CheckCircle2, AlertCircle, Loader2, TrendingUp, Plus, Minus, Info } from 'lucide-react'
import type { EvaluationDataset, EvaluationSweep, EvaluationSweepCreate, EvaluationRun } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { RetrievalApi } from './shared'

interface ParameterSweepProps {
  knowledgeBaseId: string
  datasets: EvaluationDataset[]
  api: RetrievalApi
  canEvaluate: boolean
}

type ParameterAxis = {
  key: string
  values: number[]
}

export function ParameterSweep({ knowledgeBaseId, datasets, api, canEvaluate }: ParameterSweepProps) {
  const t = useTranslations('knowledgeBases')
  const [datasetId, setDatasetId] = React.useState(() => datasets[0]?.id ?? '')
  const [sweep, setSweep] = React.useState<EvaluationSweep | null>(null)
  const [childRuns, setChildRuns] = React.useState<EvaluationRun[]>([])
  const [objective, setObjective] = React.useState<'ndcg' | 'mrr' | 'recall'>('ndcg')
  const [metricK, setMetricK] = React.useState('5')
  const [servingTopK, setServingTopK] = React.useState('10')
  const [parameterAxes, setParameterAxes] = React.useState<ParameterAxis[]>([
    { key: 'dense_weight', values: [0.5, 1.0, 1.5] },
    { key: 'lexical_weight', values: [0.5, 1.0, 1.5] },
    { key: 'rrf_k', values: [30, 60, 90] },
  ])
  const [guards, setGuards] = React.useState(JSON.stringify({
    min_ndcg_5: 0.3,
    max_latency_p95_ms: 1000,
  }, null, 2))
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState('')
  const [showApplyDialog, setShowApplyDialog] = React.useState(false)

  // Calculate total configurations
  const totalConfigs = React.useMemo(() => {
    return parameterAxes.reduce((product, axis) => product * axis.values.length, 1)
  }, [parameterAxes])

  // Estimated cost and duration
  const estimatedDuration = React.useMemo(() => {
    const dataset = datasets.find(d => d.id === datasetId)
    if (!dataset || !dataset.cases || dataset.cases.length === 0) return null
    // Rough estimate: 2s per case per config
    const seconds = dataset.cases.length * totalConfigs * 2
    const minutes = Math.ceil(seconds / 60)
    return minutes
  }, [datasetId, datasets, totalConfigs])

  // Reset sweep when dataset changes
  React.useEffect(() => {
    setSweep(null)
    setChildRuns([])
    setError('')
  }, [datasetId])

  // Load child runs when sweep completes
  React.useEffect(() => {
    if (!sweep || !datasetId || sweep.status !== 'completed') return
    api.listEvaluationRuns(knowledgeBaseId, datasetId, sweep.id)
      .then(setChildRuns)
      .catch(() => setError(t('sweepRunsLoadError')))
  }, [api, knowledgeBaseId, datasetId, sweep, t])

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
      // Convert parameter axes to space object
      const space: Record<string, number[]> = {}
      for (const axis of parameterAxes) {
        space[axis.key] = axis.values
      }
      const parsedGuards = JSON.parse(guards) as Record<string, unknown>
      const payload: EvaluationSweepCreate = {
        objective: `chunk_${objective}` as 'chunk_ndcg' | 'chunk_mrr' | 'chunk_recall' | 'document_ndcg' | 'document_mrr' | 'document_recall',
        metric_k: Number.parseInt(metricK, 10),
        serving_top_k: Number.parseInt(servingTopK, 10),
        space,
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
    setShowApplyDialog(false)
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

  const addParameterAxis = () => {
    setParameterAxes([...parameterAxes, { key: 'new_param', values: [1.0] }])
  }

  const removeParameterAxis = (index: number) => {
    setParameterAxes(parameterAxes.filter((_, i) => i !== index))
  }

  const updateAxisKey = (index: number, key: string) => {
    const updated = [...parameterAxes]
    updated[index] = { ...updated[index], key }
    setParameterAxes(updated)
  }

  const addAxisValue = (index: number) => {
    const updated = [...parameterAxes]
    const lastValue = updated[index].values[updated[index].values.length - 1] || 1.0
    updated[index] = { ...updated[index], values: [...updated[index].values, lastValue] }
    setParameterAxes(updated)
  }

  const removeAxisValue = (axisIndex: number, valueIndex: number) => {
    const updated = [...parameterAxes]
    updated[axisIndex] = {
      ...updated[axisIndex],
      values: updated[axisIndex].values.filter((_, i) => i !== valueIndex)
    }
    setParameterAxes(updated)
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
                  <Select value={datasetId} onValueChange={(v) => v && setDatasetId(v)}>
                    <SelectTrigger>
                      <SelectValue />
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
                <div className="space-y-3 rounded-md border p-4">
                  {parameterAxes.map((axis, axisIndex) => (
                    <div key={axisIndex} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <Input
                          className="flex-1"
                          placeholder={t('parameterName')}
                          value={axis.key}
                          onChange={(e) => updateAxisKey(axisIndex, e.target.value)}
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => removeParameterAxis(axisIndex)}
                          disabled={parameterAxes.length === 1}
                        >
                          <Minus className="h-4 w-4" />
                        </Button>
                      </div>
                      <div className="flex items-center gap-2">
                        <Label className="text-xs text-muted-foreground w-16">{t('values')}</Label>
                        <div className="flex-1 flex flex-wrap gap-2">
                          {axis.values.map((value, valueIndex) => (
                            <div key={valueIndex} className="flex items-center gap-1">
                              <Input
                                type="number"
                                step="0.1"
                                className="w-20"
                                value={value}
                                onChange={(e) => {
                                  const updated = [...parameterAxes]
                                  const newValues = [...updated[axisIndex].values]
                                  newValues[valueIndex] = parseFloat(e.target.value) || 0
                                  updated[axisIndex] = { ...updated[axisIndex], values: newValues }
                                  setParameterAxes(updated)
                                }}
                              />
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => removeAxisValue(axisIndex, valueIndex)}
                                disabled={axis.values.length === 1}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          ))}
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => addAxisValue(axisIndex)}
                          >
                            <Plus className="h-3 w-3 mr-1" />
                            {t('addValue')}
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={addParameterAxis}
                    className="w-full"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    {t('addParameter')}
                  </Button>
                  <div className="flex items-center justify-between pt-2 border-t">
                    <span className="text-sm font-medium">{t('totalConfigs')}</span>
                    <Badge variant="secondary" className="text-base">
                      {totalConfigs}
                    </Badge>
                  </div>
                  {estimatedDuration && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Info className="h-4 w-4" />
                      <span>{t('estimatedDuration', { minutes: estimatedDuration })}</span>
                    </div>
                  )}
                </div>
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

              {sweep.status === 'completed' && childRuns.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">{t('sweepResults')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="rounded-md border overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>{t('config')}</TableHead>
                            <TableHead>{t('objectiveMetric')}</TableHead>
                            <TableHead>{t('delta')}</TableHead>
                            <TableHead>{t('improved')}</TableHead>
                            <TableHead>{t('regressed')}</TableHead>
                            <TableHead>P95 (ms)</TableHead>
                            <TableHead>{t('errors')}</TableHead>
                            <TableHead>{t('guardStatus')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {childRuns
                            .sort((a, b) => {
                              const aMetric = a.summary_metrics?.[`${objective}_${metricK}`] ?? 0
                              const bMetric = b.summary_metrics?.[`${objective}_${metricK}`] ?? 0
                              return (bMetric as number) - (aMetric as number)
                            })
                            .map((run) => {
                              const isBaseline = run.label === 'baseline'
                              const metric = run.summary_metrics?.[`${objective}_${metricK}`]
                              const baselineRun = childRuns.find(r => r.label === 'baseline')
                              const baselineMetric = baselineRun?.summary_metrics?.[`${objective}_${metricK}`]
                              const delta = metric != null && baselineMetric != null ? (metric as number) - (baselineMetric as number) : null
                              const p95 = run.summary_metrics?.latency_p95_ms
                              const errorCount = run.summary_metrics?.error_count
                              const errors = typeof errorCount === 'number' ? errorCount : 0
                              const guardViolated = run.summary_metrics?.guard_violated

                              return (
                                <TableRow key={run.id} className={isBaseline ? 'bg-muted/50 font-medium' : ''}>
                                  <TableCell>
                                    <div className="flex items-center gap-2">
                                      {run.label || run.candidate_key}
                                      {isBaseline && <Badge variant="outline">{t('baseline')}</Badge>}
                                    </div>
                                  </TableCell>
                                  <TableCell>{typeof metric === 'number' ? metric.toFixed(4) : '-'}</TableCell>
                                  <TableCell>
                                    {delta != null ? (
                                      <span className={delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-600' : ''}>
                                        {delta > 0 ? '+' : ''}{delta.toFixed(4)}
                                      </span>
                                    ) : '-'}
                                  </TableCell>
                                  <TableCell>{typeof run.summary_metrics?.improved_count === 'number' ? run.summary_metrics.improved_count : '-'}</TableCell>
                                  <TableCell>{typeof run.summary_metrics?.regressed_count === 'number' ? run.summary_metrics.regressed_count : '-'}</TableCell>
                                  <TableCell>{typeof p95 === 'number' ? p95.toFixed(0) : '-'}</TableCell>
                                  <TableCell>{errors}</TableCell>
                                  <TableCell>
                                    {guardViolated ? (
                                      <Badge variant="destructive">{t('violated')}</Badge>
                                    ) : guardViolated === false ? (
                                      <Badge variant="secondary">{t('passed')}</Badge>
                                    ) : '-'}
                                  </TableCell>
                                </TableRow>
                              )
                            })}
                        </TableBody>
                      </Table>
                    </div>
                  </CardContent>
                </Card>
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

                    {sweep.best_run_id && childRuns.length > 0 && (
                      <div className="space-y-2">
                        <Label>{t('evidence')}</Label>
                        <div className="rounded-md bg-background p-3 space-y-2 text-sm">
                          {(() => {
                            const bestRun = childRuns.find(r => r.id === sweep.best_run_id)
                            const baselineRun = childRuns.find(r => r.label === 'baseline')
                            if (!bestRun || !baselineRun) return null

                            const bestMetric = bestRun.summary_metrics?.[`${objective}_${metricK}`]
                            const baselineMetric = baselineRun.summary_metrics?.[`${objective}_${metricK}`]
                            const delta = bestMetric != null && baselineMetric != null ? (bestMetric as number) - (baselineMetric as number) : null
                            const improvedCount = bestRun.summary_metrics?.improved_count
                            const improved = typeof improvedCount === 'number' ? improvedCount : 0
                            const regressedCount = bestRun.summary_metrics?.regressed_count
                            const regressed = typeof regressedCount === 'number' ? regressedCount : 0

                            return (
                              <>
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">{t('metricImprovement')}</span>
                                  <span className="font-medium text-green-600">
                                    {delta != null ? `+${delta.toFixed(4)}` : '-'}
                                  </span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">{t('casesImproved')}</span>
                                  <span className="font-medium">{improved}</span>
                                </div>
                                <div className="flex justify-between">
                                  <span className="text-muted-foreground">{t('casesRegressed')}</span>
                                  <span className="font-medium">{regressed}</span>
                                </div>
                                {sweep.verification_run_id && (
                                  <div className="pt-2 border-t">
                                    <Badge variant="secondary" className="gap-1">
                                      <CheckCircle2 className="h-3 w-3" />
                                      {t('verified')}
                                    </Badge>
                                  </div>
                                )}
                              </>
                            )
                          })()}
                        </div>
                      </div>
                    )}

                    {!sweep.applied && (
                      <Button
                        onClick={() => setShowApplyDialog(true)}
                        disabled={busy || !canEvaluate}
                        className="w-full"
                      >
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        {t('applyToProduction')}
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

      <Dialog open={showApplyDialog} onOpenChange={setShowApplyDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('confirmApply')}</DialogTitle>
            <DialogDescription>{t('confirmApplyDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t('parameterDiff')}</Label>
            <pre className="rounded-md bg-muted p-3 text-xs overflow-auto max-h-64">
              {sweep?.recommendation ? JSON.stringify(sweep.recommendation, null, 2) : ''}
            </pre>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowApplyDialog(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={applySweep} disabled={busy}>
              {t('confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
