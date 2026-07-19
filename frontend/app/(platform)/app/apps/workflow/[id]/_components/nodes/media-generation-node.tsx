'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Image as ImageIcon, Loader2, Video, XCircle } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { ImageLightbox, VideoLightbox, useLightbox } from '@/components/chat/image-lightbox'
import { cn } from '@/lib/utils'
import type { NodeTrace } from '../node-output-renderer'

export type MediaGenerationMode = 'image' | 'video'

export interface MediaGenerationConfig {
  mode: MediaGenerationMode
  modelId?: string
  modelName?: string
  prompt: string
  referenceImageVariable?: string
  startImageVariable?: string
  width?: number
  height?: number
  numImages?: number
  duration?: number
  aspectRatio?: string
  outputVariable: string
}

export const defaultMediaGenerationConfig: MediaGenerationConfig = {
  mode: 'image',
  prompt: '',
  numImages: 1,
  duration: 5,
  aspectRatio: '16:9',
  outputVariable: 'result',
}

interface MediaGenerationNodeData {
  type: string
  label: string
  mediaGenerationConfig?: MediaGenerationConfig
  config: Record<string, unknown>
  runtimeTrace?: NodeTrace
}

interface MediaGenerationNodeProps {
  id: string
  selected?: boolean
  data: MediaGenerationNodeData
}

export function MediaGenerationNode({ selected, data }: MediaGenerationNodeProps) {
  const t = useTranslations('workflow')
  const config = data.mediaGenerationConfig || defaultMediaGenerationConfig
  const isVideo = config.mode === 'video'
  const Icon = isVideo ? Video : ImageIcon
  const trace = data.runtimeTrace
  const output = trace?.outputs?.[config.outputVariable || 'result']
  const imageUrls = !isVideo && Array.isArray(output)
    ? output.filter((url): url is string => typeof url === 'string' && !!url)
    : []
  const videoUrl = isVideo && typeof output === 'string' ? output : null
  const imageLightbox = useLightbox()
  const [videoLightboxOpen, setVideoLightboxOpen] = React.useState(false)
  const hasPreview = imageUrls.length > 0 || !!videoUrl

  return (
    <div className={cn('group relative', hasPreview ? 'w-[280px]' : 'w-[180px]')}>
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesMediaGeneration.label')}</span>
      </div>

      <div
        className={cn(
          'relative flex items-center gap-2 px-2.5 py-2 rounded-xl border bg-card shadow-sm transition-all',
          'w-full min-w-[180px]',
          selected ? 'border-primary' : 'border-border hover:border-primary/50'
        )}
      >
        <Handle
          type="target"
          position={Position.Left}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        />

        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-fuchsia-500 text-white">
          <Icon className="h-3.5 w-3.5" />
        </div>

        <div className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate">
            {data.label || t('nodesMediaGeneration.label')}
          </span>
          <span className="text-xs text-muted-foreground truncate block">
            {isVideo ? t('nodesMediaGeneration.videoMode') : t('nodesMediaGeneration.imageMode')}
          </span>
        </div>

        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        />
      </div>

      {trace?.status === 'running' && (
        <div className="mt-2 flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          {t('runDrawer.statusRunning')}
        </div>
      )}

      {trace?.status === 'failed' && (
        <div className="mt-2 flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          <XCircle className="h-3.5 w-3.5" />
          {t('runDrawer.statusFailed')}
        </div>
      )}

      {imageUrls.length > 0 && (
        <div className={cn(
          'nodrag nopan mt-2 grid w-full gap-1 overflow-hidden rounded-xl border bg-muted/40 p-1',
          imageUrls.length > 1 && 'grid-cols-2'
        )}>
          {imageUrls.slice(0, 4).map((url, index) => (
            <button
              key={`${url}-${index}`}
              type="button"
              className={cn(
                'flex min-h-0 items-center justify-center overflow-hidden rounded-lg bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                imageUrls.length === 1 ? 'aspect-video' : 'aspect-square'
              )}
              onClick={() => imageLightbox.openLightbox(url)}
              aria-label={`Generated image ${index + 1}`}
            >
              <img
                src={url}
                alt={`Generated image ${index + 1}`}
                className="h-full w-full object-contain"
              />
            </button>
          ))}
        </div>
      )}

      {videoUrl && (
        <button
          type="button"
          className="nodrag nopan mt-2 flex aspect-video w-full items-center justify-center overflow-hidden rounded-xl border bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setVideoLightboxOpen(true)}
          aria-label="Open generated video"
        >
          <video
            src={videoUrl}
            muted
            playsInline
            preload="metadata"
            className="h-full w-full object-contain"
          />
        </button>
      )}

      <ImageLightbox
        src={imageLightbox.imageSrc}
        alt={imageLightbox.imageAlt}
        isOpen={imageLightbox.isOpen}
        onClose={imageLightbox.closeLightbox}
      />
      {videoUrl && (
        <VideoLightbox
          src={videoUrl}
          isOpen={videoLightboxOpen}
          onClose={() => setVideoLightboxOpen(false)}
        />
      )}
    </div>
  )
}
