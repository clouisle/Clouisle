'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Image as ImageIcon, Video } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

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

  return (
    <div className="group relative">
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesMediaGeneration.label')}</span>
      </div>

      <div
        className={cn(
          'relative flex items-center gap-2 px-2.5 py-2 rounded-xl border bg-card shadow-sm transition-all',
          'min-w-[180px] max-w-[240px]',
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
    </div>
  )
}
