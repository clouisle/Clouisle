'use client'

import * as React from 'react'
import * as ReactDOM from 'react-dom'
import { useLocale, useTranslations } from 'next-intl'
import { Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Loader2, SearchIcon, SparklesIcon, ChevronLeft, ChevronRight, AlertTriangle, Timer, Brain, Square, Eye, Volume2, Pencil } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Block,
  Streamdown,
  defaultRehypePlugins,
} from 'streamdown'
import type { CodeHighlighterPlugin, PluginConfig, LinkSafetyModalProps } from 'streamdown'
import { bundledLanguages, codeToTokens } from 'shiki'
import type { BundledLanguage, BundledTheme } from 'shiki'
import { createMathPlugin } from '@streamdown/math'
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
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
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
import type { ChatMessage, ChatPreviewPayload, CodePreviewPayload, MessagePart, SourceDocumentPart, SourceUrlPart, FilePart, ImagePart, TaskPart, UserInputRequestPart, MediaResultPart } from './types'
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
import { SourceContent } from './message-parts'
import { UserInputRequestCard } from './user-input-request-card'
import {
  getImageAssetUrl,
  getVideoAssetUrl,
  isMediaImageToolResult,
  isMediaVideoToolResult,
  parseToolResultOutput,
  shouldDisplayMediaResultInBody,
} from '@/lib/utils/tool-result'

