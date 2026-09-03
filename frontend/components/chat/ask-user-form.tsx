'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { AgentRunAnswerPayload, AskUserQuestion } from '@/lib/api'
import type { ChatMessage } from './types'

const ANSWER_CONTROL_SIZE_CLASS = 'h-9 w-full rounded-md px-2.5'

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
 * One question at a time for an ask_user tool call. Answers are retained
 * across pages and submitted as one structured map from the last page.
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

  if (questions.length === 0) return null

  const currentPageIndex = Math.min(pageIndex, questions.length - 1)
  const question = questions[currentPageIndex]
  const isLastPage = currentPageIndex === questions.length - 1
  const isDisabled = disabled || submitting
  const hasRequiredAnswer = (candidate: AskUserQuestion) => (
    candidate.required === false || Boolean(values[candidate.id]?.trim())
  )

  const validateQuestion = (candidate: AskUserQuestion) => {
    const valid = hasRequiredAnswer(candidate)
    setErrors((current) => ({ ...current, [candidate.id]: !valid }))
    return valid
  }

  const goToNextPage = () => {
    if (isDisabled || !validateQuestion(question)) return
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
      className={cn('space-y-3 rounded-t-lg border border-b-0 bg-muted/30 px-3 pb-3 pt-2', className)}
      data-ask-user-form
      data-ask-user-page={currentPageIndex + 1}
      data-ask-user-question-id={question.id}
    >
      <div className="flex items-start gap-2">
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-blue-500" aria-hidden="true">?</span>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('title')}</p>
            {questions.length > 1 && (
              <span className="text-xs text-muted-foreground">
                {t('progress', { current: currentPageIndex + 1, total: questions.length })}
              </span>
            )}
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor={`ask-user-${question.id}`}
              className="block text-sm font-medium leading-5"
            >
              {question.question}
              {question.required !== false && <span className="text-destructive"> *</span>}
            </label>
            {question.options && question.options.length > 0 && (
              <div className="flex flex-col gap-2">
                {question.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => {
                      setValues((current) => ({ ...current, [question.id]: option }))
                      setErrors((current) => ({ ...current, [question.id]: false }))
                    }}
                    className={cn(
                      'cursor-pointer justify-start border text-left text-sm transition-colors',
                      ANSWER_CONTROL_SIZE_CLASS,
                      values[question.id] === option
                        ? 'border-primary bg-primary/10 font-medium text-primary'
                        : 'border-border bg-background hover:bg-accent',
                      isDisabled && 'cursor-not-allowed opacity-60'
                    )}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
            <Input
              id={`ask-user-${question.id}`}
              value={values[question.id] ?? ''}
              placeholder={question.options?.length ? t('customAnswer') : undefined}
              className={ANSWER_CONTROL_SIZE_CLASS}
              disabled={isDisabled}
              aria-invalid={invalid}
              onChange={(event) => {
                setValues((current) => ({ ...current, [question.id]: event.target.value }))
                setErrors((current) => ({ ...current, [question.id]: false }))
              }}
            />
            {invalid && (
              <p className="text-xs text-destructive">{t('answerRequired')}</p>
            )}
          </div>
        </div>
      </div>
      {submitError && (
        <p className="text-xs text-destructive" role="alert">{submitError}</p>
      )}
      <div className="flex items-center justify-between gap-2">
        {currentPageIndex > 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isDisabled}
            onClick={() => setPageIndex((current) => Math.max(current - 1, 0))}
          >
            {t('previous')}
          </Button>
        ) : <span />}
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={isDisabled}
            onClick={skipAnswers}
          >
            {t('skipAll')}
          </Button>
          <Button
            type={isLastPage ? 'submit' : 'button'}
            size="sm"
            disabled={isDisabled}
            onClick={isLastPage ? undefined : goToNextPage}
          >
            {isLastPage ? (submitting ? t('submitting') : t('submit')) : t('next')}
          </Button>
        </div>
      </div>
    </form>
  )
}
