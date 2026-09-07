'use client'

import * as React from 'react'
import {
  DocxEditorViewer,
  useDocxEditor,
  useDocxPageThumbnails,
  type DocxPageThumbnailItem,
} from '@extend-ai/react-docx'
import {
  PanelLeft,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

const DOCX_MIME_TYPE =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const DOCX_PAGE_WIDTH_PX = 816
const ZOOM_OPTIONS = [50, 75, 90, 100, 110, 125, 150, 175, 200] as const
const MIN_ZOOM = 25
const MAX_ZOOM = 250

export interface DocxPreviewLabels {
  loading: string
  parseError: string
  zoomIn?: string
  zoomOut?: string
  zoomReset?: string
  toggleThumbnails?: string
  thumbnails?: string
  page?: string
  pageNumber?: (values: { page: number }) => string
  of?: string
  fitToWidth?: string
}
export interface DocxPreviewProps {
  blob: Blob
  filename?: string
  labels?: DocxPreviewLabels
  onError?: () => void
}

function ToolbarTooltip({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <Tooltip>
      <TooltipTrigger render={<span className="inline-flex" />}>
        {children}
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-xs">
        {label}
      </TooltipContent>
    </Tooltip>
  )
}

function DocxThumbnailItemCard({
  thumbnail,
  isActive,
  label,
  onSelect,
}: {
  thumbnail: DocxPageThumbnailItem
  isActive: boolean
  label: string
  onSelect: () => void
}) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null)

  React.useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    thumbnail.paint(canvas)
  }, [thumbnail])

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'group flex flex-col items-center gap-1.5 p-1.5 rounded-lg text-left transition-all hover:bg-accent/60 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring',
        isActive ? 'bg-accent text-accent-foreground font-semibold ring-1 ring-border' : 'text-muted-foreground'
      )}
      aria-label={label}
    >
      <div className="relative overflow-hidden rounded-md border bg-background shadow-xs transition-shadow group-hover:shadow-sm">
        <canvas
          ref={canvasRef}
          width={thumbnail.pixelWidthPx}
          height={thumbnail.pixelHeightPx}
          style={{
            width: `${thumbnail.widthPx}px`,
            height: `${thumbnail.heightPx}px`,
          }}
          className="block bg-white object-contain"
        />
      </div>
      <span className="text-[11px] tabular-nums font-medium">{thumbnail.pageNumber}</span>
    </button>
  )
}

