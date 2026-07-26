import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { CandidateChunk } from './candidate-pool'
import type { Grade } from './labeling'

interface QualityPanelProps {
  candidates: CandidateChunk[]
  grades: Record<string, Grade>
  onBulkMarkIrrelevant: () => void
  canEdit: boolean
}

export function QualityPanel({ candidates, grades, onBulkMarkIrrelevant, canEdit }: QualityPanelProps) {
  const t = useTranslations('knowledgeBases')

  const judged = candidates.filter(c => grades[c.chunk_id] !== undefined).length
  const unjudged = candidates.length - judged

  const positiveCount = candidates.filter(c => {
    const grade = grades[c.chunk_id]
    return grade === 'relevant' || grade === 'partial'
  }).length

  const negativeCount = candidates.filter(c => grades[c.chunk_id] === 'irrelevant').length

  const strategies = React.useMemo(() => {
    const strategySet = new Set<string>()
    candidates.forEach(c => c.strategies.forEach(s => strategySet.add(s)))
    return Array.from(strategySet)
  }, [candidates])

  const uniqueContributions = React.useMemo(() => {
    const counts: Record<string, number> = {}
    strategies.forEach(s => {
      counts[s] = candidates.filter(c => c.strategies.length === 1 && c.strategies[0] === s).length
    })
    return counts
  }, [candidates, strategies])

  const overlapCount = candidates.filter(c => c.strategies.length > 1).length

  const coverage = candidates.length > 0 ? ((judged / candidates.length) * 100).toFixed(1) : '0.0'

  return (
    <div className="space-y-3 p-3 border rounded-md bg-muted/30">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{t('qualityMetrics')}</h4>
        {unjudged > 0 && canEdit && (
          <Button
            variant="outline"
            size="sm"
            onClick={onBulkMarkIrrelevant}
          >
            {t('markAllUnlabeledIrrelevant')}
          </Button>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">{t('candidatesLabel')}:</span>{' '}
          <Badge variant="secondary">{candidates.length}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('judgedLabel')}:</span>{' '}
          <Badge variant="secondary">{judged}</Badge>{' '}
          <span className="text-muted-foreground">/ {unjudged} {t('unjudged')}</span>
        </div>
        <div>
          <span className="text-muted-foreground">{t('positiveLabel')}:</span>{' '}
          <Badge variant="secondary">{positiveCount}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('negativeLabel')}:</span>{' '}
          <Badge variant="secondary">{negativeCount}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('overlapLabel')}:</span>{' '}
          <Badge variant="secondary">{overlapCount}</Badge>
        </div>
        <div>
          <span className="text-muted-foreground">{t('coverageLabel')}:</span>{' '}
          <Badge variant="secondary">{coverage}%</Badge>
        </div>
      </div>

      <div className="text-xs space-y-1">
        <div className="text-muted-foreground">{t('strategyContributions')}:</div>
        <div className="flex flex-wrap gap-1">
          {strategies.map(s => (
            <Badge key={s} variant="outline" className="text-[10px]">
              {s}: {uniqueContributions[s] || 0} {t('unique')}
            </Badge>
          ))}
        </div>
      </div>

      <p className="text-[10px] text-muted-foreground italic">
        {t('poolRelativeNote')}
      </p>
    </div>
  )
}
