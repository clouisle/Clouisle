'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Loader2, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { toolExecutionsApi, type ToolExecution, type ToolExecutionStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface PendingToolApprovalCardProps {
  /** Bound execution the waiting tool call created. */
  executionId: string
  /** Original model-facing tool name from the run state (display fallback). */
  toolName?: string | null
  /** Re-read the owning run status so a resumed stream is picked up. */
  onRefreshRun?: () => void | Promise<void>
  className?: string
  compact?: boolean
}

function statusBadgeVariant(
  status: ToolExecutionStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'failed' || status === 'outcome_unknown' || status === 'cancelled') {
    return 'destructive'
  }
  if (status === 'ready' || status === 'executing') return 'secondary'
  if (status === 'succeeded') return 'outline'
  return 'default'
}

/**
 * Visible, non-answerable approval pause inside a chat surface.
 *
 * The card only reads the secret-safe execution projection. It never offers
 * the ask_user answer flow and never performs the side effect: decisions are
 * made against the exact approval gate in the approvals inbox, and the durable
 * worker executes only after every gate is approved.
 */
export function PendingToolApprovalCard({
  executionId,
  toolName,
  onRefreshRun,
  className,
  compact = false,
}: PendingToolApprovalCardProps) {
  const tChat = useTranslations('approvals.chat')
  const tApproval = useTranslations('approvals.approval')
  const [execution, setExecution] = React.useState<ToolExecution | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [refreshing, setRefreshing] = React.useState(false)
  const [submitting, setSubmitting] = React.useState<'approve' | 'reject' | false>(false)
  const disposedRef = React.useRef(false)
  const resumedRef = React.useRef(false)

  const load = React.useCallback(
    async (manual: boolean) => {
      if (manual) setRefreshing(true)
      try {
        const next = await toolExecutionsApi.get(executionId, { silent: true })
        if (disposedRef.current) return
        setExecution(next)
        setError(null)
      } catch (reason) {
        if (disposedRef.current) return
        if (manual || !execution) {
          setError(reason instanceof Error && reason.message ? reason.message : tChat('refreshFailed'))
        }
      } finally {
        if (!disposedRef.current && manual) setRefreshing(false)
      }
    },
    [execution, executionId, tChat]
  )

  React.useEffect(() => {
    disposedRef.current = false
    resumedRef.current = false
    void load(false)
    return () => {
      disposedRef.current = true
    }
    // The bound execution id is the only reload trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executionId])

  React.useEffect(() => {
    if (!execution || execution.status === 'awaiting_approval' || resumedRef.current) return
    // The decision was made outside this card; reconnect so the resumed run
    // paints its next events instead of leaving a stale waiting status.
    resumedRef.current = true
    void onRefreshRun?.()
  }, [execution, onRefreshRun])

  const awaiting = !execution || execution.status === 'awaiting_approval'
  React.useEffect(() => {
    if (!awaiting) return
    const timer = setInterval(() => {
      void load(false)
    }, 10000)
    return () => clearInterval(timer)
  }, [awaiting, load])

  const handleRefresh = async () => {
    await load(true)
    try {
      await onRefreshRun?.()
    } catch {
      // The execution state above is still server-authoritative.
    }
  }
  const handleDecision = async (decision: 'approve' | 'reject') => {
    setSubmitting(decision)
    try {
      await toolExecutionsApi.decide(executionId, {
        decision,
        idempotency_key: crypto.randomUUID(),
      })
      toast.success(
        tApproval(decision === 'approve' ? 'approvedToast' : 'rejectedToast')
      )
      await load(false)
      await onRefreshRun?.()
    } catch (err) {
      toast.error(
        err instanceof Error && err.message
          ? err.message
          : tApproval('decisionFailed')
      )
    } finally {
      if (!disposedRef.current) {
        setSubmitting(false)
      }
    }
  }


  const status = execution?.status
  const parameters = execution?.parameters_preview ?? {}
  const displayName = execution?.operation || toolName || executionId

  return (
    <div className={cn('mx-auto w-full max-w-3xl px-4', className)}>
      <div
        className={cn('mx-auto w-[70%] overflow-hidden rounded-t-lg border border-b-0 bg-muted/30 px-3.5 pb-3 pt-2.5 shadow-xs', compact && 'text-xs')}
        data-testid="pending-tool-approval-card"
      >
        <div className={cn('space-y-2', compact && 'space-y-1.5')}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex min-w-0 items-start gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="min-w-0">
              <p className="text-sm font-medium">{tChat('approvalTitle')}</p>
              <p className="mt-0.5 break-all text-xs text-muted-foreground">{displayName}</p>
            </div>
          </div>
          {status && (
            <Badge variant={statusBadgeVariant(status)}>
              {tApproval(`executionStatuses.${status}`)}
            </Badge>
          )}
        </div>

        {(!execution || status === 'awaiting_approval') && (
          <p className="text-xs text-muted-foreground">{tChat('approvalDescription')}</p>
        )}

        {error && <p className="text-xs text-destructive">{error}</p>}

        {!execution && !error && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {tApproval(`executionStatuses.awaiting_approval`)}
          </p>
        )}

        {execution && (
          <div className="space-y-2 text-xs">
            {execution.connection_account_label && (
              <p className="break-all text-muted-foreground">
                {tChat('account', { account: execution.connection_account_label })}
              </p>
            )}
            <details>
              <summary className="cursor-pointer text-muted-foreground">{tChat('parameters')}</summary>
              <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 font-mono text-[11px]">
                {JSON.stringify(parameters, null, 2)}
              </pre>
            </details>
          </div>
        )}

        {execution?.status === 'awaiting_approval' ? (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="default"
              className="bg-amber-600 hover:bg-amber-700 text-white"
              onClick={() => void handleDecision('approve')}
              disabled={submitting !== false || refreshing}
              data-testid="approval-card-approve-btn"
            >
              {submitting === 'approve' ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  {tApproval('submitting')}
                </>
              ) : (
                tChat('approve')
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive hover:bg-destructive/10"
              onClick={() => void handleDecision('reject')}
              disabled={submitting !== false || refreshing}
              data-testid="approval-card-reject-btn"
            >
              {submitting === 'reject' ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  {tApproval('submitting')}
                </>
              ) : (
                tChat('reject')
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void handleRefresh()}
              disabled={refreshing || submitting !== false}
              title={tChat('refreshStatus')}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
              <span className="sr-only">{tChat('refreshStatus')}</span>
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
            >
              <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
              {refreshing ? tChat('refreshing') : tChat('refreshStatus')}
            </Button>
          </div>
        )}
        </div>
      </div>
    </div>
  )
}
