import * as React from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle, ArrowDown, ArrowUp, Minus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { EvaluationRun, RunComparison } from '@/lib/api'

interface RunComparisonProps {
  runs: EvaluationRun[]
  knowledgeBaseId: string
  datasetId: string
  onCompare: (baselineId: string, candidateId: string) => Promise<RunComparison>
}

export function RunComparisonComponent({ runs, knowledgeBaseId, datasetId, onCompare }: RunComparisonProps) {
  const t = useTranslations('knowledgeBases')
  const [baselineId, setBaselineId] = React.useState<string>('')
  const [candidateId, setCandidateId] = React.useState<string>('')
  const [comparison, setComparison] = React.useState<RunComparison | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const completedRuns = runs.filter(r => r.status === 'completed')

  const handleCompare = React.useCallback(async () => {
    if (!baselineId || !candidateId) return

    setLoading(true)
    setError(null)
    try {
      const result = await onCompare(baselineId, candidateId)
      setComparison(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed')
      setComparison(null)
    } finally {
      setLoading(false)
    }
  }, [baselineId, candidateId, onCompare])

  const formatDelta = (value: number, metric: string) => {
    const isLatency = metric.includes('latency')
    const isError = metric.includes('error')
    const prefix = value > 0 ? '+' : ''
    const formatted = value.toFixed(isLatency ? 1 : 4)

    if (isLatency || isError) {
      // Higher latency or errors = worse
      return value > 0 ? (
        <span className="text-red-600">{prefix}{formatted}</span>
      ) : value < 0 ? (
        <span className="text-green-600">{formatted}</span>
      ) : (
        <span className="text-muted-foreground">{formatted}</span>
      )
    } else {
      // Higher quality metrics = better
      return value > 0 ? (
        <span className="text-green-600">{prefix}{formatted}</span>
      ) : value < 0 ? (
        <span className="text-red-600">{formatted}</span>
      ) : (
        <span className="text-muted-foreground">{formatted}</span>
      )
    }
  }

  const getDeltaIcon = (value: number, metric: string) => {
    const isLatency = metric.includes('latency')
    const isError = metric.includes('error')
    const isBetter = isLatency || isError ? value < 0 : value > 0
    const isWorse = isLatency || isError ? value > 0 : value < 0

    if (isBetter) return <ArrowUp className="h-3 w-3 text-green-600" />
    if (isWorse) return <ArrowDown className="h-3 w-3 text-red-600" />
    return <Minus className="h-3 w-3 text-muted-foreground" />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="text-sm font-medium mb-1.5 block">{t('selectBaselineRun')}</label>
          <Select value={baselineId} onValueChange={(value) => setBaselineId(value ?? '')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {completedRuns.map(run => (
                <SelectItem key={run.id} value={run.id}>
                  {new Date(run.created_at).toLocaleString()} - {run.config_snapshot.search_mode}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1">
          <label className="text-sm font-medium mb-1.5 block">{t('selectCandidateRun')}</label>
          <Select value={candidateId} onValueChange={(value) => setCandidateId(value ?? '')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {completedRuns.map(run => (
                <SelectItem key={run.id} value={run.id}>
                  {new Date(run.created_at).toLocaleString()} - {run.config_snapshot.search_mode}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={handleCompare}
          disabled={!baselineId || !candidateId || baselineId === candidateId || loading}
        >
          {loading ? 'Comparing...' : t('compareRuns')}
        </Button>
      </div>

      {error && (
        <div className="text-sm text-red-600 p-3 bg-red-50 rounded-md border border-red-200">
          {error}
        </div>
      )}

      {comparison && (
        <div className="space-y-6">
          {!comparison.comparable && (
            <div className="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-md">
              <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-800">
                <div className="font-medium">{t('incomparableRuns')}</div>
                {comparison.incompatibility_reason && (
                  <div className="mt-1">{t('incomparabilityReason', { reason: comparison.incompatibility_reason })}</div>
                )}
              </div>
            </div>
          )}

          {/* Metric Deltas */}
          <div>
            <h4 className="text-sm font-medium mb-3">{t('metricDeltas')}</h4>
            {Object.keys(comparison.metric_deltas).length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead className="text-right">{t('delta')}</TableHead>
                    <TableHead className="w-12"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(comparison.metric_deltas).map(([metric, delta]) => (
                    <TableRow key={metric}>
                      <TableCell className="font-mono text-xs">{metric}</TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {formatDelta(delta, metric)}
                      </TableCell>
                      <TableCell>{getDeltaIcon(delta, metric)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">{t('noMetricDeltas')}</p>
            )}
          </div>

          {/* Case Outcomes */}
          <div>
            <h4 className="text-sm font-medium mb-3">{t('caseOutcomes')}</h4>
            <div className="flex gap-3 text-sm">
              <Badge variant="outline" className="text-green-600 border-green-600">
                {t('improved')}: {comparison.improved_cases}
              </Badge>
              <Badge variant="outline">
                {t('unchanged')}: {comparison.unchanged_cases}
              </Badge>
              <Badge variant="outline" className="text-red-600 border-red-600">
                {t('regressed')}: {comparison.regressed_cases}
              </Badge>
              <Badge variant="outline" className="text-amber-600 border-amber-600">
                {t('unpaired')}: {comparison.unpaired_cases}
              </Badge>
            </div>
          </div>

          {/* Config Diff */}
          {Object.keys(comparison.config_diff).length > 0 && (
            <div>
              <h4 className="text-sm font-medium mb-3">{t('configDiff')}</h4>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Parameter</TableHead>
                    <TableHead>{t('baseline')}</TableHead>
                    <TableHead>{t('candidate')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(comparison.config_diff).map(([key, values]) => (
                    <TableRow key={key}>
                      <TableCell className="font-mono text-xs">{key}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {JSON.stringify(values.baseline)}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {JSON.stringify(values.candidate)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
