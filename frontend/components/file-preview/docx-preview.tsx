'use client'

import * as React from 'react'
import { DocxEditorViewer, useDocxEditor } from '@extend-ai/react-docx'
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'

interface DocxPreviewLabels {
  loading: string
  parseError: string
  zoomIn?: string
  zoomOut?: string
  zoomReset?: string
}

interface DocxPreviewProps {
  blob: Blob
  filename?: string
  labels?: DocxPreviewLabels
  onError?: () => void
}

const ZOOM_MIN = 0.5
const ZOOM_MAX = 2.5
const ZOOM_STEP = 0.1
const ZOOM_DEFAULT = 1

export function DocxPreview({ blob, filename, labels, onError }: DocxPreviewProps) {
  const [zoomScale, setZoomScale] = React.useState(ZOOM_DEFAULT)
  const [isLoaded, setIsLoaded] = React.useState(false)
  const editor = useDocxEditor()
  const displayFileName = filename || editor.fileName || 'Document.docx'

  React.useEffect(() => {
    let cancelled = false
    const file = new File([blob], displayFileName, {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })

    void editor.importDocxFile(file)
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
  }, [blob, displayFileName, editor, onError])

  React.useEffect(() => {
    if (editor.importError) {
      onError?.()
    }
  }, [editor.importError, onError])

  const handleZoomIn = React.useCallback(() => {
    setZoomScale((prev) => Math.min(ZOOM_MAX, Math.round((prev + ZOOM_STEP) * 10) / 10))
  }, [])

  const handleZoomOut = React.useCallback(() => {
    setZoomScale((prev) => Math.max(ZOOM_MIN, Math.round((prev - ZOOM_STEP) * 10) / 10))
  }, [])

  const handleResetZoom = React.useCallback(() => {
    setZoomScale(ZOOM_DEFAULT)
  }, [])

  const formattedZoom = `${Math.round(zoomScale * 100)}%`

  if (!isLoaded && editor.isImporting) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        <span aria-hidden="true" className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>{labels?.loading || 'Loading...'}</span>
      </div>
    )
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-background">
      {/* Top Toolbar matching XLSX / PDF design */}
      <div className="flex min-h-[48px] items-center justify-between gap-3 border-b bg-muted/30 px-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground" title={displayFileName}>
            {displayFileName}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {editor.totalPages > 1 && (
            <div className="mr-2 text-xs font-medium text-muted-foreground">
              {editor.currentPage} / {editor.totalPages}
            </div>
          )}
          <div className="flex items-center overflow-hidden rounded-lg border bg-background shadow-xs">
            <button
              type="button"
              disabled={zoomScale <= ZOOM_MIN}
              onClick={handleZoomOut}
              className="inline-flex h-8 w-8 items-center justify-center text-foreground hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
              title={labels?.zoomOut || 'Zoom Out'}
              aria-label={labels?.zoomOut || 'Zoom Out'}
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={handleResetZoom}
              className="inline-flex h-8 min-w-[54px] items-center justify-center border-x px-2 text-xs font-semibold text-foreground hover:bg-muted"
              title={labels?.zoomReset || 'Reset Zoom'}
            >
              {formattedZoom}
            </button>
            <button
              type="button"
              disabled={zoomScale >= ZOOM_MAX}
              onClick={handleZoomIn}
              className="inline-flex h-8 w-8 items-center justify-center text-foreground hover:bg-muted disabled:opacity-40 disabled:pointer-events-none"
              title={labels?.zoomIn || 'Zoom In'}
              aria-label={labels?.zoomIn || 'Zoom In'}
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
          </div>
          {zoomScale !== ZOOM_DEFAULT && (
            <button
              type="button"
              onClick={handleResetZoom}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border bg-background text-foreground hover:bg-muted shadow-xs"
              title={labels?.zoomReset || 'Reset Zoom'}
              aria-label={labels?.zoomReset || 'Reset Zoom'}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Document Body */}
      <div className="relative flex-1 overflow-auto bg-muted/20 p-6 flex justify-center">
        <div
          style={{
            transform: `scale(${zoomScale})`,
            transformOrigin: 'top center',
            transition: 'transform 0.1s ease-out',
          }}
          className="flex w-full justify-center"
        >
          <DocxEditorViewer
            editor={editor}
            mode="read-only"
            className="w-full max-w-4xl shadow-xs rounded-md"
          />
        </div>
      </div>
    </div>
  )
}
