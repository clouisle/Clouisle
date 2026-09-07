'use client'

import * as React from 'react'
import EmbedPDF from '@embedpdf/viewer'

interface PdfPreviewProps {
  blob: Blob
  onError?: () => void
}

export function PdfPreview({ blob, onError }: PdfPreviewProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const container = containerRef.current
    let objectUrl: string | null = null
    let element: HTMLElement | null = null

    if (!container) return

    try {
      objectUrl = URL.createObjectURL(blob)
      container.replaceChildren()
      element = EmbedPDF.init({
        target: container,
        src: objectUrl,
      })
    } catch {
      onError?.()
    }

    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
      if (element && element.parentNode) {
        element.parentNode.removeChild(element)
      }
      if (container) {
        container.replaceChildren()
      }
    }
  }, [blob, onError])

  return (
    <div className="h-full w-full overflow-hidden bg-muted/10">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  )
}
