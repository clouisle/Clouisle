'use client'

import * as React from 'react'
import Image from 'next/image'
import { useSearchParams } from 'next/navigation'
import { useParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Loader2, Bot, RotateCcw, ChevronUp, ChevronDown, PanelLeft, PanelLeftClose } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChatContainer, ChatInput, VariableForm, useVariableForm, type ChatInputFile, type FileUploadConfig } from '@/components/chat'
import { useEmbedChat } from '@/hooks/use-embed-chat'
import { embedApi, resolveEmbedMessage, type EmbedAgentInfo } from '@/lib/api/embed'
import { useEmbedHistory, type EmbedHistoryEntry } from '@/hooks/use-embed-history'
import type { VariableDefinition, VariableType } from '@/lib/api'
import { Suspense } from 'react'

function EmbedAgentChatContent() {
  const params = useParams()
  const searchParams = useSearchParams()
  const t = useTranslations('embed.page')
  const agentId = params.id as string
  const token = searchParams.get('token') || ''
  const mode = searchParams.get('mode') || 'fullscreen'

  const [agent, setAgent] = React.useState<EmbedAgentInfo | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [inputValue, setInputValue] = React.useState('')
  const [files, setFiles] = React.useState<ChatInputFile[]>([])
  const [isUploading, setIsUploading] = React.useState(false)
  const [variablesOpen, setVariablesOpen] = React.useState(true)

  // Listen for token via postMessage (more secure alternative)
  const [apiKey, setApiKey] = React.useState(token)
  React.useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'clouisle:token' && event.data?.token) {
        setApiKey(event.data.token)
      }
    }
    window.addEventListener('message', handler)
    // Notify parent that iframe is ready
    window.parent.postMessage({ type: 'clouisle:ready' }, '*')
    return () => window.removeEventListener('message', handler)
  }, [])

  // Load agent info
  React.useEffect(() => {
    if (!apiKey || !agentId) {
      setLoading(false)
      setError(t('invalidToken'))
      return
    }

    setLoading(true)
    embedApi
      .getAgentInfo(agentId, apiKey)
      .then(data => {
        setAgent(data)
        setError(null)
      })
      .catch(err => {
        const message = err instanceof Error ? resolveEmbedMessage(err.message, t('errorLoading')) : t('errorLoading')
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [agentId, apiKey, t])

  // Build initial greeting message from embed_config.bubble.greeting
  const initialMessages = React.useMemo(() => {
    const greeting = (agent?.embed_config?.bubble as Record<string, unknown> | undefined)?.greeting as string | undefined
    if (!greeting) return []
    return [{
      id: 'greeting',
      role: 'assistant' as const,
      parts: [{ type: 'text' as const, text: greeting }],
    }]
  }, [agent])

  const formVariables = React.useMemo((): VariableDefinition[] => {
    const vars = (agent?.variables || []) as Array<Record<string, unknown>>

    const normalized: VariableDefinition[] = []
    for (const v of vars) {
      const name = v.name as string | undefined
      const type = v.type as string | undefined
      if (!name || !type) continue

      normalized.push({
        name,
        type: type as VariableType,
        label: (v.label as string | null | undefined) ?? null,
        required: Boolean(v.required),
        hidden: Boolean(v.hidden),
        default: (v.default as string | null | undefined) ?? null,
        description: (v.description as string | null | undefined) ?? null,
        options: (v.options as string[] | null | undefined) ?? null,
        min: (v.min as number | null | undefined) ?? null,
        max: (v.max as number | null | undefined) ?? null,
        maxLength: (v.maxLength as number | null | undefined) ?? null,
      })
    }

    return normalized
  }, [agent])

  const variableForm = useVariableForm(formVariables)

  const chat = useEmbedChat({
    agentId,
    apiKey,
    variables: variableForm.values,
    initialMessages,
    onConversationChange: (convId) => {
      // Notify parent of conversation change
      window.parent.postMessage({ type: 'clouisle:conversation', conversationId: convId }, '*')
    },
  })
  const history = useEmbedHistory(`clouisle:embed:history:agent:${agentId}`)
  const { addEntry } = history
  const [sidebarOpen, setSidebarOpen] = React.useState(false)
  const [selectedHistoryId, setSelectedHistoryId] = React.useState<string | null>(null)

  // Check if agent has required visible variables
  const hasVisibleVariables = React.useMemo(() => {
    if (!formVariables.length) return false
    return formVariables.some((v) => !v.hidden)
  }, [formVariables])

  const fileToDataUrl = React.useCallback(async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }, [])

  const handleSend = React.useCallback(async (message: string, submittedFiles?: ChatInputFile[]) => {
    if (!message.trim()) return
    if (variableForm.needsInput && !variableForm.validate()) {
      setVariablesOpen(true)
      return
    }

    const filesToProcess = submittedFiles || files

    let images: Array<{ type: string; url: string }> | undefined
    let fileUrls: Array<{ filename: string; url: string; size: number; mime_type: string }> | undefined

    if (agent && filesToProcess && filesToProcess.length > 0) {
      // Process image files for vision
      if (agent.enable_vision) {
        const imageFiles = filesToProcess.filter(f => f.type.startsWith('image/') && !f.isDocument)
        if (imageFiles.length > 0) {
          images = await Promise.all(
            imageFiles.map(async (f) => ({
              type: 'image_url' as const,
              url: await fileToDataUrl(f.file),
            }))
          )
        }
      }

      // Process document files - upload via embed API
      if (agent.enable_file_upload) {
        const documentFiles = filesToProcess.filter(f => f.isDocument)
        if (documentFiles.length > 0) {
          try {
            setIsUploading(true)
            const uploadPromises = documentFiles.map(async (f) => {
              const updateProgress = (percent: number) => {
                setFiles(prev => prev.map(file =>
                  file.id === f.id
                    ? { ...file, isUploading: true, uploadProgress: percent }
                    : file
                ))
              }
              setFiles(prev => prev.map(file =>
                file.id === f.id
                  ? { ...file, isUploading: true, uploadProgress: 0 }
                  : file
              ))
              const result = await embedApi.uploadFile(agentId, f.file, apiKey, updateProgress)
              setFiles(prev => prev.map(file =>
                file.id === f.id
                  ? { ...file, isUploading: false, uploadProgress: 100 }
                  : file
              ))
              return {
                filename: f.name,
                url: result.url,
                size: f.size,
                mime_type: f.type,
              }
            })
            fileUrls = await Promise.all(uploadPromises)
          } catch (err) {
            console.error('Failed to upload files:', err)
            setFiles(prev => prev.map(file => ({
              ...file, isUploading: false, uploadProgress: undefined,
            })))
            setIsUploading(false)
            return
          } finally {
            setIsUploading(false)
          }
        }
      }
    }

    setInputValue('')
    setFiles([])
    await chat.sendMessage(message.trim(), images, fileUrls)
  }, [files, agent, chat, agentId, apiKey, fileToDataUrl, variableForm])

  const handleNewChat = React.useCallback(() => {
    if (chat.messages.length > 0) {
      const title = (() => {
        for (const m of chat.messages) {
          if (m.role !== 'user') continue
          for (const p of m.parts) {
            if (p.type === 'text') return p.text
          }
        }
        return t('untitled')
      })()
      addEntry({ id: chat.conversationId || `conv-${Date.now()}`, title, createdAt: Date.now(), messages: chat.messages })
    }
    chat.reset()
    setFiles([])
    variableForm.reset()
    setSelectedHistoryId(null)
  }, [chat, variableForm, addEntry, t])
  const handleSelectHistory = React.useCallback((entry: EmbedHistoryEntry) => {
    chat.stop()
    chat.setMessages(entry.messages)
    setSelectedHistoryId(entry.id)
  }, [chat])

  // Loading state
  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loadingAgent')}</span>
      </div>
    )
  }

  // Error state
  if (error || !agent) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-4">
        <Bot className="h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{error || t('errorLoading')}</p>
      </div>
    )
  }

  const isIconUrl = agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))
  const embedCfg = (agent.embed_config || {}) as Record<string, unknown>
  const showHeader = embedCfg.show_header !== false
  const showHistory = embedCfg.show_history !== false
  const allowNew = embedCfg.allow_new !== false

  // Empty state (only shown when no greeting message exists)
  const emptyState = (
    <div className="flex flex-col items-center justify-center gap-4 px-6">
      {agent.icon ? (
        isIconUrl ? (
          <div className="relative h-20 w-20 overflow-hidden">
            <Image
              src={agent.icon}
              alt={agent.name}
              fill
              unoptimized
              className="object-cover"
            />
          </div>
        ) : (
          <span className="flex h-20 w-20 items-center justify-center leading-none text-4xl">{agent.icon}</span>
        )
      ) : (
        <Bot className="h-10 w-10 text-muted-foreground" />
      )}
      <p className="max-w-sm text-center text-base text-muted-foreground">
        {agent.opening_message || agent.description || t('defaultGreeting')}
      </p>
      {agent.suggested_questions && agent.suggested_questions.length > 0 && (
        <div className="mt-1 flex flex-wrap justify-center gap-2">
          {agent.suggested_questions.map((q, i) => (
            <Button
              key={i}
              variant="outline"
              size="sm"
              className="rounded-full px-4 text-xs"
              onClick={() => {
                void handleSend(q)
              }}
            >
              {q}
            </Button>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <div className="flex h-full">
      {showHistory && (
        <aside
          className={cn(
            'h-full shrink-0 overflow-hidden border-r bg-muted/50 transition-all duration-300',
            sidebarOpen ? 'w-56' : 'w-0 border-r-0'
          )}
        >
          <div className="flex h-full w-56 flex-col">
            <div className="flex h-11 items-center justify-between border-b px-3">
              <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">{t('history')}</span>
              {allowNew && sidebarOpen && (
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewChat} title={t('newChat')}>
                  <RotateCcw className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {history.entries.length === 0 ? (
                <p className="px-2 py-4 text-xs text-muted-foreground">{t('noHistory')}</p>
              ) : (
                <ol className="space-y-1">
                  {history.entries.map((entry) => (
                    <li key={entry.id}>
                      <button
                        type="button"
                        onClick={() => handleSelectHistory(entry)}
                        className={cn(
                          'w-full rounded-md px-2 py-2 text-left transition-colors hover:bg-accent/50',
                          selectedHistoryId === entry.id && 'bg-accent'
                        )}
                      >
                        <span className="block truncate text-xs font-medium">{entry.title || t('untitled')}</span>
                        <time className="mt-0.5 block text-[10px] text-muted-foreground">
                          {new Date(entry.createdAt).toLocaleString()}
                        </time>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {showHeader && (
          <header className="flex items-center gap-2 border-b px-3 py-2">
            {showHistory && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setSidebarOpen((open) => !open)}
                aria-label={t('history')}
              >
                {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
              </Button>
            )}
            {allowNew && !sidebarOpen && chat.messages.length > 0 && (
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleNewChat} title={t('newChat')}>
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
            {!(showHistory && sidebarOpen) && (
              <div className="flex min-w-0 flex-1 items-center gap-2">
                {agent.icon && (
                  isIconUrl ? (
                    <div className="relative h-6 w-6 shrink-0 overflow-hidden">
                      <Image src={agent.icon} alt={agent.name} fill unoptimized className="object-cover" />
                    </div>
                  ) : (
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center leading-none text-lg">{agent.icon}</span>
                  )
                )}
                <span className="truncate font-medium text-sm">{agent.name}</span>
              </div>
            )}
            {mode === 'bubble' && (
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto h-7 w-7"
                onClick={() => window.parent.postMessage({ type: 'clouisle:close' }, '*')}
                title={t('close')}
              >
                <span className="text-lg leading-none">&times;</span>
              </Button>
            )}
          </header>
        )}

        {/* Chat area */}
        <div className="flex-1 overflow-hidden">
          <ChatContainer
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            hideToolCalls={agent?.hide_tool_calls ?? false}
            onSelectOption={(option) => {
              void handleSend(option)
            }}
            emptyState={emptyState}
          />
        </div>

        {/* Input */}
        <div className="pb-2 pt-1 sm:pb-3">
          {/* Variable Panel - Collapsible above input */}
          {hasVisibleVariables && (
            <div className="mx-auto max-w-3xl px-4">
              <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
                <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                  <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                    <span className="text-xs font-medium flex items-center gap-1.5">
                      {t('configureVariables')}
                      {(() => {
                        const variables = (agent.variables || []) as Array<Record<string, unknown>>
                        const visibleRequired = variables.filter(v => !v.hidden && v.required)
                        const filledCount = visibleRequired.filter(v => {
                          const val = variableForm.values[v.name as string]
                          if (v.type === 'checkbox') return true
                          if (v.type === 'array') return Array.isArray(val) && val.length > 0
                          return val !== undefined && val !== null && val !== ''
                        }).length
                        if (visibleRequired.length > 0) {
                          return (
                            <span className={cn(
                              "text-[10px] px-1 py-0.5 rounded",
                              filledCount === visibleRequired.length
                                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                : "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400"
                            )}>
                              {filledCount}/{visibleRequired.length}
                            </span>
                          )
                        }
                        return null
                      })()}
                    </span>
                    {variablesOpen ? (
                      <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                    )}
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
            onSubmit={handleSend}
            onStop={chat.stop}
            isLoading={chat.isLoading}
            isStreaming={chat.isStreaming}
            placeholder={variableForm.needsInput && !variableForm.isValid ? t('fillRequired') : (agent.description || undefined)}
            allowAttachments={agent.enable_vision}
            enableFileUpload={agent.enable_file_upload}
            fileUploadConfig={agent.file_upload_config as FileUploadConfig | null}
            files={files}
            onFilesChange={setFiles}
            isUploading={isUploading}
          />
        </div>
      </div>
    </div>
  )
}

export default function EmbedAgentPage() {
  return (
    <Suspense fallback={
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    }>
      <EmbedAgentChatContent />
    </Suspense>
  )
}
