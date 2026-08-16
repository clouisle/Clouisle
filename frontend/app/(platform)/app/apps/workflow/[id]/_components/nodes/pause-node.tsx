'use client'

import { Handle, Position } from '@xyflow/react'
import { CirclePause } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import type { PauseNodeConfig } from '../node-config/configs/pause-node-config'

interface PauseNodeData {
  type: string
  label: string
  config: Record<string, unknown>
  pauseConfig?: PauseNodeConfig
}

interface PauseNodeProps {
  selected?: boolean
  data: PauseNodeData
}

export function PauseNode({ selected, data }: PauseNodeProps) {
  const t = useTranslations('workflow')
  const config = data.pauseConfig
  const isApproval = config?.mode === 'approval'
  const variableCount = config?.inputVariables?.filter((variable) => variable.name?.trim()).length ?? 0
  const subtitle = isApproval
    ? t('nodesPause.approval')
    : variableCount > 0
      ? t('nodesPause.variableCount', { count: variableCount })
      : t('nodesPause.notConfigured')

  return (
    <div className="group relative">
      <div className="mb-2 flex h-5 items-center px-1">
        <span className="text-xs text-muted-foreground">{t('nodesPause.label')}</span>
      </div>
      <div
        className={cn(
          'relative flex min-w-[180px] max-w-[240px] items-center gap-2 rounded-xl border bg-card px-2.5 py-2 shadow-sm transition-all',
          selected ? 'border-amber-500 ring-1 ring-amber-500/20' : 'border-border hover:border-amber-500/50'
        )}
      >
        <Handle
          type="target"
          position={Position.Left}
          className="h-2! w-2! rounded-full! border-0! bg-amber-500! transition-transform group-hover:scale-150"
        />
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white">
          <CirclePause className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{data.label || t('nodesPause.label')}</span>
          <span className="block truncate text-xs text-muted-foreground">{config?.title || subtitle}</span>
        </div>
        <Handle
          type="source"
          position={Position.Right}
          className="h-2! w-2! rounded-full! border-0! bg-amber-500! transition-transform group-hover:scale-150"
        />
      </div>
    </div>
  )
}
