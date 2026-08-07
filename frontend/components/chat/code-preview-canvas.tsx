'use client'

import * as React from 'react'
import { Check, Copy, Download, Expand, FileText, Loader2, ZoomIn, ZoomOut, X } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { Streamdown } from 'streamdown'
import type { MermaidConfig } from 'mermaid'
import { bundledLanguages } from 'shiki'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CodeBlock } from '@/components/ai-elements/code-block'
import type { ArtifactPreviewPayload, ChatPreviewPayload, CodePreviewPayload, SourceDocumentPreviewPayload } from './types'
import { SegmentItem } from './message-parts'
import type { BundledLanguage } from 'shiki'

type MermaidTheme = NonNullable<MermaidConfig['theme']>

let mermaidModulePromise: Promise<typeof import('mermaid')> | null = null

const MERMAID_MIN_ZOOM = 0.05
const MERMAID_MAX_ZOOM = 15
const MERMAID_ZOOM_STEP = 0.1
const SOURCE_SEGMENT_BATCH_SIZE = 5
// React 19.2 types predate the `credentialless` iframe attribute (Chromium 110+).
// credentialless moves the iframe into its own renderer process, so heavy user
// HTML scripts running in `sandbox="allow-scripts"` cannot stall the parent
// page's main thread. Spread to bypass strict prop typing for this attribute.
const IFRAME_PROCESS_ISOLATION = { credentialless: "" } as unknown as React.IframeHTMLAttributes<HTMLIFrameElement>

// Lightweight placeholder shown while the preview panel is being dragged:
// keeps the heavy iframe from re-laying-out on every resize frame.
function PreviewResizePlaceholder() {
  return <div data-preview-resize-placeholder className="h-full w-full bg-muted/30" aria-hidden="true" />
}

function escapeClosingScriptTag(code: string) {
  return code.replace(/<\/script/gi, '<\\/script')
}

function getSourceLanguage(preview: CodePreviewPayload): BundledLanguage | null {
  if (preview.kind === 'source') {
    return preview.language in bundledLanguages ? preview.language as BundledLanguage : null
  }

  switch (preview.kind) {
    case 'html':
      return 'html'
    case 'svg':
      return 'xml'
    case 'css':
      return 'css'
    case 'javascript':
      return 'javascript'
    case 'markdown':
      return 'markdown'
    case 'mermaid':
      return null
  }
}

function getDownloadExtension(preview: CodePreviewPayload) {
  const language = preview.language.toLowerCase()
  const extensionByLanguage: Record<string, string> = {
    html: 'html',
    htm: 'html',
    xhtml: 'html',
    svg: 'svg',
    xml: 'xml',
    css: 'css',
    js: 'js',
    javascript: 'js',
    mjs: 'mjs',
    markdown: 'md',
    md: 'md',
    mermaid: 'mmd',
    mmd: 'mmd',
    ts: 'ts',
    typescript: 'ts',
    tsx: 'tsx',
    jsx: 'jsx',
    json: 'json',
    python: 'py',
    py: 'py',
    go: 'go',
    rust: 'rs',
    rs: 'rs',
    java: 'java',
    sql: 'sql',
    sh: 'sh',
    bash: 'sh',
    yaml: 'yaml',
    yml: 'yml',
  }

  return extensionByLanguage[language] ?? 'txt'
}

