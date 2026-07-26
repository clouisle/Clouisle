import * as React from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { EvaluationDataset } from '@/lib/api'

interface DatasetQualityProps {
  dataset: EvaluationDataset
  onNavigateToCase?: (caseId: string) => void
}

interface QualityMetrics {
  totalCases: number
  casesWithChunkLabels: number
  casesWithDocumentLabels: number
  expectedEmptyCases: number
  averagePositiveLabels: number
  zeroSignalCases: Array<{ id: string; query: string }>
}

function analyzeDatasetQuality(dataset: EvaluationDataset): QualityMetrics {
  const totalCases = dataset.cases.length
  let casesWithChunkLabels = 0
  let casesWithDocumentLabels = 0
  let expectedEmptyCases = 0
  let totalPositiveLabels = 0
  const zeroSignalCases: Array<{ id: string; query: string }> = []

  for (const case_ of dataset.cases) {
    if (case_.expected_empty) {
      expectedEmptyCases++
      continue
    }

    const chunkPositive = Object.values(case_.chunk_relevance || {}).filter(v => v > 0).length
    const documentPositive = Object.values(case_.document_relevance || {}).filter(v => v > 0).length

    if (chunkPositive > 0) {
      casesWithChunkLabels++
      totalPositiveLabels += chunkPositive
    }
    if (documentPositive > 0) {
      casesWithDocumentLabels++
    }

    // Zero-signal case: not expected-empty but no positive labels
    if (chunkPositive === 0 && documentPositive === 0) {
      zeroSignalCases.push({ id: case_.id, query: case_.query })
    }
  }

  const nonEmptyCases = totalCases - expectedEmptyCases
  const averagePositiveLabels = nonEmptyCases > 0 ? totalPositiveLabels / nonEmptyCases : 0

  return {
    totalCases,
    casesWithChunkLabels,
    casesWithDocumentLabels,
    expectedEmptyCases,
    averagePositiveLabels,
    zeroSignalCases,
  }
}

export function DatasetQuality({ dataset, onNavigateToCase }: DatasetQualityProps) {
  const t = useTranslations('knowledgeBases')
  const metrics = React.useMemo(() => analyzeDatasetQuality(dataset), [dataset])

  const hasWarnings = metrics.zeroSignalCases.length > 0 || metrics.totalCases < 10

  return (
    <div className="space-y-3 p-3 border rounded-md bg-muted/30">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{t('datasetQuality')}</h4>
        {hasWarnings && (
          <Badge variant="outline" className="text-amber-600 border-amber-600">
            <AlertTriangle className="h-3 w-3 mr-1" />
            {t('qualityWarnings')}
          </Badge>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">{t('totalCases')}:</span>{' '}
          <Badge variant="secondary">{metrics.totalCases}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('expectedEmpty')}:</span>{' '}
          <Badge variant="secondary">{metrics.expectedEmptyCases}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('withChunkLabels')}:</span>{' '}
          <Badge variant="secondary">{metrics.casesWithChunkLabels}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('withDocumentLabels')}:</span>{' '}
          <Badge variant="secondary">{metrics.casesWithDocumentLabels}</Badge>
        </div>
        <div className="col-span-2">
          <span className="text-muted-foreground">{t('avgPositiveLabels')}:</span>{' '}
          <Badge variant="secondary">{metrics.averagePositiveLabels.toFixed(1)}</Badge>
        </div>
      </div>

      {metrics.totalCases < 10 && (
        <div className="text-xs text-amber-600 flex items-start gap-1">
          <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
          <span>{t('lowCaseCountWarning')}</span>
        </div>
      )}

      {metrics.zeroSignalCases.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-amber-600 flex items-start gap-1">
            <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
            <span>{t('zeroSignalCasesWarning', { count: metrics.zeroSignalCases.length })}</span>
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {metrics.zeroSignalCases.map(case_ => (
              <div key={case_.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate text-muted-foreground" title={case_.query}>
                  {case_.query}
                </span>
                {onNavigateToCase && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => onNavigateToCase(case_.id)}
                  >
                    {t('fix')}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
