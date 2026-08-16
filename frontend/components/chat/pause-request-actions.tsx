'use client'

import * as React from 'react'
import { Check, CirclePause, Loader2, X } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { VariableForm } from '@/components/chat/variable-form'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { workflowsApi, type WorkflowPauseRequest } from '@/lib/api/workflows'
import { cn, formatDateTime } from '@/lib/utils'

/**
 * Single approval/input action surface shared by the run page (controlled),
 * the prominent notification dialog (self-managed) and the notification
 * center rows (compact self-managed). Keeping the load/render/submit logic in
 * one component prevents the approval flows from drifting apart.
 */
export interface PauseRequestActionsProps {
  workflowId: string
  runId: string
  pauseRequestId: string
  variant?: 'full' | 'compact'

  // Controlled mode (run page): the caller owns loading, values and the
  // submission (it needs to resume the SSE stream / refresh history).
  request?: WorkflowPauseRequest | null
  values?: Record<string, unknown>
  onValuesChange?: (values: Record<string, unknown>) => void
  onSubmit?: (values: Record<string, unknown>, comment?: string) => void | Promise<void>
  submitting?: boolean
  error?: string | null
  canSubmit?: boolean
  approverNames?: string[]

  // Self-managed mode: fired after a successful internal submission so the
  // caller can refresh or dismiss.
  onResolved?: () => void
}