function buildPreviewDocument(preview: CodePreviewPayload) {
  switch (preview.kind) {
    case 'html':
      return preview.code
    case 'svg':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body { min-height: 100%; margin: 0; background: #fff; }
    body { display: grid; place-items: center; padding: 24px; box-sizing: border-box; }
    svg { max-width: 100%; height: auto; }
  </style>
</head>
<body>${preview.code}</body>
</html>`
    case 'css':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; padding: 32px; font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; }
    .preview-card { max-width: 720px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 16px; background: white; padding: 24px; box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08); }
    .preview-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
    button, input { border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 14px; font: inherit; }
    button { cursor: pointer; background: #0f172a; color: white; }
    ${preview.code}
  </style>
</head>
<body>
  <main class="preview-card">
    <p class="preview-kicker">CSS Preview</p>
    <h1>Preview Card</h1>
    <p>This sample page provides headings, paragraphs, buttons, cards, lists, and form controls for the CSS block.</p>
    <ul>
      <li>First sample item</li>
      <li>Second sample item</li>
    </ul>
    <div class="preview-actions">
      <button>Primary button</button>
      <input placeholder="Sample input" />
    </div>
  </main>
</body>
</html>`
    case 'javascript':
      return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; padding: 32px; font-family: system-ui, sans-serif; background: #fff; color: #111827; }
    #console { margin-top: 24px; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
    #console-title { background: #f3f4f6; padding: 10px 12px; font-weight: 600; font-size: 13px; }
    #console-output { min-height: 64px; padding: 12px; white-space: pre-wrap; font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
    .warn { color: #b45309; }
    .error { color: #dc2626; }
  </style>
</head>
<body>
  <h1>JavaScript Preview</h1>
  <p>The script runs in this sandboxed iframe.</p>
  <div id="console">
    <div id="console-title">Console</div>
    <div id="console-output"></div>
  </div>
  <script>
    const output = document.getElementById('console-output');
    const write = (type, args) => {
      const line = document.createElement('div');
      line.className = type;
      line.textContent = args.map((value) => {
        if (typeof value === 'string') return value;
        try { return JSON.stringify(value); } catch { return String(value); }
      }).join(' ');
      output.appendChild(line);
    };
    ['log', 'warn', 'error'].forEach((type) => {
      const original = console[type].bind(console);
      console[type] = (...args) => {
        write(type, args);
        original(...args);
      };
    });
    window.addEventListener('error', (event) => write('error', [event.message]));
  </script>
  <script>${escapeClosingScriptTag(preview.code)}</script>
</body>
</html>`
    default:
      return ''
  }
}

async function getMermaidRenderer(theme: MermaidTheme) {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid')
  }

  const { default: mermaid } = await mermaidModulePromise
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme,
  })

  return mermaid
}

function getMermaidRenderErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Failed to render Mermaid chart'
}

function clampMermaidZoom(zoom: number) {
  return Math.min(MERMAID_MAX_ZOOM, Math.max(MERMAID_MIN_ZOOM, zoom))
}

function downloadMermaidSvg(svg: string) {
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

function MermaidPreview({ code }: { code: string }) {
  const t = useTranslations('chat.message')
  const { resolvedTheme } = useTheme()
  const theme: MermaidTheme = resolvedTheme === 'dark' ? 'dark' : 'default'
  const [svg, setSvg] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [isRendering, setIsRendering] = React.useState(true)
  const [zoom, setZoom] = React.useState(1)
  const [pan, setPan] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const dragStartRef = React.useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  const viewportRef = React.useRef<HTMLDivElement>(null)
  const diagramRef = React.useRef<HTMLDivElement>(null)
  const zoomRef = React.useRef(1)
  const gestureStartZoomRef = React.useRef(1)

  React.useEffect(() => {
    let cancelled = false
    setSvg('')
    setError(null)
    setIsRendering(true)

    void (async () => {
      try {
        const mermaid = await getMermaidRenderer(theme)
        const id = `mermaid-preview-${Math.random().toString(36).slice(2)}`
        const { svg: renderedSvg } = await mermaid.render(id, code)
        if (!cancelled) {
          setSvg(renderedSvg)
          setIsRendering(false)
        }
      } catch (renderError) {
        if (!cancelled) {
          setError(getMermaidRenderErrorMessage(renderError))
          setIsRendering(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [code, theme])

  React.useEffect(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
    setIsDragging(false)
    zoomRef.current = 1
    gestureStartZoomRef.current = 1
  }, [code])

  const handleWheel = React.useCallback((event: WheelEvent) => {
    if (!svg || event.deltaY === 0) {
      return
    }

    event.preventDefault()
    const deltaModeFactor = event.deltaMode === 1
      ? 16
      : event.deltaMode === 2
        ? viewportRef.current?.clientHeight ?? 1
        : 1
    const delta = event.deltaY * deltaModeFactor
    const nextZoom = clampMermaidZoom(zoomRef.current * Math.exp(-delta * 0.0025))
    zoomRef.current = nextZoom
    setZoom(nextZoom)
  }, [svg])

  const handleGestureStart = React.useCallback((event: Event) => {
    event.preventDefault()
    gestureStartZoomRef.current = zoomRef.current
  }, [])

  const handleGestureChange = React.useCallback((event: Event) => {
    event.preventDefault()
    if (!svg) {
      return
    }

    const scale = (event as Event & { scale?: number }).scale
    if (typeof scale !== 'number' || !Number.isFinite(scale) || scale <= 0) {
      return
    }

    const nextZoom = clampMermaidZoom(gestureStartZoomRef.current * scale)
    zoomRef.current = nextZoom
    setZoom(nextZoom)
  }, [svg])

  const handleGestureEnd = React.useCallback((event: Event) => {
    event.preventDefault()
  }, [])

  React.useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport || !svg) {
      return
    }

    const gestureOptions = { passive: false }
    viewport.addEventListener('wheel', handleWheel, gestureOptions)
    viewport.addEventListener('gesturestart', handleGestureStart, gestureOptions)
    viewport.addEventListener('gesturechange', handleGestureChange, gestureOptions)
    viewport.addEventListener('gestureend', handleGestureEnd, gestureOptions)

    return () => {
      viewport.removeEventListener('wheel', handleWheel)
      viewport.removeEventListener('gesturestart', handleGestureStart)
      viewport.removeEventListener('gesturechange', handleGestureChange)
      viewport.removeEventListener('gestureend', handleGestureEnd)
    }
  }, [handleGestureChange, handleGestureEnd, handleGestureStart, handleWheel, svg])

  React.useEffect(() => {
    if (!diagramRef.current) {
      return
    }

    diagramRef.current.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
    zoomRef.current = zoom
  }, [pan, zoom])

  const handleDownloadSvg = React.useCallback(() => {
    if (!svg) {
      return
    }
    downloadMermaidSvg(svg)
  }, [svg])

  const handleFitToView = React.useCallback(() => {
    const viewport = viewportRef.current
    const diagram = diagramRef.current
    const svgElement = diagram?.querySelector('svg')
    if (!viewport || !diagram || !svgElement) {
      return
    }

    const viewportRect = viewport.getBoundingClientRect()
    const svgRect = svgElement.getBoundingClientRect()
    if (viewportRect.width <= 0 || viewportRect.height <= 0 || svgRect.width <= 0 || svgRect.height <= 0) {
      return
    }

    const nextZoom = clampMermaidZoom(Math.min(
      (viewportRect.width - 48) / svgRect.width * zoom,
      (viewportRect.height - 48) / svgRect.height * zoom
    ))

    zoomRef.current = nextZoom
    setZoom(nextZoom)
    setPan({ x: 0, y: 0 })
    setIsDragging(false)
  }, [zoom])

  const handlePointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!svg) {
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
  }, [pan.x, pan.y, svg])

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
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

  const handlePointerUp = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
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

  if (isRendering) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{t('mermaidRendering')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full overflow-auto p-6">
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 dark:border-red-900/60 dark:bg-red-950/30">
          <p className="font-mono text-red-700 text-sm dark:text-red-300">
            {t('mermaidError', { error })}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-full min-h-0 bg-background">
      <div
        ref={viewportRef}
        className={`flex h-full min-h-0 items-center justify-center overflow-hidden p-6 select-none ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div
          ref={diagramRef}
          className="max-w-full origin-center transition-transform will-change-transform"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
      <div
        data-slot="mermaid-preview-controls"
        className="absolute right-4 top-4 z-10 flex items-center gap-1 rounded-md border bg-background p-1 shadow-sm"
      >
        <Tooltip>
          <TooltipTrigger
            onClick={handleFitToView}
            disabled={!svg}
            render={
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidFitToView')}>
                <Expand className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('mermaidFitToView')}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            onClick={() => setZoom((current) => clampMermaidZoom(current - MERMAID_ZOOM_STEP))}
            disabled={zoom <= MERMAID_MIN_ZOOM}
            render={
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidZoomOut')}>
                <ZoomOut className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('mermaidZoomOut')}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            onClick={() => setZoom((current) => clampMermaidZoom(current + MERMAID_ZOOM_STEP))}
            disabled={zoom >= MERMAID_MAX_ZOOM}
            render={
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidZoomIn')}>
                <ZoomIn className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('mermaidZoomIn')}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger
            onClick={handleDownloadSvg}
            disabled={!svg}
            render={
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidDownload')}>
                <Download className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('mermaidDownload')}</TooltipContent>
        </Tooltip>
      </div>
    </div>
  )
}
type ArtifactPreviewMode = 'image' | 'video' | 'audio' | 'pdf' | 'html' | 'markdown' | 'mermaid' | 'text' | 'unsupported'

function getArtifactPreviewMode(file: ArtifactPreviewPayload['file']): ArtifactPreviewMode {
  const mimeType = file.mimeType?.toLowerCase() ?? ''
  const filename = file.filename.toLowerCase()
  if (mimeType.startsWith('image/') || /\.(?:png|jpe?g|gif|webp|svg)$/.test(filename)) return 'image'
  if (mimeType.startsWith('video/') || /\.(?:mp4|webm|mov)$/.test(filename)) return 'video'
  if (mimeType.startsWith('audio/') || /\.(?:mp3|wav|ogg|m4a)$/.test(filename)) return 'audio'
  if (mimeType === 'application/pdf' || filename.endsWith('.pdf')) return 'pdf'
  if (mimeType === 'text/html' || /\.x?html?$/.test(filename)) return 'html'
  if (mimeType === 'text/markdown' || /\.(?:md|markdown)$/.test(filename)) return 'markdown'
  if (/\.(?:mmd|mermaid)$/.test(filename)) return 'mermaid'
  if (
    mimeType.startsWith('text/')
    || mimeType.includes('json')
    || mimeType.includes('javascript')
    || mimeType === 'application/xml'
    || mimeType.endsWith('+xml')
    || /\.(?:txt|csv|json|ya?ml|xml|js|jsx|ts|tsx|py|sql|sh)$/.test(filename)
  ) return 'text'
  return 'unsupported'
}

function ArtifactPreviewCanvas({
  preview,
  onClose,
  isResizing,
}: {
  preview: ArtifactPreviewPayload
  onClose: () => void
  isResizing?: boolean
}) {
  const t = useTranslations('chat.message')
  const file = preview.file
  const mode = React.useMemo(() => getArtifactPreviewMode(file), [file])
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null)
  const [textContent, setTextContent] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(mode !== 'unsupported')
  const [loadFailed, setLoadFailed] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    let createdObjectUrl: string | null = null
    setPreviewUrl(null)
    setTextContent('')
    setLoadFailed(false)

    if (!file.url || mode === 'unsupported') {
      if (!file.url) setLoadFailed(true)
      setIsLoading(false)
      return
    }

    let resolvedUrl: URL
    try {
      resolvedUrl = new URL(file.url, window.location.href)
      if (resolvedUrl.origin !== window.location.origin) {
        throw new Error('Artifact preview URL must be same-origin')
      }
    } catch {
      setIsLoading(false)
      setLoadFailed(true)
      return
    }

    setIsLoading(true)
    void fetch(resolvedUrl, { credentials: 'same-origin' })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Artifact preview failed with ${response.status}`)
        }
        if (mode === 'text' || mode === 'markdown' || mode === 'mermaid') {
          const content = await response.text()
          if (!cancelled) setTextContent(content)
          return
        }
        createdObjectUrl = URL.createObjectURL(await response.blob())
        if (cancelled) {
          URL.revokeObjectURL(createdObjectUrl)
          createdObjectUrl = null
          return
        }
        setPreviewUrl(createdObjectUrl)
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
      if (createdObjectUrl) URL.revokeObjectURL(createdObjectUrl)
    }
  }, [file.url, mode])

  const handleDownload = React.useCallback(() => {
    if (!file.url) return
    const link = document.createElement('a')
    link.href = file.url
    link.download = file.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [file.filename, file.url])

  let body: React.ReactNode
  if (isLoading) {
    body = (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{t('artifactPreviewLoading')}</span>
      </div>
    )
  } else if (loadFailed || mode === 'unsupported') {
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-muted-foreground">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
          <FileText className="h-6 w-6" />
        </div>
        <p className="max-w-sm text-sm">{t(loadFailed ? 'artifactPreviewLoadError' : 'artifactPreviewUnavailable')}</p>
      </div>
    )
  } else if (mode === 'image' && previewUrl) {
    body = <img src={previewUrl} alt={file.filename} className="h-full w-full object-contain p-6" />
  } else if (mode === 'video' && previewUrl) {
    body = <video src={previewUrl} controls playsInline className="h-full w-full bg-black object-contain" />
  } else if (mode === 'audio' && previewUrl) {
    body = <div className="flex h-full items-center justify-center p-8"><audio src={previewUrl} controls className="w-full max-w-xl" /></div>
  } else if (mode === 'pdf' && previewUrl) {
    body = <iframe title={file.filename} src={previewUrl} className="h-full w-full border-0 bg-white" />
  } else if (mode === 'html' && previewUrl) {
    body = isResizing ? <PreviewResizePlaceholder /> : <iframe title={file.filename} src={previewUrl} sandbox="allow-scripts" {...IFRAME_PROCESS_ISOLATION} className="h-full w-full border-0 bg-white" />
  } else if (mode === 'markdown') {
    body = <div className="h-full overflow-auto p-6"><Streamdown>{textContent}</Streamdown></div>
  } else if (mode === 'mermaid') {
    body = <MermaidPreview code={textContent} />
  } else {
    body = <pre className="h-full overflow-auto p-4 text-sm"><code>{textContent}</code></pre>
  }

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{t('artifactPreviewCanvasTitle')}</div>
          <div className="truncate text-xs text-muted-foreground">{file.filename}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Tooltip>
            <TooltipTrigger
              onClick={handleDownload}
              disabled={!file.url}
              render={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidDownloadLabel')}>
                  <Download className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent>{t('mermaidDownloadLabel')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={onClose}
              render={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('closeCodePreview')}>
                  <X className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent>{t('closeCodePreview')}</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">{body}</div>
    </div>
  )
}

function CodeContentPreviewCanvas({
  preview,
  onClose,
  isResizing,
}: {
  preview: CodePreviewPayload
  onClose: () => void
  isResizing?: boolean
}) {
  const t = useTranslations('chat.message')
  const sourceLanguage = getSourceLanguage(preview)
  const [copied, setCopied] = React.useState(false)
  const [activeTab, setActiveTab] = React.useState(preview.kind === 'source' ? 'source' : 'preview')
  const srcDoc = React.useMemo(() => (
    preview.kind === 'markdown' || preview.kind === 'source' || preview.kind === 'mermaid' ? '' : buildPreviewDocument(preview)
  ), [preview])

  React.useEffect(() => {
    setActiveTab(preview.kind === 'source' ? 'source' : 'preview')
  }, [preview])

  const handleCopy = React.useCallback(async () => {
    await navigator.clipboard.writeText(preview.code)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }, [preview.code])

  const handleDownload = React.useCallback(() => {
    const blob = new Blob([preview.code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `code.${getDownloadExtension(preview)}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }, [preview])

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="min-h-0 flex-1 gap-0">
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="flex min-w-0 items-center gap-3">
          <TabsList>
            {preview.kind !== 'source' && (
              <TabsTrigger value="preview">{t('codePreview')}</TabsTrigger>
            )}
            <TabsTrigger value="source">{t('codeSource')}</TabsTrigger>
          </TabsList>
          <span className="truncate text-sm font-medium uppercase">{preview.language}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {preview.kind !== 'markdown' && preview.kind !== 'source' && preview.kind !== 'mermaid' && (
            <span className="mr-2 hidden text-xs text-muted-foreground lg:inline">
              {t('previewScriptsEnabled')}
            </span>
          )}
          <Tooltip>
            <TooltipTrigger
              onClick={handleCopy}
              render={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={copied ? t('copied') : t('copy')}>
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              }
            />
            <TooltipContent>{copied ? t('copied') : t('copy')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={handleDownload}
              render={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('mermaidDownloadLabel')}>
                  <Download className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent>{t('mermaidDownloadLabel')}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger
              onClick={onClose}
              render={
                <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('closeCodePreview')}>
                  <X className="h-4 w-4" />
                </Button>
              }
            />
            <TooltipContent>{t('closeCodePreview')}</TooltipContent>
          </Tooltip>
        </div>
      </div>
        {preview.kind !== 'source' && (
          <TabsContent value="preview" className="min-h-0 overflow-hidden p-0">
            {preview.kind === 'markdown' ? (
              <div className="h-full overflow-auto p-6">
                <Streamdown>{preview.code}</Streamdown>
              </div>
            ) : preview.kind === 'mermaid' ? (
              <MermaidPreview code={preview.code} />
            ) : isResizing ? (
              <PreviewResizePlaceholder />
            ) : (
              <iframe
                title={t('codePreview')}
                sandbox="allow-scripts"
                {...IFRAME_PROCESS_ISOLATION}
                srcDoc={srcDoc}
                className="h-full w-full border-0 bg-white"
              />
            )}
          </TabsContent>
        )}

        <TabsContent value="source" className="min-h-0 overflow-auto p-0">
          {sourceLanguage ? (
            <CodeBlock
              code={preview.code}
              language={sourceLanguage}
              showLineNumbers
              className="h-full rounded-none border-0 [&>div]:h-full [&>div>div]:h-full [&_pre]:min-h-full"
            />
          ) : (
            <pre className="h-full overflow-auto p-4 text-sm"><code>{preview.code}</code></pre>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

function SourceDocumentPreviewCanvas({
  preview,
  onClose,
}: {
  preview: SourceDocumentPreviewPayload
  onClose: () => void
}) {
  const t = useTranslations('chat.source')
  const [visibleSegmentCount, setVisibleSegmentCount] = React.useState(SOURCE_SEGMENT_BATCH_SIZE)
  const visibleSegments = preview.segments.slice(0, visibleSegmentCount)
  const hiddenSegmentCount = preview.segments.length - visibleSegments.length

  return (
    <div className="flex h-full min-w-0 flex-col bg-background">
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <h3 className="flex min-w-0 items-center gap-2 font-semibold">
          <FileText className="h-4 w-4 shrink-0" />
          <span className="truncate">{preview.documentName}</span>
        </h3>
        <Tooltip>
          <TooltipTrigger
            onClick={onClose}
            render={
              <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={t('close')}>
                <X className="h-4 w-4" />
              </Button>
            }
          />
          <TooltipContent>{t('close')}</TooltipContent>
        </Tooltip>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="space-y-2">
          {visibleSegments.map((segment, index) => (
            <SegmentItem
              key={segment.sourceId ?? `${preview.documentId}:${segment.metadata?.page ?? index}:${index}`}
              segment={segment}
              index={index}
            />
          ))}
          {hiddenSegmentCount > 0 && (
            <button
              type="button"
              onClick={() => setVisibleSegmentCount((count) => count + SOURCE_SEGMENT_BATCH_SIZE)}
              className="w-full rounded-md border border-dashed py-2 text-sm text-primary hover:bg-muted/50 transition-colors"
            >
              {t('showMoreSegments', { count: Math.min(hiddenSegmentCount, SOURCE_SEGMENT_BATCH_SIZE) })}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function CodePreviewCanvas({
  preview,
  onClose,
  isResizing,
}: {
  preview: ChatPreviewPayload
  onClose: () => void
  isResizing?: boolean
}) {
  if (preview.kind === 'artifact') {
    return <ArtifactPreviewCanvas preview={preview} onClose={onClose} isResizing={isResizing} />
  }
  if (preview.kind === 'source-document') {
    return <SourceDocumentPreviewCanvas preview={preview} onClose={onClose} />
  }
  return <CodeContentPreviewCanvas preview={preview} onClose={onClose} isResizing={isResizing} />
}
