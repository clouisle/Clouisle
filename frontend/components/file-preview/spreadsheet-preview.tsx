'use client'

import * as React from 'react'
import * as XLSX from 'xlsx'
import { XlsxViewer } from '@extend-ai/react-xlsx'
interface SpreadsheetPreviewLabels {
  loading: string
  sheet: string
  rowsLimited: (values: { rows: number; columns: number }) => string
  parseError: string
  zoomIn?: string
  zoomOut?: string
  zoomReset?: string
}
interface SpreadsheetPreviewProps {
  blob: Blob
  filename?: string
  labels: SpreadsheetPreviewLabels
  onError?: () => void
}

function isBinarySpreadsheet(bytes: Uint8Array): boolean {
  if (bytes.length < 4) return false
  if (
    bytes[0] === 0x50 &&
    bytes[1] === 0x4B &&
    ((bytes[2] === 0x03 && bytes[3] === 0x04) ||
      (bytes[2] === 0x05 && bytes[3] === 0x06) ||
      (bytes[2] === 0x07 && bytes[3] === 0x08))
  ) return true
  if (bytes[0] === 0xD0 && bytes[1] === 0xCF && bytes[2] === 0x11 && bytes[3] === 0xE0) return true
  return false
}

function decodeSpreadsheetText(bytes: Uint8Array): string {
  try {
    const utf8Decoder = new TextDecoder('utf-8', { fatal: true })
    return utf8Decoder.decode(bytes)
  } catch {
    const gbkDecoder = new TextDecoder('gb18030')
    return gbkDecoder.decode(bytes)
  }
}

export function SpreadsheetPreview({ blob, filename, labels, onError }: SpreadsheetPreviewProps) {
  const [arrayBuffer, setArrayBuffer] = React.useState<ArrayBuffer | null>(null)
  const [hasError, setHasError] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    setHasError(false)
    setArrayBuffer(null)

    void blob.arrayBuffer()
      .then((buffer) => {
        const bytes = new Uint8Array(buffer)
        if (isBinarySpreadsheet(bytes)) {
          return buffer
        }
        // For CSV / TSV text formats, convert decoded string back to xlsx workbook buffer to avoid charset corruption
        const text = decodeSpreadsheetText(bytes)
        const workbook = XLSX.read(text, { type: 'string', cellDates: true, cellText: true })
        const output = XLSX.write(workbook, { type: 'array', bookType: 'xlsx' })
        return output as ArrayBuffer
      })
      .then((processed) => {
        if (!cancelled) setArrayBuffer(processed)
      })
      .catch(() => {
        if (!cancelled) {
          setHasError(true)
          onError?.()
        }
      })

    return () => {
      cancelled = true
    }
  }, [blob, onError])

  if (hasError) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        {labels.parseError}
      </div>
    )
  }

  if (!arrayBuffer) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        <span aria-hidden="true" className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>{labels.loading}</span>
      </div>
    )
  }

  return (
    <div className="h-full w-full overflow-hidden bg-background">
      <XlsxViewer
        file={arrayBuffer}
        fileName={filename}
        className="h-full w-full border-0"
        rounded={false}
        readOnly
        showDefaultToolbar={false}
        toolbar={(controller) => {
          const {
            activeTabIndex,
            canZoomIn,
            canZoomOut,
            defaultZoomScale,
            displayFileName,
            resetZoom,
            setActiveTabIndex,
            tabs,
            zoomIn,
            zoomOut,
            zoomScale,
          } = controller

          return (
            <div className="flex flex-col border-b bg-background">
              <div className="flex min-h-12 items-center justify-between gap-3 px-4">
                <div className="min-w-0 truncate text-xs font-semibold text-foreground/90">
                  {displayFileName}
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center overflow-hidden rounded-lg border bg-background shadow-xs">
                    <button
                      type="button"
                      disabled={!canZoomOut}
                      onClick={zoomOut}
                      className="inline-flex h-8 w-8 items-center justify-center border-r bg-transparent text-sm font-semibold text-foreground transition-colors hover:bg-muted disabled:cursor-default disabled:text-muted-foreground disabled:hover:bg-transparent"
                      aria-label={labels.zoomOut || 'Zoom out'}
                    >
                      -
                    </button>
                    <button
                      type="button"
                      onClick={resetZoom}
                      className="inline-flex h-8 min-w-15 items-center justify-center px-2 text-xs font-semibold text-foreground transition-colors hover:bg-muted"
                      style={{
                        background: Math.round(zoomScale) === Math.round(defaultZoomScale) ? 'transparent' : 'var(--muted)',
                      }}
                      aria-label={labels.zoomReset || 'Reset zoom'}
                    >
                      {Math.round(zoomScale)}%
                    </button>
                    <button
                      type="button"
                      disabled={!canZoomIn}
                      onClick={zoomIn}
                      className="inline-flex h-8 w-8 items-center justify-center border-l bg-transparent text-sm font-semibold text-foreground transition-colors hover:bg-muted disabled:cursor-default disabled:text-muted-foreground disabled:hover:bg-transparent"
                      aria-label={labels.zoomIn || 'Zoom in'}
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
              {tabs.length > 1 && (
                <div className="overflow-x-auto border-t bg-muted/20 px-3 py-1.5">
                  <div className="inline-flex items-center gap-1 rounded-lg border bg-muted/40 p-0.5" role="tablist" aria-label="Workbook sheets">
                    {tabs.map((tab, index) => {
                      const selected = index === activeTabIndex
                      return (
                        <button
                          key={tab.name}
                          type="button"
                          role="tab"
                          aria-selected={selected}
                          onClick={() => setActiveTabIndex(index)}
                          className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                            selected
                              ? 'bg-background text-foreground shadow-xs font-semibold'
                              : 'text-muted-foreground hover:bg-background/50 hover:text-foreground'
                          }`}
                        >
                          {tab.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        }}
      />
    </div>
  )
}
