'use client'

import * as React from 'react'

interface SpreadsheetPreviewLabels {
  loading: string
  sheet: string
  rowsLimited: (values: { rows: number; columns: number }) => string
  parseError: string
}

interface SpreadsheetSheet {
  name: string
  rows: string[][]
  rowCount: number
  columnCount: number
  visibleColumnCount: number
  truncated: boolean
}

interface SpreadsheetPreviewProps {
  blob: Blob
  labels: SpreadsheetPreviewLabels
}

const MAX_ROWS = 200
const MAX_COLUMNS = 50

function cellToText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (value instanceof Date) return value.toLocaleString()
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}
function isBinarySpreadsheet(bytes: Uint8Array): boolean {
  if (bytes.length < 4) return false
  // Zip based format: xlsx, ods (starts with PK..: 0x50, 0x4B)
  if (bytes[0] === 0x50 && bytes[1] === 0x4B) return true
  // Compound File Binary Format: legacy xls (starts with 0xD0, 0xCF, 0x11, 0xE0)
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

export function SpreadsheetPreview({ blob, labels }: SpreadsheetPreviewProps) {
  const [sheets, setSheets] = React.useState<SpreadsheetSheet[]>([])
  const [activeSheet, setActiveSheet] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [hasError, setHasError] = React.useState(false)

  React.useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setSheets([])
    setActiveSheet(0)
    setHasError(false)
    void blob.arrayBuffer()
      .then((buffer) => import('xlsx').then((XLSX) => ({ buffer, XLSX })))
      .then(({ buffer, XLSX }) => {
        const bytes = new Uint8Array(buffer)
        const workbook = isBinarySpreadsheet(bytes)
          ? XLSX.read(buffer, { type: 'array', cellDates: true, cellText: true })
          : XLSX.read(decodeSpreadsheetText(bytes), { type: 'string', cellDates: true, cellText: true })
        const parsedSheets = workbook.SheetNames.map((name) => {
          const sheet = workbook.Sheets[name]
          const range = sheet?.['!ref'] ? XLSX.utils.decode_range(sheet['!ref']) : null
          const rowCount = range ? range.e.r - range.s.r + 1 : 0
          const columnCount = range ? range.e.c - range.s.c + 1 : 0
          const readRange = range
            ? {
                s: range.s,
                e: {
                  r: Math.min(range.e.r, range.s.r + MAX_ROWS - 1),
                  c: Math.min(range.e.c, range.s.c + MAX_COLUMNS - 1),
                },
              }
            : undefined
          const rows = XLSX.utils.sheet_to_json(sheet, {
            header: 1,
            raw: false,
            defval: '',
            range: readRange,
          }) as unknown[][]
          const visibleRows = rows.slice(0, MAX_ROWS).map((row) => (
            Array.from({ length: Math.min(Math.max(row.length, columnCount), MAX_COLUMNS) }, (_, index) => (
              cellToText(row[index])
            ))
          ))
          const visibleColumnCount = Math.min(Math.max(columnCount, ...visibleRows.map((row) => row.length), 0), MAX_COLUMNS)

          return {
            name,
            rows: visibleRows.map((row) => row.slice(0, visibleColumnCount)),
            rowCount,
            columnCount,
            visibleColumnCount,
            truncated: rowCount > MAX_ROWS || columnCount > MAX_COLUMNS,
          }
        })

        if (!cancelled) {
          setSheets(parsedSheets)
          setIsLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHasError(true)
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [blob])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        <span aria-hidden="true" className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>{labels.loading}</span>
      </div>
    )
  }

  if (hasError || !sheets[activeSheet]) {
    return <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">{labels.parseError}</div>
  }

  const sheet = sheets[activeSheet]
  return (
    <div className="flex w-max min-w-full flex-col">
      {sheets.length > 1 && (
        <div
          data-no-drag
          className="sticky left-0 top-0 z-20 flex shrink-0 items-center gap-2 border-b bg-background/95 px-3 py-1.5 backdrop-blur supports-[backdrop-filter]:bg-background/80"
        >
          <div className="inline-flex h-7 items-center rounded-md bg-muted/60 p-0.5 text-muted-foreground">
            {sheets.map((item, index) => {
              const isActive = index === activeSheet
              return (
                <button
                  key={`${item.name}-${index}`}
                  type="button"
                  className={`inline-flex items-center justify-center whitespace-nowrap rounded-[4px] px-2.5 py-0.5 text-xs font-medium transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 ${
                    isActive
                      ? 'bg-background text-foreground shadow-xs'
                      : 'hover:bg-background/50 hover:text-foreground'
                  }`}
                  onClick={() => setActiveSheet(index)}
                >
                  {item.name}
                </button>
              )
            })}
          </div>
        </div>
      )}
      <div className="p-3">
        {sheet.truncated && (
          <p className="mb-2 text-xs text-muted-foreground">
            {labels.rowsLimited({ rows: MAX_ROWS, columns: MAX_COLUMNS })}
          </p>
        )}
        <div className="overflow-hidden rounded-md border bg-card">
          <table className="w-max border-collapse text-xs">
            <thead>
              <tr className="border-b bg-muted/50 transition-colors">
                <th className="sticky top-0 z-10 border-r bg-muted/80 px-3 py-2 text-right font-mono text-[11px] font-medium text-muted-foreground select-none">
                  #
                </th>
                {Array.from({ length: sheet.visibleColumnCount }, (_, index) => (
                  <th
                    key={index}
                    className="sticky top-0 z-10 border-r last:border-r-0 bg-muted/80 px-3 py-2 text-left font-mono text-[11px] font-medium text-muted-foreground select-none"
                  >
                    {index + 1}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {sheet.rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="transition-colors hover:bg-muted/30">
                  <th className="border-r bg-muted/30 px-3 py-1.5 text-right font-mono text-[11px] font-normal text-muted-foreground select-none">
                    {rowIndex + 1}
                  </th>
                  {Array.from({ length: sheet.visibleColumnCount }, (_, columnIndex) => (
                    <td
                      key={columnIndex}
                      className="max-w-80 whitespace-pre-wrap break-words border-r last:border-r-0 px-3 py-1.5 align-top text-foreground/90"
                    >
                      {row[columnIndex] || ''}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
