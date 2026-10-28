'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { AlertTriangle, ExternalLink, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  getElicitationUrl,
  type RunInteraction,
  type RunInteractionOutcome,
  type RunInteractionResponseInput,
} from '@/lib/api'
import {
  buildElicitationContent,
  getElicitationFields,
  type ElicitationField,
} from '@/lib/tool-interactions/elicitation-schema'
import { cn } from '@/lib/utils'
import { createIdempotencyKey } from '@/lib/utils/idempotency'

export interface InteractionRequestCardProps {
  interaction: RunInteraction
  /** Persist the authorized response; the parent refreshes the durable list. */
  onRespond: (interactionId: string, input: RunInteractionResponseInput) => Promise<unknown>
  className?: string
  /** Tighter presentation when embedded beside the chat composer. */
  compact?: boolean
}

function messageText(content: unknown): string {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object' && 'text' in item) {
          return String(item.text ?? '')
        }
        return JSON.stringify(item)
      })
      .join('\n')
  }
  return JSON.stringify(content, null, 2)
}

/**
 * Render one MCP interaction with only the actions the contract permits:
 * form elicitation accepts validated content, URL elicitation and sampling
 * accept with `content: null`, and decline/cancel are always explicit.
 *
 * This component never treats the response as a tool approval.
 */
