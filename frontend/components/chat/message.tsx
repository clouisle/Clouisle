'use client'

import * as React from 'react'
import * as ReactDOM from 'react-dom'
import { useTranslations } from 'next-intl'
import { Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Loader2, SearchIcon, SparklesIcon, Wrench, ChevronLeft, ChevronRight, AlertTriangle, Timer } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Streamdown } from 'streamdown'
import { ImageLightbox, useLightbox } from './image-lightbox'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Message as AIMessage,
  MessageContent,
  MessageActions,
  MessageAction,
  MessageAttachment,
  MessageAttachments,
} from '@/components/ai-elements/message'
import {
  ChainOfThought,
  ChainOfThoughtHeader,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from '@/components/ai-elements/chain-of-thought'
import {
  Tool,
  ToolHeader,
  ToolContent as AIToolContent,
  ToolInput,
  ToolOutput,
} from '@/components/ai-elements/tool'
import type { ChatMessage, MessagePart, TextPart, SourceDocumentPart, SourceUrlPart, ReasoningPart, ToolCallPart, McpToolCallPart, FilePart, ImagePart, TaskPart, UserInputRequestPart, MediaResultPart } from './types'
import {
  isTextPart,
  isReasoningPart,
  isToolCallPart,
  isToolResultPart,
  isMcpToolCallPart,
  isMcpToolResultPart,
  isSourcePart,
  isSourceDocumentPart,
  isFilePart,
  isImagePart,
  isMediaResultPart,
  isTaskPart,
  isUserInputRequestPart,
  isTruncatedPart,
} from './types'
import { SourceContent } from './message-parts'
import { UserInputRequestCard } from './user-input-request-card'
import {
  getImageAssetUrl,
  getVideoAssetUrl,
  isMediaImageToolResult,
  isMediaVideoToolResult,
  parseToolResultOutput,
} from '@/lib/utils/tool-result'

export interface MessageProps extends React.HTMLAttributes<HTMLDivElement> {
  message: ChatMessage
  /** Whether the message is currently streaming */
  isStreaming?: boolean
  /** Custom part renderer */
  renderPart?: (part: MessagePart, index: number) => React.ReactNode
  /** Whether to show copy button for assistant messages */
  showCopy?: boolean
  /** Whether to show feedback buttons */
  showFeedback?: boolean
  /** Callback for regenerate */
  onRegenerate?: () => void
  /** Callback for feedback */
  onFeedback?: (type: 'positive' | 'negative') => void
  /** Callback for switching version */
  onSwitchVersion?: (versionIndex: number) => void
  /** Callback when user selects an option from user input request */
  onSelectOption?: (option: string) => void
}

export const Message = React.forwardRef<HTMLDivElement, MessageProps>(
  (
    {
      message,
      isStreaming = false,
      renderPart,
      showCopy = true,
      showFeedback = false,
      onRegenerate,
      onFeedback,
      onSwitchVersion,
      onSelectOption,
      className,
      ...props
    },
    ref
  ) => {
    const t = useTranslations('chat.message')
    const tReasoning = useTranslations('chat.reasoning')
    const tTask = useTranslations('chat.task')
    const [copied, setCopied] = React.useState(false)
    const isUser = message.role === 'user'
    const isAssistant = message.role === 'assistant'
    
    // Image lightbox state
    const { isOpen: lightboxOpen, imageSrc, imageAlt, openLightbox, closeLightbox } = useLightbox()

    // Token usage and timing stats from message_end
    const usage = message.metadata?.usage as { prompt_tokens: number; completion_tokens: number; total_tokens: number } | undefined
    const timing = message.metadata?.timing as { first_token_ms: number | null; duration_ms: number; tokens_per_second: number | null } | undefined

    // Group sources together (only document sources for citations)
    const allSources = message.parts.filter(isSourcePart) as (SourceUrlPart | SourceDocumentPart)[]
    const documentSources = message.parts.filter(isSourceDocumentPart) as SourceDocumentPart[]
    const otherParts = message.parts.filter((p) => !isSourcePart(p))

    // Get text content for copying (strip citation markers)
    const getTextContent = React.useCallback(() => {
      return message.parts
        .filter(isTextPart)
        .map((part) => (part as TextPart).text.replace(/\[\[cite:\d+\]\]/g, ''))
        .join('\n')
        .trim()
    }, [message.parts])

    // Handle copy
    const handleCopy = React.useCallback(async () => {
      const text = getTextContent()
      if (!text) return

      try {
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch (err) {
        console.error('Failed to copy:', err)
      }
    }, [getTextContent])

    const renderToolResultContent = (output: unknown, isError?: boolean) => {
      const parsedOutput = parseToolResultOutput(output)

      if (isMediaImageToolResult(parsedOutput)) {
        return (
          <div className="space-y-3">
            {parsedOutput.images.length > 0 && (
              <div className="grid gap-2 sm:grid-cols-2">
                {parsedOutput.images.map((item, imageIndex) => {
                  const imageUrl = getImageAssetUrl(item.image)
                  if (!imageUrl) return null
                  return (
                    <button
                      key={`${imageIndex}-${imageUrl}`}
                      type="button"
                      className="overflow-hidden rounded-lg border bg-background text-left transition-opacity hover:opacity-90"
                      onClick={() => openLightbox(imageUrl, parsedOutput.prompt)}
                    >
                      <img
                        src={imageUrl}
                        alt={parsedOutput.prompt || 'Generated image'}
                        className="h-auto w-full object-cover"
                      />
                    </button>
                  )
                })}
              </div>
            )}
            {parsedOutput.error && (
              <div className="text-sm text-red-500">Error: {parsedOutput.error}</div>
            )}
          </div>
        )
      }

      if (isMediaVideoToolResult(parsedOutput)) {
        const videoUrl = getVideoAssetUrl(parsedOutput.video)
        return (
          <div className="space-y-3">
            {videoUrl ? (
              <video
                controls
                playsInline
                className="max-h-96 w-full rounded-lg border bg-black"
                src={videoUrl}
              />
            ) : (
              <div className="rounded-lg border border-dashed bg-muted/40 px-3 py-4 text-sm text-muted-foreground">
                {parsedOutput.status === 'completed'
                  ? 'Video generated but no preview URL is available.'
                  : parsedOutput.status === 'processing' || parsedOutput.status === 'pending'
                    ? 'Video is still being generated.'
                    : 'Video is unavailable.'}
                {typeof parsedOutput.progress === 'number' && (
                  <div className="mt-1">Progress: {Math.round(parsedOutput.progress * 100)}%</div>
                )}
              </div>
            )}
            {parsedOutput.error && (
              <div className="text-sm text-red-500">Error: {parsedOutput.error}</div>
            )}
          </div>
        )
      }

      return (
        <ToolOutput
          output={parsedOutput}
          errorText={isError ? String(parsedOutput) : undefined}
        />
      )
    }

    // Render a single part
    const renderDefaultPart = (part: MessagePart, index: number) => {
      if (isTextPart(part)) {
        return (
          <TextWithCitations
            key={index}
            text={part.text}
            sources={documentSources}
          />
        )
      }

      // Tool calls: only skip if there's reasoning (they'll be in ChainOfThought)
      // If no reasoning, render them normally in message content
      if (isToolCallPart(part) || isMcpToolCallPart(part)) {
        if (hasReasoning) {
          return null // Skip, will be rendered in ChainOfThought
        }
        // No reasoning - render tool call in message content
        const toolPart = part as ToolCallPart | McpToolCallPart
        const toolName = isToolCallPart(part)
          ? (part.toolDisplayName || part.toolName)
          : `${part.serverName}/${part.toolName}`

        // Find matching result
        const result = message.parts.find(
          (p) => (isToolResultPart(p) || isMcpToolResultPart(p)) && p.toolCallId === toolPart.toolCallId
        )

        const state = toolPart.state === 'error' ? 'output-error'
          : toolPart.state === 'done' ? 'output-available'
          : toolPart.state === 'running' ? 'input-available'
          : 'input-streaming'

        return (
          <Tool key={index} defaultOpen={false} className="my-2">
            <ToolHeader
              title={toolName}
              type="tool-call"
              state={state}
            />
            <AIToolContent>
              <ToolInput input={toolPart.input} />
              {result && (isToolResultPart(result) || isMcpToolResultPart(result)) && (
                (isToolResultPart(result) && (isMediaImageToolResult(parseToolResultOutput(result.output)) || isMediaVideoToolResult(parseToolResultOutput(result.output))))
                  ? null
                  : renderToolResultContent(result.output, result.isError)
              )}
            </AIToolContent>
          </Tool>
        )
      }

      if (isFilePart(part)) {
        const filePart = part as FilePart
        return (
          <MessageAttachment
            key={index}
            data={{
              type: 'file',
              url: filePart.url || '',
              filename: filePart.filename,
              mediaType: filePart.mimeType || 'application/octet-stream',
            }}
          />
        )
      }

      if (isImagePart(part)) {
        const imagePart = part as ImagePart
        return (
          <div
            key={index}
            className="max-w-xs rounded-lg overflow-hidden cursor-pointer hover:opacity-90 transition-opacity"
            onClick={() => openLightbox(imagePart.url, imagePart.alt)}
          >
            <img
              src={imagePart.url}
              alt={imagePart.alt || 'Uploaded image'}
              className="w-full h-auto object-cover"
            />
          </div>
        )
      }

      if (isMediaResultPart(part)) {
        const mediaPart = part as MediaResultPart
        return (
          <div key={index} className="mt-3">
            {renderToolResultContent(mediaPart.output)}
          </div>
        )
      }

      // Skip tool results (rendered with tool calls) and step starts
      if (isToolResultPart(part) || isMcpToolResultPart(part)) {
        return null
      }

      // Task parts and reasoning are always rendered in ChainOfThought
      if (isTaskPart(part) || isReasoningPart(part)) {
        return null
      }

      // User input request
      if (isUserInputRequestPart(part)) {
        const userInputPart = part as UserInputRequestPart
        return (
          <UserInputRequestCard
            key={index}
            question={userInputPart.question}
            options={userInputPart.options}
            state={userInputPart.state}
            selectedOption={userInputPart.selectedOption}
            onSelectOption={onSelectOption}
            isStreaming={isStreaming}
          />
        )
      }

      // Output truncated tip
      if (isTruncatedPart(part)) {
        return (
          <div
            key={index}
            className="flex items-start gap-2 mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-200"
          >
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{t('outputTruncated')}</span>
          </div>
        )
      }

      return null
    }

    // Get task parts and reasoning parts for ChainOfThought
    const taskParts = otherParts.filter(isTaskPart) as TaskPart[]
    const reasoningParts = otherParts.filter(isReasoningPart) as ReasoningPart[]
    const toolCallParts = otherParts.filter(isToolCallPart) as ToolCallPart[]
    // Check if we should show ChainOfThought
    // Only show if there are reasoning parts OR tasks (RAG/generating)
    // Tool calls should only be in ChainOfThought if there's reasoning
    const hasReasoning = reasoningParts.length > 0
    const hasTasks = taskParts.length > 0
    const hasChainOfThought = hasReasoning || hasTasks

    // Get text parts to check if content has started
    const textParts = otherParts.filter(isTextPart) as TextPart[]
    const hasTextContent = textParts.some(t => t.text && t.text.length > 0)

    // Check if any step is still active (streaming)
    // Chain of thought is streaming until content starts appearing
    // Only consider tool calls if there's reasoning (otherwise they're in message content)
    const isChainOfThoughtStreaming = !hasTextContent && (
      taskParts.some(t => t.state === 'running') ||
      reasoningParts.some(r => r.state === 'streaming') ||
      (hasReasoning && toolCallParts.some(tc => tc.state === 'running')) ||
      isStreaming  // Still streaming but no text yet
    )

    // Convert task state to step status
    const getStepStatus = (state: TaskPart['state']) => {
      switch (state) {
        case 'running': return 'active' as const
        case 'completed': return 'complete' as const
        case 'error': return 'error' as const
        default: return 'pending' as const
      }
    }

    // Convert tool call state to step status
    const getToolCallStepStatus = (state: ToolCallPart['state']) => {
      switch (state) {
        case 'running': return 'active' as const
        case 'done': return 'complete' as const
        case 'error': return 'error' as const
        default: return 'pending' as const
      }
    }

    // Get tool call label with state
    const getToolCallLabel = (toolPart: ToolCallPart) => {
      const name = toolPart.toolDisplayName || toolPart.toolName
      switch (toolPart.state) {
        case 'running': return `${name} 执行中`
        case 'done': return `${name} 已完成`
        case 'error': return `${name} 执行失败`
        default: return name
      }
    }

    // Render task title based on type and state
    const getTaskTitle = (taskPart: TaskPart) => {
      if (taskPart.taskType === 'rag') {
        if (taskPart.state === 'completed' && typeof taskPart.info === 'number') {
          return tTask('foundSources', { count: taskPart.info })
        }
        return tTask('searchingKnowledge')
      }
      if (taskPart.taskType === 'compression') {
        const info = (taskPart.info && typeof taskPart.info === 'object') ? taskPart.info as Record<string, unknown> : null
        const beforeTokens = typeof info?.before_tokens === 'number' ? info.before_tokens : null
        const afterTokens = typeof info?.after_tokens === 'number' ? info.after_tokens : null
        const summaryTurns = typeof info?.summary_turns === 'number' ? info.summary_turns : null
        const trigger = typeof info?.trigger === 'string' ? info.trigger : null
        const pressureLevel = typeof info?.pressure_level === 'string' ? info.pressure_level : null
        const compactedBlocks = typeof info?.compacted_blocks === 'number' ? info.compacted_blocks : null

        if (taskPart.state === 'completed' && beforeTokens && afterTokens) {
          if (trigger === 'context_length_error') {
            return tTask('compressionCompletedReactive', { before: beforeTokens, after: afterTokens })
          }
          if (trigger === 'blocking_threshold' || pressureLevel === 'blocking' || pressureLevel === 'over_budget') {
            if (summaryTurns && summaryTurns > 0) {
              return tTask('compressionCompletedBlockingSummary', { before: beforeTokens, after: afterTokens, count: summaryTurns })
            }
            return tTask('compressionCompletedBlocking', { before: beforeTokens, after: afterTokens })
          }
          if (summaryTurns && summaryTurns > 0) {
            return tTask('compressionCompletedProactiveSummary', {
              before: beforeTokens,
              after: afterTokens,
              count: compactedBlocks ?? summaryTurns,
            })
          }
          return tTask('compressionCompletedProactive', { before: beforeTokens, after: afterTokens })
        }
        if (trigger === 'context_length_error') {
          return tTask('compressingContextReactive')
        }
        if (trigger === 'blocking_threshold' || pressureLevel === 'blocking' || pressureLevel === 'over_budget') {
          return tTask('compressingContextBlocking')
        }
        return tTask('compressingContextProactive')
      }
      if (taskPart.taskType === 'generating') {
        return tTask('generating')
      }
      // Skip 'thinking' type - we now show individual tool calls instead
      return ''
    }

    // Build chain of thought steps in order: maintain original order from parts
    const buildChainOfThoughtSteps = () => {
      const steps: React.ReactNode[] = []

      // 1. RAG steps first (always at the beginning)
      taskParts.filter(t => t.taskType === 'rag').forEach((taskPart, index) => {
        steps.push(
          <ChainOfThoughtStep
            key={`rag-${index}`}
            icon={SearchIcon}
            label={getTaskTitle(taskPart)}
            status={getStepStatus(taskPart.state)}
          />
        )
      })

      // 1.5 Compression steps after RAG and before reasoning/tool execution
      taskParts.filter(t => t.taskType === 'compression').forEach((taskPart, index) => {
        steps.push(
          <ChainOfThoughtStep
            key={`compression-${index}`}
            icon={Timer}
            label={getTaskTitle(taskPart)}
            status={getStepStatus(taskPart.state)}
          />
        )
      })

      // 2. Process other parts in their original order
      // Only include tool calls and reasoning if there's reasoning content
      if (hasReasoning) {
        otherParts.forEach((part, index) => {
          if (isToolCallPart(part)) {
            const toolPart = part as ToolCallPart
            // Find matching result
            const result = message.parts.find(
              (p) => isToolResultPart(p) && p.toolCallId === toolPart.toolCallId
            )
            const state = toolPart.state === 'error' ? 'output-error'
              : toolPart.state === 'done' ? 'output-available'
              : toolPart.state === 'running' ? 'input-available'
              : 'input-streaming'

            steps.push(
              <ChainOfThoughtStep
                key={`tool-${toolPart.toolCallId}`}
                icon={Wrench}
                label={getToolCallLabel(toolPart)}
                status={getToolCallStepStatus(toolPart.state)}
              >
                <Tool defaultOpen={false} className="mt-2">
                  <ToolHeader
                    title={toolPart.toolDisplayName || toolPart.toolName}
                    type="tool-call"
                    state={state}
                  />
                  <AIToolContent>
                    <ToolInput input={toolPart.input} />
                    {result && isToolResultPart(result) && !(
                      isMediaImageToolResult(parseToolResultOutput(result.output)) ||
                      isMediaVideoToolResult(parseToolResultOutput(result.output))
                    ) && (
                      renderToolResultContent(result.output, result.isError)
                    )}
                  </AIToolContent>
                </Tool>
              </ChainOfThoughtStep>
            )
          } else if (isMcpToolCallPart(part)) {
            const mcpPart = part as McpToolCallPart
            // Find matching result
            const result = message.parts.find(
              (p) => isMcpToolResultPart(p) && p.toolCallId === mcpPart.toolCallId
            )
            const state = mcpPart.state === 'error' ? 'output-error'
              : mcpPart.state === 'done' ? 'output-available'
              : mcpPart.state === 'running' ? 'input-available'
              : 'input-streaming'

            steps.push(
              <ChainOfThoughtStep
                key={`mcp-tool-${mcpPart.toolCallId}`}
                icon={Wrench}
                label={`${mcpPart.serverName}/${mcpPart.toolName}`}
                status={getToolCallStepStatus(mcpPart.state)}
              >
                <Tool defaultOpen={false} className="mt-2">
                  <ToolHeader
                    title={`${mcpPart.serverName}/${mcpPart.toolName}`}
                    type="tool-call"
                    state={state}
                  />
                  <AIToolContent>
                    <ToolInput input={mcpPart.input} />
                    {result && isMcpToolResultPart(result) && (
                      <ToolOutput
                        output={result.output}
                        errorText={result.isError ? String(result.output) : undefined}
                      />
                    )}
                  </AIToolContent>
                </Tool>
              </ChainOfThoughtStep>
            )
          } else if (isReasoningPart(part)) {
            const reasoningPart = part as ReasoningPart
            steps.push(
              <ChainOfThoughtStep
                key={`reasoning-${index}`}
                label={reasoningPart.state === 'streaming'
                  ? tReasoning('processing')
                  : tReasoning('thoughtFor', { seconds: reasoningPart.duration ? Math.ceil(reasoningPart.duration / 1000) : 0 })
                }
                status={reasoningPart.state === 'streaming' ? 'active' : 'complete'}
              >
                {reasoningPart.text && (
                  <pre className="text-xs text-muted-foreground/70 whitespace-pre-wrap font-sans">
                    {reasoningPart.text}
                  </pre>
                )}
              </ChainOfThoughtStep>
            )
          }
        })
      }

      // 3. Generating steps last
      taskParts.filter(t => t.taskType === 'generating').forEach((taskPart, index) => {
        steps.push(
          <ChainOfThoughtStep
            key={`generating-${index}`}
            icon={SparklesIcon}
            label={getTaskTitle(taskPart)}
            status={getStepStatus(taskPart.state)}
          />
        )
      })

      return steps
    }

    // Filter parts for file attachments
    const fileParts = otherParts.filter(isFilePart)
    const contentParts = otherParts.filter((p) => !isFilePart(p) && !isToolResultPart(p) && !isMcpToolResultPart(p) && !isTaskPart(p) && !isReasoningPart(p))

    // Check if this is a loading placeholder message (only show if no ChainOfThought)
    const isLoadingMessage = message.metadata?.isLoading && contentParts.length === 0 && !hasChainOfThought

    return (
      <div
        ref={ref}
        className={cn('w-full py-3', className)}
        data-role={message.role}
        {...props}
      >
        <div className="mx-auto max-w-3xl px-4">
          <AIMessage from={message.role}>
            {/* File attachments for user messages */}
            {isUser && fileParts.length > 0 && (
              <MessageAttachments>
                {fileParts.map((part, index) =>
                  renderPart ? renderPart(part, index) : renderDefaultPart(part, index)
                )}
              </MessageAttachments>
            )}

            <MessageContent>
              {/* Chain of Thought: shows RAG, reasoning, tool calls, and generating steps in order */}
              {isAssistant && hasChainOfThought && (
                <ChainOfThought isStreaming={isChainOfThoughtStreaming}>
                  <ChainOfThoughtHeader title={tReasoning('thought')} />
                  <ChainOfThoughtContent>
                    {buildChainOfThoughtSteps()}
                  </ChainOfThoughtContent>
                </ChainOfThought>
              )}
              {/* Loading state */}
              {isLoadingMessage ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">{t('thinking')}</span>
                </div>
              ) : (
                contentParts.map((part, index) =>
                  renderPart ? renderPart(part, index) : renderDefaultPart(part, index)
                )
              )}
            </MessageContent>

            {/* Sources (grouped at bottom) */}
            {isAssistant && allSources.length > 0 && (
              <SourceContent sources={allSources} />
            )}

            {/* Actions for assistant messages */}
            {isAssistant && !isStreaming && getTextContent() && (
              <MessageActions className="opacity-0 group-hover:opacity-100 transition-opacity">
                {/* Version switcher */}
                {(message.versionCount ?? 1) > 1 && onSwitchVersion && (
                  <div className="flex items-center gap-0.5 text-muted-foreground">
                    <button
                      className="p-1 rounded hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
                      onClick={() => onSwitchVersion((message.versionNumber ?? 1) - 2)}
                      disabled={(message.versionNumber ?? 1) <= 1}
                    >
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </button>
                    <span className="text-xs tabular-nums min-w-[3ch] text-center">
                      {message.versionNumber ?? 1}/{message.versionCount ?? 1}
                    </span>
                    <button
                      className="p-1 rounded hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
                      onClick={() => onSwitchVersion(message.versionNumber ?? 1)}
                      disabled={(message.versionNumber ?? 1) >= (message.versionCount ?? 1)}
                    >
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
                {showCopy && (
                  <MessageAction
                    tooltip={copied ? t('copied') : t('copy')}
                    onClick={handleCopy}
                  >
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </MessageAction>
                )}
                {onRegenerate && (
                  <MessageAction
                    tooltip={t('regenerate')}
                    onClick={onRegenerate}
                  >
                    <RefreshCw className="h-4 w-4" />
                  </MessageAction>
                )}
                {usage && (
                  <Popover>
                    <PopoverTrigger
                      render={
                        <button className="inline-flex items-center justify-center rounded-md text-sm font-medium h-7 w-7 hover:bg-accent hover:text-accent-foreground cursor-pointer transition-colors">
                          <Timer className="h-4 w-4" />
                          <span className="sr-only">{t('tokenStats')}</span>
                        </button>
                      }
                    />
                    <PopoverContent side="top" sideOffset={8} className="w-auto min-w-[200px] p-3 text-xs">
                      <TokenStatsContent usage={usage} timing={timing} t={t} />
                    </PopoverContent>
                  </Popover>
                )}
                {showFeedback && (
                  <>
                    <MessageAction
                      tooltip={t('helpful')}
                      onClick={() => onFeedback?.('positive')}
                    >
                      <ThumbsUp className="h-4 w-4" />
                    </MessageAction>
                    <MessageAction
                      tooltip={t('notHelpful')}
                      onClick={() => onFeedback?.('negative')}
                    >
                      <ThumbsDown className="h-4 w-4" />
                    </MessageAction>
                  </>
                )}
              </MessageActions>
            )}
          </AIMessage>
        </div>
        
        {/* Image Lightbox */}
        <ImageLightbox
          src={imageSrc}
          alt={imageAlt}
          isOpen={lightboxOpen}
          onClose={closeLightbox}
        />
      </div>
    )
  }
)

Message.displayName = 'Message'

/**
 * Token stats popover content
 */
function TokenStatsContent({
  usage,
  timing,
  t,
}: {
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  timing?: { first_token_ms: number | null; duration_ms: number; tokens_per_second: number | null }
  t: (key: string) => string
}) {
  const formatTime = (ms: number) => {
    if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
    return `${ms}ms`
  }

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between gap-8">
        <span className="text-muted-foreground">{t('inputTokens')}</span>
        <span className="font-mono tabular-nums">{usage.prompt_tokens.toLocaleString()}</span>
      </div>
      <div className="flex justify-between gap-8">
        <span className="text-muted-foreground">{t('outputTokens')}</span>
        <span className="font-mono tabular-nums">{usage.completion_tokens.toLocaleString()}</span>
      </div>
      {timing?.first_token_ms != null && (
        <div className="flex justify-between gap-8">
          <span className="text-muted-foreground">{t('firstTokenTime')}</span>
          <span className="font-mono tabular-nums">{formatTime(timing.first_token_ms)}</span>
        </div>
      )}
      {timing?.duration_ms != null && (
        <div className="flex justify-between gap-8">
          <span className="text-muted-foreground">{t('totalTime')}</span>
          <span className="font-mono tabular-nums">{formatTime(timing.duration_ms)}</span>
        </div>
      )}
      {timing?.tokens_per_second != null && (
        <div className="flex justify-between gap-8">
          <span className="text-muted-foreground">{t('speed')}</span>
          <span className="font-mono tabular-nums">{timing.tokens_per_second}T/s</span>
        </div>
      )}
    </div>
  )
}

/**
 * Citation badge component with tooltip
 */
function CitationBadge({
  index,
  source,
}: {
  index: number
  source?: SourceDocumentPart
}) {
  const t = useTranslations('chat.source')
  const badge = (
    <span
      className={cn(
        'inline-flex items-center justify-center',
        'min-w-5 h-5 px-1.5 mx-0.5',
        'text-xs font-medium rounded-full',
        'bg-primary/10 text-primary hover:bg-primary/20',
        'transition-colors cursor-help',
        'align-middle'
      )}
    >
      {index}
    </span>
  )

  if (!source) {
    return badge
  }

  return (
    <Tooltip>
      <TooltipTrigger render={badge} />
      <TooltipContent side="top" className="max-w-80 p-3">
        <div className="space-y-2">
          <div className="font-medium text-sm">{source.documentName || t('documentDefault')}</div>
          <div className="text-xs text-muted-foreground line-clamp-4">
            {source.content}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

/**
 * Text content with inline citations rendered as badges with tooltips
 * Uses MutationObserver to detect when Streamdown finishes rendering,
 * then replaces citation markers with portal targets
 */
function TextWithCitations({
  text,
  sources,
}: {
  text: string
  sources: SourceDocumentPart[]
}) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const [portalTargets, setPortalTargets] = React.useState<Array<{
    element: HTMLSpanElement
    index: number
  }>>([])
  const hasSources = sources.length > 0

  // Citation marker formats: [[cite:N]] and common variants like (ref:N), [ref:N], [[ref:N]]
  const normalizeCitations = (input: string) =>
    input
      .replace(/\[\[ref:(\d+)\]\]/gi, '[[cite:$1]]')
      .replace(/\[ref:(\d+)\]/gi, '[[cite:$1]]')
      .replace(/\(ref:(\d+)\)/gi, '[[cite:$1]]')

  const createCiteRegex = () => /\[\[cite:(\d+)\]\]/g

  // Process text: strip citations if no sources
  const processedText = React.useMemo(() => {
    const normalized = normalizeCitations(text)
    if (!hasSources) {
      return normalized.replace(createCiteRegex(), '')
    }
    return normalized
  }, [text, hasSources])

  // Function to find and replace citation markers in DOM
  const processCitations = React.useCallback(() => {
    if (!containerRef.current || !hasSources) {
      setPortalTargets([])
      return
    }

    // Walk through all text nodes
    const walker = document.createTreeWalker(
      containerRef.current,
      NodeFilter.SHOW_TEXT,
      null
    )

    const nodesToProcess: Text[] = []
    let node: Text | null
    while ((node = walker.nextNode() as Text | null)) {
      if (node.textContent && createCiteRegex().test(node.textContent)) {
        nodesToProcess.push(node)
      }
    }

    if (nodesToProcess.length === 0) {
      return
    }

    const newTargets: Array<{ element: HTMLSpanElement; index: number }> = []

    // Process each text node
    nodesToProcess.forEach((textNode) => {
      const content = textNode.textContent || ''
      const fragment = document.createDocumentFragment()
      let lastIndex = 0
      let match
      const citeRegex = createCiteRegex()

      while ((match = citeRegex.exec(content)) !== null) {
        // Add text before citation
        if (match.index > lastIndex) {
          fragment.appendChild(
            document.createTextNode(content.slice(lastIndex, match.index))
          )
        }

        // Create placeholder span for portal
        const citationIndex = parseInt(match[1], 10)
        const span = document.createElement('span')
        span.className = 'cite-portal'
        span.style.display = 'inline'
        span.dataset.citeIndex = String(citationIndex)
        fragment.appendChild(span)

        newTargets.push({ element: span, index: citationIndex })
        lastIndex = citeRegex.lastIndex
      }

      // Add remaining text
      if (lastIndex < content.length) {
        fragment.appendChild(
          document.createTextNode(content.slice(lastIndex))
        )
      }

      // Replace the text node with the fragment
      if (textNode.parentNode) {
        textNode.parentNode.replaceChild(fragment, textNode)
      }
    })

    setPortalTargets((prev) => [...prev, ...newTargets])
  }, [hasSources])

  // Use MutationObserver to detect when Streamdown renders content
  React.useEffect(() => {
    if (!containerRef.current || !hasSources) {
      setPortalTargets([])
      return
    }

    // Reset portal targets when text changes
    setPortalTargets([])

    // Process any existing content
    const timeoutId = setTimeout(processCitations, 0)

    // Watch for DOM changes (streaming content)
    const observer = new MutationObserver(() => {
      processCitations()
    })

    observer.observe(containerRef.current, {
      childList: true,
      subtree: true,
      characterData: true,
    })

    return () => {
      clearTimeout(timeoutId)
      observer.disconnect()
    }
  }, [processedText, hasSources, processCitations])

  return (
    <div
      ref={containerRef}
      className="w-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
    >
      <Streamdown
        components={{
          // Use div instead of p when paragraph contains block elements (like images)
          // This prevents React hydration error: <div> cannot be a descendant of <p>
          p: ({ children, node, ...props }) => {
            // Check AST node for img elements (more reliable than checking React children)
            const hasImgInNode = node?.children?.some(
              (child: { tagName?: string; type?: string }) => 
                child.tagName === 'img' || child.type === 'element' && child.tagName === 'img'
            )
            // Also check React children for any wrapper components
            const hasBlockElements = React.Children.toArray(children).some(
              (child) => 
                React.isValidElement(child) && 
                (child.type === 'div' || child.type === 'img' || typeof child.type === 'function')
            )
            if (hasImgInNode || hasBlockElements) {
              return <div className="my-4" {...props}>{children}</div>
            }
            return <p {...props}>{children}</p>
          },
        }}
      >
        {processedText}
      </Streamdown>
      {/* Render citation badges via portals */}
      {portalTargets.map(({ element, index }) =>
        ReactDOM.createPortal(
          <CitationBadge
            key={`cite-${index}-${element.dataset.citeIndex}`}
            index={index}
            source={sources[index - 1]}
          />,
          element
        )
      )}
    </div>
  )
}

export { type ChatMessage }
