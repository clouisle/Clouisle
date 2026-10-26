'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Check, Loader2, RefreshCw, ShieldCheck, X } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Textarea } from '@/components/ui/textarea'
import {
  toolApprovalsApi,
  type ToolApprovalRequest,
  type ToolApprovalVote,
} from '@/lib/api'
import { createIdempotencyKey } from '@/lib/utils/idempotency'

export interface ApprovalsInboxProps {
  /** Only show the pending request bound to this durable execution. */
  executionId?: string | null
  /** Change this value to reload from the server. */
  refreshKey?: number
  onClearExecutionFilter?: () => void
}

const ENTRYPOINTS: Record<string, true> = {
  chat: true,
  agent_run: true,
  workflow: true,
  api_key: true,
  schedule: true,
  channel: true,
  embed: true,
  subworkflow: true,
  nested_agent: true,
  tool_test: true,
  admin_test: true,
}
const GATE_KINDS: Record<string, true> = { caller: true, user: true, team_role: true }
const RUN_KINDS: Record<string, true> = { agent: true, workflow: true }

const PAGE_SIZE = 20
const FILTER_SCAN_PAGES = 5

interface DecisionTarget {
  request: ToolApprovalRequest
  vote: ToolApprovalVote
}

/**
 * Approval inbox for the current approver.
 *
 * Decisions target one exact persisted gate id and are never applied
 * optimistically: the list is refetched after the server returns the
 * authoritative execution status.
 */