export function PauseRequestActions({
  workflowId,
  runId,
  pauseRequestId,
  variant = 'full',
  request: controlledRequest,
  values: controlledValues,
  onValuesChange,
  onSubmit,
  submitting: controlledSubmitting,
  error: controlledError,
  canSubmit = true,
  approverNames = [],
  onResolved,
}: PauseRequestActionsProps) {
  const t = useTranslations('run')
  const locale = useLocale()
  const controlled = controlledRequest !== undefined

  const [request, setRequest] = React.useState<WorkflowPauseRequest | null>(
    controlledRequest ?? null,
  )
  const [values, setValues] = React.useState<Record<string, unknown>>({})
  const [isLoading, setIsLoading] = React.useState(false)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [comment, setComment] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [isUploading, setIsUploading] = React.useState(false)

  React.useEffect(() => {
    if (controlledRequest !== undefined) setRequest(controlledRequest)
  }, [controlledRequest])

  // Self-managed loading: dialog needs the full request; compact rows need
  // the mode to render the right action.
  React.useEffect(() => {
    if (controlled) return
    let cancelled = false
    setIsLoading(true)
    workflowsApi
      .getPendingPauseRequest(workflowId, runId)
      .then((loaded) => {
        if (!cancelled) setRequest(loaded)
      })
      .catch(() => {
        if (!cancelled) setError(t('pause.loadError'))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [controlled, workflowId, runId, t])

  const submitting = controlled ? controlledSubmitting ?? false : isSubmitting
  const currentError = controlled ? controlledError : error
  const currentValues = controlled ? controlledValues ?? {} : values
  const handleValuesChange = controlled
    ? onValuesChange ?? (() => {})
    : setValues
  // Self-managed callers rely on the backend's can_submit (false after this
  // user already submitted in a require-all approval).
  const effectiveCanSubmit = controlled ? canSubmit : (request?.can_submit ?? true)
  const disabled = submitting || isUploading || !effectiveCanSubmit

  const handleSubmit = async (payload: Record<string, unknown>) => {
    if (controlled) {
      await onSubmit?.(payload, comment)
      return
    }
    setIsSubmitting(true)
    setError(null)
    try {
      const result = await workflowsApi.submitPauseRequest(workflowId, runId, pauseRequestId, payload, comment)
      // require-all approvals return status "pending" until every approver
      // has decided; the run keeps waiting.
      if (result?.status === 'pending') {
        toast.success(t('pause.submittedWaiting'))
      } else {
        toast.success(t('pause.submitted'))
      }
      onResolved?.()
    } catch {
      setError(t('pause.submitError'))
      toast.error(t('pause.submitError'))
    } finally {
      setIsSubmitting(false)
    }
  }

  // Compact rows (notification center): actions only, no description/form.
  if (variant === 'compact') {
    if (isLoading) {
      return <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
    }
    if (!request || currentError) {
      return null
    }
    if (request.mode !== 'approval') {
      // Variable input needs the full form: send the user to the run page.
      return (
        <a
          href={`/run/${workflowId}?run=${runId}`}
          className="inline-flex h-8 items-center rounded-md border border-input bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          {t('pause.fillInline')}
        </a>
      )
    }
    return (
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          className="cursor-pointer"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation()
            void handleSubmit({ decision: 'rejected' })
          }}
        >
          {t('pause.reject')}
        </Button>
        <Button
          size="sm"
          className="cursor-pointer"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation()
            void handleSubmit({ decision: 'approved' })
          }}
        >
          {t('pause.approve')}
        </Button>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="mt-6 flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('pause.loading')}
      </div>
    )
  }

  if (!request) {
    return null
  }

  const title = request.title || request.node_name
  const approvalRecords = request.approvals ?? []

  return (
    <section
      aria-labelledby="workflow-pause-heading"
      className="mt-6 overflow-hidden rounded-xl border border-amber-500/30 bg-amber-500/[0.06] shadow-sm"
    >
      <div className="flex gap-3 border-b border-amber-500/20 bg-background/60 px-5 py-4 backdrop-blur-sm">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white shadow-sm">
          <CirclePause className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <h3 id="workflow-pause-heading" className="text-base font-semibold text-foreground">
            {request.workflow_name || title}
            <span className="ml-2 inline-flex items-center rounded bg-amber-500/15 px-1.5 py-0.5 align-middle text-[10px] font-medium text-amber-700 dark:text-amber-300">
              {request.mode === 'approval' ? t('pause.typeApproval') : t('pause.typeInput')}
            </span>
          </h3>
          {(title !== request.workflow_name && title) || request.triggered_by_name ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {title !== request.workflow_name && title ? `${title} · ` : ''}
              {request.triggered_by_name && t('pause.triggeredBy', { name: request.triggered_by_name })}
              {request.triggered_at && ` · ${formatDateTime(request.triggered_at, locale)}`}
            </p>
          ) : null}
        </div>
      </div>

      {request.description && (
        <div className="border-b border-amber-500/20 bg-background/60 px-5 py-3">
          <p className="whitespace-pre-wrap text-sm text-foreground">{request.description}</p>
        </div>
      )}

      <div className="p-5">
        {currentError && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{currentError}</AlertDescription>
          </Alert>
        )}

        {!effectiveCanSubmit && !request.already_submitted && (
          <Alert className="mb-4 border-amber-500/30 bg-amber-500/[0.08]">
            <AlertDescription className="text-sm">
              {approverNames.length > 0
                ? t('pause.approversOnly', { names: approverNames.join(', ') })
                : t('pause.ownerAdminOnly')}
            </AlertDescription>
          </Alert>
        )}

        {request.mode === 'approval' && request.require_all ? (
          <div className="space-y-4">
            {request.already_submitted && (
              <Alert className="border-amber-500/30 bg-amber-500/[0.08]">
                <AlertDescription className="text-sm">{t('pause.alreadySubmitted')}</AlertDescription>
              </Alert>
            )}
            <div className="rounded-lg border bg-background/60 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">
                  {t('pause.approvalProgress', {
                    approved: approvalRecords.filter((record) => record.decision === 'approved').length,
                    total: request.approver_ids.length,
                  })}
                </span>
              </div>
              <ul className="mt-2 space-y-1">
                {request.approver_ids.map((approverId) => {
                  const record = approvalRecords.find((item) => item.approver_id === approverId)
                  const name = record?.username
                    ?? request.approver_names[request.approver_ids.indexOf(approverId)]
                    ?? ''
                  const status = record?.decision ?? 'pending'
                  const statusKey = `pause.approverStatus${status.charAt(0).toUpperCase()}${status.slice(1)}`
                  return (
                    <li key={approverId} className="flex items-center justify-between text-xs">
                      <span className="min-w-0 truncate">{name}</span>
                      <span
                        className={cn(
                          'shrink-0',
                          status === 'approved' && 'text-green-600 dark:text-green-400',
                          status === 'rejected' && 'text-red-600 dark:text-red-400',
                          status === 'pending' && 'text-muted-foreground',
                        )}
                      >
                        {t(statusKey)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
            {!request.already_submitted && (
              <>
                <Textarea
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder={t('pause.commentPlaceholder')}
                  disabled={disabled}
                  className="min-h-24 resize-y bg-background dark:bg-background"
                />
                <div className="flex flex-wrap justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={disabled}
                    onClick={() => void handleSubmit({ decision: 'rejected' })}
                  >
                    {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <X className="mr-2 h-4 w-4" />}
                    {t('pause.reject')}
                  </Button>
                  <Button
                    type="button"
                    disabled={disabled}
                    onClick={() => void handleSubmit({ decision: 'approved' })}
                  >
                    {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                    {t('pause.approve')}
                  </Button>
                </div>
              </>
            )}
          </div>
        ) : request.mode === 'approval' ? (
          <div className="space-y-4">
            <Textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder={t('pause.commentPlaceholder')}
              disabled={disabled}
              className="min-h-24 resize-y bg-background dark:bg-background"
            />
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={disabled}
                onClick={() => void handleSubmit({ decision: 'rejected' })}
              >
                {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <X className="mr-2 h-4 w-4" />}
                {t('pause.reject')}
              </Button>
              <Button
                type="button"
                disabled={disabled}
                onClick={() => void handleSubmit({ decision: 'approved' })}
              >
                {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                {t('pause.approve')}
              </Button>
            </div>
          </div>
        ) : request.input_variables.length === 0 ? (
          <div className="flex justify-end">
            <Button
              type="button"
              disabled={disabled}
              onClick={() => void handleSubmit(currentValues)}
            >
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
              {t('pause.submit')}
            </Button>
          </div>
        ) : (
          <VariableForm
            variables={request.input_variables}
            values={currentValues}
            onChange={handleValuesChange}
            onSubmit={() => void handleSubmit(currentValues)}
            submitLabel={submitting ? t('pause.submitting') : t('pause.submit')}
            compact={false}
            disabled={disabled}
            onUploadingChange={setIsUploading}
          />
        )}
      </div>
    </section>
  )
}
