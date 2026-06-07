'use client'

import * as React from 'react'
import * as ReactDOM from 'react-dom'
import { useLocale, useTranslations } from 'next-intl'
import { Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Loader2, SearchIcon, SparklesIcon, Wrench, ChevronLeft, ChevronRight, AlertTriangle, Timer, Brain, Square, Eye, Volume2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Block,
  Streamdown,
  defaultRehypePlugins,
} from 'streamdown'
import type { CodeHighlighterPlugin, PluginConfig, LinkSafetyModalProps } from 'streamdown'
import { bundledLanguages, codeToTokens } from 'shiki'
import type { BundledLanguage, BundledTheme } from 'shiki'
import { ImageLightbox, useLightbox } from './image-lightbox'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import type { ChatMessage, CodePreviewPayload, MessagePart, TextPart, SourceDocumentPart, SourceUrlPart, ReasoningPart, ToolCallPart, McpToolCallPart, FilePart, ImagePart, TaskPart, UserInputRequestPart, MediaResultPart } from './types'
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
  isStoppedPart,
  isIterationCapReachedPart,
} from './types'
import { SourceContent, FileListContent } from './message-parts'
import { UserInputRequestCard } from './user-input-request-card'
import {
  getImageAssetUrl,
  getVideoAssetUrl,
  isMediaImageToolResult,
  isMediaVideoToolResult,
  parseToolResultOutput,
  shouldDisplayMediaResultInBody,
} from '@/lib/utils/tool-result'

