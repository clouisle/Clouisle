'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { AskUserQuestion } from '@/lib/api'

export interface AskUserFormProps {
  /** Questions rendered by this shared multi-question form. */
  questions: AskUserQuestion[]
  /** Whether interaction is disabled (streaming/answered). */
  disabled?: boolean
  /** Submit one structured answer set; answers keyed by question id. */
  onSubmit: (answers: Record<string, unknown>) => Promise<void>
  className?: string
}

/**
 * Normalize the raw ask_user tool arguments into question definitions.
 * Invalid payloads return an empty result and disable rendering.
 */
export function normalizeAskUserQuestions(input: Record<string, unknown>): AskUserQuestion[] {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return []
  const raw = input.questions
  if (!Array.isArray(raw) || raw.length === 0) return []

  const questions: AskUserQuestion[] = []
  const seenIds = new Set<string>()
  for (const item of raw) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const entry = item as Record<string, unknown>
    const id = typeof entry.id === 'string' ? entry.id.trim() : ''
    const question = typeof entry.question === 'string' ? entry.question.trim() : ''
    if (!id || !question || seenIds.has(id)) return []

    let options: string[] | undefined
    if (entry.options !== undefined) {
      if (!Array.isArray(entry.options)) return []
      options = []
      for (const option of entry.options) {
        if (typeof option !== 'string' || !option.trim()) return []
        options.push(option.trim())
      }
    }

    const required = entry.required === undefined ? true : entry.required
    if (typeof required !== 'boolean') return []
    seenIds.add(id)
    questions.push({ id, question, options, required })
  }
  return questions
}

/**
 * Shared multi-question interaction form for an ask_user tool call.
 * One question uses the identical array-based path as several.
 */
export function AskUserForm({
  questions,
  disabled = false,
  onSubmit,
  className,
}: AskUserFormProps) {
  const t = useTranslations('chat.message.askUser')
  const [values, setValues] = React.useState<Record<string, string>>({})
  const [errors, setErrors] = React.useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  if (questions.length === 0) return null

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    const missing: Record<string, boolean> = {}
    for (const q of questions) {
      if (q.required !== false && !(values[q.id] && values[q.id].trim())) {
        missing[q.id] = true
      }
    }
    setErrors(missing)
    if (Object.keys(missing).length > 0) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(values)
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setSubmitting(false)
    }
  }

  const isDisabled = disabled || submitting

  return (
    <form
      onSubmit={(event) => { void handleSubmit(event) }}
      className={cn('space-y-3', className)}
      data-ask-user-form
    >
      <div className="flex items-start gap-2">
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-blue-500" aria-hidden="true">?</span>
        <div className="flex-1 min-w-0 space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('title')}</p>
          {questions.map((q) => {
            const invalid = Boolean(errors[q.id])
            return (
              <div key={q.id} className="space-y-1.5">
                <label
                  htmlFor={`ask-user-${q.id}`}
                  className="block text-sm font-medium leading-5"
                >
                  {q.question}
                  {q.required !== false && <span className="text-destructive"> *</span>}
                </label>
                {q.options && q.options.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {q.options.map((option) => (
                      <button
                        key={option}
                        type="button"
                        disabled={isDisabled}
                        onClick={() => {
                          setValues((current) => ({ ...current, [q.id]: option }))
                          setErrors((current) => ({ ...current, [q.id]: false }))
                        }}
                        className={cn(
                          'rounded-full border px-3 py-1 text-sm transition-colors cursor-pointer',
                          values[q.id] === option
                            ? 'border-primary bg-primary/10 text-primary font-medium'
                            : 'border-border bg-background hover:bg-accent',
                          isDisabled && 'cursor-not-allowed opacity-60'
                        )}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                ) : (
                  <Input
                    id={`ask-user-${q.id}`}
                    value={values[q.id] ?? ''}
                    disabled={isDisabled}
                    aria-invalid={invalid}
                    onChange={(event) => {
                      setValues((current) => ({ ...current, [q.id]: event.target.value }))
                      setErrors((current) => ({ ...current, [q.id]: false }))
                    }}
                  />
                )}
                {invalid && (
                  <p className="text-xs text-destructive">{t('answerRequired')}</p>
                )}
              </div>
            )
          })}
        </div>
      </div>
      {submitError && (
        <p className="text-xs text-destructive" role="alert">{submitError}</p>
      )}
      <div className="flex items-center justify-end gap-2">
        <Button type="submit" size="sm" disabled={isDisabled}>
          {submitting ? t('submitting') : t('submit')}
        </Button>
      </div>
    </form>
  )
}
