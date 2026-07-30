'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'
import rehypeSanitize from 'rehype-sanitize'
import { cn } from '@/lib/utils'

const MarkdownPreview = dynamic(
  () => import('@uiw/react-markdown-preview').then((mod) => mod.default),
  { ssr: false }
)

interface ChunkMarkdownProps {
  source: string
  className?: string
}

export function ChunkMarkdown({ source, className }: ChunkMarkdownProps) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div
      className={cn('wmde-markdown text-sm', className)}
      data-color-mode={mounted && resolvedTheme === 'dark' ? 'dark' : 'light'}
    >
      <MarkdownPreview source={source} rehypePlugins={[[rehypeSanitize]]} />
    </div>
  )
}