const CODE_FENCE_REGEX = /^```([^\r\n`]*)\r?\n([\s\S]*?)\r?\n```$/
const STREAMING_REHYPE_PLUGINS = [
  defaultRehypePlugins.sanitize,
  defaultRehypePlugins.harden,
]
const CHAT_CODE_THEMES: [BundledTheme, BundledTheme] = ['github-light', 'github-dark']
const chatCodeHighlighter: CodeHighlighterPlugin = {
  name: 'shiki',
  type: 'code-highlighter',
  highlight: (options, callback) => {
    if (!(options.language in bundledLanguages)) {
      return null
    }

    void codeToTokens(options.code, {
      lang: options.language,
      themes: {
        light: options.themes[0] as BundledTheme,
        dark: options.themes[1] as BundledTheme,
      },
    }).then((result) => callback?.(result)).catch(() => undefined)

    return null
  },
  supportsLanguage: (language) => language in bundledLanguages,
  getSupportedLanguages: () => Object.keys(bundledLanguages) as BundledLanguage[],
  getThemes: () => CHAT_CODE_THEMES,
}
const chatStreamdownPlugins: PluginConfig = {
  code: chatCodeHighlighter,
}
const SPEECH_STARTED_EVENT = 'clouisle:chat-speech-started'
const SPEECH_HIGHLIGHT_CLASS = 'rounded-sm bg-yellow-200/80 px-0.5 text-foreground shadow-[inset_0_-0.45em_0_rgba(250,204,21,0.45)] dark:bg-yellow-300/35 dark:shadow-[inset_0_-0.45em_0_rgba(250,204,21,0.28)]'
type ChatSpeechStartedEvent = CustomEvent<{ messageId: string }>

type ParsedCodeFence = {
  language: string
  code: string
}

type ToolArtifact = {
  path?: string
  url?: string
  filename?: string
  size?: number
  content_type?: string
  contentType?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getSpeechPreferredLanguages(locale: string) {
  const languages = [locale]

  if (typeof navigator !== 'undefined') {
    languages.push(...navigator.languages)
    if (navigator.language) {
      languages.push(navigator.language)
    }
  }

  return Array.from(new Set(languages.filter(Boolean)))
}

function findSpeechVoice(voices: SpeechSynthesisVoice[], preferredLanguages: string[]) {
  const normalizedLanguages = preferredLanguages.map((language) => language.toLowerCase())

  return voices.find((voice) => normalizedLanguages.includes(voice.lang.toLowerCase()))
    ?? voices.find((voice) => normalizedLanguages.some((language) => voice.lang.toLowerCase().startsWith(`${language.split('-')[0]}-`)))
    ?? null
}

function getSpeechSynthesis() {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
    return null
  }

  return window.speechSynthesis
}

function getSpeechText(text: string) {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/[*_~]+/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

type SpeechSentence = {
  text: string
  start: number
  end: number
}

const SPEECH_ABBREVIATIONS = new Set([
  'mr',
  'mrs',
  'ms',
  'dr',
  'prof',
  'sr',
  'jr',
  'st',
  'vs',
  'etc',
  'e.g',
  'i.e',
  'u.s',
  'u.k',
])

function getTrimmedSentence(text: string, start: number, end: number): SpeechSentence | null {
  const raw = text.slice(start, end)
  const leading = raw.search(/\S/)
  if (leading < 0) {
    return null
  }

  const trimmed = raw.trimEnd()
  return {
    text: trimmed.slice(leading),
    start: start + leading,
    end: start + trimmed.length,
  }
}

function shouldSplitSpeechSentence(text: string, index: number) {
  const char = text[index]
  if (char === '\n' || /[。！？；]/.test(char)) {
    return true
  }

  if (!/[.!?;]/.test(char)) {
    return false
  }

  const previous = text[index - 1] ?? ''
  const next = text[index + 1] ?? ''
  if (char === '.' && /\d/.test(previous) && /\d/.test(next)) {
    return false
  }

  const token = text.slice(0, index).match(/([A-Za-z][A-Za-z.]*)$/)?.[1].toLowerCase()
  if (char === '.' && token && SPEECH_ABBREVIATIONS.has(token)) {
    return false
  }

  return !next || /[\s"'”’)]/.test(next)
}

function splitSpeechSentences(text: string): SpeechSentence[] {
  const sentences: SpeechSentence[] = []
  let sentenceStart = 0

  for (let index = 0; index < text.length; index += 1) {
    if (!shouldSplitSpeechSentence(text, index)) {
      continue
    }

    const sentence = getTrimmedSentence(text, sentenceStart, index + 1)
    if (sentence) {
      sentences.push(sentence)
    }
    sentenceStart = index + 1
  }

  const finalSentence = getTrimmedSentence(text, sentenceStart, text.length)
  if (finalSentence) {
    sentences.push(finalSentence)
  }

  return sentences.length > 0 ? sentences : [{ text, start: 0, end: text.length }]
}

function findSpeechSentence(sentences: SpeechSentence[], charIndex: number) {
  return sentences.find((sentence) => charIndex >= sentence.start && charIndex < sentence.end) ?? sentences.at(-1) ?? null
}

function getToolArtifacts(output: unknown): FilePart[] {
  if (!isRecord(output) || !Array.isArray(output.artifacts)) {
    return []
  }

  return output.artifacts
    .filter(isRecord)
    .map((artifact): FilePart | null => {
      const item = artifact as ToolArtifact
      const filename = item.filename || item.path?.split('/').pop() || item.path || 'artifact'
      if (!item.url) {
        return null
      }
      return {
        type: 'file',
        filename,
        url: item.url,
        size: typeof item.size === 'number' ? item.size : undefined,
        mimeType: item.content_type || item.contentType,
      }
    })
    .filter((file): file is FilePart => file !== null)
}


function parseCodeFence(content: string): ParsedCodeFence | null {
  const match = content.match(CODE_FENCE_REGEX)
  if (!match) {
    return null
  }

  const language = match[1].trim().split(/\s+/)[0]?.toLowerCase() ?? ''
  return {
    language,
    code: match[2].replace(/\r\n?/g, '\n'),
  }
}

function getPreviewKind(language: string, code: string): CodePreviewPayload['kind'] | null {
  if (language === 'mermaid') {
    return 'mermaid'
  }
  if (language === 'html' || language === 'htm' || language === 'xhtml') {
    return 'html'
  }
  if (language === 'svg' || (language === 'xml' && code.trimStart().toLowerCase().startsWith('<svg'))) {
    return 'svg'
  }
  if (language === 'css') {
    return 'css'
  }
  if (language === 'js' || language === 'javascript' || language === 'mjs') {
    return 'javascript'
  }
  if (language === 'md' || language === 'markdown') {
    return 'markdown'
  }

  return null
}

function PreviewableCodeBlock({
  content,
  index,
  shouldParseIncompleteMarkdown,
  parsedFence,
  previewKind,
  onOpenCodePreview,
  ...props
}: React.ComponentProps<typeof Block> & {
  parsedFence: ParsedCodeFence
  previewKind: CodePreviewPayload['kind'] | null
  onOpenCodePreview: (payload: CodePreviewPayload) => void
}) {
  const t = useTranslations('chat.message')
  const language = parsedFence.language || previewKind || 'text'
  const blockRef = React.useRef<HTMLDivElement>(null)
  const [toolbar, setToolbar] = React.useState<HTMLDivElement | null>(null)

  React.useLayoutEffect(() => {
    const block = blockRef.current
    if (!block) {
      setToolbar(null)
      return
    }

    const syncToolbar = () => {
      setToolbar(block.querySelector<HTMLDivElement>('[data-streamdown="code-block-header"] > div'))
    }

    syncToolbar()
    const observer = new MutationObserver(syncToolbar)
    observer.observe(block, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [content])

  const previewButton = (
    <button
      type="button"
      className="order-first inline-flex h-6 cursor-pointer items-center gap-1 rounded-md px-2 text-xs font-medium text-muted-foreground transition hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      onClick={() => onOpenCodePreview({
        id: `${language}:${parsedFence.code.length}:${parsedFence.code.slice(0, 32)}`,
        language,
        code: parsedFence.code,
        kind: previewKind ?? 'source',
      })}
    >
      <Eye className="h-3.5 w-3.5" />
      <span>{t('openCodePreview')}</span>
    </button>
  )

  return (
    <div ref={blockRef}>
      <Block
        content={content}
        index={index}
        shouldParseIncompleteMarkdown={shouldParseIncompleteMarkdown}
        {...props}
      />
      {toolbar ? ReactDOM.createPortal(previewButton, toolbar) : null}
    </div>
  )
}


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
  /** Callback when a previewable code block is opened */
  onOpenCodePreview?: (payload: CodePreviewPayload) => void
  /** Hide tool call cards and tool execution details */
  hideToolCalls?: boolean
  /** Controlled open state for chain of thought */
  chainOfThoughtOpen?: boolean
  /** Callback when chain of thought open state changes */
  onChainOfThoughtOpenChange?: (open: boolean) => void
  /** Called when this message starts speaking so the parent can scroll it into view */
  onRequestScrollIntoView?: () => void
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
      onOpenCodePreview,
      hideToolCalls = false,
      chainOfThoughtOpen,
      onChainOfThoughtOpenChange,
      onRequestScrollIntoView,
      className,
      ...props
    },
    ref
  ) => {
    const t = useTranslations('chat.message')
    const locale = useLocale()
    const tReasoning = useTranslations('chat.reasoning')
    const tTask = useTranslations('chat.task')
    const [copied, setCopied] = React.useState(false)
    const [isSpeechSupported, setIsSpeechSupported] = React.useState(false)
    const [speechVoices, setSpeechVoices] = React.useState<SpeechSynthesisVoice[]>([])
    const [isSpeakingThisMessage, setIsSpeakingThisMessage] = React.useState(false)
    const [activeSpeechSentence, setActiveSpeechSentence] = React.useState<string | null>(null)
    const speechUtteranceRef = React.useRef<SpeechSynthesisUtterance | null>(null)
    const speechSessionRef = React.useRef(0)
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
    const hasIterationCapMarker = otherParts.some(isIterationCapReachedPart)
    const iterationCapLabel = t('iterationCapReached').trim()

    // Get text content for copying (strip citation markers)
    const textContent = message.parts
      .filter((part): part is TextPart => (
        isTextPart(part)
        && !(hasIterationCapMarker && part.text.trim() === iterationCapLabel)
      ))
      .map((part) => part.text.replace(/\[\[cite:\d+\]\]/g, ''))
      .join('\n')
      .trim()

    // Handle copy
    const handleCopy = async () => {
      if (!textContent) return

      try {
        await navigator.clipboard.writeText(textContent)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch (err) {
        console.error('Failed to copy:', err)
      }
    }

    const resetSpeechState = React.useCallback(() => {
      speechUtteranceRef.current = null
      setIsSpeakingThisMessage(false)
      setActiveSpeechSentence(null)
    }, [])

    React.useEffect(() => {
      const speechSynthesis = getSpeechSynthesis()
      if (!speechSynthesis) {
        return
      }

      setIsSpeechSupported(true)
      const syncVoices = () => setSpeechVoices(speechSynthesis.getVoices())
      syncVoices()
      speechSynthesis.addEventListener('voiceschanged', syncVoices)

      return () => {
        speechSynthesis.removeEventListener('voiceschanged', syncVoices)
        if (speechUtteranceRef.current) {
          speechSynthesis.cancel()
          resetSpeechState()
        }
      }
    }, [resetSpeechState])

    React.useEffect(() => {
      const handleSpeechStarted = (event: Event) => {
        const speechEvent = event as ChatSpeechStartedEvent
        if (speechEvent.detail.messageId !== message.id) {
          resetSpeechState()
        }
      }

      window.addEventListener(SPEECH_STARTED_EVENT, handleSpeechStarted)
      return () => window.removeEventListener(SPEECH_STARTED_EVENT, handleSpeechStarted)
    }, [message.id, resetSpeechState])

    const handleToggleSpeech = React.useCallback(() => {
      const speechSynthesis = getSpeechSynthesis()
      const speechText = getSpeechText(textContent)
      if (!speechSynthesis || !speechText) {
        return
      }

      if (isSpeakingThisMessage) {
        speechSessionRef.current += 1
        speechSynthesis.cancel()
        resetSpeechState()
        return
      }

      speechSessionRef.current += 1
      const sessionId = speechSessionRef.current
      speechSynthesis.cancel()

      const utterance = new SpeechSynthesisUtterance(speechText)
      const sentences = splitSpeechSentences(speechText)
      const preferredLanguages = getSpeechPreferredLanguages(locale)
      const voice = findSpeechVoice(speechVoices, preferredLanguages)
      const fallbackLanguage = preferredLanguages[0] || 'en-US'

      utterance.lang = voice?.lang ?? fallbackLanguage
      if (voice) {
        utterance.voice = voice
      }
      utterance.rate = 1
      utterance.pitch = 1
      utterance.volume = 1
      utterance.onboundary = (event) => {
        if (speechSessionRef.current !== sessionId || event.charIndex < 0) {
          return
        }
        const sentence = findSpeechSentence(sentences, event.charIndex)
        setActiveSpeechSentence(sentence?.text ?? null)
      }
      utterance.onend = () => {
        if (speechSessionRef.current === sessionId) {
          resetSpeechState()
        }
      }
      utterance.onerror = () => {
        if (speechSessionRef.current === sessionId) {
          resetSpeechState()
        }
      }

      speechUtteranceRef.current = utterance
      setActiveSpeechSentence(sentences[0]?.text ?? null)
      setIsSpeakingThisMessage(true)
      window.dispatchEvent(new CustomEvent(SPEECH_STARTED_EVENT, { detail: { messageId: message.id } }))
      speechSynthesis.speak(utterance)
    }, [isSpeakingThisMessage, locale, message.id, resetSpeechState, speechVoices, textContent])

    React.useEffect(() => {
      if (isSpeakingThisMessage) {
        onRequestScrollIntoView?.()
      }
    }, [isSpeakingThisMessage, onRequestScrollIntoView])

    const renderToolResultContent = (output: unknown, isError?: boolean) => {
      const parsedOutput = parseToolResultOutput(output)

      if (isMediaImageToolResult(parsedOutput)) {
        if (parsedOutput.success === false) {
          return (
            <ToolOutput
              output={undefined}
              errorText={parsedOutput.error || (isError ? t('toolExecutionFailed') : undefined)}
            />
          )
        }

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
                        alt={parsedOutput.prompt || t('generatedImageAlt')}
                        className="h-auto w-full object-cover"
                      />
                    </button>
                  )
                })}
              </div>
            )}
            {parsedOutput.error && (
              <div className="text-sm text-red-500">{t('error')}: {parsedOutput.error}</div>
            )}
          </div>
        )
      }

      if (isMediaVideoToolResult(parsedOutput)) {
        if (parsedOutput.success === false) {
          return (
            <ToolOutput
              output={undefined}
              errorText={parsedOutput.error || (isError ? t('toolExecutionFailed') : undefined)}
            />
          )
        }

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
                  ? t('videoPreviewUnavailable')
                  : parsedOutput.status === 'processing' || parsedOutput.status === 'pending'
                    ? t('videoProcessing')
                    : t('videoUnavailable')}
                {typeof parsedOutput.progress === 'number' && (
                  <div className="mt-1">{t('progress', { value: Math.round(parsedOutput.progress * 100) })}</div>
                )}
              </div>
            )}
            {parsedOutput.error && (
              <div className="text-sm text-red-500">{t('error')}: {parsedOutput.error}</div>
            )}
          </div>
        )
      }

      const artifactFiles = getToolArtifacts(parsedOutput)
      if (artifactFiles.length > 0) {
        return (
          <div className="space-y-3">
            <FileListContent files={artifactFiles} />
            <ToolOutput
              output={parsedOutput}
              errorText={isError ? t('toolExecutionFailed') : undefined}
            />
          </div>
        )
      }

      return (
        <ToolOutput
          output={parsedOutput}
          errorText={isError ? t('toolExecutionFailed') : undefined}
        />
      )
    }

    // Render a single part
    const renderDefaultPart = (part: MessagePart, index: number) => {
      if (isTextPart(part)) {
        if (hasIterationCapMarker && part.text.trim() === iterationCapLabel) {
          return null
        }
        return (
          <TextWithCitations
            key={index}
            text={part.text}
            sources={documentSources}
            isStreaming={isStreaming && part.state !== 'done'}
            activeSpeechSentence={activeSpeechSentence}
            onOpenCodePreview={onOpenCodePreview}
          />
        )
      }

      // Tool calls: only skip if there's reasoning (they'll be in ChainOfThought)
      // If no reasoning, render them normally in message content
      if (isToolCallPart(part) || isMcpToolCallPart(part)) {
        if (hideToolCalls) {
          return null
        }
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
                (isToolResultPart(result) && shouldDisplayMediaResultInBody(result.output))
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

      if (isIterationCapReachedPart(part)) {
        return (
          <div
            key={index}
            className="flex items-start gap-2 mt-3 rounded-lg border border-orange-200 bg-orange-50 px-3 py-2.5 text-sm text-orange-800 dark:border-orange-800/50 dark:bg-orange-950/30 dark:text-orange-200"
          >
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{t('iterationCapReached')}</span>
          </div>
        )
      }

      // Manually stopped marker is rendered once at message level
      if (isStoppedPart(part)) {
        return null
      }

      return null
    }

    // Get task parts and reasoning parts for ChainOfThought
    const isManuallyStoppedMessage = Boolean(message.metadata?.isManuallyStopped) || otherParts.some(isStoppedPart)
    const streamErrorMessage = typeof message.metadata?.errorMessage === 'string'
      ? message.metadata.errorMessage
      : null
    const isErroredMessage = Boolean(isAssistant && message.metadata?.isError)
    const preservedErrorNote = streamErrorMessage ?? t('partialResponseError')
    const showPreservedErrorNote = Boolean(
      isErroredMessage && message.metadata?.preservedPartialProgress
    )
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
        case 'running': return t('toolRunning', { name })
        case 'done': return t('toolCompleted', { name })
        case 'error': return t('toolFailed', { name })
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
            if (hideToolCalls) return
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
                    {result && isToolResultPart(result) && !shouldDisplayMediaResultInBody(result.output) && (
                      renderToolResultContent(result.output, result.isError)
                    )}
                  </AIToolContent>
                </Tool>
              </ChainOfThoughtStep>
            )
          } else if (isMcpToolCallPart(part)) {
            if (hideToolCalls) return
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
                      renderToolResultContent(result.output, result.isError)
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
                icon={Brain}
                label={reasoningPart.state === 'streaming'
                  ? tReasoning('thinking')
                  : tReasoning('thoughtFor', { seconds: reasoningPart.duration ? Math.ceil(reasoningPart.duration / 1000) : 0 })
                }
                status={reasoningPart.state === 'streaming' ? 'active' : 'complete'}
              >
                {reasoningPart.text && (
                  <pre className="text-xs text-muted-foreground/70 whitespace-pre-wrap break-words font-sans">
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
    const contentParts = otherParts.filter((p) => (
      !isFilePart(p)
      && !isToolResultPart(p)
      && !isMcpToolResultPart(p)
      && !isTaskPart(p)
      && !isReasoningPart(p)
      && !(hideToolCalls && (isToolCallPart(p) || isMcpToolCallPart(p)))
    ))
    const visibleContentParts = (
      isErroredMessage
      && !showPreservedErrorNote
      && streamErrorMessage
    )
      ? contentParts.filter((part) => !(isTextPart(part) && part.text.trim() === streamErrorMessage.trim()))
      : contentParts

    // Check if this is a loading placeholder message (only show if no ChainOfThought)
    const isLoadingMessage = message.metadata?.isLoading && visibleContentParts.length === 0 && !hasChainOfThought
    const isStandaloneErrorMessage = Boolean(
      isErroredMessage
      && !showPreservedErrorNote
      && visibleContentParts.length === 0
      && !hasChainOfThought
      && !isLoadingMessage
    )

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
                <ChainOfThought
                  isStreaming={isChainOfThoughtStreaming}
                  open={chainOfThoughtOpen ?? false}
                  onOpenChange={onChainOfThoughtOpenChange}
                  defaultOpen={false}
                >
                  <ChainOfThoughtHeader title={tReasoning('thought')} />
                  <ChainOfThoughtContent containScroll className="max-h-80 overflow-y-auto pr-2 [scrollbar-gutter:stable]">
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
                visibleContentParts.map((part, index) =>
                  renderPart ? renderPart(part, index) : renderDefaultPart(part, index)
                )
              )}
              {isErroredMessage && (
                <div className={cn('flex items-start gap-1.5 text-xs text-destructive', !isStandaloneErrorMessage && 'mt-3')}>
                  <AlertTriangle className={cn('h-3.5 w-3.5 shrink-0', !isStandaloneErrorMessage && 'mt-0.5')} />
                  <span>{showPreservedErrorNote ? preservedErrorNote : (streamErrorMessage ?? t('error'))}</span>
                </div>
              )}
              {isAssistant && isManuallyStoppedMessage && (
                <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Square className="h-3 w-3 shrink-0 fill-current" />
                  <span>{t('manuallyStopped')}</span>
                </div>
              )}
            </MessageContent>

            {/* Sources (grouped at bottom) */}
            {isAssistant && allSources.length > 0 && (
              <SourceContent sources={allSources} />
            )}

            {/* Actions for assistant messages */}
            {isAssistant && !isStreaming && textContent && (
           <MessageActions className={cn("transition-opacity", isSpeakingThisMessage ? "opacity-100" : "opacity-0 group-hover:opacity-100")}>
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
                <MessageAction
                  tooltip={isSpeechSupported ? (isSpeakingThisMessage ? t('stopListening') : t('listen')) : t('speechUnavailable')}
                  onClick={handleToggleSpeech}
                  disabled={!isSpeechSupported}
                >
                  {isSpeakingThisMessage ? <Square className="h-4 w-4 fill-current" /> : <Volume2 className="h-4 w-4" />}
                </MessageAction>
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
function PreviewableMarkdownBlock({
  content,
  index,
  shouldParseIncompleteMarkdown,
  isStreaming,
  onOpenCodePreview,
  ...props
}: React.ComponentProps<typeof Block> & {
  isStreaming: boolean
  onOpenCodePreview?: (payload: CodePreviewPayload) => void
}) {
  const parsedFence = !isStreaming && onOpenCodePreview ? parseCodeFence(content) : null
  const previewKind = parsedFence ? getPreviewKind(parsedFence.language, parsedFence.code) : null

  if (parsedFence && onOpenCodePreview) {
    return (
      <PreviewableCodeBlock
        content={content}
        index={index}
        shouldParseIncompleteMarkdown={shouldParseIncompleteMarkdown}
        parsedFence={parsedFence}
        previewKind={previewKind}
        onOpenCodePreview={onOpenCodePreview}
        {...props}
      />
    )
  }

  return (
    <Block
      content={content}
      index={index}
      shouldParseIncompleteMarkdown={shouldParseIncompleteMarkdown}
      {...props}
    />
  )
}

function getAuthenticatedApiAssetUrl(src: string): string | null {
  return src.startsWith('/api/v1/') ? src : null
}

function isBlockedImageSrc(src: string): boolean {
  const normalized = src.trim().toLowerCase()
  return normalized.startsWith('javascript:') || normalized.startsWith('data:')
}

type AuthenticatedMarkdownImageCacheEntry = {
  objectUrl?: string
  promise?: Promise<string>
}

const MAX_AUTHENTICATED_MARKDOWN_IMAGE_CACHE_SIZE = 100
const authenticatedMarkdownImageCache = new Map<string, AuthenticatedMarkdownImageCacheEntry>()

function setAuthenticatedMarkdownImageCache(src: string, entry: AuthenticatedMarkdownImageCacheEntry) {
  if (entry.objectUrl && authenticatedMarkdownImageCache.size >= MAX_AUTHENTICATED_MARKDOWN_IMAGE_CACHE_SIZE) {
    const oldestKey = authenticatedMarkdownImageCache.keys().next().value
    if (oldestKey !== undefined) {
      const oldestEntry = authenticatedMarkdownImageCache.get(oldestKey)
      if (oldestEntry?.objectUrl) URL.revokeObjectURL(oldestEntry.objectUrl)
      authenticatedMarkdownImageCache.delete(oldestKey)
    }
  }

  authenticatedMarkdownImageCache.set(src, entry)
}

type AuthenticatedMarkdownImageProps = Omit<React.ComponentProps<'img'>, 'src' | 'alt'> & {
  src?: string
  alt?: string
}

function getCachedAuthenticatedImageUrl(src: string): string | null {
  return authenticatedMarkdownImageCache.get(src)?.objectUrl ?? null
}

function getInitialMarkdownImageUrl(src: string): string | null {
  if (!src || isBlockedImageSrc(src)) {
    return null
  }

  const authenticatedUrl = getAuthenticatedApiAssetUrl(src)
  return authenticatedUrl ? getCachedAuthenticatedImageUrl(authenticatedUrl) : src
}

function loadAuthenticatedMarkdownImage(src: string): Promise<string> {
  const cached = authenticatedMarkdownImageCache.get(src)
  if (cached?.objectUrl) {
    return Promise.resolve(cached.objectUrl)
  }
  if (cached?.promise) {
    return cached.promise
  }

  const token = localStorage.getItem('access_token')
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined
  const promise = fetch(src, { headers })
    .then((response) => {
      if (!response.ok) throw new Error('image_load_failed')
      return response.blob()
    })
    .then((blob) => {
      const objectUrl = URL.createObjectURL(blob)
      setAuthenticatedMarkdownImageCache(src, { objectUrl })
      return objectUrl
    })
    .catch((error) => {
      authenticatedMarkdownImageCache.delete(src)
      throw error
    })

  setAuthenticatedMarkdownImageCache(src, { promise })
  return promise
}

function AuthenticatedMarkdownImage({ src = '', alt = '', ...props }: AuthenticatedMarkdownImageProps) {
  const [prevSrc, setPrevSrc] = React.useState(src)
  const [objectUrl, setObjectUrl] = React.useState<string | null>(() => getInitialMarkdownImageUrl(src))
  const [failed, setFailed] = React.useState(() => Boolean(src && isBlockedImageSrc(src)))

  if (src !== prevSrc) {
    setPrevSrc(src)
    setObjectUrl(getInitialMarkdownImageUrl(src))
    setFailed(Boolean(src && isBlockedImageSrc(src)))
  }

  React.useEffect(() => {
    let cancelled = false

    setFailed(false)
    if (!src) {
      setObjectUrl(null)
      return () => {
        cancelled = true
      }
    }
    if (isBlockedImageSrc(src)) {
      setObjectUrl(null)
      setFailed(true)
      return () => {
        cancelled = true
      }
    }
    const authenticatedUrl = getAuthenticatedApiAssetUrl(src)
    if (!authenticatedUrl) {
      setObjectUrl(src)
      return () => {
        cancelled = true
      }
    }

    const cachedObjectUrl = getCachedAuthenticatedImageUrl(authenticatedUrl)
    if (cachedObjectUrl) {
      setObjectUrl(cachedObjectUrl)
      return () => {
        cancelled = true
      }
    }

    setObjectUrl(null)
    loadAuthenticatedMarkdownImage(authenticatedUrl)
      .then((url) => {
        if (!cancelled) setObjectUrl(url)
      })
      .catch((error) => {
        if (!cancelled && (error as Error).name !== 'AbortError') setFailed(true)
      })

    return () => {
      cancelled = true
    }
  }, [src])

  if (failed || !objectUrl) {
    return <span className="text-muted-foreground">{alt || src}</span>
  }

  return <img {...props} src={objectUrl} alt={alt} loading="lazy" />
}

function isSameOriginChatLink(url: string) {
  if (typeof window === 'undefined') {
    return false
  }

  try {
    const resolvedUrl = new URL(url, window.location.href)
    return (
      (resolvedUrl.protocol === 'http:' || resolvedUrl.protocol === 'https:')
      && resolvedUrl.origin === window.location.origin
    )
  } catch {
    return false
  }
}

function LinkSafetyModal({
  url,
  isOpen,
  onClose,
  onConfirm,
}: LinkSafetyModalProps) {
  const t = useTranslations('chat.message')

  if (!isOpen || typeof document === 'undefined') {
    return null
  }

  return ReactDOM.createPortal(
    <Dialog open={isOpen} onOpenChange={(open) => {
      if (!open) {
        onClose()
      }
    }}>
      <DialogContent showCloseButton={false} className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('linkSafetyTitle')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>{t('linkSafetyDescription')}</p>
          <div className="break-all rounded-md bg-muted/50 px-3 py-2 font-mono text-xs text-foreground">
            {url}
          </div>
        </div>
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            className="inline-flex h-9 items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
            onClick={onClose}
          >
            {t('linkSafetyCancel')}
          </button>
          <button
            type="button"
            className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            onClick={() => {
              onConfirm()
              onClose()
            }}
          >
            {t('linkSafetyContinue')}
          </button>
        </div>
      </DialogContent>
    </Dialog>,
    document.body
  )
}

function TextWithCitations({
  text,
  sources,
  isStreaming = false,
  activeSpeechSentence,
  onOpenCodePreview,
}: {
  text: string
  sources: SourceDocumentPart[]
  isStreaming?: boolean
  activeSpeechSentence?: string | null
  onOpenCodePreview?: (payload: CodePreviewPayload) => void
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

  const clearSpeechHighlight = React.useCallback(() => {
    const highlightedElements = containerRef.current?.querySelectorAll('mark[data-speech-highlight="true"]')
    if (!highlightedElements) {
      return
    }

    highlightedElements.forEach((highlighted) => {
      const parent = highlighted.parentNode
      highlighted.replaceWith(document.createTextNode(highlighted.textContent ?? ''))
      parent?.normalize()
    })
  }, [])

  const applySpeechHighlight = React.useCallback(() => {
    clearSpeechHighlight()
    if (!containerRef.current || !activeSpeechSentence) {
      return
    }

    const textNodes: Text[] = []
    const walker = document.createTreeWalker(
      containerRef.current,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: (node) => {
          const parent = node.parentElement
          if (!parent || parent.closest('[data-streamdown="code-block"], .cite-portal, [data-speech-highlight="true"]')) {
            return NodeFilter.FILTER_REJECT
          }
          return node.textContent ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP
        },
      }
    )

    let node: Text | null
    while ((node = walker.nextNode() as Text | null)) {
      textNodes.push(node)
    }

    const renderedText = textNodes.map((textNode) => textNode.textContent ?? '').join('')
    const start = renderedText.indexOf(activeSpeechSentence)
    if (start < 0) {
      return
    }
    const end = start + activeSpeechSentence.length
    let cursor = 0

    textNodes.forEach((textNode) => {
      const content = textNode.textContent ?? ''
      const nodeStart = cursor
      const nodeEnd = cursor + content.length
      cursor = nodeEnd

      const highlightStart = Math.max(start, nodeStart)
      const highlightEnd = Math.min(end, nodeEnd)
      if (highlightStart >= highlightEnd || !textNode.parentNode) {
        return
      }

      const localStart = highlightStart - nodeStart
      const localEnd = highlightEnd - nodeStart
      const fragment = document.createDocumentFragment()
      const before = content.slice(0, localStart)
      const highlightedText = content.slice(localStart, localEnd)
      const after = content.slice(localEnd)
      const mark = document.createElement('mark')
      mark.dataset.speechHighlight = 'true'
      mark.className = SPEECH_HIGHLIGHT_CLASS
      mark.textContent = highlightedText

      if (before) {
        fragment.appendChild(document.createTextNode(before))
      }
      fragment.appendChild(mark)
      if (after) {
        fragment.appendChild(document.createTextNode(after))
      }
      textNode.parentNode.replaceChild(fragment, textNode)
    })
  }, [activeSpeechSentence, clearSpeechHighlight])

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

  const rehypePlugins = isStreaming ? STREAMING_REHYPE_PLUGINS : undefined

  const components = React.useMemo(() => ({
    img: ({ src, alt, ...props }: React.ComponentProps<'img'>) => (
      <AuthenticatedMarkdownImage src={typeof src === 'string' ? src : undefined} alt={alt || ''} {...props} />
    ),
    p: ({ children, node, ...props }: React.ComponentProps<'p'> & {
      node?: {
        children?: Array<{ tagName?: string; type?: string }>
      }
    }) => {
      const hasImgInNode = node?.children?.some(
        (child) => child.tagName === 'img' || child.type === 'element' && child.tagName === 'img'
      )
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
  }), [])

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

  React.useEffect(() => {
    const timeoutId = setTimeout(applySpeechHighlight, 0)
    return () => {
      clearTimeout(timeoutId)
      clearSpeechHighlight()
    }
  }, [activeSpeechSentence, applySpeechHighlight, clearSpeechHighlight, processedText])

  React.useEffect(() => {
    if (!isStreaming || !containerRef.current) {
      return
    }

    const scrollCodeBlocksToBottom = () => {
      containerRef.current?.querySelectorAll<HTMLElement>('[data-streamdown="code-block-body"]').forEach((block) => {
        block.scrollTop = block.scrollHeight
      })
    }

    scrollCodeBlocksToBottom()
    const observer = new MutationObserver(scrollCodeBlocksToBottom)
    observer.observe(containerRef.current, {
      childList: true,
      subtree: true,
      characterData: true,
    })

    return () => observer.disconnect()
  }, [isStreaming, processedText])

  return (
    <div
      ref={containerRef}
      data-chat-streaming={isStreaming ? 'true' : 'false'}
      className="w-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
    >
      <Streamdown
        isAnimating={isStreaming}
        components={components}
        rehypePlugins={rehypePlugins}
        plugins={isStreaming ? undefined : chatStreamdownPlugins}
        linkSafety={{
          enabled: true,
          onLinkCheck: (url) => isSameOriginChatLink(url),
          renderModal: (props) => <LinkSafetyModal {...props} />,
        }}
        BlockComponent={(props) => (
          <PreviewableMarkdownBlock
            {...props}
            isStreaming={isStreaming}
            onOpenCodePreview={onOpenCodePreview}
          />
        )}
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
