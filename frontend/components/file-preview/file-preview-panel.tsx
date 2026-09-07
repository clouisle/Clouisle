'use client'

import * as React from 'react'
import type { IframeHTMLAttributes } from 'react'
import { AlertTriangle, Download, Expand, ShieldAlert, ZoomIn, ZoomOut, X } from 'lucide-react'
import { Streamdown } from 'streamdown'
import { DocxPreview } from './docx-preview'
import { PdfPreview } from './pdf-preview'
import { PptxPreview } from './pptx-preview'
import { PreviewZoomViewport, type PreviewZoomFitMode } from './preview-zoom-viewport'
import { SpreadsheetPreview } from './spreadsheet-preview'
import { getFilePreviewMode, type FilePreviewMode, type PreviewFile } from './file-preview-types'

export interface FilePreviewLabels {
  title: string
  loading: string
  unavailable: string
  loadError: string
  permissionDenied?: string
  unauthorized?: string
  tooLarge: string
  download: string
  close: string
  sheet: string
  rowsLimited: (values: { rows: number; columns: number }) => string
  parseError: string
  zoomIn: string
  zoomOut: string
  fitToView: string
}

export interface FilePreviewPanelProps {
  file: PreviewFile
  labels?: Partial<FilePreviewLabels>
  loadFile?: () => Promise<Blob>
  onClose?: () => void
  isResizing?: boolean
  maxPreviewBytes?: number
  className?: string
}

const DEFAULT_MAX_PREVIEW_BYTES = 20 * 1024 * 1024
const DEFAULT_LABELS: FilePreviewLabels = {
  title: 'File preview',
  loading: 'Loading preview...',
  unavailable: 'This file type cannot be previewed here. Download the file to open it.',
  loadError: 'The file preview could not be loaded. Download the file to open it.',
  permissionDenied: 'You do not have permission to view or download this file.',
  unauthorized: 'You need to be logged in to view or download this file.',
  tooLarge: 'This file is too large to preview. Download the file to open it.',
  download: 'Download',
  close: 'Close',
  sheet: 'Sheet',
  rowsLimited: ({ rows, columns }) => `Showing the first ${rows} rows and ${columns} columns.`,
  parseError: 'The file could not be read. Download the file to open it.',
  zoomIn: 'Zoom in',
  zoomOut: 'Zoom out',
  fitToView: 'Fit to view',
}
const IFRAME_PROCESS_ISOLATION = { credentialless: '' } as unknown as IframeHTMLAttributes<HTMLIFrameElement>

type PreviewStatus = 'loading' | 'ready' | 'error' | 'too-large' | 'unsupported' | 'forbidden' | 'unauthorized'

let mermaidModulePromise: Promise<typeof import('mermaid')> | null = null

