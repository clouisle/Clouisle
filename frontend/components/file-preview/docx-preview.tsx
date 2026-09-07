'use client'

import * as React from 'react'
import { ReactDocxViewer, useDocxModel } from '@extend-ai/react-docx'

interface DocxPreviewProps {
  blob: Blob
  onError: () => void
}

export function DocxPreview({ blob, onError }: DocxPreviewProps) {
  const [arrayBuffer, setArrayBuffer] = React.useState<ArrayBuffer | undefined>(undefined)

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

  const { model, error } = useDocxModel(arrayBuffer)

  React.useEffect(() => {
    if (error) {
      onError()
    }
  }, [error, onError])

  if (!arrayBuffer || !model) {
    return null
  }

  return (
    <div className="h-full w-full overflow-auto bg-muted/20 p-6 flex justify-center">
      <ReactDocxViewer
        model={model}
        className="w-full max-w-4xl shadow-sm rounded-md"
      />
    </div>
  )
}
