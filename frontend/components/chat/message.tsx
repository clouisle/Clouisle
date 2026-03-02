'use client'

import * as React from 'react'
import * as ReactDOM from 'react-dom'
import { useTranslations } from 'next-intl'
import { Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Loader2, SearchIcon, SparklesIcon, Wrench, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Streamdown } from 'streamdown'
import { ImageLightbox, useLightbox } from './image-lightbox'
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
import type { ChatMessage, MessagePart, TextPart, SourceDocumentPart, SourceUrlPart, ReasoningPart, ToolCallPart, McpToolCallPart, FilePart, ImagePart, TaskPart, UserInputRequestPart } from './types'
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
  isTaskPart,
  isUserInputRequestPart,
} from './types'
import { SourceContent } from './message-parts'
import { UserInputRequestCard } from './user-input-request-card'

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

      // Tool calls are now rendered in ChainOfThought, skip here
      if (isToolCallPart(part) || isMcpToolCallPart(part)) {
        return null
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

      // Skip tool results (rendered with tool calls) and step starts
      if (isToolResultPart(part) || isMcpToolResultPart(part)) {
        return null
      }

      // Task parts and reasoning are rendered in ChainOfThought
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
          />
        )
      }

      return null
    }

    // Get task parts and reasoning parts for ChainOfThought
    const taskParts = otherParts.filter(isTaskPart) as TaskPart[]
    const reasoningParts = otherParts.filter(isReasoningPart) as ReasoningPart[]
    const toolCallParts = otherParts.filter(isToolCallPart) as ToolCallPart[]

    // Check if we should show ChainOfThought (has tasks, reasoning, or tool calls)
    const hasChainOfThought = taskParts.length > 0 || reasoningParts.length > 0 || toolCallParts.length > 0

    // Get text parts to check if content has started
    const textParts = otherParts.filter(isTextPart) as TextPart[]
    const hasTextContent = textParts.some(t => t.text && t.text.length > 0)

    // Check if any step is still active (streaming)
    // Chain of thought is streaming until content starts appearing
    const isChainOfThoughtStreaming = !hasTextContent && (
      taskParts.some(t => t.state === 'running') ||
      reasoningParts.some(r => r.state === 'streaming') ||
      toolCallParts.some(tc => tc.state === 'running') ||
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
        if (taskPart.state === 'completed' && taskPart.info) {
          return tTask('foundSources', { count: taskPart.info })
        }
        return tTask('searchingKnowledge')
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

      // 2. Process other parts in their original order (tool calls and reasoning interleaved)
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
                  {result && isToolResultPart(result) && (
                    <ToolOutput
                      output={result.output}
                      errorText={result.isError ? String(result.output) : undefined}
                    />
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
