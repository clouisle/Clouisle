'use client'

import * as React from 'react'
import * as ReactDOM from 'react-dom'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import type { MermaidConfig } from 'mermaid'
import { Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Loader2, SearchIcon, SparklesIcon, Wrench, ChevronLeft, ChevronRight, AlertTriangle, Timer, Brain, Square, ZoomIn, ZoomOut, Download, Maximize2, Minimize2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Block,
  Streamdown,
} from 'streamdown'
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

const MERMAID_FENCE_REGEX = /^```mermaid\r?\n([\s\S]*?)\r?\n```$/
const MERMAID_PARTIAL_FENCE_REGEX = /^```mermaid\r?\n([\s\S]*)$/
const MERMAID_PARTIAL_OPENING_REGEX = /```mermaid\r?\n([\s\S]*)$/
const MERMAID_MIN_ZOOM = 0.5
const MERMAID_MAX_ZOOM = 2
const MERMAID_ZOOM_STEP = 0.1
const mermaidSvgCache = new Map<string, string>()
const mermaidStreamSessions = new Map<string, MermaidStreamSession>()
let mermaidModulePromise: Promise<typeof import('mermaid')> | null = null
let mermaidInitializedTheme: MermaidTheme | null = null

type MermaidTheme = NonNullable<MermaidConfig['theme']>

type MermaidStreamSession = {
  committedCode: string
  renderedSvg: string
  animatedSvg: string
  renderedTheme: MermaidTheme
  error: string | null
}

function normalizeMermaidCode(content: string) {
  return content.replace(/\r\n?/g, '\n')
}

function getMermaidRenderErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Failed to render Mermaid chart'
}

function getMermaidSession(streamKey: string) {
  return mermaidStreamSessions.get(streamKey) ?? null
}

function isMermaidFence(content: string) {
  return MERMAID_FENCE_REGEX.test(content)
}

function isPartialMermaidFence(content: string) {
  if (!MERMAID_PARTIAL_FENCE_REGEX.test(content)) {
    return false
  }

  return !content.trimEnd().endsWith('```')
}

function extractMermaidCode(content: string) {
  const match = content.match(MERMAID_FENCE_REGEX) ?? content.match(MERMAID_PARTIAL_OPENING_REGEX)
  return normalizeMermaidCode(match?.[1] ?? content)
}

function getMermaidCacheKey(code: string, theme: MermaidTheme) {
  return `${theme}:${code}`
}

function isMermaidCommentLine(line: string) {
  return line.trimStart().startsWith('%%')
}

function areMermaidDelimitersBalanced(line: string) {
  if (!line.trim() || isMermaidCommentLine(line)) {
    return true
  }

  let round = 0
  let square = 0
  let curly = 0
  let quote: '"' | '\'' | null = null
  let escaped = false

  for (const char of line) {
    if (quote) {
      if (escaped) {
        escaped = false
        continue
      }
      if (char === '\\') {
        escaped = true
        continue
      }
      if (char === quote) {
        quote = null
      }
      continue
    }

    if (char === '"' || char === '\'') {
      quote = char
      continue
    }

    if (char === '(') round += 1
    if (char === ')') round -= 1
    if (char === '[') square += 1
    if (char === ']') square -= 1
    if (char === '{') curly += 1
    if (char === '}') curly -= 1

    if (round < 0 || square < 0 || curly < 0) {
      return false
    }
  }

  return quote === null && round === 0 && square === 0 && curly === 0
}

function hasDanglingMermaidConnector(line: string) {
  const trimmed = line.trim()
  if (!trimmed) {
    return false
  }

  return /(?:-->|---|==>|-\.->|--|==|~~>|~~~|->|=>)\s*$/.test(trimmed)
    || /\|\s*$/.test(trimmed)
}

function hasUnbalancedMermaidEdgeLabel(line: string) {
  const pipeCount = line.split('|').length - 1
  return pipeCount % 2 === 1
}

