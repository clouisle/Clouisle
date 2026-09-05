import { describe, expect, test } from 'bun:test'

import {
  TONE_STYLES,
  abnormalReason,
  formatBucket,
  formatCompactNumber,
  formatDuration,
  formatNumber,
  formatPercent,
  getRiskLevel,
  percentOf,
  readNumber,
  readString,
  sourceLabel,
  statusLabel,
  timeoutTypeLabel,
  workerTaskLabel,
  toneBarClass,
  toneDotClass,
  toneForStatus,
  toneTextClass,
} from './observability-helpers'

const t = (key: string) => `translated:${key}`

describe('observability helpers', () => {
  test('classifies risk at exact thresholds and prioritizes TTFT', () => {
    expect(getRiskLevel(0, 99, 9999, null)).toEqual({ key: 'healthy', summaryKey: 'healthSummaryHealthy', tone: 'success' })
    expect(getRiskLevel(1, 99, 0, null)).toEqual({ key: 'warning', summaryKey: 'healthSummaryWarning', tone: 'warning' })
    expect(getRiskLevel(5, 100, 0, null)).toEqual({ key: 'critical', summaryKey: 'healthSummaryCritical', tone: 'danger' })
    expect(getRiskLevel(0, 100, 30000, 2999)).toEqual({ key: 'healthy', summaryKey: 'healthSummaryHealthy', tone: 'success' })
    expect(getRiskLevel(0, 100, 0, 10000)).toEqual({ key: 'critical', summaryKey: 'healthSummaryCritical', tone: 'danger' })
  })

  test('maps tones, classes, and known labels without application dependencies', () => {
    expect(toneForStatus('failed')).toBe('danger')
    expect(toneForStatus('running')).toBe('info')
    expect(toneForStatus('other')).toBe('neutral')
    expect(TONE_STYLES.warning).toContain('bg-amber-500/10')
    expect(toneDotClass('success')).toBe('bg-emerald-500')
    expect(toneBarClass('neutral')).toBe('bg-muted-foreground/50')
    expect(toneTextClass('danger')).toBe('text-destructive')
    expect(statusLabel(null, t)).toBe('translated:status.unknown')
    expect(statusLabel('custom', t)).toBe('custom')
    expect(sourceLabel('agent', t)).toBe('translated:sources.agent')
    expect(sourceLabel('other', t)).toBe('translated:sources.other')
    expect(sourceLabel('custom', t)).toBe('translated:sources.unknown')
    expect(timeoutTypeLabel('global', t)).toBe('translated:timeoutTypes.global')
    expect(timeoutTypeLabel('custom', t)).toBe('custom')
    expect(workerTaskLabel('app.tasks.knowledge_base.embed_document_chunks_task', t)).toBe('translated:workers.tasks.embedDocumentChunks')
    expect(workerTaskLabel('send_notification_email', t)).toBe('translated:workers.tasks.sendEmailNotification')
    expect(workerTaskLabel('app.tasks.workflow.resume_workflow_task', t)).toBe('translated:workers.tasks.resumeWorkflow')
    expect(workerTaskLabel('resume_workflow_task', t)).toBe('translated:workers.tasks.resumeWorkflow')
    expect(workerTaskLabel('app.tasks.agent.run_agent_task', t)).toBe('translated:workers.tasks.runAgentTask')
    expect(workerTaskLabel('run_agent_task', t)).toBe('translated:workers.tasks.runAgentTask')
    expect(workerTaskLabel('custom', t)).toBe('custom')
  })

  test('reads safe values and formats fallbacks', () => {
    const row = { number: 3, numeric: ' 4 ', blank: ' ', infinite: Infinity, reason: 'failed', detail: 'unused' }
    expect(readNumber(row, ['infinite', 'numeric', 'number'])).toBe(4)
    expect(readNumber(row, ['blank'])).toBeNull()
    expect(readString(row, ['blank', 'detail'])).toBe('unused')
    expect(readString(row, ['missing'])).toBe('-')
    expect(abnormalReason(row)).toBe('failed')
    expect(formatNumber(null)).toBe('-')
    expect(formatNumber(1234)).toBe(new Intl.NumberFormat().format(1234))
    expect(formatCompactNumber(1234)).toBe(new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(1234))
    expect(formatPercent(1.24)).toBe('1.2%')
    expect(formatDuration(null)).toBe('-')
    expect(formatDuration(999.6)).toBe('1000ms')
    expect(formatDuration(1000)).toBe('1.0s')
    expect(formatBucket('invalid')).toBe('invalid')
    expect(formatBucket(null)).toBe('-')
    expect(percentOf(1, 3)).toBe(33.3)
    expect(percentOf(1, 0)).toBe(0)
  })
})
