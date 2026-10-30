'use client'

import * as React from 'react'
import type { IframeHTMLAttributes } from 'react'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'
import { useTranslations } from 'next-intl'
import { AlertTriangle, Download, Expand, ShieldAlert, ZoomIn, ZoomOut, X } from 'lucide-react'
import { Streamdown } from 'streamdown'
import {
  createViewerLabels,
  ViewerI18nProvider,
} from '@/components/extend/viewer-i18n'
import { PreviewZoomViewport, type PreviewZoomFitMode } from './preview-zoom-viewport'
import { getFilePreviewMode, type FilePreviewMode, type PreviewFile } from './file-preview-types'

const PdfPreview = dynamic(
  () => import('@/components/extend/pdf-viewer').then((mod) => mod.PDFViewer),
  { ssr: false },
)

const DocxPreview = dynamic(
  () => import('@/components/extend/docx-viewer').then((mod) => mod.DocxViewerPreview),
  { ssr: false },
)

const PptxPreview = dynamic(
  () => import('@/components/extend/pptx-viewer').then((mod) => mod.PptxViewerPreview),
  { ssr: false },
)

const SpreadsheetPreview = dynamic(
  () => import('@/components/extend/xlsx-viewer').then((mod) => mod.XlsxViewerPreview),
  { ssr: false },
)

const CsvPreview = dynamic(
  () => import('@/components/extend/csv-viewer').then((mod) => mod.CsvViewer),
  { ssr: false },
)

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
  toggleThumbnails?: string
  thumbnails?: string
  fitToWidth?: string
  pageNumber?: (values: { page: number }) => string
}

export interface FilePreviewPanelProps {
  file: PreviewFile
  labels?: Partial<FilePreviewLabels>
  loadFile?: () => Promise<Blob>
  locale?: string
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
  toggleThumbnails: 'Toggle thumbnails',
  thumbnails: 'Thumbnails',
  fitToWidth: 'Fit to width',
  pageNumber: ({ page }) => `Page ${page}`,
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
  return mode === 'text' || mode === 'markdown' || mode === 'mermaid' || mode === 'csv'
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

/** CSV exports are often GBK; try UTF-8 first and fall back to GB18030. */
function decodeCsvBytes(bytes: Uint8Array): string {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return new TextDecoder('gb18030').decode(bytes)
  }
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

function isProtectedRawUrl(url: string | undefined): boolean {
  if (!url) return false
  try {
    return new URL(url, window.location.href).pathname.startsWith('/api/v1/')
  } catch {
    return false
  }
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
  const { resolvedTheme } = useTheme()
  const tViewer = useTranslations('common.fileViewer')
  const viewerLabels = React.useMemo(() => createViewerLabels(tViewer), [tViewer])
  const [isDark, setIsDark] = React.useState(false)
  const [status, setStatus] = React.useState<PreviewStatus>(mode === 'unsupported' ? 'unsupported' : 'loading')
  const [blob, setBlob] = React.useState<Blob | null>(null)
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null)
  const [textContent, setTextContent] = React.useState('')
  const htmlPreviewIframeRef = React.useRef<HTMLIFrameElement>(null)

  React.useEffect(() => {
    setIsDark(resolvedTheme === 'dark')
  }, [resolvedTheme])

  React.useLayoutEffect(() => {
    const iframe = htmlPreviewIframeRef.current
    if (!iframe) return

    if (isResizing) {
      iframe.style.width = `${iframe.getBoundingClientRect().width}px`
      iframe.style.maxWidth = 'none'
    } else {
      iframe.style.removeProperty('width')
      iframe.style.removeProperty('max-width')
    }
  }, [isResizing, mode, previewUrl])