export function DocxPreview({
  blob,
  filename,
  labels,
  onError,
}: DocxPreviewProps) {
  const [isAutoFit, setIsAutoFit] = React.useState(true)
  const [autoFitScale, setAutoFitScale] = React.useState<number>(100)
  const [manualZoomScale, setManualZoomScale] = React.useState<number>(100)
  const [isLoaded, setIsLoaded] = React.useState(false)
  const [sidebarOpen, setSidebarOpen] = React.useState(true)
  const [selectedPageIndex, setSelectedPageIndex] = React.useState(0)

  const viewportRef = React.useRef<HTMLDivElement | null>(null)

  const editor = useDocxEditor()
  const editorRef = React.useRef(editor)
  editorRef.current = editor
  const { thumbnails } = useDocxPageThumbnails(editor, {
    resolution: 110,
    maxWidthPx: 110,
    maxHeightPx: 160,
  })

  const displayFileName = filename || editor.fileName || 'Document.docx'
  const totalPages = editor.totalPages || 1
  const currentPage = editor.currentPage || selectedPageIndex + 1
  const activePageIndex = currentPage - 1
  const effectiveZoomScale = isAutoFit ? autoFitScale : manualZoomScale

  const calculateFitZoom = React.useCallback((viewportWidth: number) => {
    if (!viewportWidth || viewportWidth <= 0) return 100
    // Container horizontal padding is p-6 (24px + 24px = 48px)
    const availableWidth = viewportWidth - 48
    if (availableWidth <= 0) return 100
    const rawScale = Math.floor((availableWidth / DOCX_PAGE_WIDTH_PX) * 100)
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, rawScale))
  }, [])

  // Responsive Fit-to-Width Resize Observer
  React.useEffect(() => {
    const el = viewportRef.current
    if (!el) return

    const updateFit = (width?: number) => {
      const currentWidth = width ?? el.clientWidth
      if (currentWidth > 0) {
        setAutoFitScale(calculateFitZoom(currentWidth))
      }
    }

    updateFit()

    if (typeof ResizeObserver === 'undefined') {
      const handleResize = () => updateFit()
      window.addEventListener('resize', handleResize)
      return () => window.removeEventListener('resize', handleResize)
    }

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      const width = entry?.contentRect?.width ?? el.clientWidth
      updateFit(width)
    })
    observer.observe(el)

    return () => {
      observer.disconnect()
    }
  }, [calculateFitZoom, isLoaded, sidebarOpen])

  // Command / Ctrl + Mouse Wheel Zoom and Pinch Gesture
  const handleWheel = React.useCallback(
    (event: WheelEvent) => {
      if ((!event.ctrlKey && !event.metaKey) || event.deltaY === 0) return

      event.preventDefault()
      const deltaModeFactor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? (viewportRef.current?.clientHeight ?? 1) : 1
      const delta = event.deltaY * deltaModeFactor
      const currentScale = isAutoFit ? autoFitScale : manualZoomScale

      // Exponential smooth zoom factor based on delta
      const factor = Math.exp(-delta * 0.0025)
      const nextScale = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(currentScale * factor)))

      setIsAutoFit(false)
      setManualZoomScale(nextScale)
    },
    [autoFitScale, isAutoFit, manualZoomScale]
  )

  React.useEffect(() => {
    const el = viewportRef.current
    if (!el) return

    const options = { passive: false }
    el.addEventListener('wheel', handleWheel, options)
    return () => {
      el.removeEventListener('wheel', handleWheel)
    }
  }, [handleWheel])

  React.useEffect(() => {
    let cancelled = false
    const file = new File([blob], displayFileName, {
      type: DOCX_MIME_TYPE,
    })

    void editorRef.current
      .importDocxFile(file)
      .then(() => {
        if (!cancelled) {
          setIsLoaded(true)
        }
      })
      .catch(() => {
        if (!cancelled) {
          onError?.()
        }
      })

    return () => {
      cancelled = true
    }
  }, [blob, displayFileName, onError])

  React.useEffect(() => {
    if (editor.importError) {
      onError?.()
    }
  }, [editor.importError, onError])

  const handleZoomIn = React.useCallback(() => {
    setIsAutoFit(false)
    setManualZoomScale((curr) => {
      const base = isAutoFit ? effectiveZoomScale : curr
      const next = ZOOM_OPTIONS.find((v) => v > base)
      return next ?? ZOOM_OPTIONS[ZOOM_OPTIONS.length - 1]
    })
  }, [effectiveZoomScale, isAutoFit])

  const handleZoomOut = React.useCallback(() => {
    setIsAutoFit(false)
    setManualZoomScale((curr) => {
      const base = isAutoFit ? effectiveZoomScale : curr
      const prev = [...ZOOM_OPTIONS].reverse().find((v) => v < base)
      return prev ?? ZOOM_OPTIONS[0]
    })
  }, [effectiveZoomScale, isAutoFit])

  const handleSelectZoom = React.useCallback((val: string | null) => {
    if (!val || val === 'fit') {
      setIsAutoFit(true)
    } else {
      setIsAutoFit(false)
      setManualZoomScale(Number(val))
    }
  }, [])

  const handleResetToFit = React.useCallback(() => {
    setIsAutoFit(true)
  }, [])

  const handleSelectPage = React.useCallback(
    (pageIndex: number) => {
      setSelectedPageIndex(pageIndex)
      if (typeof editor === 'object' && editor !== null && 'revealPage' in editor) {
        const reveal = editor.revealPage
        if (typeof reveal === 'function') {
          reveal(pageIndex)
        }
      }
    },
    [editor]
  )

  if (!isLoaded && editor.isImporting) {
    return (
      <div className="flex h-full w-full items-center justify-center p-8 text-sm text-muted-foreground bg-background">
        <Loader2 className="mr-2 h-4 w-4 animate-spin text-primary" />
        <span>{labels?.loading || 'Loading...'}</span>
      </div>
    )
  }

  return (
    <TooltipProvider delay={200}>
      <div className="flex h-full w-full flex-col overflow-hidden bg-background">
        {/* Streamlined Document Review Toolbar */}
        <div className="flex h-12 min-h-12 shrink-0 items-center justify-between gap-2 border-b bg-background px-3 shadow-2xs z-20">
          <div className="flex items-center gap-1.5 min-w-0">
            {/* Sidebar Toggle */}
            <ToolbarTooltip label={labels?.toggleThumbnails || 'Toggle thumbnails'}>
              <Button
                type="button"
                variant={sidebarOpen ? 'secondary' : 'ghost'}
                size="icon-sm"
                onClick={() => setSidebarOpen((prev) => !prev)}
                className="h-8 w-8"
                aria-label={labels?.toggleThumbnails || 'Toggle thumbnails'}
              >
                <PanelLeft className="h-4 w-4" />
              </Button>
            </ToolbarTooltip>

            {/* Document Title */}
            <div className="mx-2 hidden md:block max-w-[200px] truncate text-xs font-semibold text-foreground/90" title={displayFileName}>
              {displayFileName}
            </div>

            {/* Page indicator */}
            <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground px-2 h-7 rounded-md bg-muted/40">
              <span className="text-foreground">{currentPage}</span>
              <span>/</span>
              <span>{totalPages}</span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Unified Zoom & Reset Controls Group */}
            <div className="flex items-center rounded-lg border bg-background shadow-xs overflow-hidden">
              <ToolbarTooltip label={labels?.zoomOut || 'Zoom Out'}>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={effectiveZoomScale <= MIN_ZOOM}
                  onClick={handleZoomOut}
                  className="h-8 w-8 rounded-none border-r hover:bg-muted"
                  aria-label={labels?.zoomOut || 'Zoom Out'}
                >
                  <ZoomOut className="h-4 w-4" />
                </Button>
              </ToolbarTooltip>

              <Select
                value={isAutoFit ? 'fit' : String(manualZoomScale)}
                onValueChange={handleSelectZoom}
              >
                <SelectTrigger className="h-8 min-w-[92px] rounded-none border-0 px-2.5 text-xs font-semibold focus:ring-0 focus:ring-offset-0">
                  <SelectValue>{isAutoFit ? `${effectiveZoomScale}% (Fit)` : `${effectiveZoomScale}%`}</SelectValue>
                </SelectTrigger>
                <SelectContent align="center" className="min-w-[120px]">
                  <SelectItem value="fit" className="text-xs font-medium">
                    {labels?.fitToWidth || 'Fit to width'}
                  </SelectItem>
                  {ZOOM_OPTIONS.map((zoom) => (
                    <SelectItem key={zoom} value={String(zoom)} className="text-xs">
                      {zoom}%
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <ToolbarTooltip label={labels?.zoomIn || 'Zoom In'}>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={effectiveZoomScale >= MAX_ZOOM}
                  onClick={handleZoomIn}
                  className="h-8 w-8 rounded-none border-l hover:bg-muted"
                  aria-label={labels?.zoomIn || 'Zoom In'}
                >
                  <ZoomIn className="h-4 w-4" />
                </Button>
              </ToolbarTooltip>

              {!isAutoFit && (
                <ToolbarTooltip label={labels?.zoomReset || 'Fit to width'}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={handleResetToFit}
                    className="h-8 w-8 rounded-none border-l hover:bg-muted"
                    aria-label={labels?.zoomReset || 'Fit to width'}
                  >
                    <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </ToolbarTooltip>
              )}
            </div>
          </div>
        </div>

        {/* Main Workspace Body */}
        <div className="relative flex flex-1 overflow-hidden">
          {/* Left Thumbnail Rail */}
          {sidebarOpen && (
            <aside
              data-testid="docx-thumbnail-sidebar"
              className="w-36 shrink-0 border-r bg-muted/20 flex flex-col overflow-hidden transition-[width] duration-150"
            >
              <div className="flex h-9 items-center justify-between border-b px-3 text-[11px] font-semibold text-muted-foreground">
                <span>{labels?.thumbnails || labels?.page || 'Thumbnails'}</span>
                <span className="tabular-nums">{totalPages}</span>
              </div>
              <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
                {thumbnails && thumbnails.length > 0 ? (
                  thumbnails.map((t) => (
                    <DocxThumbnailItemCard
                      key={t.pageIndex}
                      thumbnail={t}
                      isActive={activePageIndex === t.pageIndex}
                      label={labels?.pageNumber?.({ page: t.pageNumber }) || `Page ${t.pageNumber}`}
                      onSelect={() => handleSelectPage(t.pageIndex)}
                    />
                  ))
                ) : (
                  <div className="flex flex-col items-center justify-center p-4 text-center text-xs text-muted-foreground">
                    <span>1</span>
                  </div>
                )}
              </div>
            </aside>
          )}

          {/* Document Content Viewport */}
          <main
            ref={viewportRef}
            data-testid="docx-viewport"
            className="relative flex-1 overflow-auto p-6 flex justify-center bg-muted/30"
          >
            <div
              style={{
                zoom: effectiveZoomScale / 100,
              }}
              className="flex justify-center min-w-fit pb-12 transition-[zoom] duration-100 ease-out"
            >
              <DocxEditorViewer
                editor={editor}
                mode="read-only"
                pageBackgroundColor="#ffffff"
                pageGapBackgroundColor="transparent"
                pageVirtualization={{
                  enabled: true,
                  overscan: 2,
                  zoomScale: effectiveZoomScale / 100,
                }}
                className="w-full shadow-md rounded-sm"
              />
            </div>
          </main>
        </div>
      </div>
    </TooltipProvider>
  )
}
