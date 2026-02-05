'use client'

import * as React from 'react'
import { Handle, Position, useReactFlow } from '@xyflow/react'
import { Zap, MoreHorizontal, Play, Type, AlignLeft, ListChecks, Hash, CheckSquare, File, Image, Files, Images } from 'lucide-react'
import { cn } from '@/lib/utils'

// 参数类型定义
type ParameterType = 'text' | 'paragraph' | 'select' | 'number' | 'checkbox' | 'array' | 'object' | 'file' | 'image' | 'files' | 'images'

interface Parameter {
  id: string
  name: string
  type: ParameterType
  required: boolean
  defaultValue?: string
  description?: string
}

// 参数类型图标映射
const parameterTypeIcons: Record<ParameterType, React.ElementType> = {
  text: Type,
  paragraph: AlignLeft,
  select: ListChecks,
  number: Hash,
  checkbox: CheckSquare,
  array: Type,
  object: Type,
  file: File,
  image: Image,
  files: Files,
  images: Images,
}

interface TriggerNodeData {
  type: string
  label: string
  parameters?: Parameter[]
  config: Record<string, unknown>
}

interface TriggerNodeProps {
  id: string
  selected?: boolean
  data: TriggerNodeData
}

export function TriggerNode({ id, selected, data }: TriggerNodeProps) {
  const { getEdges } = useReactFlow()
  
  const edges = getEdges()
  const hasOutgoingEdge = edges.some(edge => edge.source === id)

  // 获取必填参数
  const requiredParams = (data.parameters || []).filter(p => p.required)

  return (
    <div className="group relative">
      {/* Start Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">开始</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background">
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
          'relative flex flex-col rounded-xl border bg-card shadow-sm transition-all',
          'min-w-[180px] max-w-[260px]',
          selected 
            ? 'border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white">
            <Zap className="h-3.5 w-3.5" />
          </div>
          
          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            触发器
          </span>

          {/* Handle - always visible */}
          <Handle
            type="source"
            position={Position.Right}
            className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
          />
        </div>

        {/* Required Parameters */}
        {requiredParams.length > 0 && (
          <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
            {requiredParams.map((param) => {
              const TypeIcon = parameterTypeIcons[param.type] || Type
              return (
                <div key={param.id} className="flex items-center justify-between bg-muted rounded-md px-2 py-1">
                  <div className="flex items-center gap-1">
                    <span className="text-primary/80 text-[10px] font-mono">{'{x}'}</span>
                    <span className="text-[11px] text-foreground/80">{param.name}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-[9px] text-muted-foreground">必填</span>
                    <div className="w-4 h-4 rounded border border-border/60 bg-background flex items-center justify-center">
                      <TypeIcon className="h-2.5 w-2.5 text-muted-foreground" />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