function isIncompleteMermaidDirectiveLine(line: string, subgraphDepth: number) {
  const trimmed = line.trim()
  if (!trimmed || isMermaidCommentLine(line)) {
    return false
  }

  if (/^end\b/i.test(trimmed)) {
    return subgraphDepth === 0
  }

  if (/^(?:classDef|style|linkStyle|click|class)\b/i.test(trimmed)) {
    return /(?:[:,=]|\.\.|->|=>|-)$/.test(trimmed)
  }

  return false
}

function getMermaidSubgraphDelta(line: string) {
  const trimmed = line.trim()
  if (/^subgraph\b/i.test(trimmed)) {
    return 1
  }
  if (/^end\b/i.test(trimmed)) {
    return -1
  }
  return 0
}

function getRenderableMermaidPrefix(code: string) {
  const normalized = normalizeMermaidCode(code)
  const lines = normalized.split('\n')
  const completeLines = lines.slice(0, -1)

  if (completeLines.length === 0) {
    return ''
  }

  const safeLines: string[] = []
  let committedLineCount = 0
  let subgraphDepth = 0

  for (const line of completeLines) {
    if (!areMermaidDelimitersBalanced(line) || hasUnbalancedMermaidEdgeLabel(line) || hasDanglingMermaidConnector(line) || isIncompleteMermaidDirectiveLine(line, subgraphDepth)) {
      break
    }

    const nextDepth = subgraphDepth + getMermaidSubgraphDelta(line)
    if (nextDepth < 0) {
      break
    }

    safeLines.push(line)
    subgraphDepth = nextDepth

    if (subgraphDepth === 0) {
      committedLineCount = safeLines.length
    }
  }

  return safeLines.slice(0, committedLineCount).join('\n').trimEnd()
}

function normalizeMermaidText(value: string | null | undefined) {
  return value?.replace(/\s+/g, ' ').trim() ?? ''
}

function getMermaidNodeSignature(node: Element, index: number) {
  const id = node.getAttribute('data-id') ?? node.getAttribute('id')
  if (id) {
    return `id:${id}`
  }

  const label = normalizeMermaidText(node.textContent)
  if (label) {
    return `label:${label}`
  }

  return `node:${index}`
}

function getMermaidEdgeSignature(edgePath: Element, edgeLabel: Element | undefined, index: number) {
  const id = edgePath.getAttribute('id')
  if (id) {
    return `id:${id}`
  }

  const title = normalizeMermaidText(edgePath.querySelector('title')?.textContent)
  if (title) {
    return `title:${title}`
  }

  const label = normalizeMermaidText(edgeLabel?.textContent)
  if (label) {
    return `label:${label}`
  }

  return `edge:${index}`
}

function animateNewMermaidElements(previousSvg: string, nextSvg: string) {
  if (!previousSvg || typeof DOMParser === 'undefined' || typeof XMLSerializer === 'undefined') {
    return nextSvg
  }

  const parser = new DOMParser()
  const previousDoc = parser.parseFromString(previousSvg, 'image/svg+xml')
  const nextDoc = parser.parseFromString(nextSvg, 'image/svg+xml')

  if (previousDoc.querySelector('parsererror') || nextDoc.querySelector('parsererror')) {
    return nextSvg
  }

  const previousNodes = new Set(
    Array.from(previousDoc.querySelectorAll('g.node')).map((node, index) => getMermaidNodeSignature(node, index))
  )
  const previousEdgePaths = Array.from(previousDoc.querySelectorAll('g.edgePath'))
  const previousEdgeLabels = Array.from(previousDoc.querySelectorAll('g.edgeLabel'))
  const previousEdges = new Set(
    previousEdgePaths.map((edgePath, index) => getMermaidEdgeSignature(edgePath, previousEdgeLabels[index], index))
  )

  const nextNodes = Array.from(nextDoc.querySelectorAll('g.node'))
  nextNodes.forEach((node, index) => {
    if (!previousNodes.has(getMermaidNodeSignature(node, index))) {
      node.classList.add('mermaid-stream-node-enter')
    }
  })

  const nextEdgePaths = Array.from(nextDoc.querySelectorAll('g.edgePath'))
  const nextEdgeLabels = Array.from(nextDoc.querySelectorAll('g.edgeLabel'))
  nextEdgePaths.forEach((edgePath, index) => {
    if (!previousEdges.has(getMermaidEdgeSignature(edgePath, nextEdgeLabels[index], index))) {
      edgePath.classList.add('mermaid-stream-edge-enter')
      nextEdgeLabels[index]?.classList.add('mermaid-stream-edge-enter')
    }
  })

  return new XMLSerializer().serializeToString(nextDoc.documentElement)
}

