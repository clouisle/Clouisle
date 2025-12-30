'use client'

import * as React from 'react'
import { Handle, Position, useReactFlow } from '@xyflow/react'
import { Wrench, Plus, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ToolNodeData {
  type: string
  label: string
  config: {
    tool_id?: string
    tool_name?: string
  }
}

interface ToolNodeProps {
  id: string
  selected?: boolean
  data: ToolNodeData
}

export function ToolNode({ id, selected, data }: ToolNodeProps) {
  const { getEdges } = useReactFlow()
  
  const edges = getEdges()
  const hasOutgoingEdge = edges.some(edge => edge.source === id)

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">工具</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      {/* Node Card */}
      <div
        className={cn(
          'relative flex items-center gap-3 px-3 py-2.5 rounded-2xl border bg-card shadow-sm transition-all',
          'min-w-[180px] max-w-[240px]',
          selected 
            ? 'ring-2 ring-primary ring-offset-2 border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="!w-3 !h-3 !bg-primary !border-2 !border-background !-left-1.5"
        />

        {/* Icon */}
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-500 text-white">
          <Wrench className="h-4 w-4" />
        </div>
        
        {/* Label */}
        <span className="flex-1 text-sm font-medium truncate">
          {data.label || '工具'}
        </span>

        {/* Handle as Add Button - positioned on the right edge */}
        <Handle
          type="source"
          position={Position.Right}
          className={cn(
            '!w-6 !h-6 !rounded-full !border-2 !border-primary !-right-3 !flex !items-center !justify-center',
            hasOutgoingEdge 
              ? '!bg-primary' 
              : '!bg-background opacity-0 group-hover:opacity-100 transition-opacity hover:!bg-muted'
          )}
        >
          {!hasOutgoingEdge && <Plus className="h-3 w-3 text-primary pointer-events-none" />}
        </Handle>
      </div>
    </div>
  )
}
