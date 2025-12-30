'use client'

import * as React from 'react'
import { Handle, Position, NodeProps } from '@xyflow/react'
import { Square } from 'lucide-react'
import { cn } from '@/lib/utils'

interface EndNodeData {
  type: string
  label: string
  config: Record<string, unknown>
}

export function EndNode({ selected }: NodeProps) {
  return (
    <div
      className={cn(
        'px-4 py-3 rounded-lg border-2 bg-card shadow-sm min-w-[150px]',
        'border-red-500 bg-red-50 dark:bg-red-950/20',
        selected && 'ring-2 ring-primary ring-offset-2'
      )}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-red-500 !border-2 !border-white !w-3 !h-3"
      />
      
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-md bg-red-500 text-white">
          <Square className="h-3.5 w-3.5" />
        </div>
        <span className="text-sm font-medium">结束</span>
      </div>
    </div>
  )
}
