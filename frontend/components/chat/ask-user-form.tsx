'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import type { AgentRunAnswerPayload, AskUserQuestion } from '@/lib/api'
import type { ChatMessage } from './types'

export interface AskUserFormProps {
  /** Questions rendered by this shared multi-question form. */
  questions: AskUserQuestion[]
  /** Whether interaction is disabled (streaming/answered). */
  disabled?: boolean
  /** Submit one structured answer result. */
  onSubmit: (answer: AgentRunAnswerPayload) => Promise<void>
  className?: string
}

export interface PendingAskUserFormProps {
  /** Conversation parts containing the server-persisted tool call. */
  messages: ChatMessage[]
  /** Server-authoritative tool call currently awaiting an answer. */
  pendingToolCallId?: string | null
  disabled?: boolean
  /** Submit against the original durable tool call. */
  onSubmit?: (toolCallId: string, answer: AgentRunAnswerPayload) => Promise<void>
  className?: string
}

export interface PendingAskUserRequest {
  toolCallId: string
  questions: AskUserQuestion[]
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
 * Resolve the valid ask_user call that the server says is awaiting answers.
 * Message history owns the original question payload; run state owns identity.
 */
export function getPendingAskUserRequest(
  messages: ChatMessage[],
  pendingToolCallId?: string | null
): PendingAskUserRequest | null {
  if (!pendingToolCallId) return null

  for (const message of messages) {
    for (const part of message.parts) {
      if (
        part.type !== 'tool-call'
        || part.toolName !== 'ask_user'
        || part.toolCallId !== pendingToolCallId
      ) {
        continue
      }

      const questions = normalizeAskUserQuestions(part.input)
      return questions.length > 0 ? { toolCallId: part.toolCallId, questions } : null
    }
  }

  return null
}

/**
 * Render the current pending ask_user request beside the composer, not in a
 * durable conversation message.
 */
export function PendingAskUserForm({
  messages,
  pendingToolCallId,
  disabled = false,
  onSubmit,
  className,
}: PendingAskUserFormProps) {
  const request = getPendingAskUserRequest(messages, pendingToolCallId)
  if (!request || !onSubmit) return null

  return (
    <div className={cn('mx-auto max-w-3xl px-4', className)} data-pending-ask-user-form>
      <AskUserForm
        key={request.toolCallId}
        questions={request.questions}
        disabled={disabled}
        onSubmit={(answer) => onSubmit(request.toolCallId, answer)}
        className="mx-auto w-[70%]"
      />
    </div>
  )
}

/**
 * Questionnaire-styled interaction surface for an ask_user tool call.
 * Questions are rendered sequentially with choices, optional freeform text,
 * and skip support.
 */
export function AskUserForm({
  questions,
  disabled = false,
  onSubmit,
  className,
}: AskUserFormProps) {
  const t = useTranslations('chat.message.askUser')
  const [pageIndex, setPageIndex] = React.useState(0)
  const [values, setValues] = React.useState<Record<string, string>>({})
  const [errors, setErrors] = React.useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = React.useState(false)
  const [submitError, setSubmitError] = React.useState<string | null>(null)

  const currentPageIndex = Math.min(pageIndex, Math.max(questions.length - 1, 0))
  const question = questions[currentPageIndex]
  const isLastPage = currentPageIndex === questions.length - 1
  const isDisabled = disabled || submitting


  if (questions.length === 0 || !question) return null
  const hasRequiredAnswer = (candidate: AskUserQuestion) => (
    candidate.required === false || Boolean(values[candidate.id]?.trim())
  )


  const goToNextPage = () => {
    if (isDisabled) return
    const valid = hasRequiredAnswer(question)
    setErrors((current) => ({ ...current, [question.id]: !valid }))
    if (!valid) return
    setPageIndex((current) => Math.min(current + 1, questions.length - 1))
  }

  const submitAnswer = async (answer: AgentRunAnswerPayload) => {
    if (isDisabled) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await onSubmit(answer)
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setSubmitting(false)
    }
  }

