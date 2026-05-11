'use client'

import * as React from 'react'
import Image from 'next/image'
import { useSearchParams, useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Loader2, Bot, RotateCcw, ChevronUp, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChatContainer, ChatInput, VariableForm, useVariableForm } from '@/components/chat'
import type { ChatMessage } from '@/components/chat/types'
import type { VariableDefinition, VariableType } from '@/lib/api'
import { embedApi, resolveEmbedMessage, type EmbedWorkflowInfo } from '@/lib/api/embed'
import { Suspense } from 'react'

function EmbedWorkflowContent() {
  const params = useParams()
  const searchParams = useSearchParams()
  const t = useTranslations('embed.page')
  const workflowId = params.id as string
  const token = searchParams.get('token') || ''
  const mode = searchParams.get('mode') || 'fullscreen'

  const [workflow, setWorkflow] = React.useState<EmbedWorkflowInfo | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [inputValue, setInputValue] = React.useState('')
  const [variablesOpen, setVariablesOpen] = React.useState(true)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = React.useState(false)
  const closeConnectionRef = React.useRef<(() => void) | null>(null)
  const currentMessageRef = React.useRef<ChatMessage | null>(null)
  // Track node types to determine token routing (answer vs LLM)
  const nodeTypesRef = React.useRef<Map<string, string>>(new Map())

  const [apiKey, setApiKey] = React.useState(token)
  React.useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'clouisle:token' && event.data?.token) {
        setApiKey(event.data.token)
      }
    }
    window.addEventListener('message', handler)
    window.parent.postMessage({ type: 'clouisle:ready' }, '*')
    return () => window.removeEventListener('message', handler)
  }, [])


  React.useEffect(() => {
    if (!apiKey || !workflowId) {
      setLoading(false)
      setError(t('invalidToken'))
      return
    }
    setLoading(true)
    embedApi
      .getWorkflowInfo(workflowId, apiKey)
      .then(data => { setWorkflow(data); setError(null) })
      .catch(err => {
        const message = err instanceof Error ? resolveEmbedMessage(err.message, t('errorLoading')) : t('errorLoading')
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [workflowId, apiKey, t])

  const initialMessages = React.useMemo(() => {
    const greeting = (workflow?.embed_config?.bubble as Record<string, unknown> | undefined)?.greeting as string | undefined
    if (!greeting) return []
    return [{ id: 'greeting', role: 'assistant' as const, parts: [{ type: 'text' as const, text: greeting }] }]
  }, [workflow])

  const initialMessagesApplied = React.useRef(false)
  React.useEffect(() => {
    if (initialMessages.length > 0 && !initialMessagesApplied.current) {
      initialMessagesApplied.current = true
      setMessages(initialMessages)
    }
  }, [initialMessages])

  // Filter out 'query' variable - it's bound to the input box
  const formVariables = React.useMemo((): VariableDefinition[] => {
    const vars = (workflow?.variables || []) as Array<{
      name: string; type?: string; label?: string; required?: boolean
      hidden?: boolean; default?: string; description?: string
      options?: string[]; min?: number; max?: number; maxLength?: number
    }>
    const normalized: VariableDefinition[] = []
    for (const v of vars) {
      if (!v.name || !v.type) continue
      if (v.name === 'query') continue
      normalized.push({
        name: v.name,
        type: v.type as VariableType,
        label: v.label ?? null,
        required: Boolean(v.required),
        hidden: Boolean(v.hidden),
        default: v.default ?? null,
        description: v.description ?? null,
        options: v.options ?? null,
        min: v.min ?? null,
        max: v.max ?? null,
        maxLength: v.maxLength ?? null,
      })
    }
    return normalized
  }, [workflow])

  const variableForm = useVariableForm(formVariables)

  const hasVisibleVariables = React.useMemo(() => {
    return formVariables.some(v => !v.hidden)
  }, [formVariables])


  const handleWorkflowEvent = React.useCallback((event: { type: string; data: Record<string, unknown> }) => {
    const { type, data } = event

    switch (type) {
      case 'workflow_start': break

      case 'node_start': {
        const nodeId = data.node_id as string
        const nodeType = data.node_type as string
        // Track node type for token routing
        nodeTypesRef.current.set(nodeId, nodeType)
        break
      }

      case 'token': {
        const nodeId = data.node_id as string
        const tokenText = data.token as string

        // Only route answer node tokens to visible text output
        // LLM node tokens are not shown in the chat (matches debug drawer behavior)
        const nodeType = nodeTypesRef.current.get(nodeId)
        if (nodeType !== 'answer') break

        if (!currentMessageRef.current) {
          const msg: ChatMessage = { id: `msg-${Date.now()}`, role: 'assistant', parts: [{ type: 'text', text: tokenText }] }
          currentMessageRef.current = msg
          setMessages(prev => [...prev, msg])
        } else {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.role === 'assistant') {
              const parts = [...last.parts]
              const lastPart = parts[parts.length - 1]
              if (lastPart?.type === 'text') {
                parts[parts.length - 1] = { ...lastPart, text: lastPart.text + tokenText }
              } else {
                parts.push({ type: 'text', text: tokenText })
              }
              updated[updated.length - 1] = { ...last, parts }
            }
            return updated
          })
        }
        break
      }

      case 'node_complete': {
        // Answer node tokens are already streamed (real or pseudo), nothing to add here
        break
      }

      case 'node_error':
        // Node errors are not shown as chat messages in embed
        break

      case 'workflow_complete':
        setIsStreaming(false)
        break

      case 'workflow_error': {
        const errorMessage = resolveEmbedMessage(data.error, t('errorLoading'))
        if (errorMessage) {
          const errorMsg: ChatMessage = { id: `error-${Date.now()}`, role: 'assistant', parts: [{ type: 'text', text: errorMessage }] }
          setMessages(prev => [...prev, errorMsg])
        }
        setIsStreaming(false)
        break
      }
    }
  }, [t])


  const handleRun = React.useCallback(async (query: string) => {
    if (!query.trim()) return

    if (variableForm.needsInput && !variableForm.validate()) {
      setVariablesOpen(true)
      return
    }

    const inputs: Record<string, unknown> = { query: query.trim(), ...variableForm.values }

    // Add user message
    const userMsg: ChatMessage = { id: `user-${Date.now()}`, role: 'user', parts: [{ type: 'text', text: query.trim() }] }
    setMessages(prev => [...prev, userMsg])
    setInputValue('')
    currentMessageRef.current = null
    nodeTypesRef.current.clear()
    setIsStreaming(true)

    try {
      const { run_id } = await embedApi.runWorkflow(workflowId, inputs, apiKey)
      const close = embedApi.streamWorkflowRun(run_id, apiKey, {
        onEvent: handleWorkflowEvent,
        onError: (err) => { console.error('Workflow SSE error:', err); setIsStreaming(false) },
        onComplete: () => setIsStreaming(false),
      })
      closeConnectionRef.current = close
    } catch (err) {
      console.error('Failed to start workflow:', err)
      setIsStreaming(false)
    }
  }, [
    workflowId,
    apiKey,
    variableForm,
    handleWorkflowEvent,
  ])

  const handleStop = React.useCallback(() => {
    closeConnectionRef.current?.()
    closeConnectionRef.current = null
    setIsStreaming(false)
  }, [])

  const handleNewChat = React.useCallback(() => {
    handleStop()
    setMessages(initialMessages)
    currentMessageRef.current = null
    nodeTypesRef.current.clear()
    initialMessagesApplied.current = initialMessages.length > 0
    variableForm.reset()
  }, [handleStop, initialMessages, variableForm])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loadingAgent')}</span>
      </div>
    )
  }

  if (error || !workflow) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
        <Bot className="h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{error || t('errorLoading')}</p>
      </div>
    )
  }

  const isIconUrl = workflow.icon && (workflow.icon.startsWith('http') || workflow.icon.startsWith('/'))

  const emptyState = (
    <div className="flex flex-col items-center justify-center gap-4 px-6">
      {workflow.icon ? (
        isIconUrl ? (
          <div className="relative h-20 w-20 overflow-hidden">
            <Image
              src={workflow.icon}
              alt={workflow.name}
              fill
              unoptimized
              className="object-cover"
            />
          </div>
        ) : (
          <span className="flex h-20 w-20 items-center justify-center leading-none text-4xl">{workflow.icon}</span>
        )
      ) : (
        <Bot className="h-10 w-10 text-muted-foreground" />
      )}
      <p className="max-w-sm text-center text-base text-muted-foreground">
        {workflow.description || t('defaultGreeting')}
      </p>
    </div>
  )

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 sm:px-4 py-2">
        <div className="flex items-center gap-2">
          {workflow.icon && (
            isIconUrl ? (
              <div className="relative h-6 w-6 overflow-hidden">
                <Image
                  src={workflow.icon}
                  alt={workflow.name}
                  fill
                  unoptimized
                  className="object-cover"
                />
              </div>
            ) : (
              <span className="flex h-6 w-6 items-center justify-center leading-none text-lg">{workflow.icon}</span>
            )
          )}
          <span className="font-medium text-sm">{workflow.name}</span>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewChat} title={t('newChat')}>
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          )}
          {mode === 'bubble' && (
            <Button variant="ghost" size="icon" className="h-7 w-7"
              onClick={() => window.parent.postMessage({ type: 'clouisle:close' }, '*')} title={t('close')}>
              <span className="text-lg leading-none">&times;</span>
            </Button>
          )}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-hidden">
        <ChatContainer messages={messages} isStreaming={isStreaming} emptyState={emptyState} />
      </div>

      {/* Input */}
      <div className="pb-2 pt-1 sm:pb-3">
        {hasVisibleVariables && (
          <div className="mx-auto max-w-3xl px-4">
            <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
              <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                  <span className="text-xs font-medium flex items-center gap-1.5">
                    {t('configureVariables')}
                  </span>
                  {variablesOpen ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-2.5 pb-2.5 pt-0.5">
                    <VariableForm
                      variables={formVariables}
                      values={variableForm.values}
                      onChange={variableForm.setValues}
                      fieldErrors={variableForm.fieldErrors}
                      className="space-y-2"
                    />
                  </div>
                </CollapsibleContent>
              </div>
            </Collapsible>
          </div>
        )}
        <ChatInput
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleRun}
          onStop={handleStop}
          isLoading={isStreaming}
          isStreaming={isStreaming}
          placeholder={variableForm.needsInput && !variableForm.isValid ? t('fillRequired') : (workflow.description || undefined)}
        />
      </div>
    </div>
  )
}

export default function EmbedWorkflowPage() {
  return (
    <Suspense fallback={
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    }>
      <EmbedWorkflowContent />
    </Suspense>
  )
}
