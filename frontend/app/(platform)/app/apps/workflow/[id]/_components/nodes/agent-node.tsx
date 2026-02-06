'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Bot, MoreHorizontal, Play } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import type { AgentNodeConfig } from '../node-config/configs/agent-node-config'

interface AgentNodeData {
  type: string
  label: string
  config: Record<string, unknown>
  agentConfig?: AgentNodeConfig
}

interface AgentNodeProps {
  id: string
  selected?: boolean
  data: AgentNodeData
}

export function AgentNode({ selected, data }: AgentNodeProps) {
  const t = useTranslations('workflow')
  // 从 agentConfig 获取智能体信息
  const agentName = data.agentConfig?.agentName
  const hasAgent = !!data.agentConfig?.agentId

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesAgent.label')}</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background" title={t('nodesCommon.debugRun')}>
            <Play className="h-3 w-3 text-muted-foreground" />
          </button>
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      {/* Node Card */}
      <div
        className={cn(
          'relative flex items-center gap-2 px-2.5 py-2 rounded-xl border bg-card shadow-sm transition-all',
          'min-w-[180px] max-w-[240px]',
          selected 
            ? 'border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        />

        {/* Icon */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-500 text-white">
          <Bot className="h-3.5 w-3.5" />
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate">
            {data.label || t('nodesAgent.label')}
          </span>
          {hasAgent ? (
            <span className="text-xs text-muted-foreground truncate block">{agentName}</span>
          ) : (
            <span className="text-xs text-amber-500">{t('nodesAgent.notSelected')}</span>
          )}
        </div>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        />
      </div>
    </div>
  )
}
