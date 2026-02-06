'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { FileText, MoreHorizontal, Play } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 模板输入变量
export interface TemplateInput {
  id: string
  name: string                   // 变量名（在模板中使用，如 arg1）
  value: string                  // 变量值（引用上游变量，如 {{query}}）
  valueSource?: string           // 变量来源节点
}

// 模板转换配置
export interface TemplateConfig {
  inputs: TemplateInput[]        // 输入变量列表
  template: string               // Jinja2 模板内容
  outputVariable: string         // 输出变量名（固定为 output）
  outputDescription: string      // 输出描述
}

// 默认模板配置
export const defaultTemplateConfig: TemplateConfig = {
  inputs: [],
  template: '',
  outputVariable: 'output',
  outputDescription: '转换后内容',
}

interface TemplateNodeData {
  type: string
  label: string
  templateConfig?: TemplateConfig
  config: Record<string, unknown>
}

interface TemplateNodeProps {
  id: string
  selected?: boolean
  data: TemplateNodeData
}

export function TemplateNode({ id, selected, data }: TemplateNodeProps) {
  const t = useTranslations('workflow')
  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesTemplate.label')}</span>
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
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
        />

        {/* Icon */}
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-white">
          <FileText className="h-3.5 w-3.5" />
        </div>
        
        {/* Label */}
        <span className="flex-1 text-sm font-medium truncate">
          {data.label || t('nodesTemplate.label')}
        </span>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
        />
      </div>
    </div>
  )
}
