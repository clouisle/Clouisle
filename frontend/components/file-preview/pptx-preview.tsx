'use client'

import * as React from 'react'
import { ReactPptxViewer } from '@extend-ai/react-pptx'
import '@extend-ai/react-pptx/styles.css'
interface PptxPreviewProps {
  blob: Blob
  onError: () => void
}

export function PptxPreview({ blob, onError }: PptxPreviewProps) {
  const [arrayBuffer, setArrayBuffer] = React.useState<ArrayBuffer | null>(null)

  React.useEffect(() => {
    let cancelled = false
    void blob.arrayBuffer()
      .then((buf) => {
        if (!cancelled) setArrayBuffer(buf)
      })
      .catch(() => {
        if (!cancelled) onError()
      })
    return () => {
      cancelled = true
    }
  }, [blob, onError])

  if (!arrayBuffer) {
    return null
  }

  return (
    <div className="h-full w-full overflow-hidden bg-muted/10">
      <ReactPptxViewer
        source={arrayBuffer}
        mode="continuous"
        className="h-full w-full"
      />
    </div>
  )
}
