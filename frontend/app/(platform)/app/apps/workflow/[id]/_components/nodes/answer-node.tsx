'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { MessageSquareText, MoreHorizontal, Type, Hash, ToggleLeft, Brackets, Braces, File, FileQuestion } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 输出变量定义
export interface OutputVariable {
  id: string
  name: string           // 输出变量名（外部可见）
  sourceVariable: string // 源变量引用（如 {{node.var}}），传到后端用
  sourceNodeLabel?: string // 源节点标签（用于显示）
  sourceVariableName?: string // 源变量名称（用于显示，如 query）
  type: 'string' | 'number' | 'boolean' | 'array' | 'object' | 'file' | 'any'
  description?: string   // 变量描述
}

// 输出节点配置
export interface AnswerNodeConfig {
  // 输出变量列表
  outputs: OutputVariable[]
  // 流式输出配置
  streaming: {
    enabled: boolean      // 是否启用流式输出
    variable?: string     // 流式输出的变量名（通常是 LLM 的 response）
  }
}

// 默认配置
export const defaultAnswerNodeConfig: AnswerNodeConfig = {
  outputs: [],
  streaming: {
    enabled: false,
  },
}

// 类型图标映射
const typeIconMap: Record<string, React.ElementType> = {
  string: Type,
  number: Hash,
  boolean: ToggleLeft,
  array: Brackets,
  object: Braces,
  file: File,
  any: FileQuestion,
}

// 类型显示名称
const typeDisplayMap: Record<string, string> = {
  string: 'String',
  number: 'Number',
  boolean: 'Boolean',
  array: 'Array',
  object: 'Object',
  file: 'File',
  any: 'Any',
}

interface AnswerNodeData {
  type: string
  label: string
  answerConfig?: AnswerNodeConfig
  config: Record<string, unknown>
}

interface AnswerNodeProps {
  id: string
  selected?: boolean
  data: AnswerNodeData
}

export function AnswerNode({ selected, data }: AnswerNodeProps) {
  const t = useTranslations('workflow')
  const config = data.answerConfig || defaultAnswerNodeConfig
  const outputs = config.outputs || []
  const hasOutputs = outputs.length > 0

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesAnswer.label')}</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      {/* Node Card */}
      <div
        className={cn(
          'relative flex flex-col rounded-xl border bg-card shadow-sm transition-all',
          'min-w-44 max-w-56',
          selected 
            ? 'border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Output Handle - 允许连接后续节点实现分段输出 */}
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-emerald-500 text-white">
            <MessageSquareText className="h-3.5 w-3.5" />
          </div>
          
          {/* Label */}
          <div className="flex-1 min-w-0">
            <span className="block text-sm font-medium truncate">
              {data.label || t('nodesAnswer.label')}
            </span>
            {config.streaming.enabled && (
              <span className="text-xs text-emerald-500">{t('nodesAnswer.streaming')}</span>
            )}
          </div>
        </div>

        {/* Output Variables List */}
        {hasOutputs && (
          <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
            {outputs.slice(0, 4).map((output) => {
              const TypeIcon = typeIconMap[output.type] || FileQuestion
              return (
                <div 
                  key={output.id}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1.5 bg-emerald-500/10"
                >
                  <TypeIcon className="h-3 w-3 text-emerald-500 shrink-0" />
                  <span className="text-[11px] text-foreground/80 font-medium truncate flex-1">
                    {output.name || t('nodesCommon.unnamed')}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0">
                    {typeDisplayMap[output.type] || output.type}
                  </span>
                </div>
              )
            })}
            {outputs.length > 4 && (
              <div className="text-[10px] text-muted-foreground text-center py-0.5">
                {t('nodesAnswer.outputCount', { n: outputs.length - 4 })}
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!hasOutputs && (
          <div className="px-2.5 pb-2 pt-0.5">
            <div className="flex items-center justify-center py-2 text-[11px] text-muted-foreground">
              {t('nodesAnswer.clickToConfigure')}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
