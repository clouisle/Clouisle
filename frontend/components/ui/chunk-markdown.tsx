'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTheme } from 'next-themes'
import rehypeSanitize from 'rehype-sanitize'
import { getAuthenticatedApiAssetUrl } from '@/components/chat/authenticated-asset'
import { AuthenticatedImage } from '@/components/chat/authenticated-media'
import { cn } from '@/lib/utils'

const KB_MEDIA_ASSET_PATH =
  /^\/api\/v1\/(?:admin\/)?knowledge-bases\/[^/]+\/documents\/[^/]+\/media\/[^/]+$/

function AuthenticatedMarkdownImage({
  src = '',
  alt = '',
  className,
  title,
  width,
  height,
}: React.ComponentProps<'img'>) {
  const assetUrl = getAuthenticatedApiAssetUrl(typeof src === 'string' ? src : '')
  if (!assetUrl) return alt ? <span>{alt}</span> : null

  const pathname = assetUrl.split(/[?#]/, 1)[0]
  if (!KB_MEDIA_ASSET_PATH.test(pathname)) return alt ? <span>{alt}</span> : null
  return (
    <AuthenticatedImage
      src={assetUrl}
      alt={alt}
      className={className}
      title={title}
      width={width}
      height={height}
    />
  )
}

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
      <MarkdownPreview
        source={source}
        rehypePlugins={[[rehypeSanitize]]}
        components={{ img: AuthenticatedMarkdownImage }}
      />
    </div>
  )
}