  const submitAnswers = async () => {
    if (isDisabled) return

    const missing = questions.findIndex((candidate) => !hasRequiredAnswer(candidate))
    if (missing !== -1) {
      setErrors(Object.fromEntries(
        questions.map((candidate) => [candidate.id, !hasRequiredAnswer(candidate)])
      ))
      setPageIndex(missing)
      return
    }

    const answers = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value.trim())
    )
    await submitAnswer({ answers })
  }

  const skipAnswers = () => {
    if (isDisabled) return
    setErrors({})
    void submitAnswer({ answers: {}, skipped: true })
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (isLastPage) {
      void submitAnswers()
      return
    }
    goToNextPage()
  }

  const invalid = Boolean(errors[question.id])

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        'rounded-t-lg border border-b-0 bg-muted/30 px-3.5 pb-3 pt-2.5 shadow-xs',
        className
      )}
      data-ask-user-form
      data-ask-user-page={currentPageIndex + 1}
      data-ask-user-question-id={question.id}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
          <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-blue-500/10 text-[10px] font-bold text-blue-600 dark:text-blue-400">?</span>
          {t('title')}
        </div>
        {questions.length > 1 && (
          <span className="text-xs text-muted-foreground">
            {t('progress', { current: currentPageIndex + 1, total: questions.length })}
          </span>
        )}
      </div>

      <div className="pr-1">
        <div className="mb-2 text-sm font-semibold text-foreground">
          {question.question}
          {question.required !== false && <span className="text-destructive ml-0.5">*</span>}
        </div>

        <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto p-1 [scrollbar-width:thin]">
          {question.options?.map((option) => {
            const isChecked = values[question.id] === option
            return (
              <button
                key={option}
                type="button"
                disabled={isDisabled}
                data-checked={isChecked ? true : undefined}
                onClick={() => {
                  setValues((current) => ({ ...current, [question.id]: option }))
                  setErrors((current) => ({ ...current, [question.id]: false }))
                }}
                className={cn(
                  'group/questionnaire-choice relative flex min-h-9 w-full cursor-pointer items-center gap-2.5 rounded-md border border-input bg-background/50 px-3 py-1.5 text-start text-sm transition-colors outline-none select-none hover:bg-muted/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
                  isChecked
                    ? 'border-primary bg-primary/15 font-medium text-primary shadow-sm ring-1 ring-primary/40 dark:bg-primary/25'
                    : '',
                )}
              >
                {option}
              </button>
            )
          })}
        </div>
          <input
            id={`ask-user-${question.id}`}
            data-slot="questionnaire-input"
            value={question.options?.includes(values[question.id] ?? '') ? '' : values[question.id] ?? ''}
            placeholder={question.options?.length ? t('customAnswer') : undefined}
            disabled={isDisabled}
            aria-invalid={invalid}
            onInput={(event) => {
              const text = event.currentTarget.value
              setValues((current) => ({ ...current, [question.id]: text }))
              setErrors((current) => ({ ...current, [question.id]: false }))
            }}
            className="mt-1.5 h-9 w-full min-w-0 rounded-md border border-input bg-background/50 px-2.5 py-1 text-sm transition-[color,box-shadow,background-color] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive"
          />

        {invalid && <p className="text-xs text-destructive">{t('answerRequired')}</p>}
      </div>

      {submitError && <p className="text-xs text-destructive" role="alert">{submitError}</p>}

      <div className="flex items-center justify-between gap-2 pt-1">
        {currentPageIndex > 0 ? (
          <button
            type="button"
            disabled={isDisabled}
            onClick={() => setPageIndex((current) => Math.max(current - 1, 0))}
            className="h-8 rounded-md px-2.5 text-sm hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
          >
            {t('previous')}
          </button>
        ) : <span />}
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={isDisabled}
            onClick={skipAnswers}
            className="h-8 rounded-md px-2.5 text-sm text-muted-foreground hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
          >
            {t('skipAll')}
          </button>
          {isLastPage ? (
            <button
              type="submit"
              disabled={isDisabled}
              className="h-8 rounded-md bg-primary px-3 text-sm text-primary-foreground hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
            >
              {submitting ? t('submitting') : t('submit')}
            </button>
          ) : (
            <button
              type="button"
              disabled={isDisabled}
              onClick={goToNextPage}
              className="h-8 rounded-md bg-primary px-3 text-sm text-primary-foreground hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
            >
              {t('next')}
            </button>
          )}
        </div>
      </div>
    </form>
  )
}