  React.useEffect(() => {
    let cancelled = false
    let createdObjectUrl: string | null = null

    setStatus(mode === 'unsupported' ? 'unsupported' : 'loading')
    setBlob(null)
    setPreviewUrl(null)
    setTextContent('')

    if (mode === 'unsupported' && !loadFile) return
    if (mode !== 'unsupported' && !loadFile && file.size !== undefined && file.size > maxPreviewBytes) {
      setStatus('too-large')
      return
    }

    const applyBlob = async (loadedBlob: Blob): Promise<boolean> => {
      if (loadedBlob.size > maxPreviewBytes) {
        if (!cancelled) setStatus('too-large')
        return false
      }
      if (isTextMode(mode)) {
        const content = mode === 'csv'
          ? decodeCsvBytes(new Uint8Array(await loadedBlob.arrayBuffer()))
          : await readBlobText(loadedBlob)
        if (!cancelled) setTextContent(content)
        return true
      }

      createdObjectUrl = URL.createObjectURL(loadedBlob)
      if (cancelled) {
        URL.revokeObjectURL(createdObjectUrl)
        createdObjectUrl = null
        return false
      }
      setPreviewUrl(createdObjectUrl)
      return true
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
            decoded = mode === 'csv'
              ? decodeCsvBytes(merged)
              : new TextDecoder().decode(merged)
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
        if (!(await applyBlob(loadedBlob))) return
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
    const href = previewUrl || loadedBlobUrl || (isProtectedRawUrl(file.url) ? null : file.url)
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
    status === 'unauthorized'
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
  } else if (mode === 'pdf' && previewUrl) {
    body = (
      <PdfPreview
        src={previewUrl}
        fileName={file.filename}
        className="h-full w-full"
        defaultZoom="automatic"
        showUpload={false}
      />
    )
  } else if (mode === 'html' && previewUrl) {
    // Keep the blob-backed document mounted while resizing; remounting reloads its embedded resources.
    body = <iframe
      title={file.filename}
      src={previewUrl}
      sandbox="allow-scripts"
      ref={htmlPreviewIframeRef}
      {...IFRAME_PROCESS_ISOLATION}
      className={isResizing ? 'h-full w-full border-0 bg-white pointer-events-none' : 'h-full w-full border-0 bg-white'}
      tabIndex={isResizing ? -1 : undefined}
    />
  } else if (mode === 'docx' && previewUrl) {
    body = (
      <DocxPreview
        src={previewUrl}
        fileName={file.filename}
        className="h-full w-full"
        defaultZoom="automatic"
        isDark={isDark}
        onIsDarkChange={setIsDark}
        showUpload={false}
      />
    )
  } else if (mode === 'pptx' && previewUrl) {
    body = (
      <PptxPreview
        src={previewUrl}
        fileName={file.filename}
        className="h-full w-full"
        defaultZoom="automatic"
        showUpload={false}
      />
    )
  } else if (mode === 'spreadsheet' && previewUrl) {
    body = (
      <SpreadsheetPreview
        src={previewUrl}
        fileName={file.filename}
        className="h-full w-full"
        isDark={isDark}
        onIsDarkChange={setIsDark}
        showUpload={false}
      />
    )
  } else if (mode === 'csv') {
    body = <CsvPreview data={textContent} className="h-full w-full" />
  } else if (mode === 'markdown') {
    body = <div className="h-full overflow-auto p-6"><Streamdown>{textContent}</Streamdown></div>
  } else if (mode === 'mermaid') {
    body = <MermaidFilePreview code={textContent} />
  } else {
    body = <pre className="h-full overflow-auto p-4 text-sm"><code>{textContent}</code></pre>
  }
  const zoomFitMode = status === 'ready' ? getZoomFitMode(mode) : null
  const previewBody = (
    <ViewerI18nProvider labels={viewerLabels}>
      {zoomFitMode ? (
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
      ) : body}
    </ViewerI18nProvider>
  )

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
            disabled={status === 'forbidden' || status === 'unauthorized' || (!file.url && !blob && !previewUrl) || (isProtectedRawUrl(file.url) && !blob && !previewUrl)}
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
