'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Bot, MoreHorizontal, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { LLMNodeConfigData } from '../node-config/configs/llm-node-config'

interface LLMNodeData {
  type: string
  label: string
  config: Record<string, unknown>
  llmConfig?: LLMNodeConfigData
}

interface LLMNodeProps {
  id: string
  selected?: boolean
  data: LLMNodeData
}

export function LLMNode({ id, selected, data }: LLMNodeProps) {
  // 从 llmConfig 获取模型信息
  const modelName = data.llmConfig?.modelName
  const hasModel = !!data.llmConfig?.modelId

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">LLM</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
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
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0"
        />

        {/* Icon */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-white">
          <Bot className="h-3.5 w-3.5" />
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate">
            {data.label || 'LLM'}
          </span>
          {hasModel ? (
            <div className="flex items-center gap-1 mt-0.5">
              <Sparkles className="h-3 w-3 text-blue-500" />
              <span className="text-xs text-muted-foreground truncate">{modelName}</span>
            </div>
          ) : (
            <span className="text-xs text-amber-500">未选择模型</span>
          )}
        </div>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0"
        />
      </div>
    </div>
  )
}