function MermaidFilePreview({ code }: { code: string }) {
  const [svg, setSvg] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [zoom, setZoom] = React.useState(1)
  const [pan, setPan] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const dragRef = React.useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  const id = React.useId().replace(/:/g, '_')

  React.useEffect(() => {
    let cancelled = false
    mermaidModulePromise ??= import('mermaid')
    void mermaidModulePromise
      .then((mod) => {
        const mermaid = mod.default
        mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' })
        return mermaid.render(`mermaid_${id}`, code)
      })
      .then(({ svg: renderedSvg }) => {
        if (!cancelled) {
          setSvg(renderedSvg)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram')
        }
      })
    return () => {
      cancelled = true
    }
  }, [code, id])

  if (error) {
    return <pre className="h-full overflow-auto p-4 text-xs text-destructive"><code>{code}</code></pre>
  }

  return (
    <div className="relative h-full min-h-0 bg-background">
      <div
        className={`flex h-full min-h-0 items-center justify-center overflow-hidden p-6 select-none ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        onPointerDown={(e) => {
          dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }
          setIsDragging(true)
          ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          if (!isDragging) return
          setPan({
            x: dragRef.current.panX + (e.clientX - dragRef.current.x),
            y: dragRef.current.panY + (e.clientY - dragRef.current.y),
          })
        }}
        onPointerUp={(e) => {
          if (!isDragging) return
          setIsDragging(false)
          try {
            ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
          } catch {
            // ignore
          }
        }}
        onPointerCancel={() => setIsDragging(false)}
      >
        <div
          className="max-w-full origin-center transition-transform will-change-transform"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
      <div className="absolute right-4 top-4 z-10 flex items-center gap-1 rounded-md border bg-background p-1 shadow-sm">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
          onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }}
        >
          <Expand className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
          onClick={() => setZoom((z) => Math.max(0.2, z - 0.1))}
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent"
          onClick={() => setZoom((z) => Math.min(5, z + 0.1))}
        >
          <ZoomIn className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

function isTextMode(mode: FilePreviewMode): boolean {
  return mode === 'text' || mode === 'markdown' || mode === 'mermaid'
}
function getZoomFitMode(mode: FilePreviewMode): PreviewZoomFitMode | null {
  switch (mode) {
    case 'image':
    case 'video':
      return 'contain'
    default:
      return null
  }
}

function readBlobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text()
  return new Response(blob).text()
}

async function fetchPreviewResponse(url: string): Promise<Response> {
  let resolvedUrl: URL
  try {
    resolvedUrl = new URL(url, window.location.href)
    if (resolvedUrl.origin !== window.location.origin) {
      throw new Error('File preview URL must be same-origin')
    }
  } catch {
    throw new Error('Invalid file preview URL')
  }

  const response = await fetch(resolvedUrl, { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`File preview failed with ${response.status}`)
  return response
}

export function FilePreviewPanel({
  file,
  labels,
  loadFile,
  onClose,
  isResizing = false,
  maxPreviewBytes = DEFAULT_MAX_PREVIEW_BYTES,
  className,
}: FilePreviewPanelProps) {
  const mode = React.useMemo(
    () => getFilePreviewMode(file),
    [file],
  )
  const resolvedLabels = {
    ...DEFAULT_LABELS,
    ...labels,
    rowsLimited: labels?.rowsLimited ?? DEFAULT_LABELS.rowsLimited,
  }
  const [status, setStatus] = React.useState<PreviewStatus>(mode === 'unsupported' ? 'unsupported' : 'loading')
  const [blob, setBlob] = React.useState<Blob | null>(null)
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null)
  const [textContent, setTextContent] = React.useState('')
  const [parseFailed, setParseFailed] = React.useState(false)
  const handleDocxError = React.useCallback(() => setParseFailed(true), [])
  const handlePptxError = React.useCallback(() => setParseFailed(true), [])

  React.useEffect(() => {
    let cancelled = false
    let createdObjectUrl: string | null = null

    setStatus(mode === 'unsupported' ? 'unsupported' : 'loading')
    setBlob(null)
    setPreviewUrl(null)
    setTextContent('')
    setParseFailed(false)

    if (mode === 'unsupported' && !loadFile) return
    if (mode !== 'unsupported' && !loadFile && file.size !== undefined && file.size > maxPreviewBytes) {
      setStatus('too-large')
      return
    }

    const applyBlob = async (loadedBlob: Blob) => {
      if (loadedBlob.size > maxPreviewBytes) {
        if (!cancelled) setStatus('too-large')
        return
      }
      if (isTextMode(mode)) {
        const content = await readBlobText(loadedBlob)
        if (!cancelled) setTextContent(content)
        return
      }

      createdObjectUrl = URL.createObjectURL(loadedBlob)
      if (cancelled) {
        URL.revokeObjectURL(createdObjectUrl)
        createdObjectUrl = null
        return
      }
      setPreviewUrl(createdObjectUrl)
    }
    const load = async () => {
      if (loadFile) {
        const loadedBlob = await loadFile()
        if (!cancelled) setBlob(loadedBlob)
        if (mode === 'unsupported') {
          if (!cancelled) setStatus('unsupported')
          return
        }
        if (loadedBlob.size > maxPreviewBytes) {
          if (!cancelled) setStatus('too-large')
          return
        }
        await applyBlob(loadedBlob)
      } else {
        if (!file.url) throw new Error('File preview URL is missing')
        const response = await fetchPreviewResponse(file.url)
        const contentLengthHeader = response.headers?.get('content-length')
        const contentLength = contentLengthHeader ? Number(contentLengthHeader) : 0
        if (contentLength > maxPreviewBytes) throw new Error('File preview is too large')

        if (isTextMode(mode)) {
          let decoded = ''
          if (response.body && typeof response.body.getReader === 'function') {
            const reader = response.body.getReader()
            const chunks: Uint8Array[] = []
            let totalBytes = 0
            while (true) {
              const { done, value } = await reader.read()
              if (done) break
              if (value) {
                totalBytes += value.byteLength
                if (totalBytes > maxPreviewBytes) {
                  void reader.cancel()
                  throw new Error('File preview is too large')
                }
                chunks.push(value)
              }
            }
            const merged = new Uint8Array(totalBytes)
            let offset = 0
            for (const chunk of chunks) {
              merged.set(chunk, offset)
              offset += chunk.byteLength
            }
            decoded = new TextDecoder().decode(merged)
          } else if (typeof response.text === 'function') {
            decoded = await response.text()
            if (new TextEncoder().encode(decoded).byteLength > maxPreviewBytes) {
              throw new Error('File preview is too large')
            }
          }
          if (!cancelled) {
            setBlob(new Blob([decoded], { type: file.mimeType || response.headers?.get('content-type') || 'text/plain' }))
            setTextContent(decoded)
            setStatus('ready')
          }
          return
        }

        const loadedBlob = await response.blob()
        if (!cancelled) setBlob(loadedBlob)
        await applyBlob(loadedBlob)
      }
      if (!cancelled && mode !== 'unsupported') setStatus('ready')
    }

    void load()
      .catch((error: unknown) => {
        if (cancelled) return
        const message = error instanceof Error ? error.message : String(error)
        if (message === 'File preview is too large') {
          setStatus('too-large')
        } else if (message.includes('403') || message.includes('permission_denied') || message.includes('access_denied')) {
          setStatus('forbidden')
        } else if (message.includes('401') || message.includes('not_authenticated') || message.includes('unauthorized')) {
          setStatus('unauthorized')
        } else {
          setStatus('error')
        }
      })

    return () => {
      cancelled = true
      if (createdObjectUrl) URL.revokeObjectURL(createdObjectUrl)
    }
  }, [file.filename, file.mimeType, file.size, file.url, loadFile, maxPreviewBytes, mode])

  const handleDownload = React.useCallback(() => {
    const loadedBlobUrl = !previewUrl && blob ? URL.createObjectURL(blob) : null
    const href = previewUrl || loadedBlobUrl || file.url
    if (!href) return

    const link = document.createElement('a')
    link.href = href
    link.download = file.filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    if (loadedBlobUrl) URL.revokeObjectURL(loadedBlobUrl)
  }, [blob, file.filename, file.url, previewUrl])

  let body: React.ReactNode
  if (status === 'loading') {
    body = (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>{resolvedLabels.loading}</span>
      </div>
    )
  } else if (
    status === 'too-large' ||
    status === 'error' ||
    status === 'unsupported' ||
    status === 'forbidden' ||
    status === 'unauthorized' ||
    parseFailed
  ) {
    const message = status === 'too-large'
      ? resolvedLabels.tooLarge
      : status === 'unsupported'
        ? resolvedLabels.unavailable
        : status === 'forbidden'
          ? (resolvedLabels.permissionDenied || resolvedLabels.loadError)
          : status === 'unauthorized'
            ? (resolvedLabels.unauthorized || resolvedLabels.loadError)
            : resolvedLabels.loadError
    const iconNode = status === 'forbidden' || status === 'unauthorized' ? (
      <ShieldAlert className="h-6 w-6 text-destructive" />
    ) : (
      <AlertTriangle className="h-6 w-6 text-amber-500" />
    )
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-muted-foreground">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted/70">
          {iconNode}
        </div>
        <p className="max-w-sm text-sm">{message}</p>
      </div>
    )
  } else if (mode === 'image' && previewUrl) {
    body = <img src={previewUrl} alt={file.filename} className="block max-w-none object-contain p-6" />
  } else if (mode === 'video' && previewUrl) {
    body = <video src={previewUrl} controls playsInline className="block max-w-none bg-black object-contain" />
  } else if (mode === 'audio' && previewUrl) {
    body = <div className="flex h-full items-center justify-center p-8"><audio src={previewUrl} controls className="w-full max-w-xl" /></div>
  } else if (mode === 'pdf' && blob) {
    body = <PdfPreview blob={blob} onError={handleDocxError} />
  } else if (mode === 'html' && previewUrl) {
    body = isResizing
      ? <div data-preview-resize-placeholder className="flex h-full items-center justify-center text-sm text-muted-foreground">{resolvedLabels.loading}</div>
      : <iframe
        title={file.filename}
        src={previewUrl}
        sandbox="allow-scripts"
        {...IFRAME_PROCESS_ISOLATION}
        className="h-full w-full border-0 bg-white"
      />
  } else if (mode === 'docx' && blob) {
    body = <DocxPreview blob={blob} onError={handleDocxError} />
  } else if (mode === 'pptx' && blob) {
    body = <PptxPreview blob={blob} onError={handlePptxError} />
  } else if (mode === 'spreadsheet' && blob) {
    body = (
      <SpreadsheetPreview
        blob={blob}
        labels={{
          loading: resolvedLabels.loading,
          sheet: resolvedLabels.sheet,
          rowsLimited: resolvedLabels.rowsLimited,
          parseError: resolvedLabels.parseError,
        }}
        onError={handleDocxError}
      />
    )
  } else if (mode === 'markdown') {
    body = <div className="h-full overflow-auto p-6"><Streamdown>{textContent}</Streamdown></div>
  } else if (mode === 'mermaid') {
    body = <MermaidFilePreview code={textContent} />
  } else {
    body = <pre className="h-full overflow-auto p-4 text-sm"><code>{textContent}</code></pre>
  }
  const zoomFitMode = status === 'ready' && !parseFailed ? getZoomFitMode(mode) : null
  const previewBody = zoomFitMode ? (
    <PreviewZoomViewport
      fitKey={`${mode}:${file.url || file.filename}`}
      fitMode={zoomFitMode}
      labels={{
        zoomIn: resolvedLabels.zoomIn,
        zoomOut: resolvedLabels.zoomOut,
        fitToView: resolvedLabels.fitToView,
      }}
    >
      {body}
    </PreviewZoomViewport>
  ) : body

  return (
    <div className={`flex h-full min-w-0 flex-col bg-background ${className || ''}`}>
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{resolvedLabels.title}</div>
          <div className="truncate text-xs text-muted-foreground">{file.filename}</div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={handleDownload}
            disabled={status === 'forbidden' || status === 'unauthorized' || (!file.url && !blob && !previewUrl)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
            aria-label={resolvedLabels.download}
          >
            <><Download className="h-4 w-4" /><span className="sr-only">{resolvedLabels.download}</span></>
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              aria-label={resolvedLabels.close}
            >
              <><X className="h-4 w-4" /><span className="sr-only">{resolvedLabels.close}</span></>
            </button>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">{previewBody}</div>
    </div>
  )
}
