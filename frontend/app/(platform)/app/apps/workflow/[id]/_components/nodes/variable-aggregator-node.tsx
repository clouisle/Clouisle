'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Combine, MoreHorizontal, Home, Braces, List, Link, Merge } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 聚合模式
export type AggregationMode = 'object' | 'array' | 'concat' | 'merge'

// 变量映射项
export interface VariableMapping {
  id: string
  sourceVariable: string      // 源变量，如 {{node1.output}}
  sourceNodeLabel?: string    // 源节点名称（用于显示）
  targetKey?: string          // 目标键名（object模式下使用）
}

// 聚合器配置
export interface VariableAggregatorConfig {
  mode: AggregationMode           // 聚合模式
  variables: VariableMapping[]    // 要聚合的变量列表
  outputVariable: string          // 输出变量名
  // concat模式特有配置
  separator?: string              // 分隔符（默认为空字符串）
  // merge模式特有配置
  mergeStrategy?: 'shallow' | 'deep'  // 合并策略
}

// 默认配置
export const defaultVariableAggregatorConfig: VariableAggregatorConfig = {
  mode: 'object',
  variables: [],
  outputVariable: 'result',
  separator: '',
  mergeStrategy: 'shallow',
}

// 聚合模式图标配置
export const aggregationModeIcons: Record<AggregationMode, React.ComponentType<{ className?: string }>> = {
  object: Braces,
  array: List,
  concat: Link,
  merge: Merge,
}

// 聚合模式输出类型配置
export const aggregationModeOutputTypes: Record<AggregationMode, string> = {
  object: 'Object',
  array: 'Array',
  concat: 'String',
  merge: 'Object',
}

// 获取聚合模式配置（带翻译）
export function getAggregationModeConfig(t: (key: string) => string): Record<AggregationMode, {
  label: string
  description: string
  outputType: string
  icon: React.ComponentType<{ className?: string }>
}> {
  return {
    object: {
      label: t('nodesVariableAggregator.modeObject'),
      description: t('nodesVariableAggregator.modeObjectDesc'),
      outputType: 'Object',
      icon: Braces,
    },
    array: {
      label: t('nodesVariableAggregator.modeArray'),
      description: t('nodesVariableAggregator.modeArrayDesc'),
      outputType: 'Array',
      icon: List,
    },
    concat: {
      label: t('nodesVariableAggregator.modeConcat'),
      description: t('nodesVariableAggregator.modeConcatDesc'),
      outputType: 'String',
      icon: Link,
    },
    merge: {
      label: t('nodesVariableAggregator.modeMerge'),
      description: t('nodesVariableAggregator.modeMergeDesc'),
      outputType: 'Object',
      icon: Merge,
    },
  }
}

interface VariableAggregatorNodeData {
  type: string
  label: string
  variableAggregatorConfig?: VariableAggregatorConfig
  config: Record<string, unknown>
  [key: string]: unknown
}

interface VariableAggregatorNodeProps {
  id: string
  selected?: boolean
  data: VariableAggregatorNodeData
}

// 从变量字符串中提取变量名，如 {{node.output}} -> output
const extractVariableName = (variable: string) => {
  const match = variable.match(/\{\{(.+?)\}\}/)
  if (match) {
    const parts = match[1].split('.')
    return parts[parts.length - 1]
  }
  return variable
}

export function VariableAggregatorNode({ id, selected, data }: VariableAggregatorNodeProps) {
  const t = useTranslations('workflow')
  const config = data.variableAggregatorConfig || defaultVariableAggregatorConfig
  const aggregationModeConfig = getAggregationModeConfig(t)
  const modeConfig = aggregationModeConfig[config.mode]
  const ModeIcon = modeConfig.icon
  const variables = config.variables || []
  const hasVariables = variables.length > 0

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesVariableAggregator.label')}</span>
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
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500 text-white">
            <Combine className="h-3.5 w-3.5" />
          </div>
          
          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodesVariableAggregator.label')}
          </span>
          
          {/* Mode badge */}
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-600 dark:text-violet-400">
            <ModeIcon className="h-3 w-3" />
            <span className="text-[10px] font-medium">{modeConfig.label}</span>
          </div>
        </div>

        {/* Variables List */}
        <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
          {hasVariables ? (
            variables.slice(0, 3).map((variable, index) => (
              <div 
                key={variable.id}
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 bg-violet-500/10"
              >
                {/* 序号 */}
                <span className="text-[10px] text-muted-foreground w-3">{index + 1}.</span>
                
                {/* 来源节点 */}
                <div className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                  <Home className="h-2.5 w-2.5" />
                  <span className="max-w-12.5 truncate">{variable.sourceNodeLabel || t('nodesCommon.unknown')}</span>
                </div>
                <span className="text-muted-foreground/50">/</span>
                
                {/* 变量名 */}
                <div className="flex items-center gap-0.5">
                  <span className="text-violet-500/80 text-[10px] font-mono">{'{x}'}</span>
                  <span className="text-[11px] text-foreground/80 max-w-12.5 truncate">
                    {extractVariableName(variable.sourceVariable)}
                  </span>
                </div>
                
                {/* object模式显示目标键名 */}
                {config.mode === 'object' && variable.targetKey && (
                  <>
                    <span className="text-muted-foreground/50">→</span>
                    <span className="text-[11px] text-violet-600 dark:text-violet-400 font-medium max-w-10 truncate">
                      {variable.targetKey}
                    </span>
                  </>
                )}
              </div>
            ))
          ) : (
            <div className="flex items-center justify-center py-2 text-[11px] text-muted-foreground">
              {t('nodesVariableAggregator.clickToConfigure')}
            </div>
          )}
          
          {/* 更多变量指示 */}
          {variables.length > 3 && (
            <div className="text-[10px] text-muted-foreground text-center py-0.5">
              {t('nodesVariableAggregator.moreVariables', { n: variables.length - 3 })}
            </div>
          )}
        </div>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />
      </div>
    </div>
  )
}
