'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertCircle, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import Image from 'next/image'
import { ApiError, publicAgentsApi, type PublicAgent } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AgentChatEmptyState, AgentChatSurface, useVariableForm } from '@/components/chat'
import { useRun } from '@/hooks/use-run'
import { extractVariables } from '@/lib/utils/extract-variables'

interface AgentRunPageProps {
  id: string
}

export function AgentRunPage({ id }: AgentRunPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('run')
  const tVars = useTranslations('chat.variables')
  const [metadata, setMetadata] = React.useState<PublicAgent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)
  const [input, setInput] = React.useState('')
  const [variablesOpen, setVariablesOpen] = React.useState(true)

  React.useEffect(() => {
    const fetchMetadata = async () => {
      try {
        setIsLoading(true)
        setError(null)
        const data = await publicAgentsApi.getPublicAgent(id)
        setMetadata(data)
        // Default-collapse the variable panel unless required inputs must be filled
        setVariablesOpen(extractVariables(data, 'agent').some(v => !v.hidden && v.required))
      } catch (err) {
        const isNotFound = err instanceof ApiError && (err.code === 404 || (err.code >= 4000 && err.code < 5000))
        setError(new Error(isNotFound ? t('notFound') : t('loadError')))
      } finally {
        setIsLoading(false)
      }
    }

    void fetchMetadata()
  }, [id, t])

  const variables = React.useMemo(() => extractVariables(metadata, 'agent'), [metadata])
  const {
    values: variableValues,
    setValues: setVariableValues,
    needsInput: needsVariableInput,
    isValid: variablesValid,
    fieldErrors: variableFieldErrors,
    validate: validateVariables,
  } = useVariableForm(variables)

  const handleConversationChange = React.useCallback((nextConversationId: string) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString())
    nextSearchParams.set('conversation', nextConversationId)
    router.replace(`/run/${id}?${nextSearchParams.toString()}`)
  }, [id, router, searchParams])

  const { messages, isStreaming, isLoading: runLoading, sendMessage, stop, conversationId, runId, runStatus, pendingAskUserToolCallId, submitAskUser, reconnect, regenerate, editMessage, switchVersion } = useRun({
    id,
    type: 'agent',
    conversationId: searchParams.get('conversation') || undefined,
    variables: variableValues,
    onConversationChange: handleConversationChange,
  })


  const handleSendMessage = async (text: string) => {
    if (!text.trim()) return
    if (needsVariableInput && !validateVariables()) {
      setVariablesOpen(true)
      return
    }
    setInput('')
    await sendMessage(text)
  }

  if (isLoading) {
    return <div className="h-screen flex items-center justify-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
  }

  if (error || !metadata) {
    return (
      <div className="h-screen flex flex-col items-center justify-center p-4 bg-background">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('error')}</AlertTitle>
          <AlertDescription>{error ? error.message : t('notFound')}</AlertDescription>
        </Alert>
        <Button variant="ghost" className="mt-4" onClick={() => router.push('/')}>{t('backToHome')}</Button>
      </div>
    )
  }

  const displayIcon = metadata.icon || metadata.avatar_url
  const isIconUrl = Boolean(displayIcon && (displayIcon.startsWith('http') || displayIcon.startsWith('/')))
  const runStatusLabel = runStatus
    ? runStatus === 'queued'
      ? t('status.queued')
      : runStatus === 'running'
        ? t('status.running')
        : runStatus === 'stopping'
          ? t('status.stopping')
          : runStatus === 'completing'
            ? t('status.completing')
            : runStatus === 'waiting'
              ? t('status.waiting')
              : runStatus === 'completed'
                ? t('status.success')
                : runStatus === 'stopped'
                  ? t('status.cancelled')
                  : runStatus === 'failed'
                    ? t('status.failed')
                    : t('status.interrupted')
    : null
  const runActive = runStatus === 'queued' || runStatus === 'running' || runStatus === 'stopping' || runStatus === 'completing' || runStatus === 'waiting'
  const showReconnect = Boolean(runId && runActive)

  return (
    <div className="h-screen flex overflow-hidden bg-background">
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-4 h-14 border-b shrink-0">
          <div className="flex items-center gap-2">
            {displayIcon ? isIconUrl ? (
              <div className="relative h-6 w-6 rounded overflow-hidden"><Image src={displayIcon} alt={metadata.name} fill unoptimized className="object-cover" /></div>
            ) : <span className="flex h-6 w-6 items-center justify-center leading-none text-lg">{displayIcon}</span> : <Sparkles className="h-5 w-5 text-primary" />}
            <div><h1 className="font-medium text-sm">{metadata.name}</h1>{metadata.description && <p className="text-xs text-muted-foreground">{metadata.description}</p>}</div>
          </div>
          <div className="flex items-center gap-2">
            {runStatus && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {runActive && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />}
                {runStatusLabel}
              </span>
            )}
            {showReconnect && (
              <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" onClick={() => reconnect?.()}>
                <RefreshCw className="h-3.5 w-3.5" />
                {t('reconnect')}
              </Button>
            )}
          </div>
        </header>
        <AgentChatSurface
          messages={messages}
          isStreaming={isStreaming}
          isLoading={runLoading}
          loadingLabel={runStatus === 'queued' || runStatus === 'waiting' || runStatus === 'stopping' ? runStatusLabel ?? undefined : undefined}
          hideToolCalls={Boolean(metadata.hide_tool_calls)}
          hideMessageActions={Boolean(metadata.hide_message_actions)}
          hideReasoning={Boolean(metadata.hide_reasoning)}
          conversationId={conversationId}
          onRegenerate={regenerate}
          onEditMessage={editMessage}
          onSwitchVersion={switchVersion}
          emptyState={
            <AgentChatEmptyState
              agentName={metadata.name}
              icon={metadata.icon}
              avatarUrl={metadata.avatar_url}
              openingMessage={metadata.opening_message}
              fallbackMessage={t('welcomeMessage')}
              suggestedQuestions={metadata.suggested_questions}
              onSuggestedQuestion={handleSendMessage}
            />
          }
          inputValue={input}
          onInputChange={setInput}
          onSubmit={handleSendMessage}
          onStop={stop}
          placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : t('typePlaceholder')}
          inputDisabled={runStatus === 'waiting'}
          pendingAskUserToolCallId={pendingAskUserToolCallId}
          onSubmitAskUser={submitAskUser}
          variables={variables}
          variableValues={variableValues}
          onVariablesChange={setVariableValues}
          variableFieldErrors={variableFieldErrors}
          variablesOpen={variablesOpen}
          onVariablesOpenChange={setVariablesOpen}
          allowAttachments={false}
          poweredByText={metadata.powered_by_text}
          className="flex-1"
        />
        </div>
      </div>
  )
}