const CODE_FENCE_REGEX = /^ {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n([\s\S]*?)(?:\r?\n)?(`{3,}|~{3,})[ \t\r\n]*$/
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
const chatMathPlugin = createMathPlugin({ singleDollarTextMath: true })
const chatStreamdownPlugins: PluginConfig = {
  code: chatCodeHighlighter,
  math: chatMathPlugin,
}
const SPEECH_STARTED_EVENT = 'clouisle:chat-speech-started'
const SPEECH_HIGHLIGHT_CLASS = 'rounded-sm bg-yellow-200/80 px-0.5 text-foreground shadow-[inset_0_-0.45em_0_rgba(250,204,21,0.45)] dark:bg-yellow-300/35 dark:shadow-[inset_0_-0.45em_0_rgba(250,204,21,0.28)]'
type ChatSpeechStartedEvent = CustomEvent<{ messageId: string }>

type ParsedCodeFence = {
  language: string
  code: string
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

const SPEECH_EMOJI_REGEX = /(?:\p{Extended_Pictographic}|\p{Regional_Indicator}|[☀-➿])[️︎]?(?:‍(?:\p{Extended_Pictographic}|\p{Regional_Indicator}|[☀-➿])[️︎]?)*|[\u{1F3FB}-\u{1F3FF}]/gu

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
    .replace(SPEECH_EMOJI_REGEX, '')
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



function parseCodeFence(content: string): ParsedCodeFence | null {
  const match = content.match(CODE_FENCE_REGEX)
  if (!match) {
    return null
  }

  const [, openingFence, info, code, closingFence] = match
  if (
    openingFence.charAt(0) !== closingFence.charAt(0)
    || closingFence.length < openingFence.length
  ) {
    return null
  }

  const language = info.trim().split(/\s+/)[0]?.toLowerCase() ?? ''
  return {
    language,
    code: code.replace(/\r\n?/g, '\n'),
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
  const [header, setHeader] = React.useState<HTMLDivElement | null>(null)
  const [toolbar, setToolbar] = React.useState<HTMLDivElement | null>(null)
  React.useLayoutEffect(() => {
    const block = blockRef.current
    if (!block) {
      setHeader(null)
      setToolbar(null)
      return
    }

    const syncToolbar = () => {
      setHeader(block.querySelector<HTMLDivElement>('[data-streamdown="code-block-header"]'))
      setToolbar(block.querySelector<HTMLDivElement>('[data-streamdown="code-block-actions"]'))
    }

    syncToolbar()
    const observer = new MutationObserver(syncToolbar)
    observer.observe(block, { childList: true, subtree: true })
    return () => observer.disconnect()
  }, [content])

  const previewButton = (
    <button
      type="button"
      className="order-first inline-flex h-6 cursor-pointer items-center gap-1 rounded-md px-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
      {toolbar
        ? ReactDOM.createPortal(previewButton, toolbar)
        : header
          ? ReactDOM.createPortal(
            <div className="ml-auto flex shrink-0 items-center" data-chat-code-preview-fallback>
              {previewButton}
            </div>,
            header,
          )
          : null}
    </div>
  )
}


export interface MessageProps extends React.HTMLAttributes<HTMLDivElement> {
  message: ChatMessage
  /** Whether the message is currently streaming */
  isStreaming?: boolean
  /** Optional label for an assistant loading placeholder. */
  loadingLabel?: string
  /** Custom part renderer */
  renderPart?: (part: MessagePart, index: number) => React.ReactNode
  /** Content rendered between the message body and action controls */
  afterContent?: React.ReactNode
  showCopy?: boolean
  /** Whether to show feedback buttons */
  showFeedback?: boolean
  /** Callback for regenerate */
  onRegenerate?: () => void
  /** Callback for editing user messages */
  onEditMessage?: (content: string) => Promise<void>
  /** Callback for feedback */
  onFeedback?: (type: 'positive' | 'negative') => void
  /** Callback for switching version */
  onSwitchVersion?: (versionIndex: number) => void
  /** Callback when user selects an option from user input request */
  onSelectOption?: (option: string) => void
  /** Callback when a generated image is selected as a later reference */
  onSelectImageReference?: (image: { asset_ref: string; url: string }) => void
  /** Callback when a previewable code block is opened */
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void
  /** Hide tool call cards and tool execution details */
  hideToolCalls?: boolean
  /** Hide token usage/speed stats popover */
  hideMessageActions?: boolean
  /** Hide reasoning / chain-of-thought panel */
  hideReasoning?: boolean
  /** Current conversation ID (shown on errors for debugging) */
  conversationId?: string | null
  /** Controlled open state for chain of thought */
  chainOfThoughtOpen?: boolean
  /** Callback when chain of thought open state changes */
  onChainOfThoughtOpenChange?: (open: boolean) => void
  /** Called when this message starts speaking so the parent can scroll it into view */
  onRequestScrollIntoView?: () => void
}

const MessageComponent = React.forwardRef<HTMLDivElement, MessageProps>(
  function MessageComponent(
    {
      message,
      isStreaming = false,
      loadingLabel,
      renderPart,
      afterContent,
      showCopy = true,
      showFeedback = false,
      onRegenerate,
      onEditMessage,
      onFeedback,
      onSwitchVersion,
      onSelectOption,
      onSelectImageReference,
      onOpenCodePreview,
      hideToolCalls = false,
      hideMessageActions = false,
      hideReasoning = false,
      conversationId,
      chainOfThoughtOpen,
      onChainOfThoughtOpenChange,
      onRequestScrollIntoView,
      className,
      ...props
    },
    ref
  ) {
    const t = useTranslations('chat.message')
    const locale = useLocale()
    const tReasoning = useTranslations('chat.reasoning')
    const tTask = useTranslations('chat.task')
    const [copied, setCopied] = React.useState(false)
    const [isSpeechSupported, setIsSpeechSupported] = React.useState(false)
    const [speechVoices, setSpeechVoices] = React.useState<SpeechSynthesisVoice[]>([])
    const [isSpeakingThisMessage, setIsSpeakingThisMessage] = React.useState(false)
    const [activeSpeechSentence, setActiveSpeechSentence] = React.useState<string | null>(null)
    const [isEditing, setIsEditing] = React.useState(false)
    const [editDraft, setEditDraft] = React.useState('')
    const [isSavingEdit, setIsSavingEdit] = React.useState(false)
    const speechUtteranceRef = React.useRef<SpeechSynthesisUtterance | null>(null)
    const speechSessionRef = React.useRef(0)
    const isUser = message.role === 'user'
    const isAssistant = message.role === 'assistant'
    const runInputState = typeof message.metadata?.runInputState === 'string'
      ? message.metadata.runInputState
      : null
    const runInputKind = message.metadata?.runInputKind === 'follow_up' ? 'follow_up' : 'steer'
    const runInputLabel = runInputState === 'queued'
      ? t(runInputKind === 'follow_up' ? 'queuedFollowUp' : 'queuedSteering')
      : runInputState === 'committed'
        ? t(runInputKind === 'follow_up' ? 'committedFollowUp' : 'committedSteering')
        : null
    
    // Image lightbox state
    const { isOpen: lightboxOpen, imageSrc, imageAlt, openLightbox, closeLightbox } = useLightbox()

    // Token usage and timing stats from message_end
    const usage = message.metadata?.usage as { prompt_tokens: number; completion_tokens: number; total_tokens: number; cache_read_tokens?: number; cache_creation_tokens?: number } | undefined
    const timing = message.metadata?.timing as { first_token_ms: number | null; duration_ms: number; tokens_per_second: number | null } | undefined

    // Keep non-source parts in the exact backend/stream order. Timeline
    // renderers use the original message index for stable keys and callbacks.
    const {
      allSources,
      documentSources,
      otherParts,
      otherPartEntries,
      hasIterationCapMarker,
    } = React.useMemo(() => {
      const nextAllSources: (SourceUrlPart | SourceDocumentPart)[] = []
      const nextDocumentSources: SourceDocumentPart[] = []
      const nextOtherPartEntries: Array<{ part: MessagePart; index: number }> = []
      let nextHasIterationCapMarker = false

      for (const [index, part] of message.parts.entries()) {
        if (isSourcePart(part)) {
          nextAllSources.push(part as SourceUrlPart | SourceDocumentPart)
          if (isSourceDocumentPart(part)) {
            nextDocumentSources.push(part)
          }
          continue
        }

        nextOtherPartEntries.push({ part, index })
        if (isIterationCapReachedPart(part)) {
          nextHasIterationCapMarker = true
        }
      }

      return {
        allSources: nextAllSources,
        documentSources: nextDocumentSources,
        otherParts: nextOtherPartEntries.map(({ part }) => part),
        otherPartEntries: nextOtherPartEntries,
        hasIterationCapMarker: nextHasIterationCapMarker,
      }
    }, [message.parts])
    const iterationCapLabel = t('iterationCapReached').trim()

    // Get text content for copying (strip citation markers)
    const textContent = React.useMemo(() => {
      const parts: string[] = []
      for (const part of message.parts) {
        if (
          isTextPart(part)
          && !(hasIterationCapMarker && part.text.trim() === iterationCapLabel)
        ) {
          parts.push(part.text.replace(/\[\[cite:\d+\]\]/g, ''))
        }
      }
      return parts.join('\n').trim()
    }, [hasIterationCapMarker, iterationCapLabel, message.parts])

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

    const startEdit = React.useCallback(() => {
      setEditDraft(textContent)
      setIsEditing(true)
    }, [textContent])

    const cancelEdit = React.useCallback(() => {
      setIsEditing(false)
      setEditDraft('')
    }, [])

    const saveEdit = React.useCallback(async () => {
      const nextContent = editDraft.trim()
      if (!onEditMessage || !nextContent || nextContent === textContent) return
      setIsSavingEdit(true)
      try {
        await onEditMessage(nextContent)
        setIsEditing(false)
        setEditDraft('')
      } finally {
        setIsSavingEdit(false)
      }
    }, [editDraft, onEditMessage, textContent])

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


    const renderToolResultContent = React.useCallback((output: unknown, isError?: boolean) => {
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
                    <div
                      key={`${imageIndex}-${imageUrl}`}
                      className="relative overflow-hidden rounded-lg border bg-background"
                    >
                      <button
                        type="button"
                        className="block w-full text-left transition-opacity hover:opacity-90"
                        aria-label={`${t('openCodePreview')}: ${parsedOutput.prompt || t('generatedImageAlt')}`}
                        onClick={() => openLightbox(imageUrl, parsedOutput.prompt)}
                      >
                        <img
                          src={imageUrl}
                          alt={parsedOutput.prompt || t('generatedImageAlt')}
                          className="h-auto w-full object-cover"
                        />
                        <span aria-hidden="true" className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-md bg-background/90 text-foreground shadow-sm">
                          <Eye className="h-4 w-4" />
                        </span>
                      </button>
                      {item.image.asset_ref && onSelectImageReference && (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="absolute bottom-2 left-2"
                          onClick={() => onSelectImageReference({
                            asset_ref: item.image.asset_ref as string,
                            url: imageUrl,
                          })}
                        >
                          {t('useAsReference')}
                        </Button>
                      )}
                    </div>
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


      return (
        <ToolOutput
          output={parsedOutput}
          errorText={isError ? t('toolExecutionFailed') : undefined}
        />
      )
    }, [onSelectImageReference, openLightbox, t])

    // Render a single part
    const { toolResultsByCallIndex, pairedToolResultIndexes } = React.useMemo(() => {
      const resultsByCallIndex = new Map<number, MessagePart>()
      const pairedResultIndexes = new Set<number>()

      for (let callOffset = 0; callOffset < otherPartEntries.length; callOffset += 1) {
        const callEntry = otherPartEntries[callOffset]
        if (!isToolCallPart(callEntry.part) && !isMcpToolCallPart(callEntry.part)) continue

        for (let resultOffset = callOffset + 1; resultOffset < otherPartEntries.length; resultOffset += 1) {
          const resultEntry = otherPartEntries[resultOffset]
          const resultPart = resultEntry.part
          const isDuplicateCall = isToolCallPart(callEntry.part)
            ? isToolCallPart(resultPart) && resultPart.toolCallId === callEntry.part.toolCallId
            : isMcpToolCallPart(resultPart) && resultPart.toolCallId === callEntry.part.toolCallId
          if (isDuplicateCall) {
            break
          }
          const isMatchingResult = isToolCallPart(callEntry.part)
            ? isToolResultPart(resultPart) && resultPart.toolCallId === callEntry.part.toolCallId
            : isMcpToolResultPart(resultPart) && resultPart.toolCallId === callEntry.part.toolCallId
          if (isMatchingResult && !pairedResultIndexes.has(resultEntry.index)) {
            resultsByCallIndex.set(callEntry.index, resultPart)
            pairedResultIndexes.add(resultEntry.index)
            break
          }
        }
      }

      return {
        toolResultsByCallIndex: resultsByCallIndex,
        pairedToolResultIndexes: pairedResultIndexes,
      }
    }, [otherPartEntries])

    const renderDefaultPart = React.useCallback((part: MessagePart, index: number) => {
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
            onOpenImage={openLightbox}
          />
        )
      }

      if (isToolCallPart(part) || isMcpToolCallPart(part)) {
        if (hideToolCalls) return null
        const toolName = isToolCallPart(part)
          ? (part.toolDisplayName || part.toolName)
          : `${part.serverName}/${part.toolName}`
        const result = toolResultsByCallIndex.get(index)
        const state = part.state === 'error' ? 'output-error'
          : part.state === 'done' ? 'output-available'
            : part.state === 'running' ? 'input-available'
              : 'input-streaming'

        return (
          <Tool
            key={index}
            defaultOpen={false}
            className="mb-2 rounded-md border bg-muted/30"
            data-chat-timeline-index={index}
            data-chat-tool-node="true"
            data-tool-call-id={part.toolCallId}
          >
            <ToolHeader title={toolName} type="tool-call" state={state} />
            <AIToolContent>
              <ToolInput input={part.input} />
              {result && (isToolResultPart(result) || isMcpToolResultPart(result)) && (
                (isToolResultPart(result) && shouldDisplayMediaResultInBody(result.output))
                  ? null
                  : renderToolResultContent(result.output, result.isError)
              )}
            </AIToolContent>
          </Tool>
        )
      }

      if (isToolResultPart(part) || isMcpToolResultPart(part)) {
        if (hideToolCalls || pairedToolResultIndexes.has(index)) return null
        const toolName = isToolResultPart(part)
          ? (part.toolDisplayName || part.toolName)
          : `${part.serverName}/${part.toolName}`
        const state = part.isError ? 'output-error' : 'output-available'
        return (
          <Tool
            key={index}
            defaultOpen={false}
            className="mb-2 rounded-md border bg-muted/30"
            data-chat-timeline-index={index}
            data-chat-tool-node="true"
            data-tool-call-id={part.toolCallId}
          >
            <ToolHeader title={toolName} type="tool-call" state={state} />
            <AIToolContent>
              {renderToolResultContent(part.output, part.isError)}
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
          <button
            key={index}
            type="button"
            className="relative block max-w-xs overflow-hidden rounded-lg text-left transition-opacity hover:opacity-90"
            aria-label={`${t('openCodePreview')}: ${imagePart.alt || t('generatedImageAlt')}`}
            onClick={() => openLightbox(imagePart.url, imagePart.alt)}
          >
            <img
              src={imagePart.url}
              alt={imagePart.alt || 'Uploaded image'}
              className="h-auto w-full object-cover"
            />
            <span aria-hidden="true" className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-md bg-background/90 text-foreground shadow-sm">
              <Eye className="h-4 w-4" />
            </span>
          </button>
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

      if (isStoppedPart(part) || isTaskPart(part) || isReasoningPart(part)) {
        return null
      }

      return null
    }, [
      activeSpeechSentence,
      documentSources,
      hasIterationCapMarker,
      hideToolCalls,
      isStreaming,
      iterationCapLabel,
      onOpenCodePreview,
      onSelectOption,
      openLightbox,
      pairedToolResultIndexes,
      renderToolResultContent,
      t,
      toolResultsByCallIndex,
    ])
    const isManuallyStoppedMessage = Boolean(message.metadata?.isManuallyStopped) || otherParts.some(isStoppedPart)
    const streamErrorMessage = typeof message.metadata?.errorMessage === 'string'
      ? message.metadata.errorMessage
      : null
    const isErroredMessage = Boolean(isAssistant && message.metadata?.isError)
    const preservedErrorNote = streamErrorMessage ?? t('partialResponseError')
    const showPreservedErrorNote = Boolean(
      isErroredMessage && message.metadata?.preservedPartialProgress
    )
    const textParts = React.useMemo(() => otherParts.filter(isTextPart), [otherParts])
    const fileParts = React.useMemo(() => otherParts.filter(isFilePart), [otherParts])
    const visibleContentEntries = React.useMemo(() => {
      return otherPartEntries.filter(({ part }) => {
        if (isFilePart(part)) return false
        if (isErroredMessage && !showPreservedErrorNote && streamErrorMessage && isTextPart(part)) {
          return part.text.trim() !== streamErrorMessage.trim()
        }
        return true
      })
    }, [isErroredMessage, otherPartEntries, showPreservedErrorNote, streamErrorMessage])
    const hasVisibleTimelineContent = visibleContentEntries.some(({ part }) => {
      if (isStoppedPart(part)) return false
      if (isReasoningPart(part)) return !hideReasoning
      if (isTaskPart(part)) return !hideReasoning && part.taskType !== 'thinking'
      if (isToolCallPart(part) || isMcpToolCallPart(part)) return !hideToolCalls
      if (isToolResultPart(part) || isMcpToolResultPart(part)) return !hideToolCalls
      if (isTextPart(part)) return Boolean(part.text.trim())
      return true
    })
    const hasTextContent = textParts.some(part => part.text.length > 0)
    const hasMessageContent = hasTextContent
      || otherParts.some(part => (
        isReasoningPart(part)
        || isTaskPart(part)
        || isToolCallPart(part)
        || isMcpToolCallPart(part)
        || isToolResultPart(part)
        || isMcpToolResultPart(part)
      ))
      || isErroredMessage
    const isLoadingMessage = Boolean(message.metadata?.isLoading && !hasVisibleTimelineContent)
    const isStandaloneErrorMessage = Boolean(
      isErroredMessage
      && !showPreservedErrorNote
      && !hasVisibleTimelineContent
      && !isLoadingMessage
    )

    // Convert task state to step status
    const getStepStatus = React.useCallback((state: TaskPart['state']) => {
      switch (state) {
        case 'running': return 'active' as const
        case 'completed': return 'complete' as const
        case 'error': return 'error' as const
        default: return 'pending' as const
      }
    }, [])

    // Render task title based on type and state
    const getTaskTitle = React.useCallback((taskPart: TaskPart) => {
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
        const summarySourceTokens = typeof info?.summary_source_tokens === 'number' && info.summary_source_tokens > 0
          ? info.summary_source_tokens
          : null
        const summaryResultTokens = typeof info?.summary_result_tokens === 'number' && info.summary_result_tokens > 0
          ? info.summary_result_tokens
          : null
        const summarySavedTokens = typeof info?.summary_saved_tokens === 'number'
          ? info.summary_saved_tokens
          : null
        const summaryTurns = typeof info?.summary_turns === 'number' ? info.summary_turns : null
        const trigger = typeof info?.trigger === 'string' ? info.trigger : null
        const pressureLevel = typeof info?.pressure_level === 'string' ? info.pressure_level : null
        const compactedBlocks = typeof info?.compacted_blocks === 'number' ? info.compacted_blocks : null
        const hasSummaryTokenStats = summarySourceTokens !== null && summaryResultTokens !== null
        const displayBeforeTokens = summarySourceTokens ?? beforeTokens
        const displayAfterTokens = summaryResultTokens ?? afterTokens
        const displaySavedTokens = summarySavedTokens ?? (
          displayBeforeTokens !== null && displayAfterTokens !== null
            ? Math.max(displayBeforeTokens - displayAfterTokens, 0)
            : 0
        )

        if (taskPart.state === 'completed' && displayBeforeTokens !== null && displayAfterTokens !== null) {
          if (trigger === 'context_length_error') {
            return tTask('compressionCompletedReactive', { before: displayBeforeTokens, after: displayAfterTokens })
          }
          if (trigger === 'blocking_threshold' || pressureLevel === 'blocking' || pressureLevel === 'over_budget') {
            if (hasSummaryTokenStats || (summaryTurns !== null && summaryTurns > 0)) {
              return tTask('compressionCompletedBlockingSummary', {
                before: displayBeforeTokens,
                after: displayAfterTokens,
                saved: displaySavedTokens,
                count: summaryTurns ?? 0,
              })
            }
            return tTask('compressionCompletedBlocking', { before: displayBeforeTokens, after: displayAfterTokens })
          }
          if (hasSummaryTokenStats || (summaryTurns !== null && summaryTurns > 0)) {
            return tTask('compressionCompletedProactiveSummary', {
              before: displayBeforeTokens,
              after: displayAfterTokens,
              saved: displaySavedTokens,
              count: summaryTurns ?? compactedBlocks ?? 0,
            })
          }
          return tTask('compressionCompletedProactive', { before: displayBeforeTokens, after: displayAfterTokens })
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
    }, [tTask])

    const getThoughtAction = React.useCallback((entries: Array<{ part: MessagePart; index: number }>) => {
      for (let entryIndex = entries.length - 1; entryIndex >= 0; entryIndex -= 1) {
        const part = entries[entryIndex].part
        if (isToolCallPart(part)) return part.toolDisplayName || part.toolName
        if (isMcpToolCallPart(part)) return `${part.serverName}/${part.toolName}`
        if (isTaskPart(part) && part.taskType !== 'thinking') return getTaskTitle(part)
      }


      return null
    }, [getTaskTitle])

    const getThoughtTitle = React.useCallback((entries: Array<{ part: MessagePart; index: number }>, isStreaming: boolean) => {
      const action = getThoughtAction(entries)
      if (action) {
        return `${isStreaming ? tReasoning('thinking') : tReasoning('thought')}: ${action}`
      }

      const reasoningPart = entries.find(({ part }) => isReasoningPart(part))?.part
      if (reasoningPart && isReasoningPart(reasoningPart) && !isStreaming) {
        return tReasoning('thoughtFor', { seconds: reasoningPart.duration ? Math.ceil(reasoningPart.duration / 1000) : 0 })
      }
      return isStreaming ? tReasoning('thinking') : tReasoning('thoughtDefault')
    }, [getThoughtAction, tReasoning])
    const renderOrdinaryPart = React.useCallback((part: MessagePart, index: number) => {
      if (
        isReasoningPart(part)
        || isTaskPart(part)
        || isToolCallPart(part)
        || isMcpToolCallPart(part)
        || isToolResultPart(part)
        || isMcpToolResultPart(part)
      ) {
        return null
      }
      return renderPart ? renderPart(part, index) : renderDefaultPart(part, index)
    }, [renderDefaultPart, renderPart])

    const renderThoughtEntry = React.useCallback((part: MessagePart, index: number) => {
      if (isReasoningPart(part)) {
        const title = part.state === 'streaming'
          ? tReasoning('thinking')
          : tReasoning('thoughtFor', { seconds: part.duration ? Math.ceil(part.duration / 1000) : 0 })
        return (
          <ChainOfThoughtStep
            key={index}
            data-chat-timeline-index={index}
            icon={Brain}
            label={title}
            status={part.state === 'streaming' ? 'active' : 'complete'}
          >
            {part.text && (
              <pre className="text-xs text-muted-foreground/70 whitespace-pre-wrap break-words font-sans">
                {part.text}
              </pre>
            )}
          </ChainOfThoughtStep>
        )
      }

      if (isTaskPart(part)) {
        const icon = part.taskType === 'rag'
          ? SearchIcon
          : part.taskType === 'compression' ? Timer : SparklesIcon
        return (
          <ChainOfThoughtStep
            key={index}
            data-chat-timeline-index={index}
            icon={icon}
            label={getTaskTitle(part)}
            status={getStepStatus(part.state)}
          />
        )
      }

      if (
        isToolCallPart(part)
        || isMcpToolCallPart(part)
        || isToolResultPart(part)
        || isMcpToolResultPart(part)
      ) {
        // The Tool header is the disclosure node inside the thought process.
        return renderDefaultPart(part, index)
      }

      return null
    }, [getStepStatus, getTaskTitle, renderDefaultPart, tReasoning])

    const isThoughtEntry = React.useCallback((entry: { part: MessagePart; index: number }) => {
      const { part, index } = entry
      if (isReasoningPart(part)) return !hideReasoning
      if (isTaskPart(part)) return !hideReasoning && part.taskType !== 'thinking'
      if (isToolCallPart(part) || isMcpToolCallPart(part)) return !hideToolCalls
      if (isToolResultPart(part) || isMcpToolResultPart(part)) {
        return !hideToolCalls && !pairedToolResultIndexes.has(index)
      }
      return false
    }, [hideReasoning, hideToolCalls, pairedToolResultIndexes])

    const isThoughtEntryStreaming = React.useCallback((part: MessagePart) => {
      if (isReasoningPart(part)) return part.state === 'streaming'
      if (isTaskPart(part)) return part.state === 'running'
      if (isToolCallPart(part) || isMcpToolCallPart(part)) {
        return part.state === 'pending' || part.state === 'running'
      }
      return false
    }, [])

    const renderThoughtGroup = React.useCallback((entries: Array<{ part: MessagePart; index: number }>) => {
      const isThoughtStreaming = entries.some(({ part }) => isThoughtEntryStreaming(part))
      const title = getThoughtTitle(entries, isThoughtStreaming)
      const firstIndex = entries[0]?.index ?? 0

      return (
        <ChainOfThought
          key={`thought-${firstIndex}`}
          data-chat-timeline-index={firstIndex}
          data-chat-thought-process="true"
          isStreaming={isThoughtStreaming}
          open={chainOfThoughtOpen}
          onOpenChange={onChainOfThoughtOpenChange}
          defaultOpen={isThoughtStreaming}
        >
          <ChainOfThoughtHeader title={title} icon={Brain} />
          <ChainOfThoughtContent>
            {entries.map(({ part, index }) => renderThoughtEntry(part, index))}
          </ChainOfThoughtContent>
        </ChainOfThought>
      )
    }, [chainOfThoughtOpen, getThoughtTitle, isThoughtEntryStreaming, onChainOfThoughtOpenChange, renderThoughtEntry])

    const renderOrderedTimeline = React.useCallback(() => {
      const rendered: React.ReactNode[] = []
      let thoughtEntries: Array<{ part: MessagePart; index: number }> = []
      let hasReasoning = false

      const flushThoughtEntries = () => {
        if (thoughtEntries.length === 0) return
        rendered.push(renderThoughtGroup(thoughtEntries))
        thoughtEntries = []
        hasReasoning = false
      }

      for (const entry of visibleContentEntries) {
        if (
          (isToolResultPart(entry.part) || isMcpToolResultPart(entry.part))
          && pairedToolResultIndexes.has(entry.index)
        ) continue
        if (isThoughtEntry(entry)) {
          // Each reasoning iteration gets its own disclosure container. Tool
          // and task nodes following it stay inside that iteration's process.
          if (isReasoningPart(entry.part) && hasReasoning) {
            flushThoughtEntries()
          }
          thoughtEntries.push(entry)
          if (isReasoningPart(entry.part)) hasReasoning = true
          continue
        }

        flushThoughtEntries()
        if (isTextPart(entry.part) && entry.part.text.length === 0) continue
        rendered.push(renderOrdinaryPart(entry.part, entry.index))
      }
      flushThoughtEntries()

      return rendered
    }, [isThoughtEntry, pairedToolResultIndexes, renderOrdinaryPart, renderThoughtGroup, visibleContentEntries])

    const messageBody = React.useMemo(() => (
      <>
        {isUser && fileParts.length > 0 && (
          <MessageAttachments>
            {fileParts.map((part, index) =>
              renderPart ? renderPart(part, index) : renderDefaultPart(part, index)
            )}
          </MessageAttachments>
        )}

        <MessageContent>
          {isUser && runInputLabel && (
            <div className="mb-1 text-xs text-muted-foreground">{runInputLabel}</div>
          )}
          {isEditing ? (
            <div className="space-y-2">
              <Textarea
                value={editDraft}
                onChange={(event) => setEditDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    cancelEdit()
                  }
                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                    event.preventDefault()
                    void saveEdit()
                  }
                }}
                placeholder={t('editPlaceholder')}
                className="min-h-24 resize-y bg-background text-foreground"
                disabled={isSavingEdit}
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={cancelEdit}
                  disabled={isSavingEdit}
                >
                  {t('cancelEdit')}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void saveEdit()}
                  disabled={isSavingEdit || !editDraft.trim() || editDraft.trim() === textContent}
                >
                  {isSavingEdit && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                  {t('saveEdit')}
                </Button>
              </div>
            </div>
          ) : isLoadingMessage ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">{loadingLabel ?? t('thinking')}</span>
            </div>
          ) : (
            renderOrderedTimeline()
          )}
          {isErroredMessage && (
            <div className={cn('flex flex-col gap-1 text-xs', !isStandaloneErrorMessage && 'mt-3')}>
              <div className="flex items-start gap-1.5 text-destructive">
                <AlertTriangle className={cn('h-3.5 w-3.5 shrink-0', !isStandaloneErrorMessage && 'mt-0.5')} />
                <span>{showPreservedErrorNote ? preservedErrorNote : (streamErrorMessage ?? t('error'))}</span>
                {typeof message.metadata?.errorCode === 'number' && (
                  <code className="rounded bg-destructive/10 px-1 font-mono text-[10px]">
                    {t('errorCode')} {message.metadata.errorCode}
                  </code>
                )}
              </div>
              {conversationId && (
                <div className="flex items-center gap-1.5 pl-5 text-muted-foreground">
                  <span>{t('conversationId')}:</span>
                  <code className="font-mono text-[10px]">{conversationId}</code>
                </div>
              )}
            </div>
          )}
          {isAssistant && isManuallyStoppedMessage && (
            <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Square className="h-3 w-3 shrink-0 fill-current" />
              <span>{t('manuallyStopped')}</span>
            </div>
          )}
        </MessageContent>

        {isAssistant && allSources.length > 0 && (
          <SourceContent sources={allSources} onOpenCodePreview={onOpenCodePreview} />
        )}
      </>
    ), [
      allSources,
      cancelEdit,
      conversationId,
      editDraft,
      fileParts,
      isAssistant,
      isEditing,
      isErroredMessage,
      isLoadingMessage,
      loadingLabel,
      message.metadata?.errorCode,
      isManuallyStoppedMessage,
      isSavingEdit,
      isStandaloneErrorMessage,
      isUser,
      onOpenCodePreview,
      preservedErrorNote,
      renderDefaultPart,
      renderOrderedTimeline,
      renderPart,
      runInputLabel,
      saveEdit,
      showPreservedErrorNote,
      streamErrorMessage,
      t,
      textContent,
    ])

    return (
      <div
        ref={ref}
        className={cn('w-full py-3', className)}
        data-role={message.role}
        {...props}
      >
        <div className="mx-auto max-w-3xl px-4">
          <AIMessage from={message.role}>
            {messageBody}
            {afterContent}

            {/* Actions for user messages */}
            {isUser && !isStreaming && !isEditing && textContent && !hideMessageActions && (showCopy || onEditMessage || onSwitchVersion) && (
              <MessageActions className="transition-opacity opacity-0 group-hover:opacity-100 justify-end">
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
                {onEditMessage && (
                  <MessageAction tooltip={t('edit')} onClick={startEdit}>
                    <Pencil className="h-4 w-4" />
                  </MessageAction>
                )}
              </MessageActions>
            )}

            {/* Actions for assistant messages */}
            {isAssistant && !isStreaming && hasMessageContent && !hideMessageActions && (
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

function areMessagePropsEqual(prev: Readonly<MessageProps>, next: Readonly<MessageProps>) {
  return prev.message === next.message
    && prev.isStreaming === next.isStreaming
    && prev.loadingLabel === next.loadingLabel
    && prev.renderPart === next.renderPart
    && prev.afterContent === next.afterContent
    && prev.showCopy === next.showCopy
    && prev.showFeedback === next.showFeedback
    && prev.onRegenerate === next.onRegenerate
    && prev.onEditMessage === next.onEditMessage
    && prev.onFeedback === next.onFeedback
    && prev.onSwitchVersion === next.onSwitchVersion
    && prev.onSelectOption === next.onSelectOption
    && prev.onSelectImageReference === next.onSelectImageReference
    && prev.onOpenCodePreview === next.onOpenCodePreview
    && prev.hideToolCalls === next.hideToolCalls
    && prev.hideMessageActions === next.hideMessageActions
    && prev.hideReasoning === next.hideReasoning
    && prev.conversationId === next.conversationId
    && prev.chainOfThoughtOpen === next.chainOfThoughtOpen
    && prev.onChainOfThoughtOpenChange === next.onChainOfThoughtOpenChange
    && prev.onRequestScrollIntoView === next.onRequestScrollIntoView
    && prev.className === next.className
}

export const Message = React.memo(MessageComponent, areMessagePropsEqual)

Message.displayName = 'Message'

/**
 * Token stats popover content
 */
function TokenStatsContent({
  usage,
  timing,
  t,
}: {
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number; cache_read_tokens?: number; cache_creation_tokens?: number }
  timing?: { first_token_ms: number | null; duration_ms: number; tokens_per_second: number | null }
  t: (key: string) => string
}) {
  const formatTime = (ms: number) => {
    if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
    return `${ms}ms`
  }
  const cacheReadTokens = usage.cache_read_tokens ?? 0
  const cacheCreationTokens = usage.cache_creation_tokens ?? 0

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
      {cacheReadTokens > 0 && (
        <div className="flex justify-between gap-8">
          <span className="text-muted-foreground">{t('cachedTokens')}</span>
          <span className="font-mono tabular-nums">{cacheReadTokens.toLocaleString()}</span>
        </div>
      )}
      {cacheCreationTokens > 0 && (
        <div className="flex justify-between gap-8">
          <span className="text-muted-foreground">{t('cacheCreationTokens')}</span>
          <span className="font-mono tabular-nums">{cacheCreationTokens.toLocaleString()}</span>
        </div>
      )}
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
 * Text content with lightweight inline citation markers.
 * Keep citation handling in string preprocessing so message rendering does not
 * run DOM TreeWalker / MutationObserver / portal work on every Streamdown update.
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
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void
}) {
  const blockRef = React.useRef<HTMLDivElement>(null)

  React.useLayoutEffect(() => {
    if (!isStreaming || !props.isIncomplete) return

    const body = blockRef.current?.querySelector<HTMLElement>('[data-streamdown="code-block-body"]')
    if (body) body.scrollTop = body.scrollHeight
  }, [content, isStreaming, props.isIncomplete])
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

  const block = (
    <Block
      content={content}
      index={index}
      shouldParseIncompleteMarkdown={shouldParseIncompleteMarkdown}
      {...props}
    />
  )

  if (!isStreaming || !props.isIncomplete) {
    return block
  }

  return (
    <div ref={blockRef} data-chat-code-autoscroll="true">
      {block}
    </div>
  )
}

function getAuthenticatedApiAssetUrl(src: string): string | null {
  return src.startsWith('/api/v1/') ? src : null
}

function isBlockedImageSrc(src: string): boolean {
  const normalized = src.trim().toLowerCase()
  return normalized.startsWith('javascript:') || normalized.startsWith('data:') || normalized.startsWith('vbscript:')
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
  onPreview?: (src: string, alt?: string) => void
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

function AuthenticatedMarkdownImage({ src = '', alt = '', onPreview, ...props }: AuthenticatedMarkdownImageProps) {
  const t = useTranslations('chat.message')
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

  return (
    <span className="relative inline-block max-w-full">
      <img {...props} src={objectUrl} alt={alt} loading="lazy" />
      {onPreview && (
        <button
          type="button"
          className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-md bg-background/90 text-foreground shadow-sm transition-colors hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={`${t('openCodePreview')}: ${alt || t('generatedImageAlt')}`}
          onClick={() => onPreview(objectUrl, alt)}
        >
          <Eye className="h-4 w-4" />
        </button>
      )}
    </span>
  )
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

const CODE_BLOCK_REGEX = /(```[\s\S]*?(?:```|$)|`[^`]*?(?:`|$))/g
const ESCAPED_MATH_BLOCK_REGEX = /\\\[([\s\S]*?)\\\]/g
const ESCAPED_MATH_INLINE_REGEX = /\\\(([\s\S]*?)\\\)/g
const BARE_MATH_BLOCK_REGEX = /(^|\n)\s*\[((?:\[[^\[\]]*\]|[^\[\]])*)\]\s*(?=\n|$)/g
const BARE_LATEX_INLINE_REGEX = /(^|[\s，。；：、])\(\s*((?:\([^()]*\)|[^()])*)\s*\)(?=$|[\s，。；：、,.!?])/g
const BARE_LATEX_FORMULA_LINE_REGEX = /^(\s*)(\\(?:cos|sin|tan|log|ln|text|frac|sqrt|sum|prod|int|mathbf|mathrm|mathbb|cdot|times|leq|geq)\b.*(?:=|\\frac|\\sum|\\sqrt|\\cdot).*)\s*$/
const MATH_COMMAND_REGEX = /\\[A-Za-z]+/
const TIGHT_STRONG_MARKER_REGEX = /\*\*([^*\n]+?)\*\*(?=[\p{Script=Han}\p{Letter}\p{Number}])/gu

function normalizeTightStrongMarkers(input: string) {
  if (!input) {
    return ''
  }

  return input
    .split(CODE_BLOCK_REGEX)
    .map((segment) => {
      if (!segment || segment.startsWith('`')) {
        return segment
      }
      return segment.replace(TIGHT_STRONG_MARKER_REGEX, '<strong>$1</strong>')
    })
    .join('')
}

function normalizeBareLatexFormulaLines(input: string) {
  if (!input) {
    return ''
  }

  let insideMathBlock = false
  return input
    .split('\n')
    .map((line) => {
      if (line.trim() === '$$') {
        insideMathBlock = !insideMathBlock
        return line
      }
      if (insideMathBlock) {
        return line
      }
      const match = line.match(BARE_LATEX_FORMULA_LINE_REGEX)
      if (!match) {
        return line
      }
      return `${match[1]}$$\n${match[2].trim()}\n${match[1]}$$`
    })
    .join('\n')
}

function normalizeBareMathDelimiters(input: string) {
  if (!input) {
    return ''
  }

  return input
    .split(CODE_BLOCK_REGEX)
    .map((segment) => {
      if (!segment) {
        return ''
      }
      if (segment.startsWith('`')) {
        return segment
      }
      return normalizeBareLatexFormulaLines(segment)
        .replace(ESCAPED_MATH_BLOCK_REGEX, (_, formula: string) => `\n\n$$\n${formula}\n$$`)
        .replace(ESCAPED_MATH_INLINE_REGEX, (_, formula: string) => `$${formula}$`)
        .replace(BARE_MATH_BLOCK_REGEX, (match, prefix: string, formula: string) => {
          if (!MATH_COMMAND_REGEX.test(formula)) {
            return match
          }
          return `${prefix}\n\n$$\n${formula.trim()}\n$$`
        })
        .replace(BARE_LATEX_INLINE_REGEX, (match, prefix: string, formula: string) => {
          if (!MATH_COMMAND_REGEX.test(formula)) {
            return match
          }
          return `${prefix}$${formula.trim()}$`
        })
    })
    .join('')
}

const CITE_MARKER_REGEX = /\[\[cite:(\d+)\]\]/g

function normalizeCitationMarkers(input: string, normalizeMath: boolean) {
  const normalized = normalizeMath ? normalizeBareMathDelimiters(input) : input
  return normalizeTightStrongMarkers(normalized)
    .replace(/\[\[ref:(\d+)\]\]/gi, '[[cite:$1]]')
    .replace(/\[ref:(\d+)\]/gi, '[[cite:$1]]')
    .replace(/\(ref:(\d+)\)/gi, '[[cite:$1]]')
}

function formatCitationMarker(index: number, sources: SourceDocumentPart[]) {
  if (index < 1 || index > sources.length) {
    return ''
  }
  return ` [${index}]`
}

export const TextWithCitations = React.memo(function TextWithCitations({
  text,
  sources,
  isStreaming = false,
  activeSpeechSentence,
  onOpenCodePreview,
  onOpenImage,
}: {
  text: string
  sources: SourceDocumentPart[]
  isStreaming?: boolean
  activeSpeechSentence?: string | null
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void
  onOpenImage?: (src: string, alt?: string) => void
}) {
  const containerRef = React.useRef<HTMLDivElement>(null)
  const hasSources = sources.length > 0

  const processedText = React.useMemo(() => {
    const normalized = normalizeCitationMarkers(text, !isStreaming)
    if (!hasSources) {
      return normalized.replace(CITE_MARKER_REGEX, '')
    }
    return normalized.replace(CITE_MARKER_REGEX, (_, rawIndex: string) => (
      formatCitationMarker(Number.parseInt(rawIndex, 10), sources)
    ))
  }, [text, hasSources, sources, isStreaming])

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
          if (!parent || parent.closest('[data-streamdown="code-block"], [data-speech-highlight="true"]')) {
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

  const rehypePlugins = isStreaming ? STREAMING_REHYPE_PLUGINS : undefined

  const components = React.useMemo(() => ({
    img: ({ src, alt, ...props }: React.ComponentProps<'img'>) => (
      <AuthenticatedMarkdownImage
        src={typeof src === 'string' ? src : undefined}
        alt={alt || ''}
        onPreview={onOpenImage}
        {...props}
      />
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
  }), [onOpenImage])

  const renderMarkdownBlock = React.useCallback((props: React.ComponentProps<typeof Block>) => (
    <PreviewableMarkdownBlock
      {...props}
      isStreaming={isStreaming}
      onOpenCodePreview={onOpenCodePreview}
    />
  ), [isStreaming, onOpenCodePreview])

  React.useEffect(() => {
    if (!activeSpeechSentence) {
      clearSpeechHighlight()
      return
    }
    const timeoutId = setTimeout(applySpeechHighlight, 0)
    return () => {
      clearTimeout(timeoutId)
      clearSpeechHighlight()
    }
  }, [activeSpeechSentence, applySpeechHighlight, clearSpeechHighlight, processedText])

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
        BlockComponent={renderMarkdownBlock}
      >
        {processedText}
      </Streamdown>
    </div>
  )
}, (prevProps, nextProps) => (
  prevProps.text === nextProps.text
  && prevProps.sources === nextProps.sources
  && prevProps.isStreaming === nextProps.isStreaming
  && prevProps.activeSpeechSentence === nextProps.activeSpeechSentence
  && prevProps.onOpenCodePreview === nextProps.onOpenCodePreview
  && prevProps.onOpenImage === nextProps.onOpenImage
))

export { type ChatMessage }
