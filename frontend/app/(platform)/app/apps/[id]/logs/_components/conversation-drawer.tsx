'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
import { Clock, Zap, Loader2, WrenchIcon, CheckCircle2, ChevronDown, ChevronRight, FileText, Paperclip, ImageIcon, Brain } from 'lucide-react'
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
      <SheetContent side="right" className="w-[60%]! max-w-none! p-0 flex flex-col" showCloseButton={false}>
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
        {/* Reasoning content (Chain of Thought) */}
        {message.reasoning_content && (
          <ReasoningSection content={message.reasoning_content} duration={message.duration_ms} />
        )}
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
        <div className="space-y-2 max-w-[85%]">
          {/* User message bubble */}
          <div className="rounded-lg px-4 py-2.5 bg-primary text-primary-foreground">
            <p className="text-sm whitespace-pre-wrap wrap-break-word">{message.content}</p>
          </div>
          {/* User attachments: images and files */}
          {(message.images && message.images.length > 0) || (message.file_urls && message.file_urls.length > 0) ? (
            <UserAttachments images={message.images} fileUrls={message.file_urls} />
          ) : null}
        </div>
      ) : (
        <div className="w-full space-y-3">
          {/* Reasoning content (Chain of Thought) */}
          {message.reasoning_content && (
            <ReasoningSection content={message.reasoning_content} duration={message.duration_ms} />
          )}
          {/* Main text content */}
          {message.content && (
            <Streamdown className="text-sm prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              {message.content}
            </Streamdown>
          )}
        </div>
      )}

      {/* Token Usage & Model Info */}
      {isAssistant && (message.token_usage || message.model_used || message.duration_ms) && (
        <MessageMeta message={message} t={t} />
      )}

      {/* RAG Context */}
      {message.rag_context && message.rag_context.length > 0 && (
        <RagContextSection ragContext={message.rag_context} />
      )}
    </div>
  )
}

// User attachments: images and files
function UserAttachments({ 
  images, 
  fileUrls 
}: { 
  images?: Array<{ type: string; url: string }> | null
  fileUrls?: Array<{ filename: string; url: string; size: number; mime_type: string }> | null
}) {
  const hasImages = images && images.length > 0
  const hasFiles = fileUrls && fileUrls.length > 0
  
  if (!hasImages && !hasFiles) return null

  return (
    <div className="flex flex-wrap gap-2 justify-end">
      {/* Images */}
      {hasImages && images!.map((img, index) => (
        <a 
          key={`img-${index}`}
          href={img.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block"
        >
          <img 
            src={img.url} 
            alt={`attachment-${index}`}
            className="max-w-[120px] max-h-[120px] rounded-lg border object-cover hover:opacity-90 transition-opacity"
          />
        </a>
      ))}
      
      {/* Files */}
      {hasFiles && fileUrls!.map((file, index) => (
        <a
          key={`file-${index}`}
          href={file.url}
          target="_blank"
          rel="noopener noreferrer"
          download={file.filename}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-muted/50 hover:bg-muted transition-colors max-w-[200px]"
        >
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="text-xs font-medium truncate">{file.filename}</p>
            <p className="text-xs text-muted-foreground">
              {formatFileSize(file.size)}
            </p>
          </div>
        </a>
      ))}
    </div>
  )
}

// Format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Reasoning/Chain of Thought section
function ReasoningSection({ content, duration }: { content: string; duration?: number | null }) {
  const t = useTranslations('agents.logs')
  const [isOpen, setIsOpen] = React.useState(false)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
      <CollapsibleTrigger className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
        <Brain className="h-4 w-4" />
        <span>{t('reasoning')}</span>
        {duration && (
          <span className="text-xs">({(duration / 1000).toFixed(1)}s)</span>
        )}
        <ChevronRight className={cn("h-4 w-4 transition-transform", isOpen && "rotate-90")} />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 p-3 rounded-lg bg-muted/50 border-l-2 border-muted-foreground/30">
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{content}</p>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

// RAG Context section - 参考 chat 的 source-content 风格
function RagContextSection({ ragContext }: { ragContext: Record<string, unknown>[] }) {
  const t = useTranslations('agents.logs')
  const [isOpen, setIsOpen] = React.useState(false)

  return (
    <div className="mt-2 overflow-hidden">
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors cursor-pointer">
          <span>{t('ragContextCount', { count: ragContext.length })}</span>
          <ChevronDown className={cn("h-4 w-4 transition-transform duration-200", isOpen && "rotate-180")} />
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 space-y-1">
          {ragContext.map((ctx, index) => (
            <RagSourceItem key={index} ctx={ctx} index={index} />
          ))}
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}

// 单个来源项组件
function RagSourceItem({ ctx, index }: { ctx: Record<string, unknown>; index: number }) {
  const t = useTranslations('agents.logs')
  const [isOpen, setIsOpen] = React.useState(false)
  
  const content = (ctx.content as string) || (ctx.text as string) || JSON.stringify(ctx)
  const source = (ctx.source as string) || (ctx.document_name as string) || (ctx.file_name as string)
  const score = ctx.score as number | undefined
  
  // 截取预览内容
  const getPreviewContent = () => {
    if (content.length <= 60) return content
    return content.slice(0, 60) + '...'
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
      <CollapsibleTrigger className="w-full text-left">
        <div className="flex items-start gap-2 p-3 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors">
          <div className="mt-0.5 shrink-0">
            <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <span className="shrink-0">{source || t('segment', { index: index + 1 })}</span>
              {score !== undefined && (
                <span className="text-primary/70 shrink-0">
                  {t('relevance', { score: Math.round(score * 100) })}
                </span>
              )}
            </div>
            {!isOpen && (
              <div className="text-sm text-muted-foreground line-clamp-1">
                {getPreviewContent()}
              </div>
            )}
          </div>
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="p-3 ml-6 border-l-2 border-muted">
          <div className="text-sm whitespace-pre-wrap break-all">
            {content}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
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
