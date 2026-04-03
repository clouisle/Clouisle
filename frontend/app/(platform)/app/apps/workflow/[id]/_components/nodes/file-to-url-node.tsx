'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Link } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 文件转URL输入配置
export interface FileToUrlInput {
  id: string
  name: string                   // 输出变量名
  sourceVariable: string         // 源文件变量引用（如 {{start.image}}）
  sourceType: 'file' | 'image' | 'files' | 'images'  // 源类型
}

// 文件转URL节点配置
export interface FileToUrlConfig {
  inputs: FileToUrlInput[]       // 输入列表（支持多个文件变量）
  ensureAbsolute: boolean        // 是否确保绝对URL
}

// 默认配置
export const defaultFileToUrlConfig: FileToUrlConfig = {
  inputs: [],
  ensureAbsolute: true,
}

interface FileToUrlNodeData {
  type: string
  label: string
  fileToUrlConfig?: FileToUrlConfig
  config: Record<string, unknown>
}

interface FileToUrlNodeProps {
  id: string
  selected?: boolean
  data: FileToUrlNodeData
}

export function FileToUrlNode({ selected, data }: FileToUrlNodeProps) {
  const t = useTranslations('workflow')
  const config = data.fileToUrlConfig || defaultFileToUrlConfig
  const inputCount = config.inputs.length

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesFileToUrl.label')}</span>
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
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-500 text-white">
          <Link className="h-3.5 w-3.5" />
        </div>
        
        {/* Content */}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium truncate block">
            {data.label || t('nodesFileToUrl.label')}
          </span>
          {inputCount > 0 && (
            <span className="text-xs text-muted-foreground">
              {t('nodesFileToUrl.inputCount', { count: inputCount })}
            </span>
          )}
        </div>

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
