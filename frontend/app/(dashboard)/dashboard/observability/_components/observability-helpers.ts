export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'
type ObservabilityTranslator = (key: never) => string

function translate(t: ObservabilityTranslator, key: string) {
  return t(key as never)
}
const WORKER_TASK_KEYS: Record<string, string> = {
  // Agent
  'run_agent_task': 'runAgentTask',
  'app.tasks.agent.run_agent_task': 'runAgentTask',

  // Workflow
  'run_workflow_task': 'runWorkflow',
  'app.tasks.workflow.run_workflow_task': 'runWorkflow',
  'resume_workflow_task': 'resumeWorkflow',
  'app.tasks.workflow.resume_workflow_task': 'resumeWorkflow',
  'cancel_workflow_task': 'cancelWorkflow',
  'app.tasks.workflow.cancel_workflow_task': 'cancelWorkflow',

  // Knowledge Base
  'backfill_lexical_index_task': 'backfillLexicalIndex',
  'app.tasks.knowledge_base.backfill_lexical_index_task': 'backfillLexicalIndex',
  'embed_document_chunks_task': 'embedDocumentChunks',
  'app.tasks.knowledge_base.embed_document_chunks_task': 'embedDocumentChunks',
  'index_document_lexically_task': 'indexDocumentLexically',
  'app.tasks.knowledge_base.index_document_lexically_task': 'indexDocumentLexically',
  'process_document_task': 'processDocument',
  'app.tasks.knowledge_base.process_document_task': 'processDocument',
  'process_url_document_task': 'processUrlDocument',
  'app.tasks.knowledge_base.process_url_document_task': 'processUrlDocument',
  'rechunk_document_task': 'rechunkDocument',
  'app.tasks.knowledge_base.rechunk_document_task': 'rechunkDocument',
  'reprocess_document_task': 'reprocessDocument',
  'app.tasks.knowledge_base.reprocess_document_task': 'reprocessDocument',
  'retry_failed_chunk_task': 'retryFailedChunk',
  'app.tasks.knowledge_base.retry_failed_chunk_task': 'retryFailedChunk',
  'retry_failed_chunks_task': 'retryFailedChunks',
  'app.tasks.knowledge_base.retry_failed_chunks_task': 'retryFailedChunks',

  // Sandbox
  'run_sandbox_job_task': 'runSandboxJob',
  'app.tasks.sandbox.run_sandbox_job_task': 'runSandboxJob',
  'cleanup_expired_sandbox_sessions': 'cleanupSandboxSessions',
  'cleanup_expired_sandbox_sessions_task': 'cleanupSandboxSessions',
  'tasks.cleanup_expired_sandbox_sessions': 'cleanupSandboxSessions',
  'app.tasks.sandbox.cleanup_expired_sandbox_sessions_task': 'cleanupSandboxSessions',

  // Session Memory
  'extract_session_memory_task': 'extractSessionMemory',
  'app.tasks.session_memory.extract_session_memory_task': 'extractSessionMemory',

  // Notifications
  'send_notification_task': 'sendNotification',
  'app.tasks.notification.send_notification_task': 'sendNotification',
  'send_notification_email': 'sendEmailNotification',
  'send_notification_email_task': 'sendEmailNotification',
  'app.tasks.notification.send_notification_email_task': 'sendEmailNotification',
  'send_notification_dingtalk': 'sendDingTalkNotification',
  'send_notification_dingtalk_task': 'sendDingTalkNotification',
  'app.tasks.notification.send_notification_dingtalk_task': 'sendDingTalkNotification',
  'send_notification_wechat': 'sendWeChatNotification',
  'send_notification_wechat_task': 'sendWeChatNotification',
  'app.tasks.notification.send_notification_wechat_task': 'sendWeChatNotification',
  'send_notification_feishu': 'sendFeishuNotification',
  'send_notification_feishu_task': 'sendFeishuNotification',
  'app.tasks.notification.send_notification_feishu_task': 'sendFeishuNotification',
  'send_notification_webhook': 'sendWebhookNotification',
  'send_notification_webhook_task': 'sendWebhookNotification',
  'app.tasks.notification.send_notification_webhook_task': 'sendWebhookNotification',
  'send_notification_slack': 'sendSlackNotification',
  'send_notification_slack_task': 'sendSlackNotification',
  'app.tasks.notification.send_notification_slack_task': 'sendSlackNotification',

  // Audit & Security & Usage
  'create_audit_log_task': 'createAuditLog',
  'app.tasks.audit_log.create_audit_log_task': 'createAuditLog',
  'archive_old_audit_logs': 'archiveAuditLogs',
  'archive_old_audit_logs_task': 'archiveAuditLogs',
  'tasks.archive_old_audit_logs': 'archiveAuditLogs',
  'app.tasks.audit_log.archive_old_audit_logs_task': 'archiveAuditLogs',
  'check_api_key_expiration': 'checkApiKeyExpiration',
  'check_api_key_expiration_task': 'checkApiKeyExpiration',
  'tasks.check_api_key_expiration': 'checkApiKeyExpiration',
  'app.tasks.api_key.check_api_key_expiration_task': 'checkApiKeyExpiration',
  'check_password_expiration': 'checkPasswordExpiration',
  'check_password_expiration_task': 'checkPasswordExpiration',
  'tasks.check_password_expiration': 'checkPasswordExpiration',
  'app.tasks.password_expiration.check_password_expiration_task': 'checkPasswordExpiration',
  'reset_daily_usage': 'resetDailyUsage',
  'reset_daily_usage_task': 'resetDailyUsage',
  'tasks.reset_daily_usage': 'resetDailyUsage',
  'app.tasks.usage.reset_daily_usage_task': 'resetDailyUsage',
  'reset_monthly_usage': 'resetMonthlyUsage',
  'reset_monthly_usage_task': 'resetMonthlyUsage',
  'tasks.reset_monthly_usage': 'resetMonthlyUsage',
  'app.tasks.usage.reset_monthly_usage_task': 'resetMonthlyUsage',
}


