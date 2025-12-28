'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
import { Clock, Zap, Loader2, WrenchIcon, CheckCircle2, ChevronDown } from 'lucide-react'
import { Streamdown } from 'streamdown'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { CodeBlock } from '@/components/ai-elements/code-block'
import type { ConversationWithMessages, Message } from '@/lib/api'

interface ConversationDrawerProps {
  conversation: ConversationWithMessages | null
  isLoading: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Helper to format relative time
function formatRelativeTime(dateString: string, locale: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (locale === 'zh') {
    if (diffSec < 60) return '刚刚'
    if (diffMin < 60) return `${diffMin} 分钟前`
    if (diffHour < 24) return `${diffHour} 小时前`
    if (diffDay < 30) return `${diffDay} 天前`
    return date.toLocaleDateString('zh-CN')
  } else {
    if (diffSec < 60) return 'just now'
    if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`
    if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`
    if (diffDay < 30) return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`
    return date.toLocaleDateString('en-US')
  }
}

// Helper to format full datetime
function formatDateTime(dateString: string, locale: string): string {
  const date = new Date(dateString)
  if (locale === 'zh') {
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } else {
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
}

export function ConversationDrawer({
  conversation,
  isLoading,
  open,
  onOpenChange,
}: ConversationDrawerProps) {
  const t = useTranslations('agents.logs')
  const locale = useLocale()

  // Calculate total tokens
  const totalTokens = conversation?.messages.reduce((sum, msg) => {
    if (msg.token_usage) {
      return sum + (msg.token_usage.prompt || 0) + (msg.token_usage.completion || 0)
    }
    return sum
  }, 0) ?? 0

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl md:max-w-2xl p-0 flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : conversation ? (
          <>
            <SheetHeader className="px-6 py-4 border-b shrink-0">
              <SheetTitle className="text-lg">
                {conversation.title || t('untitledConversation')}
              </SheetTitle>
              <SheetDescription className="flex items-center gap-4 text-sm">
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {formatDateTime(conversation.created_at, locale)}
                </span>
                <span className="flex items-center gap-1">
                  <Zap className="h-3.5 w-3.5" />
                  {totalTokens.toLocaleString()} tokens
                </span>
              </SheetDescription>

              {/* Variables if any */}
              {conversation.variables && Object.keys(conversation.variables).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(conversation.variables).map(([key, value]) => (
                    <Badge key={key} variant="secondary" className="text-xs">
                      {key}: {String(value)}
                    </Badge>
                  ))}
                </div>
              )}
            </SheetHeader>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto">
              <div className="p-6 space-y-6">
                {conversation.messages.map((message) => (
                  <MessageItem key={message.id} message={message} locale={locale} />
                ))}
              </div>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}

interface MessageItemProps {
  message: Message
  locale: string
}

function MessageItem({ message, locale }: MessageItemProps) {
  const t = useTranslations('agents.logs')
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'
  const isTool = message.role === 'tool'

  // Skip system messages
  if (message.role === 'system') return null

  // Tool result message
  if (isTool) {
    return <ToolResultMessage message={message} />
  }

  // Assistant message with tool calls
  if (isAssistant && message.tool_calls && message.tool_calls.length > 0) {
    return (
      <div className="w-full space-y-3">
        {/* Tool calls */}
        {message.tool_calls.map((toolCall, index) => (
          <ToolCallMessage key={index} toolCall={toolCall} />
        ))}
        {/* Text content if any */}
        {message.content && (
          <div className="mt-3">
            <Streamdown className="text-sm prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              {message.content}
            </Streamdown>
          </div>
        )}
        {/* Token info */}
        {(message.token_usage || message.model_used || message.duration_ms) && (
          <MessageMeta message={message} t={t} />
        )}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col', isUser && 'items-end')}>
      {/* Role & Time */}
      <div className={cn('flex items-center gap-2 mb-1.5', isUser && 'flex-row-reverse')}>
        <span className="text-xs font-medium">
          {isUser ? t('user') : t('assistant')}
        </span>
        <span className="text-xs text-muted-foreground">
          {formatRelativeTime(message.created_at, locale)}
        </span>
        {message.version_count && message.version_count > 1 && (
          <Badge variant="outline" className="text-xs py-0">
            v{message.version_number}/{message.version_count}
          </Badge>
        )}
      </div>

      {/* Message Content */}
      {isUser ? (
        <div className="rounded-lg px-4 py-2.5 max-w-[85%] bg-primary text-primary-foreground">
          <p className="text-sm whitespace-pre-wrap wrap-break-word">{message.content}</p>
        </div>
      ) : (
        <div className="w-full">
          <Streamdown className="text-sm prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            {message.content}
          </Streamdown>
        </div>
      )}

      {/* Token Usage & Model Info */}
      {isAssistant && (message.token_usage || message.model_used || message.duration_ms) && (
        <MessageMeta message={message} t={t} />
      )}

      {/* RAG Context indicator */}
      {message.rag_context && message.rag_context.length > 0 && (
        <div className="mt-1.5">
          <Badge variant="secondary" className="text-xs">
            📚 {t('ragContextCount', { count: message.rag_context.length })}
          </Badge>
        </div>
      )}
    </div>
  )
}

// Tool call message (assistant calling a tool)
function ToolCallMessage({ toolCall }: { toolCall: Record<string, unknown> }) {
  const [open, setOpen] = React.useState(false)
  
  // Handle different tool_call structures
  // Standard OpenAI format: { id, type, function: { name, arguments } }
  // Or direct format: { name, arguments }
  let toolName = 'unknown'
  let args: string | undefined

  if (toolCall.function && typeof toolCall.function === 'object') {
    const functionData = toolCall.function as Record<string, unknown>
    toolName = (functionData.name as string) || 'unknown'
    args = functionData.arguments as string | undefined
  } else if (toolCall.name) {
    // Direct format
    toolName = toolCall.name as string
    args = toolCall.arguments as string | undefined
  }

  let parsedArgs: unknown = null
  try {
    if (args) {
      parsedArgs = JSON.parse(args)
    }
  } catch {
    parsedArgs = args
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full rounded-md border">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 p-3 hover:bg-muted/50">
        <div className="flex items-center gap-2">
          <WrenchIcon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">{toolName}</span>
          <Badge variant="secondary" className="text-xs gap-1">
            <CheckCircle2 className="h-3 w-3 text-green-600" />
            已调用
          </Badge>
        </div>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t p-3 space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">参数</h4>
          <div className="rounded-md bg-muted/50">
            <CodeBlock code={parsedArgs ? (typeof parsedArgs === 'string' ? parsedArgs : JSON.stringify(parsedArgs, null, 2)) : '{}'} language="json" />
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// Tool result message
function ToolResultMessage({ message }: { message: Message }) {
  const [open, setOpen] = React.useState(false)
  const toolName = message.tool_name || 'unknown'

  let content = message.content
  let isJson = false
  try {
    const parsed = JSON.parse(message.content)
    content = JSON.stringify(parsed, null, 2)
    isJson = true
  } catch {
    // Keep original content
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full rounded-md border">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 p-3 hover:bg-muted/50">
        <div className="flex items-center gap-2">
          <WrenchIcon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">{toolName}</span>
          <Badge variant="secondary" className="text-xs gap-1">
            <CheckCircle2 className="h-3 w-3 text-green-600" />
            完成
          </Badge>
        </div>
        <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="border-t p-3 space-y-2">
          <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">结果</h4>
          <div className="rounded-md bg-muted/50 overflow-x-auto">
            {isJson ? (
              <CodeBlock code={content} language="json" />
            ) : (
              <pre className="text-xs p-3 whitespace-pre-wrap">{content}</pre>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// Token/model meta info
function MessageMeta({ message, t }: { message: Message; t: ReturnType<typeof useTranslations> }) {
  return (
    <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
      {message.model_used && (
        <Tooltip>
          <TooltipTrigger>
            <span className="cursor-help">{message.model_used}</span>
          </TooltipTrigger>
          <TooltipContent>{t('modelUsed')}</TooltipContent>
        </Tooltip>
      )}
      {message.token_usage && (
        <Tooltip>
          <TooltipTrigger>
            <span className="cursor-help">
              {(message.token_usage.prompt || 0) + (message.token_usage.completion || 0)} tokens
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {t('tokenBreakdown', {
              prompt: message.token_usage.prompt || 0,
              completion: message.token_usage.completion || 0,
            })}
          </TooltipContent>
        </Tooltip>
      )}
      {message.duration_ms && (
        <Tooltip>
          <TooltipTrigger>
            <span className="cursor-help">{message.duration_ms}ms</span>
          </TooltipTrigger>
          <TooltipContent>{t('responseDuration')}</TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}
