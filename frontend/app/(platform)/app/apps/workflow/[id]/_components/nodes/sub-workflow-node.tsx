'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Workflow, MoreHorizontal, Play } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SubWorkflowNodeConfig } from '../node-config/configs/sub-workflow-node-config'

interface SubWorkflowNodeData {
  type: string
  label: string
  config: Record<string, unknown>
  subWorkflowConfig?: SubWorkflowNodeConfig
}

interface SubWorkflowNodeProps {
  id: string
  selected?: boolean
  data: SubWorkflowNodeData
}

export function SubWorkflowNode({ id, selected, data }: SubWorkflowNodeProps) {
  // 从 subWorkflowConfig 获取工作流信息
  const workflowName = data.subWorkflowConfig?.workflowName
  const hasWorkflow = !!data.subWorkflowConfig?.workflowId

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">子工作流</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background" title="调试运行">
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
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-500 text-white">
          <Workflow className="h-3.5 w-3.5" />
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <span className="block text-sm font-medium truncate">
            {data.label || '子工作流'}
          </span>
          {hasWorkflow ? (
            <span className="text-xs text-muted-foreground truncate block">{workflowName}</span>
          ) : (
            <span className="text-xs text-amber-500">未选择工作流</span>
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
