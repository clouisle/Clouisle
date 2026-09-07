'use client'

import * as React from 'react'
import { Expand, ZoomIn, ZoomOut } from 'lucide-react'

export type PreviewZoomFitMode = 'contain' | 'width' | 'native'

export interface PreviewZoomLabels {
  zoomIn: string
  zoomOut: string
  fitToView: string
}

export interface PreviewZoomViewportProps {
  children: React.ReactNode
  labels: PreviewZoomLabels
  fitMode?: PreviewZoomFitMode
  fitKey?: string
  isResizing?: boolean
  className?: string
  contentClassName?: string
  minZoom?: number
  maxZoom?: number
  zoomStep?: number
}

const FIT_PADDING = 48
const FIT_DEBOUNCE_MS = 150
const DEFAULT_MIN_ZOOM = 0.25
const DEFAULT_MAX_ZOOM = 4
const DEFAULT_ZOOM_STEP = 0.1

type Size = { width: number; height: number }
type Pan = { x: number; y: number }

function clampZoom(zoom: number, minZoom: number, maxZoom: number) {
  return Math.min(maxZoom, Math.max(minZoom, zoom))
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function applyTransform(element: HTMLElement, pan: Pan, zoom: number) {
  element.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`
}

export function PreviewZoomViewport({
  children,
  labels,
  fitMode = 'contain',
  fitKey,
  isResizing = false,
  className,
  contentClassName,
  minZoom = DEFAULT_MIN_ZOOM,
  maxZoom = DEFAULT_MAX_ZOOM,
  zoomStep = DEFAULT_ZOOM_STEP,
}: PreviewZoomViewportProps) {
  const [zoom, setZoom] = React.useState(1)
  const [pan, setPan] = React.useState<Pan>({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const viewportRef = React.useRef<HTMLDivElement>(null)
  const contentRef = React.useRef<HTMLDivElement>(null)
  const zoomRef = React.useRef(1)
  const panRef = React.useRef<Pan>({ x: 0, y: 0 })
  const gestureStartZoomRef = React.useRef(1)
  const dragStartRef = React.useRef({ x: 0, y: 0, panX: 0, panY: 0 })
  const fitTimerRef = React.useRef<number | null>(null)
  const hasUserAdjustedRef = React.useRef(false)

  const setPanValue = React.useCallback((nextPan: Pan) => {
    panRef.current = nextPan
    setPan(nextPan)
  }, [])

  const getBaseContentSize = React.useCallback((currentZoom = zoomRef.current): Size | null => {
    const content = contentRef.current
    if (!content) return null

    const contentRect = content.getBoundingClientRect()
    if (contentRect.width <= 0 || contentRect.height <= 0) return null

    const scale = Math.max(currentZoom, 0.001)
    return {
      width: contentRect.width / scale,
      height: contentRect.height / scale,
    }
  }, [])

  const getPanForZoom = React.useCallback((requestedPan: Pan, targetZoom: number, baseSize?: Size | null): Pan => {
    if (fitMode === 'native') return { x: 0, y: 0 }

    const viewport = viewportRef.current
    const size = baseSize ?? getBaseContentSize()
    if (!viewport || !size) return requestedPan

    const viewportRect = viewport.getBoundingClientRect()
    const availableWidth = Math.max(viewportRect.width - FIT_PADDING, 1)
    const availableHeight = Math.max(viewportRect.height - FIT_PADDING, 1)
    const scaledWidth = size.width * targetZoom
    const scaledHeight = size.height * targetZoom

    return {
      // Keep narrow content centered, but keep wide content's left edge reachable.
      x: scaledWidth <= availableWidth
        ? (availableWidth - scaledWidth) / 2
        : clamp(requestedPan.x, availableWidth - scaledWidth, 0),
      // Documents remain top-aligned when zoomed out. Tall content can still be
      // panned upward without ever leaving an unreachable blank region above it.
      y: scaledHeight <= availableHeight
        ? 0
        : clamp(requestedPan.y, availableHeight - scaledHeight, 0),
    }
  }, [fitMode, getBaseContentSize])

  const setZoomValue = React.useCallback((nextZoom: number) => {
    const clampedZoom = clampZoom(nextZoom, minZoom, maxZoom)
    const baseSize = getBaseContentSize()
    const nextPan = getPanForZoom(panRef.current, clampedZoom, baseSize)
    zoomRef.current = clampedZoom
    setZoom(clampedZoom)
    setPanValue(nextPan)
  }, [getBaseContentSize, getPanForZoom, maxZoom, minZoom, setPanValue])

  const applyFitToView = React.useCallback(() => {
    const viewport = viewportRef.current
    const content = contentRef.current
    if (!viewport || !content) return

    if (fitMode === 'native') {
      hasUserAdjustedRef.current = false
      zoomRef.current = 1
      setZoom(1)
      setPanValue({ x: 0, y: 0 })
      setIsDragging(false)
      return
    }

    const viewportRect = viewport.getBoundingClientRect()
    const baseSize = getBaseContentSize()
    if (
      viewportRect.width <= 0
      || viewportRect.height <= 0
      || !baseSize
    ) {
      return
    }

    const availableWidth = Math.max(viewportRect.width - FIT_PADDING, 1)
    const availableHeight = Math.max(viewportRect.height - FIT_PADDING, 1)
    const nextZoom = fitMode === 'width'
      ? availableWidth / baseSize.width
      : Math.min(availableWidth / baseSize.width, availableHeight / baseSize.height)
    const clampedZoom = clampZoom(nextZoom, minZoom, maxZoom)
    if (!Number.isFinite(clampedZoom) || clampedZoom <= 0) return

    hasUserAdjustedRef.current = false
    zoomRef.current = clampedZoom
    setZoom(clampedZoom)
    setPanValue(getPanForZoom({ x: 0, y: 0 }, clampedZoom, baseSize))
    setIsDragging(false)
  }, [fitMode, getBaseContentSize, getPanForZoom, minZoom, maxZoom, setPanValue])

  React.useEffect(() => {
    hasUserAdjustedRef.current = false
    zoomRef.current = 1
    setZoom(1)
    setPanValue({ x: 0, y: 0 })
    setIsDragging(false)
  }, [fitKey, setPanValue])

  React.useEffect(() => {
    const viewport = viewportRef.current
    const content = contentRef.current
    if (!viewport || !content) return

    const scheduleFit = () => {
      if (fitTimerRef.current !== null) {
        window.clearTimeout(fitTimerRef.current)
      }
      fitTimerRef.current = window.setTimeout(() => {
        fitTimerRef.current = null
        applyFitToView()
      }, FIT_DEBOUNCE_MS)
    }

    if (typeof ResizeObserver === 'undefined') {
      applyFitToView()
      return
    }

    const resizeObserver = new ResizeObserver(() => {
      if (hasUserAdjustedRef.current) {
        setPanValue(getPanForZoom(panRef.current, zoomRef.current))
        if (contentRef.current) contentRef.current.style.transition = ''
        return
      }
      scheduleFit()
    })

    resizeObserver.observe(viewport)
    resizeObserver.observe(content)
    scheduleFit()

    return () => {
      if (fitTimerRef.current !== null) {
        window.clearTimeout(fitTimerRef.current)
        fitTimerRef.current = null
      }
      resizeObserver.disconnect()
    }
  }, [applyFitToView, fitKey, getPanForZoom, setPanValue])

  const handleWheel = React.useCallback((event: WheelEvent) => {
    if ((!event.ctrlKey && !event.metaKey) || event.deltaY === 0) return

    event.preventDefault()
    const deltaModeFactor = event.deltaMode === 1
      ? 16
      : event.deltaMode === 2
        ? viewportRef.current?.clientHeight ?? 1
        : 1
    const delta = event.deltaY * deltaModeFactor
    hasUserAdjustedRef.current = true
    setZoomValue(zoomRef.current * Math.exp(-delta * 0.0025))
  }, [setZoomValue])

  const handleGestureStart = React.useCallback((event: Event) => {
    event.preventDefault()
    gestureStartZoomRef.current = zoomRef.current
  }, [])

  const handleGestureChange = React.useCallback((event: Event) => {
    event.preventDefault()
    const scale = (event as Event & { scale?: number }).scale
    if (typeof scale !== 'number' || !Number.isFinite(scale) || scale <= 0) return

    hasUserAdjustedRef.current = true
    setZoomValue(gestureStartZoomRef.current * scale)
  }, [setZoomValue])

  const handleGestureEnd = React.useCallback((event: Event) => {
    event.preventDefault()
  }, [])

  React.useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

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
  }, [handleGestureChange, handleGestureEnd, handleGestureStart, handleWheel])

  React.useEffect(() => {
    if (!contentRef.current) return
    panRef.current = pan
    zoomRef.current = zoom
    contentRef.current.style.transformOrigin = 'top left'
    applyTransform(contentRef.current, pan, zoom)
  }, [pan, zoom])

  const handlePointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement | null
    if (target?.closest('button, a, input, select, textarea, [role="button"], [data-no-drag]')) {
      return
    }
    dragStartRef.current = {
      x: event.clientX,
      y: event.clientY,
      panX: panRef.current.x,
      panY: panRef.current.y,
    }
    setIsDragging(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
    if (contentRef.current) contentRef.current.style.transition = 'none'
  }, [])

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || !contentRef.current) return

    const requestedPan = {
      x: dragStartRef.current.panX + event.clientX - dragStartRef.current.x,
      y: dragStartRef.current.panY + event.clientY - dragStartRef.current.y,
    }
    const nextPan = getPanForZoom(requestedPan, zoomRef.current)
    applyTransform(contentRef.current, nextPan, zoomRef.current)
  }, [getPanForZoom, isDragging])

  const handlePointerUp = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return

    const requestedPan = {
      x: dragStartRef.current.panX + event.clientX - dragStartRef.current.x,
      y: dragStartRef.current.panY + event.clientY - dragStartRef.current.y,
    }
    const nextPan = getPanForZoom(requestedPan, zoomRef.current)
    setPanValue(nextPan)
    setIsDragging(false)
    hasUserAdjustedRef.current = true
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    if (contentRef.current) contentRef.current.style.transition = ''
  }, [getPanForZoom, isDragging, setPanValue])

  const contentClass = [
    fitMode === 'native' ? 'h-full w-full' : 'w-max',
    'origin-top-left will-change-transform',
    !isDragging && 'transition-transform',
    contentClassName,
  ].filter(Boolean).join(' ')

  return (
    <div className={`relative h-full min-h-0 overflow-hidden bg-background ${className || ''}`} data-preview-zoom-viewport>
      <div
        ref={viewportRef}
        className={`flex h-full min-h-0 items-start justify-start overflow-auto p-6 select-none ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        data-preview-zoom-scroll-area
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div
          ref={contentRef}
          className={contentClass}
          data-preview-zoom-content
          style={{ transformOrigin: 'top left', transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {children}
        </div>
      </div>
      <div
        data-slot="file-preview-zoom-controls"
        className="absolute right-4 top-4 z-10 flex items-center gap-1 rounded-md border bg-background p-1 shadow-sm"
      >
        <button
          type="button"
          onClick={() => {
            hasUserAdjustedRef.current = true
            setZoomValue(zoomRef.current - zoomStep)
          }}
          disabled={zoom <= minZoom}
          aria-label={labels.zoomOut}
          title={labels.zoomOut}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <span className="min-w-12 px-1 text-center text-xs tabular-nums text-muted-foreground" aria-live="polite">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={() => {
            hasUserAdjustedRef.current = true
            setZoomValue(zoomRef.current + zoomStep)
          }}
          disabled={zoom >= maxZoom}
          aria-label={labels.zoomIn}
          title={labels.zoomIn}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={applyFitToView}
          aria-label={labels.fitToView}
          title={labels.fitToView}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <Expand className="h-4 w-4" />
        </button>
      </div>
      {isResizing && <div className="pointer-events-none absolute inset-0 bg-background/20" aria-hidden="true" />}
    </div>
  )
}
