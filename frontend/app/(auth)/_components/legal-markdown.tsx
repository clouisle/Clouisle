'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'

const MarkdownPreview = dynamic(
  () => import('@uiw/react-md-editor').then(mod => mod.default.Markdown),
  {
    ssr: false,
    loading: () => <LegalMarkdownSkeleton />,
  },
)

export function preloadLegalMarkdown() {
  if (typeof window !== 'undefined') {
    import('@uiw/react-md-editor').catch(() => {})
  }
}

function LegalMarkdownSkeleton() {
  return (
    <div className="animate-pulse space-y-3" aria-hidden="true">
      <div className="h-5 w-1/3 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-5/6 rounded bg-muted" />
        <div className="h-3 w-4/6 rounded bg-muted" />
      </div>
      <div className="h-4 w-1/4 rounded bg-muted" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-3/4 rounded bg-muted" />
      </div>
    </div>
  )
}

export function LegalMarkdown({ source }: { source: string }) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div
      className="wmde-markdown text-sm"
      data-color-mode={mounted && resolvedTheme === 'dark' ? 'dark' : 'light'}
    >
      <MarkdownPreview source={source} />
    </div>
  )
}
