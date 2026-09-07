'use client'

import * as React from 'react'
import * as XLSX from 'xlsx'
import { XlsxViewer } from '@extend-ai/react-xlsx'
interface SpreadsheetPreviewLabels {
  loading: string
  sheet: string
  rowsLimited: (values: { rows: number; columns: number }) => string
  parseError: string
}

interface SpreadsheetPreviewProps {
  blob: Blob
  filename?: string
  labels: SpreadsheetPreviewLabels
  onError?: () => void
}

function isBinarySpreadsheet(bytes: Uint8Array): boolean {
  if (bytes.length < 4) return false
  if (bytes[0] === 0x50 && bytes[1] === 0x4B) return true
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
        showDefaultToolbar
      />
    </div>
  )
}
