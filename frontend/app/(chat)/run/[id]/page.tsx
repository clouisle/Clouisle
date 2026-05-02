'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Loader2, AlertCircle, Sparkles, GitBranch, ChevronDown, ChevronUp } from 'lucide-react'
import Image from 'next/image'
import { ApiError, publicAgentsApi, workflowsApi, type PublicAgent, type Workflow } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChatContainer, ChatInput, VariableForm, useVariableForm } from '@/components/chat'
import { useRun, type RunType } from '@/hooks/use-run'
import { extractVariables } from '@/lib/utils/extract-variables'
import { cn } from '@/lib/utils'

interface UnifiedRunPageProps {
  params: Promise<{ id: string }>
}

export default function UnifiedRunPage({ params }: UnifiedRunPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('run')
  const tVars = useTranslations('chat.variables')

  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)
  const [metadata, setMetadata] = React.useState<PublicAgent | Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)
  const [input, setInput] = React.useState('')
  const [variablesOpen, setVariablesOpen] = React.useState(true)

  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])

  // Get type from URL (default to agent for backward compatibility)
  const type = (searchParams.get('type') as RunType) || 'agent'
  const conversationParam = searchParams.get('conversation')

  // Fetch metadata (Agent or Workflow)
  React.useEffect(() => {
    const fetchMetadata = async () => {
      if (!resolvedParams) return

      try {
        setIsLoading(true)
        setError(null)

        if (type === 'agent') {
          const data = await publicAgentsApi.getPublicAgent(resolvedParams.id)
          setMetadata(data as PublicAgent)
        } else {
          const data = await workflowsApi.getWorkflow(resolvedParams.id)
          setMetadata(data as Workflow)
        }
      } catch (err) {
        const isNotFound = err instanceof ApiError && (err.code === 404 || (err.code >= 4000 && err.code < 5000))
        setError(new Error(isNotFound ? t('notFound') : t('loadError')))
      } finally {
        setIsLoading(false)
      }
    }

    fetchMetadata()
  }, [resolvedParams, type, t])

  // Extract variables from metadata (for workflow, we'll handle query separately)
  const variables = React.useMemo(() => {
    const vars = extractVariables(metadata, type)
    // Filter out 'query' variable as it will be handled by input box
    return type === 'workflow' ? vars.filter(v => v.name !== 'query') : vars
  }, [metadata, type])

  // Variable form state
  const {
    values: variableValues,
    setValues: setVariableValues,
    needsInput: needsVariableInput,
    isValid: variablesValid,
    fieldErrors: variableFieldErrors,
    validate: validateVariables,
  } = useVariableForm(variables)

  // Check if there are any visible variables
  const hasVisibleVariables = variables.some((v) => !v.hidden)

  // Count required variables
  const requiredCount = variables.filter((v) => !v.hidden && v.required).length
  const filledRequiredCount = variables.filter((v) => {
    if (v.hidden || !v.required) return false
    const value = variableValues[v.name]
    if (v.type === 'checkbox') return true
    if (v.type === 'array') {
      // Array is valid if it's a non-empty array or valid JSON string
      if (Array.isArray(value)) {
        return value.length > 0
      }
      if (typeof value === 'string' && value.trim()) {
        try {
          const parsed = JSON.parse(value)
          return Array.isArray(parsed) && parsed.length > 0
        } catch {
          return false
        }
      }
      return false
    }
    return value !== undefined && value !== null && value !== ''
  }).length

  // Use unified run hook
  const {
    messages,
    isStreaming,
    isLoading: runLoading,
    sendMessage,
    stop,
  } = useRun({
    id: resolvedParams?.id || '',
    type,
    conversationId: conversationParam || undefined,
    isDebug: type === 'workflow' ? searchParams.get('debug') === 'true' : false,
    variables: variableValues,
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

  if (isLoading || !resolvedParams) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !metadata) {
    return (
      <div className="h-screen flex flex-col items-center justify-center p-4 bg-background">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('error')}</AlertTitle>
          <AlertDescription>
            {error ? error.message : t('notFound')}
          </AlertDescription>
        </Alert>
        <Button
          variant="ghost"
          className="mt-4"
          onClick={() => router.push('/')}
        >
          {t('backToHome')}
        </Button>
      </div>
    )
  }

  const avatarUrl = 'avatar_url' in metadata ? metadata.avatar_url : null
  const displayIcon = metadata.icon || avatarUrl
  const isIconUrl = Boolean(displayIcon && (displayIcon.startsWith('http') || displayIcon.startsWith('/')))
  return (
    <div className="h-screen flex overflow-hidden bg-background">
      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between px-4 h-14 border-b shrink-0">
          <div className="flex items-center gap-3">
            {/* Icon */}
            <div className="flex items-center gap-2">
              {displayIcon ? (
                isIconUrl ? (
                  <div className="relative h-6 w-6 rounded overflow-hidden">
                    <Image
                      src={displayIcon}
                      alt={metadata.name}
                      fill
                      unoptimized
                      className="object-cover"
                    />
                  </div>
                ) : (
                  <span className="flex h-6 w-6 items-center justify-center leading-none text-lg">{displayIcon}</span>
                )
              ) : type === 'agent' ? (
                <Sparkles className="h-5 w-5 text-primary" />
              ) : (
                <GitBranch className="h-5 w-5 text-primary" />
              )}

              <div>
                <h1 className="font-medium text-sm">{metadata.name}</h1>
                {metadata.description && (
                  <p className="text-xs text-muted-foreground">{metadata.description}</p>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <ChatContainer
            messages={messages}
            isStreaming={isStreaming}
            hideToolCalls={type === 'agent' ? Boolean((metadata as PublicAgent).hide_tool_calls) : false}
            className="flex-1 min-h-0 overflow-y-auto"
            onSelectOption={(option) => {
              void handleSendMessage(option)
            }}
            emptyState={
              <div className="flex-1 flex flex-col items-center justify-center px-4">
                {/* Icon */}
                <div className="mb-8">
                  {displayIcon ? (
                    isIconUrl ? (
                      <div className="relative h-20 w-20 rounded-full overflow-hidden ring-2 ring-border">
                        <Image
                          src={displayIcon}
                          alt={metadata.name}
                          fill
                          unoptimized
                          className="object-cover"
                        />
                      </div>
                    ) : (
                      <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center ring-2 ring-border">
                        <span className="flex h-full w-full items-center justify-center leading-none text-4xl">{displayIcon}</span>
                      </div>
                    )
                  ) : (
                    <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                      {type === 'agent' ? (
                        <Sparkles className="h-6 w-6 text-primary" />
                      ) : (
                        <GitBranch className="h-6 w-6 text-primary" />
                      )}
                    </div>
                  )}
                </div>

                {/* Welcome Message */}
                <h1 className="text-2xl md:text-3xl font-medium text-foreground text-center mb-4">
                  {type === 'agent' && 'opening_message' in metadata
                    ? metadata.opening_message || t('welcomeMessage')
                    : metadata.description || t('welcomeMessage')}
                </h1>

                {/* Suggested Questions (for Agent) */}
                {type === 'agent' && 'suggested_questions' in metadata && metadata.suggested_questions && metadata.suggested_questions.length > 0 && (
                  <div className="flex flex-wrap justify-center gap-2 max-w-2xl mt-8">
                    {metadata.suggested_questions.slice(0, 4).map((q, i) => (
                      <button
                        key={i}
                        onClick={() => handleSendMessage(q)}
                        className="px-4 py-2 text-sm text-foreground/80 border border-border rounded-full hover:bg-accent hover:border-border transition-colors cursor-pointer"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            }
          />

          {/* Input Area */}
          <div className="relative pb-4 shrink-0">
            {/* Variable Panel - Collapsible above input */}
            {hasVisibleVariables && (
              <div className="mx-auto max-w-3xl px-4">
                <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
                  <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                    <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                      <span className="text-muted-foreground">
                        {tVars('title')}
                        {requiredCount > 0 && (
                          <span className={cn(
                            "ml-1.5",
                            filledRequiredCount === requiredCount ? "text-green-600" : "text-orange-500"
                          )}>
                            {filledRequiredCount}/{requiredCount}
                          </span>
                        )}
                      </span>
                      {variablesOpen ? (
                        <ChevronDown className="h-3 w-3 text-muted-foreground" />
                      ) : (
                        <ChevronUp className="h-3 w-3 text-muted-foreground" />
                      )}
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="px-2.5 pb-2.5 pt-0.5">
                        <VariableForm
                          variables={variables}
                          values={variableValues}
                          onChange={setVariableValues}
                          fieldErrors={variableFieldErrors}
                          className="space-y-2"
                        />
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>
              </div>
            )}

            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={handleSendMessage}
              onStop={stop}
              placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : (type === 'workflow' ? t('workflowInputPlaceholder') : t('typePlaceholder'))}
              disabled={runLoading && !isStreaming}
              isLoading={runLoading}
              isStreaming={isStreaming}
            />

            {/* Footer */}
            <p className="text-[11px] text-center text-muted-foreground mt-2">
              {type === 'agent' && 'created_by' in metadata
                ? t('poweredBy', { name: metadata.created_by?.username || 'Clouisle' })
                : t('poweredBy', { name: 'Clouisle' })}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
