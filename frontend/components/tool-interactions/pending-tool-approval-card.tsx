'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Loader2, RefreshCw, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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

  const status = execution?.status
  const parameters = execution?.parameters_preview ?? {}
  const displayName = execution?.operation || toolName || executionId

  return (
    <Card
      size={compact ? 'sm' : 'default'}
      className={cn('mx-auto w-[70%] border-amber-500/40 bg-amber-500/5', className)}
      data-testid="pending-tool-approval-card"
    >
      <CardContent className={cn('space-y-2 px-4', compact && 'space-y-1.5')}>
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

        <p className="text-xs text-muted-foreground">{tChat('approvalDescription')}</p>

        {error && <p className="text-xs text-destructive">{error}</p>}

        {!execution && !error && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            {tApproval(`executionStatuses.awaiting_approval`)}
          </p>
        )}

        {execution && (
          <div className="space-y-2 text-xs">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
              <dt className="text-muted-foreground">{tApproval('operation')}</dt>
              <dd className="break-all font-medium">{execution.operation}</dd>
              {execution.connection_account_label && (
                <>
                  <dt className="text-muted-foreground">{tApproval('accountLabel')}</dt>
                  <dd className="break-all">{execution.connection_account_label}</dd>
                </>
              )}
              <dt className="text-muted-foreground">{tChat('statusLabel')}</dt>
              <dd>{tApproval(`executionStatuses.${execution.status}`)}</dd>
            </dl>
            <details>
              <summary className="cursor-pointer text-muted-foreground">{tChat('parameters')}</summary>
              <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 font-mono text-[11px]">
                {JSON.stringify(parameters, null, 2)}
              </pre>
            </details>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
          >
            <RefreshCw className={cn('h-3.5 w-3.5', refreshing && 'animate-spin')} />
            {refreshing ? tChat('refreshing') : tChat('refreshStatus')}
          </Button>
          <Button
            size="sm"
            nativeButton={false}
            render={<Link href={`/app/capabilities/approvals?execution=${encodeURIComponent(executionId)}`} />}
          >
            {tChat('openInbox')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