async function getMermaidRenderer(theme: MermaidTheme) {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid')
  }

  const { default: mermaid } = await mermaidModulePromise
  if (mermaidInitializedTheme !== theme) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme,
    })
    mermaidInitializedTheme = theme
  }

  return mermaid
}

function clampMermaidZoom(zoom: number) {
  return Math.min(MERMAID_MAX_ZOOM, Math.max(MERMAID_MIN_ZOOM, zoom))
}

async function downloadMermaidSvg(svg: string) {
  const blob = new Blob([svg], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'diagram.svg'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function MermaidToolbarButton({
  onClick,
  title,
  disabled,
  children,
  iconOnly = false,
  className,
}: {
  onClick: () => void
  title: string
  disabled?: boolean
  children: React.ReactNode
  iconOnly?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40',
        iconOnly
          ? 'h-8 w-8 rounded-full hover:bg-background/70'
          : 'h-8 gap-1 rounded-xl px-1.5 text-xs font-medium hover:bg-background/70',
        className
      )}
    >
      {children}
    </button>
  )
}

function MermaidSegmentButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-sm px-3 py-1 text-xs font-medium transition-colors',
        active
          ? 'bg-background text-foreground shadow-sm'
          : 'text-muted-foreground hover:text-foreground'
      )}
    >
      {children}
    </button>
  )
}