export function ApprovalsInbox({
  executionId,
  refreshKey = 0,
  onClearExecutionFilter,
}: ApprovalsInboxProps) {
  const t = useTranslations('approvals.approval')
  const tRef = React.useRef(t)
  tRef.current = t
  const [page, setPage] = React.useState(1)
  const [requests, setRequests] = React.useState<ToolApprovalRequest[]>([])
  const [total, setTotal] = React.useState(0)
  const [filtered, setFiltered] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [decision, setDecision] = React.useState<DecisionTarget | null>(null)
  const [reason, setReason] = React.useState('')
  const [submitting, setSubmitting] = React.useState(false)

  React.useEffect(() => {
    setPage(1)
  }, [executionId])

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (executionId) {
        // The list endpoint has no execution filter, so scan a bounded number
        // of pages to find the request the chat surface linked to.
        const collected: ToolApprovalRequest[] = []
        for (let scanPage = 1; scanPage <= FILTER_SCAN_PAGES; scanPage += 1) {
          const response = await toolApprovalsApi.list({ page: scanPage, page_size: 100 })
          collected.push(...response.items)
          if (collected.length >= response.total || response.items.length === 0) break
        }
        setRequests(
          collected.filter(
            (request) => request.execution_id === executionId && request.status === 'pending'
          )
        )
        setTotal(collected.length)
        setFiltered(true)
      } else {
        const response = await toolApprovalsApi.list({ page, page_size: PAGE_SIZE })
        setRequests(response.items)
        setTotal(response.total)
        setFiltered(false)
      }
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tRef.current('loadFailed'))
      setRequests([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [executionId, page])

  React.useEffect(() => {
    void load()
  }, [load, refreshKey])

  const openDecision = (request: ToolApprovalRequest, vote: ToolApprovalVote) => {
    setDecision({ request, vote })
    setReason('')
  }

  const confirmDecision = async () => {
    if (!decision || submitting) return
    setSubmitting(true)
    try {
      const result = await toolApprovalsApi.decide(decision.request.id, {
        decision: decision.vote,
        reason: reason.trim() || null,
        idempotency_key: createIdempotencyKey('approval'),
      })
      const description = [
        t('executionStatus', { status: t(`executionStatuses.${result.execution_status}`) }),
        result.remaining_approvals > 0
          ? t('remainingApprovals', { count: result.remaining_approvals })
          : null,
      ]
        .filter(Boolean)
        .join(' · ')
      toast.success(
        decision.vote === 'approve' ? t('approvedToast') : t('rejectedToast'),
        { description }
      )
      setDecision(null)
      setReason('')
      // Server-authoritative refresh: no optimistic removal.
      await load()
    } catch (reason) {
      toast.error(
        reason instanceof Error && reason.message ? reason.message : t('decisionFailed')
      )
    } finally {
      setSubmitting(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  if (loading && requests.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loading')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-10">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('retry')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (requests.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center gap-2 py-12">
          <ShieldCheck className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">{t('empty')}</p>
          <p className="text-sm text-muted-foreground">
            {executionId ? t('filteredByExecution') : t('emptyHint')}
          </p>
          {executionId && onClearExecutionFilter && (
            <Button variant="outline" size="sm" onClick={onClearExecutionFilter}>
              {t('clearFilter')}
            </Button>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3" data-testid="approvals-inbox">
      <div>
        <h2 className="text-lg font-semibold">{t('listTitle')}</h2>
        <p className="text-sm text-muted-foreground">{t('listDescription')}</p>
        {filtered && (
          <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{t('filteredByExecution')}</span>
            {onClearExecutionFilter && (
              <Button variant="link" size="xs" onClick={onClearExecutionFilter}>
                {t('clearFilter')}
              </Button>
            )}
          </div>
        )}
      </div>

      {requests.map((request) => {
        const display = request.masked_display
        const connection = display.connection
        const entrypoint = display.entrypoint && ENTRYPOINTS[display.entrypoint]
          ? t(`entrypoints.${display.entrypoint}`)
          : display.entrypoint
        const runKind = display.run_kind && RUN_KINDS[display.run_kind]
          ? t(`runKinds.${display.run_kind}`)
          : display.run_kind
        const gateKind = GATE_KINDS[request.gate_kind]
          ? t(`gateKinds.${request.gate_kind}`)
          : request.gate_kind
        const parameters = display.parameters ?? {}

        return (
          <Card key={request.id} data-testid={`approval-request-${request.id}`}>
            <CardContent className="space-y-3 px-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="break-all text-base font-medium">
                    {display.tool_name || display.tool_id || request.execution_id}
                  </p>
                  <p className="break-all text-xs text-muted-foreground">
                    {display.operation || '—'}
                  </p>
                </div>
                <Badge variant={request.status === 'pending' ? 'default' : 'outline'}>{t(`statuses.${request.status}`)}</Badge>
              </div>

              <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                <div className="flex gap-2">
                  <dt className="text-muted-foreground">{t('gateKind')}:</dt>
                  <dd>{gateKind}</dd>
                </div>
                <div className="flex gap-2">
                  <dt className="text-muted-foreground">{t('stage', { index: request.stage_index + 1 })}</dt>
                </div>
                {entrypoint && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">{t('entrypoint')}:</dt>
                    <dd>{entrypoint}</dd>
                  </div>
                )}
                {runKind && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">{runKind}:</dt>
                    <dd className="break-all">{display.run_id}</dd>
                  </div>
                )}
                {connection && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">{t('connection')}:</dt>
                    <dd>
                      {connection.account_label || connection.scope || connection.connection_id}
                    </dd>
                  </div>
                )}
                {request.expires_at && (
                  <div className="flex gap-2">
                    <dt className="text-muted-foreground">
                      {t('expiresAt', { time: new Date(request.expires_at).toLocaleString() })}
                    </dt>
                  </div>
                )}
              </dl>

              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">{t('parameters')}</p>
                {Object.keys(parameters).length > 0 ? (
                  <pre className="max-h-48 overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px]">
                    {JSON.stringify(parameters, null, 2)}
                  </pre>
                ) : (
                  <p className="text-xs text-muted-foreground">{t('noParameters')}</p>
                )}
              </div>

              {display.policy_sources && display.policy_sources.length > 0 && (
                <p className="text-[11px] text-muted-foreground">
                  {t('policySources')}: {display.policy_sources.join(', ')}
                </p>
              )}

              {display.note && (
                <p className="text-[11px] text-muted-foreground">{display.note}</p>
              )}

              {request.status === 'pending' && (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => openDecision(request, 'approve')}>
                    <Check className="mr-1.5 h-3.5 w-3.5" />
                    {t('approve')}
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => openDecision(request, 'reject')}
                  >
                    <X className="mr-1.5 h-3.5 w-3.5" />
                    {t('reject')}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}

      {!filtered && totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{t('pageInfo', { page, totalPages })}</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1 || loading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              {t('previous')}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((current) => current + 1)}
            >
              {t('next')}
            </Button>
          </div>
        </div>
      )}

      <AlertDialog
        open={decision !== null}
        onOpenChange={(open) => {
          if (!open && !submitting) setDecision(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {decision?.vote === 'reject' ? t('decisionTitleReject') : t('decisionTitleApprove')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {decision?.vote === 'reject'
                ? t('decisionDescriptionReject')
                : t('decisionDescriptionApprove')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1">
            <label className="text-xs font-medium" htmlFor="approval-reason">
              {t('reasonLabel')}
            </label>
            <Textarea
              id="approval-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t('reasonPlaceholder')}
              maxLength={2000}
              rows={3}
              disabled={submitting}
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant={decision?.vote === 'reject' ? 'destructive' : 'default'}
              disabled={submitting}
              onClick={() => void confirmDecision()}
            >
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {decision?.vote === 'reject' ? t('confirmReject') : t('confirmApprove')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