export function InteractionRequestCard({
  interaction,
  onRespond,
  className,
  compact = false,
}: InteractionRequestCardProps) {
  const t = useTranslations('approvals.interaction')
  const [values, setValues] = React.useState<Record<string, string | boolean>>({})
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [error, setError] = React.useState<string | null>(null)
  const [submitting, setSubmitting] = React.useState<RunInteractionOutcome | null>(null)
  const [recorded, setRecorded] = React.useState(false)

  const payload = interaction.payload
  const formFields = React.useMemo(
    () => (payload.mode === 'form' ? getElicitationFields(payload.requested_schema) : []),
    [payload]
  )
  const secretFields = formFields.filter((field) => field.secret)
  const authorizationUrl = getElicitationUrl(payload)
  const isPending = interaction.status === 'pending'
  const acceptsContent = payload.mode === 'form'
  const acceptLabel = payload.mode === 'sampling' ? t('acceptSampling') : t('accept')
  const acceptDisabled =
    !isPending
    || submitting !== null
    || recorded
    || secretFields.length > 0
    || (payload.mode === 'url' && !authorizationUrl)
  const declineDisabled = !isPending || submitting !== null || recorded

  React.useEffect(() => {
    const initial: Record<string, string | boolean> = {}
    for (const field of formFields) initial[field.name] = field.defaultValue
    setValues(initial)
    setFieldErrors({})
    setError(null)
    setRecorded(false)
    setSubmitting(null)
  }, [interaction.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const setValue = (field: ElicitationField, value: string | boolean) => {
    setValues((current) => ({ ...current, [field.name]: value }))
    setFieldErrors((current) => {
      if (!current[field.name]) return current
      const next = { ...current }
      delete next[field.name]
      return next
    })
  }

  const submit = async (action: RunInteractionOutcome) => {
    if (submitting !== null || recorded) return
    setError(null)

    let content: Record<string, unknown> | null = null
    if (action === 'accept' && acceptsContent) {
      const result = buildElicitationContent(formFields, values, {
        required: (field) => t('fieldRequired', { field }),
        invalidNumber: (field) => t('invalidNumber', { field }),
        invalidJson: (field) => t('invalidJson', { field }),
      })
      if (Object.keys(result.errors).length > 0) {
        setFieldErrors(result.errors)
        return
      }
      content = result.content
    }

    setSubmitting(action)
    try {
      await onRespond(interaction.id, {
        action,
        content,
        idempotency_key: createIdempotencyKey(`interaction-${action}`),
      })
      setRecorded(true)
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : t('responseFailed'))
    } finally {
      setSubmitting(null)
    }
  }

  const statusKey = interaction.status as
    | 'pending'
    | 'responded'
    | 'expired'
    | 'cancelled'
    | 'connection_lost'
  const actionable = isPending && !recorded

  return (
    <Card
      size={compact ? 'sm' : 'default'}
      className={cn('border-border/70', className)}
      data-testid={`run-interaction-${interaction.id}`}
    >
      <CardContent className={cn('space-y-3 px-4', compact && 'space-y-2')}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="font-medium">
              {payload.mode === 'sampling' ? t('kinds.sampling') : t('kinds.elicitation')}
            </p>
            {interaction.tool_name && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {t('toolLabel')}: {interaction.tool_name}
              </p>
            )}
          </div>
          <Badge variant={actionable ? 'default' : 'outline'}>{t(`statuses.${statusKey}`)}</Badge>
        </div>

        {payload.mode === 'sampling' && (
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">{t('samplingDescription')}</p>
            <div className="rounded-md border bg-muted/30 p-2 text-xs">
              <p className="font-medium">{t('systemPrompt')}</p>
              <p className="mt-1 whitespace-pre-wrap break-words">
                {payload.system_prompt || t('noSystemPrompt')}
              </p>
            </div>
            <div className="rounded-md border bg-muted/30 p-2 text-xs">
              <p className="font-medium">{t('messages')}</p>
              <div className="mt-1 max-h-40 space-y-1 overflow-y-auto">
                {payload.messages.map((message, index) => (
                  <p key={`${message.role}-${index}`} className="whitespace-pre-wrap break-words">
                    <span className="font-medium">{message.role}: </span>
                    {messageText(message.content)}
                  </p>
                ))}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{t('maxTokens', { count: payload.max_tokens })}</p>
            {payload.model_preferences && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">{t('modelPreferences')}</summary>
                <pre className="mt-1 overflow-x-auto rounded bg-muted/40 p-2">
                  {JSON.stringify(payload.model_preferences, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}

        {payload.mode === 'form' && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('formDescription')}</p>
            {payload.message && <p className="whitespace-pre-wrap text-sm">{payload.message}</p>}
            {secretFields.length > 0 && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{t('secretFieldsBlocked')}</span>
              </div>
            )}
            {formFields.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('noFields')}</p>
            ) : (
              <div className="space-y-2">
                {formFields.map((field) => (
                  <div key={field.name} className="space-y-1">
                    <label className="text-xs font-medium" htmlFor={`${interaction.id}-${field.name}`}>
                      {field.label}
                      {field.required && <span className="ml-0.5 text-destructive">*</span>}
                    </label>
                    {field.description && (
                      <p className="text-[11px] text-muted-foreground">{field.description}</p>
                    )}
                    {field.secret ? (
                      <input
                        id={`${interaction.id}-${field.name}`}
                        type="password"
                        disabled
                        value=""
                        readOnly
                        className="h-8 w-full rounded-md border border-dashed bg-muted/40 px-2 text-sm"
                      />
                    ) : field.type === 'boolean' ? (
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          id={`${interaction.id}-${field.name}`}
                          type="checkbox"
                          checked={values[field.name] === true}
                          disabled={!actionable}
                          onChange={(event) => setValue(field, event.target.checked)}
                        />
                        {field.label}
                      </label>
                    ) : field.type === 'enum' ? (
                      <select
                        id={`${interaction.id}-${field.name}`}
                        value={typeof values[field.name] === 'string' ? String(values[field.name]) : ''}
                        disabled={!actionable}
                        onChange={(event) => setValue(field, event.target.value)}
                        className="h-8 w-full rounded-md border bg-background px-2 text-sm"
                      >
                        <option value="" />
                        {field.options.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    ) : field.type === 'json' ? (
                      <textarea
                        id={`${interaction.id}-${field.name}`}
                        value={typeof values[field.name] === 'string' ? String(values[field.name]) : ''}
                        disabled={!actionable}
                        onChange={(event) => setValue(field, event.target.value)}
                        rows={3}
                        className="w-full rounded-md border bg-background p-2 font-mono text-xs"
                      />
                    ) : (
                      <input
                        id={`${interaction.id}-${field.name}`}
                        type={field.type === 'number' ? 'number' : 'text'}
                        value={typeof values[field.name] === 'string' ? String(values[field.name]) : ''}
                        disabled={!actionable}
                        onChange={(event) => setValue(field, event.target.value)}
                        className="h-8 w-full rounded-md border bg-background px-2 text-sm"
                      />
                    )}
                    {fieldErrors[field.name] && (
                      <p className="text-[11px] text-destructive">{fieldErrors[field.name]}</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {payload.mode === 'url' && (
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">{t('urlDescription')}</p>
            {payload.message && <p className="whitespace-pre-wrap">{payload.message}</p>}
            {authorizationUrl ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  nativeButton={false}
                  render={
                    <a href={authorizationUrl} target="_blank" rel="noopener noreferrer" />
                  }
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {t('openAuthorizationPage')}
                </Button>
                <p className="text-[11px] text-muted-foreground">{t('urlHint')}</p>
              </>
            ) : (
              <p className="text-xs text-destructive">{t('invalidUrl')}</p>
            )}
          </div>
        )}

        {interaction.expires_at && isPending && (
          <p className="text-[11px] text-muted-foreground">
            {t('expiresAt', { time: new Date(interaction.expires_at).toLocaleString() })}
          </p>
        )}

        {!isPending && (
          <p className="text-xs text-muted-foreground">
            {interaction.status === 'connection_lost'
              ? t('connectionLostNotice')
              : t(`statuses.${statusKey}`)}
          </p>
        )}

        {recorded && <p className="text-xs text-muted-foreground">{t('responseRecorded')}</p>}
        {error && <p className="text-xs text-destructive">{error}</p>}

        {actionable && (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => void submit('accept')} disabled={acceptDisabled}>
              {submitting === 'accept' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {acceptLabel}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void submit('decline')}
              disabled={declineDisabled}
            >
              {t('decline')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => void submit('cancel')}
              disabled={declineDisabled}
            >
              {t('cancel')}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