function MermaidBlock({
  code,
  theme,
  isComplete,
  streamKey,
}: {
  code: string
  theme: MermaidTheme
  isComplete: boolean
  streamKey: string
}) {
  const t = useTranslations('chat.message')
  const initialSession = React.useMemo(() => getMermaidSession(streamKey), [streamKey])
  const [mode, setMode] = React.useState<'diagram' | 'code'>('diagram')
  const [svg, setSvg] = React.useState(initialSession?.animatedSvg ?? '')
  const [error, setError] = React.useState<string | null>(initialSession?.error ?? null)
  const [isRendering, setIsRendering] = React.useState(() => !initialSession?.animatedSvg && code.trim().length > 0)
  const [zoom, setZoom] = React.useState(1)
  const [pan, setPan] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const [isFullscreen, setIsFullscreen] = React.useState(false)
  const dragStartRef = React.useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  const diagramRef = React.useRef<HTMLDivElement>(null)
  const renderVersionRef = React.useRef(0)
  const committedCodeRef = React.useRef(initialSession?.committedCode ?? '')
  const renderedSvgRef = React.useRef(initialSession?.renderedSvg ?? '')
  const renderedThemeRef = React.useRef<MermaidTheme>(initialSession?.renderedTheme ?? theme)
  const displayedSvgRef = React.useRef(initialSession?.animatedSvg ?? '')
  const rawNormalizedCode = React.useMemo(() => normalizeMermaidCode(code), [code])
  const normalizedCode = React.useMemo(() => rawNormalizedCode.trimEnd(), [rawNormalizedCode])
  const renderableStreamingCode = React.useMemo(() => getRenderableMermaidPrefix(rawNormalizedCode), [rawNormalizedCode])
  const codeToRender = isComplete ? normalizedCode : renderableStreamingCode

  React.useEffect(() => {
    const session = getMermaidSession(streamKey)
    committedCodeRef.current = session?.committedCode ?? ''
    renderedSvgRef.current = session?.renderedSvg ?? ''
    renderedThemeRef.current = session?.renderedTheme ?? theme
    displayedSvgRef.current = session?.animatedSvg ?? ''
    setSvg(session?.animatedSvg ?? '')
    setError(session?.error ?? null)
    setIsRendering(!session?.animatedSvg && normalizedCode.trim().length > 0)
  }, [normalizedCode, streamKey, theme])

  React.useEffect(() => {
    displayedSvgRef.current = svg
  }, [svg])

  React.useEffect(() => {
    if (mode === 'code') {
      return
    }

    if (!codeToRender) {
      setIsRendering(!displayedSvgRef.current && normalizedCode.trim().length > 0)
      if (!isComplete) {
        setError(null)
      }
      return
    }

    const alreadyRendered = renderedThemeRef.current === theme
      && committedCodeRef.current === codeToRender
      && renderedSvgRef.current.length > 0

    if (alreadyRendered) {
      setError(null)
      setIsRendering(false)
      return
    }

    let cancelled = false
    const requestVersion = ++renderVersionRef.current

    const commitRenderedSvg = (renderedSvg: string) => {
      const previousRenderedSvg = renderedThemeRef.current === theme ? renderedSvgRef.current : ''
      const nextAnimatedSvg = previousRenderedSvg === renderedSvg
        ? displayedSvgRef.current || renderedSvg
        : animateNewMermaidElements(previousRenderedSvg, renderedSvg)

      const nextSession: MermaidStreamSession = {
        committedCode: codeToRender,
        renderedSvg,
        animatedSvg: nextAnimatedSvg,
        renderedTheme: theme,
        error: null,
      }

      mermaidStreamSessions.set(streamKey, nextSession)
      committedCodeRef.current = codeToRender
      renderedSvgRef.current = renderedSvg
      renderedThemeRef.current = theme
      displayedSvgRef.current = nextAnimatedSvg
      setSvg((currentSvg) => currentSvg === nextAnimatedSvg ? currentSvg : nextAnimatedSvg)
      setError(null)
      setIsRendering(false)
    }

    const handleRenderError = (renderError: unknown) => {
      if (!isComplete) {
        setIsRendering(false)
        return
      }

      const nextError = getMermaidRenderErrorMessage(renderError)
      mermaidStreamSessions.set(streamKey, {
        committedCode: committedCodeRef.current,
        renderedSvg: renderedSvgRef.current,
        animatedSvg: displayedSvgRef.current,
        renderedTheme: renderedThemeRef.current,
        error: nextError,
      })
      setError(nextError)
      setIsRendering(false)
    }

    const cacheKey = getMermaidCacheKey(codeToRender, theme)
    const cachedSvg = mermaidSvgCache.get(cacheKey)
    if (cachedSvg) {
      commitRenderedSvg(cachedSvg)
      return
    }

    setIsRendering(!displayedSvgRef.current)

    void (async () => {
      try {
        const mermaid = await getMermaidRenderer(theme)
        const id = `mermaid-${Math.random().toString(36).slice(2)}`
        const { svg: renderedSvg } = await mermaid.render(id, codeToRender)
        mermaidSvgCache.set(cacheKey, renderedSvg)
        if (!cancelled && requestVersion === renderVersionRef.current) {
          commitRenderedSvg(renderedSvg)
        }
      } catch (renderError) {
        if (!cancelled && requestVersion === renderVersionRef.current) {
          handleRenderError(renderError)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [codeToRender, isComplete, mode, normalizedCode, theme, streamKey])

  React.useEffect(() => {
    if (!isFullscreen) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsFullscreen(false)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isFullscreen])

  React.useEffect(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setIsDragging(false)
  }, [mode, isFullscreen])

  React.useEffect(() => {
    if (!diagramRef.current) {
      return
    }

    diagramRef.current.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
  }, [pan, zoom])

  const handleDownload = React.useCallback(() => {
    if (!svg) {
      return
    }
    void downloadMermaidSvg(svg)
  }, [svg])

  const handleDiagramPointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (mode !== 'diagram' || !svg) {
      return
    }

    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: pan.x,
      panY: pan.y,
    }
    setIsDragging(true)
    event.currentTarget.setPointerCapture(event.pointerId)
    if (diagramRef.current) {
      diagramRef.current.style.transition = 'none'
    }
  }, [mode, pan.x, pan.y, svg])

  const handleDiagramPointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || !diagramRef.current) {
      return
    }

    const deltaX = event.clientX - dragStartRef.current.x
    const deltaY = event.clientY - dragStartRef.current.y
    const nextPan = {
      x: dragStartRef.current.panX + deltaX,
      y: dragStartRef.current.panY + deltaY,
    }

    diagramRef.current.style.transform = `translate(${nextPan.x}px, ${nextPan.y}px) scale(${zoom})`
  }, [isDragging, zoom])

  const handleDiagramPointerUp = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) {
      return
    }

    const deltaX = event.clientX - dragStartRef.current.x
    const deltaY = event.clientY - dragStartRef.current.y
    const nextPan = {
      x: dragStartRef.current.panX + deltaX,
      y: dragStartRef.current.panY + deltaY,
    }

    setPan(nextPan)
    setIsDragging(false)
    event.currentTarget.releasePointerCapture(event.pointerId)
    if (diagramRef.current) {
      diagramRef.current.style.transition = ''
    }
  }, [isDragging])

  const maxBodyHeight = isFullscreen ? 'calc(100vh - 120px)' : '420px'

  const diagramContent = isRendering && !svg && !error
    ? (
      <div
        className="flex min-h-[240px] items-center justify-center gap-2 text-sm text-muted-foreground"
        style={{ maxHeight: maxBodyHeight }}
      >
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{t('mermaidRendering')}</span>
      </div>
    )
      : error
        ? (
          <div className="mx-6 mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 dark:border-red-900/60 dark:bg-red-950/30">
            <p className="font-mono text-red-700 text-sm dark:text-red-300">
              {t('mermaidError', { error })}
            </p>
          </div>
        )
        : (
          <div
            className="mx-3 mb-3 mt-1.5 overflow-hidden rounded-xl bg-background px-4 py-4"
            style={{ maxHeight: maxBodyHeight }}
          >
            <div
              className={cn(
                'flex min-h-[240px] items-center justify-center overflow-hidden select-none',
                isDragging ? 'cursor-grabbing' : 'cursor-grab'
              )}
              onPointerDown={handleDiagramPointerDown}
              onPointerMove={handleDiagramPointerMove}
              onPointerUp={handleDiagramPointerUp}
              onPointerCancel={handleDiagramPointerUp}
            >
              <div
                ref={diagramRef}
                className="origin-center transition-transform will-change-transform"
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
                dangerouslySetInnerHTML={{ __html: svg }}
              />
            </div>
          </div>
        )

  const codeContent = (
    <div className="mx-3 mb-3 mt-1.5 overflow-hidden rounded-xl bg-background" style={{ maxHeight: maxBodyHeight }}>
      <pre className="h-full overflow-auto p-4 text-sm">
        <code>{normalizedCode}</code>
      </pre>
    </div>
  )

  const content = (
    <div className={cn(
      'overflow-hidden rounded-xl border border-border/60 bg-muted/30',
      isFullscreen ? 'h-full' : 'w-full'
    )}>
      <div className="flex items-center justify-between px-4 pb-1.5 pt-3">
        <div className="inline-flex items-center gap-0.5 rounded-sm bg-muted p-0.5 shadow-sm">
          <MermaidSegmentButton active={mode === 'diagram'} onClick={() => setMode('diagram')}>
            {t('mermaidDiagram')}
          </MermaidSegmentButton>
          <MermaidSegmentButton active={mode === 'code'} onClick={() => setMode('code')}>
            {t('mermaidCode')}
          </MermaidSegmentButton>
        </div>
        <div className="flex items-center gap-0.5 text-muted-foreground">
          <MermaidToolbarButton
            iconOnly
            onClick={() => setZoom((current) => clampMermaidZoom(current - MERMAID_ZOOM_STEP))}
            title={t('mermaidZoomOut')}
            disabled={mode !== 'diagram' || zoom <= MERMAID_MIN_ZOOM}
          >
            <ZoomOut className="h-4 w-4" />
          </MermaidToolbarButton>
          <MermaidToolbarButton
            iconOnly
            onClick={() => setZoom((current) => clampMermaidZoom(current + MERMAID_ZOOM_STEP))}
            title={t('mermaidZoomIn')}
            disabled={mode !== 'diagram' || zoom >= MERMAID_MAX_ZOOM}
          >
            <ZoomIn className="h-4 w-4" />
          </MermaidToolbarButton>
          <div className="mx-1.5 h-6 w-px bg-border" />
          <MermaidToolbarButton
            onClick={handleDownload}
            title={t('mermaidDownload')}
            disabled={mode !== 'diagram' || !svg}
            className="px-1"
          >
            <Download className="h-4 w-4" />
            <span>{t('mermaidDownloadLabel')}</span>
          </MermaidToolbarButton>
          <MermaidToolbarButton
            onClick={() => setIsFullscreen((value) => !value)}
            title={isFullscreen ? t('mermaidExitFullscreen') : t('mermaidEnterFullscreen')}
            disabled={mode !== 'diagram'}
            className="px-1"
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            <span>{isFullscreen ? t('mermaidExitFullscreenLabel') : t('mermaidEnterFullscreenLabel')}</span>
          </MermaidToolbarButton>
        </div>
      </div>
      {mode === 'diagram' ? diagramContent : codeContent}
    </div>
  )

  if (!isFullscreen) {
    return content
  }

  return ReactDOM.createPortal(
    <div className="fixed inset-0 z-50 bg-background/95 p-4 backdrop-blur-sm">
      <div className="mx-auto h-full w-full max-w-[1400px]">{content}</div>
    </div>,
    document.body
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
        if (hasIterationCapMarker && part.text.trim() === iterationCapLabel) {
          return null
        }
        return (
          <TextWithCitations
            key={index}
            messageId={message.id}
            partIndex={index}
            text={part.text}
            sources={documentSources}
            isStreaming={isStreaming && part.state !== 'done'}
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
                icon={Brain}
                label={reasoningPart.state === 'streaming'
                  ? tReasoning('thinking')
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

            <MessageContent className={cn(isErroredMessage && 'rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2')}>
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
function MermaidMarkdownBlock({
  content,
  index,
  shouldParseIncompleteMarkdown,
  mermaidTheme,
  isStreaming,
  streamKey,
  ...props
}: React.ComponentProps<typeof Block> & {
  mermaidTheme: MermaidTheme
  isStreaming: boolean
  streamKey: string
}) {
  if (isMermaidFence(content) || (isStreaming && isPartialMermaidFence(content))) {
    return (
      <MermaidBlock
        code={extractMermaidCode(content)}
        theme={mermaidTheme}
        isComplete={isMermaidFence(content)}
        streamKey={streamKey}
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

function TextWithCitations({
  messageId,
  partIndex,
  text,
  sources,
  isStreaming = false,
}: {
  messageId: string
  partIndex: number
  text: string
  sources: SourceDocumentPart[]
  isStreaming?: boolean
}) {
  const { resolvedTheme } = useTheme()
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

  const mermaidTheme = resolvedTheme === 'dark' ? 'dark' : 'default'
  const mermaidStreamKeyPrefix = React.useMemo(
    () => `${messageId}:${partIndex}`,
    [messageId, partIndex]
  )

  const components = React.useMemo(() => ({
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

  return (
    <div
      ref={containerRef}
      className="w-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
    >
      <Streamdown
        isAnimating={isStreaming}
        components={components}
        BlockComponent={(props) => (
          <MermaidMarkdownBlock
            {...props}
            mermaidTheme={mermaidTheme}
            isStreaming={isStreaming}
            streamKey={`${mermaidStreamKeyPrefix}:${props.index}`}
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
