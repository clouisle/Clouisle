'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { AlertCircle, ChevronDown, ChevronUp, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import Image from 'next/image'
import { ApiError, publicAgentsApi, type PublicAgent } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChatContainer, ChatInput, VariableForm, useVariableForm } from '@/components/chat'
import { useRun } from '@/hooks/use-run'
import { extractVariables } from '@/lib/utils/extract-variables'
import { cn } from '@/lib/utils'

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
        setMetadata(await publicAgentsApi.getPublicAgent(id))
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
  const hasVisibleVariables = variables.some((variable) => !variable.hidden)
  const requiredCount = variables.filter((variable) => !variable.hidden && variable.required).length
  const filledRequiredCount = variables.filter((variable) => {
    if (variable.hidden || !variable.required) return false
    const value = variableValues[variable.name]
    if (variable.type === 'checkbox') return true
    if (variable.type === 'array') {
      if (Array.isArray(value)) return value.length > 0
      if (typeof value === 'string' && value.trim()) {
        try {
          return Array.isArray(JSON.parse(value)) && JSON.parse(value).length > 0
        } catch {
          return false
        }
      }
      return false
    }
    return value !== undefined && value !== null && value !== ''
  }).length

  const handleConversationChange = React.useCallback((nextConversationId: string) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString())
    nextSearchParams.set('conversation', nextConversationId)
    router.replace(`/run/${id}?${nextSearchParams.toString()}`)
  }, [id, router, searchParams])

  const { messages, isStreaming, isLoading: runLoading, sendMessage, stop, conversationId, runId, runStatus, reconnect } = useRun({
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
            : runStatus === 'completed'
              ? t('status.success')
              : runStatus === 'stopped'
                ? t('status.cancelled')
                : runStatus === 'failed'
                  ? t('status.failed')
                  : t('status.interrupted')
    : null
  const runActive = runStatus === 'queued' || runStatus === 'running' || runStatus === 'stopping' || runStatus === 'completing'
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
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <ChatContainer
            messages={messages}
            isStreaming={isStreaming}
            isLoading={runLoading}
            hideToolCalls={Boolean(metadata.hide_tool_calls)}
            hideMessageActions={Boolean(metadata.hide_message_actions)}
            hideReasoning={Boolean(metadata.hide_reasoning)}
            conversationId={conversationId}
            className="flex-1 min-h-0 overflow-y-auto"
            onSelectOption={(option) => void handleSendMessage(option)}
            emptyState={
              <div className="flex-1 flex flex-col items-center justify-center px-4">
                <div className="mb-8">
                  {displayIcon ? isIconUrl ? (
                    <div className="relative h-20 w-20 rounded-full overflow-hidden ring-2 ring-border"><Image src={displayIcon} alt={metadata.name} fill unoptimized className="object-cover" /></div>
                  ) : <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center ring-2 ring-border"><span className="text-4xl">{displayIcon}</span></div> : <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center"><Sparkles className="h-6 w-6 text-primary" /></div>}
                </div>
                <h1 className="text-2xl md:text-3xl font-medium text-foreground text-center mb-4 max-w-3xl">{metadata.opening_message || t('welcomeMessage')}</h1>
                {metadata.suggested_questions && metadata.suggested_questions.length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2 max-w-3xl mt-8">
                    {metadata.suggested_questions.slice(0, 4).map((question, index) => <button key={index} onClick={() => void handleSendMessage(question)} className="px-4 py-2 text-sm text-foreground/80 border border-border rounded-lg hover:bg-accent transition-colors cursor-pointer w-full text-center">{question}</button>)}
                  </div>
                )}
              </div>
            }
          />
          <div className="relative pb-4 shrink-0">
            {hasVisibleVariables && (
              <div className="mx-auto max-w-3xl px-4">
                <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
                  <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                    <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                      <span className="text-muted-foreground">{tVars('title')}{requiredCount > 0 && <span className={cn('ml-1.5', filledRequiredCount === requiredCount ? 'text-green-600' : 'text-orange-500')}>{filledRequiredCount}/{requiredCount}</span>}</span>
                      {variablesOpen ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronUp className="h-3 w-3 text-muted-foreground" />}
                    </CollapsibleTrigger>
                    <CollapsibleContent><div className="px-2.5 pb-2.5 pt-0.5"><VariableForm variables={variables} values={variableValues} onChange={setVariableValues} fieldErrors={variableFieldErrors} className="space-y-2" /></div></CollapsibleContent>
                  </div>
                </Collapsible>
              </div>
            )}
            <ChatInput value={input} onChange={setInput} onSubmit={handleSendMessage} onStop={stop} placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : t('typePlaceholder')} disabled={false} isLoading={runLoading} isStreaming={isStreaming} />
            {metadata.powered_by_text && <p className="text-[11px] text-center text-muted-foreground mt-2">{metadata.powered_by_text}</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
