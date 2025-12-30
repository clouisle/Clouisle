'use client'

import * as React from 'react'
import { Handle, Position, NodeProps } from '@xyflow/react'
import { Play } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StartNodeData {
  type: string
  label: string
  config: Record<string, unknown>
}

export function StartNode({ selected }: NodeProps) {
  return (
    <div
      className={cn(
        'px-4 py-3 rounded-lg border-2 bg-card shadow-sm min-w-[150px]',
        'border-green-500 bg-green-50 dark:bg-green-950/20',
        selected && 'ring-2 ring-primary ring-offset-2'
      )}
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-md bg-green-500 text-white">
          <Play className="h-3.5 w-3.5" />
        </div>
        <span className="text-sm font-medium">开始</span>
      </div>
      
      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-green-500 !border-2 !border-white !w-3 !h-3"
      />
    </div>
  )
}