export const TONE_STYLES: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border',
  success: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/20 dark:text-emerald-300',
  warning: 'bg-amber-500/10 text-amber-700 border-amber-500/20 dark:text-amber-300',
  danger: 'bg-destructive/10 text-destructive border-destructive/20',
  info: 'bg-sky-500/10 text-sky-700 border-sky-500/20 dark:text-sky-300',
}

export function getRiskLevel(timeoutRate: number, successRate: number, p95: number | null, ttftP95: number | null): { key: 'healthy' | 'warning' | 'critical'; summaryKey: 'healthSummaryHealthy' | 'healthSummaryWarning' | 'healthSummaryCritical'; tone: Tone } {
  if (timeoutRate >= 5 || successRate < 95 || (ttftP95 != null ? ttftP95 >= 10000 : (p95 ?? 0) >= 30000)) {
    return { key: 'critical', summaryKey: 'healthSummaryCritical', tone: 'danger' }
  }
  if (timeoutRate >= 1 || successRate < 99 || (ttftP95 != null ? ttftP95 >= 3000 : (p95 ?? 0) >= 10000)) {
    return { key: 'warning', summaryKey: 'healthSummaryWarning', tone: 'warning' }
  }
  return { key: 'healthy', summaryKey: 'healthSummaryHealthy', tone: 'success' }
}

export function toneForStatus(status: string): Tone {
  if (status === 'danger' || status === 'unhealthy' || status === 'failed' || status === 'error') return 'danger'
  if (status === 'warning' || status === 'unknown' || status === 'timeout') return 'warning'
  if (status === 'healthy' || status === 'success') return 'success'
  if (status === 'running') return 'info'
  return 'neutral'
}

export function statusLabel(status: string | null | undefined, t: ObservabilityTranslator) {
  const normalized = status || 'unknown'
  const keys = new Set(['healthy', 'warning', 'danger', 'unhealthy', 'unknown', 'success', 'failed', 'running', 'pending', 'cancelled', 'timeout', 'error'])
  return keys.has(normalized) ? translate(t, `status.${normalized}`) : normalized
}

export function sourceLabel(source: string | null | undefined, t: ObservabilityTranslator) {
  if (source === 'agent' || source === 'workflow' || source === 'system' || source === 'other') {
    return translate(t, `sources.${source}`)
  }
  return translate(t, 'sources.unknown')
}


export function workerTaskLabel(task: string | null | undefined, t: ObservabilityTranslator) {
  if (!task) return '-'
  if (task.startsWith('unrecognized:')) return translate(t, 'workers.tasks.unrecognized')
  if (task.startsWith('unscanned:')) return translate(t, 'workers.tasks.unrecognized')
  const key = WORKER_TASK_KEYS[task] || WORKER_TASK_KEYS[task.split('.').pop() || '']
  return key ? translate(t, `workers.tasks.${key}`) : task
}


export function timeoutTypeLabel(type: string | null | undefined, t: ObservabilityTranslator) {
  const normalized = type || 'unknown'
  const keys = new Set(['unknown', 'idle', 'global', 'workflow', 'agent'])
  return keys.has(normalized) ? translate(t, `timeoutTypes.${normalized}`) : normalized
}

export function abnormalReason(row: Record<string, unknown>) {
  return readString(row, ['reason', 'message', 'detail', 'error'])
}

export function readNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return null
}

export function readString(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return '-'
}

export function formatNumber(value: number | null | undefined) {
  if (value == null) return '-'
  return new Intl.NumberFormat().format(value)
}

export function formatCompactNumber(value: number) {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function formatPercent(value: number) {
  return `${value.toFixed(1)}%`
}

export function formatDuration(value: number | null | undefined) {
  if (value == null) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`
  return `${Math.round(value)}ms`
}

export function formatBucket(value: string | null | undefined, locale: string = 'en') {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function percentOf(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 1000) / 10
}

export function toneDotClass(tone: Tone) {
  return {
    neutral: 'bg-muted-foreground',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-destructive',
    info: 'bg-sky-500',
  }[tone]
}

export function toneBarClass(tone: Tone) {
  return {
    neutral: 'bg-muted-foreground/50',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-destructive',
    info: 'bg-sky-500',
  }[tone]
}

export function toneTextClass(tone: Tone) {
  return {
    neutral: 'text-foreground',
    success: 'text-emerald-700 dark:text-emerald-300',
    warning: 'text-amber-700 dark:text-amber-300',
    danger: 'text-destructive',
    info: 'text-sky-700 dark:text-sky-300',
  }[tone]
}
