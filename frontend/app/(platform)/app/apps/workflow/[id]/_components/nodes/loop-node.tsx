'use client'

import * as React from 'react'
import { Handle, Position, NodeResizeControl } from '@xyflow/react'
import { useTranslations } from 'next-intl'
import { Infinity, MoreHorizontal, Play, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ConditionRule } from './condition-node'

// 循环变量类型
export type LoopVariableType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 循环内部变量定义
export interface LoopVariable {
  id: string
  name: string
  type: LoopVariableType
  defaultValue: string
  description?: string
}

// 循环配置
export interface LoopConfig {
  maxIterations: number           // 最大循环次数
  indexVariable: string           // 循环索引变量名，如 index
  // 循环内部变量（每次迭代可更新）
  loopVariables: LoopVariable[]   // 循环变量列表
  // 退出条件（使用与条件分支相同的结构）
  exitConditions: ConditionRule[] // 退出条件规则列表
  exitLogicOperator: 'and' | 'or' // 多条件之间的逻辑关系
  // 输出结果配置
  outputVariable: string          // 循环结果输出变量名，如 results
}

// 默认循环配置
export const defaultLoopConfig: LoopConfig = {
  maxIterations: 10,
  indexVariable: 'index',
  loopVariables: [],
  exitConditions: [],
  exitLogicOperator: 'and',
  outputVariable: 'results',
}

interface LoopNodeData {
  type: string
  label: string
  loopConfig?: LoopConfig
  config: Record<string, unknown>
  [key: string]: unknown
}

interface LoopNodeProps {
  id: string
  selected?: boolean
  data: LoopNodeData
  width?: number
  height?: number
}

// 循环容器节点 - 作为父节点容纳子节点
export function LoopNode({ selected, data, width, height }: LoopNodeProps) {
  const t = useTranslations('workflow')
  const config = data.loopConfig || defaultLoopConfig

  return (
    <div 
      className={cn(
        'group relative rounded-2xl border-2 bg-card shadow-sm transition-all',
        selected 
          ? 'border-primary' 
          : 'border-border hover:border-primary/50'
      )}
      style={{ 
        width: width || 500, 
        height: height || 280,
      }}
    >
      {/* 右下角调整大小手柄 */}
      <NodeResizeControl
        minWidth={400}
        minHeight={220}
        position="bottom-right"
        className="bg-transparent! border-0!"
        style={{ right: 4, bottom: 4 }}
      >
        <svg 
          className="w-3 h-3 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          viewBox="0 0 6 6"
          fill="currentColor"
        >
          <circle cx="5" cy="5" r="1" />
          <circle cx="5" cy="2" r="1" />
          <circle cx="2" cy="5" r="1" />
        </svg>
      </NodeResizeControl>

      {/* Input Handle - 外部输入 */}
      <Handle
        type="target"
        position={Position.Left}
        className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        style={{ top: '50%' }}
      />

      {/* Output Handle - 完成后继续 */}
      <Handle
        type="source"
        position={Position.Right}
        id="done"
        className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
        style={{ top: '50%' }}
      />
      
      {/* 输出变量标签 */}
      <div 
        className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground font-mono bg-muted/50 px-1.5 py-0.5 rounded"
      >
        {config.outputVariable || 'results'}[]
      </div>
      
      {/* Node Label - 顶部标签 */}
      <div className="flex items-center justify-between px-3 pt-2 h-8">
        <div className="flex items-center gap-1.5">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-cyan-500 text-white">
            <Infinity className="h-2.5 w-2.5" />
          </div>
          <span className="text-xs font-medium">{data.label || t('nodesLoop.label')}</span>
        </div>
        <div className="flex items-center gap-1">
          {/* 最大循环次数标记 */}
          <span className="text-[10px] text-cyan-500 bg-cyan-500/10 px-1.5 py-0.5 rounded mr-1">
            {t('nodesLoop.maxIterations', { count: config.maxIterations })}
          </span>
          <button className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity">
            <Play className="h-3 w-3" />
          </button>
          <button className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity">
            <MoreHorizontal className="h-3 w-3" />
          </button>
        </div>
      </div>
      
      {/* 内部子图区域 */}
      <div
        className="absolute left-3 right-3 bottom-3 top-10 rounded-xl border border-dashed border-border/50 bg-muted/50"
      />
    </div>
  )
}

// 循环开始节点 - 作为循环容器内的起始节点
interface LoopStartNodeProps {
  id: string
  selected?: boolean
  data: {
    type: string
    label: string
    parentLoopId: string
    loopConfig?: LoopConfig
    config: Record<string, unknown>
    [key: string]: unknown
  }
}

export function LoopStartNode({ selected, data }: LoopStartNodeProps) {
  const config = data.loopConfig || defaultLoopConfig
  
  // 构建变量显示文本
  const variableNames = [config.indexVariable || 'index']
  if (config.loopVariables && config.loopVariables.length > 0) {
    variableNames.push(...config.loopVariables.map(v => v.name))
  }
  const displayText = variableNames.length > 2 
    ? `${variableNames.slice(0, 2).join(', ')}...` 
    : variableNames.join(', ')
  
  return (
    <div className="group relative">
      {/* 循环开始节点 - 圆形 */}
      <div 
        className={cn(
          'relative flex items-center justify-center',
          'w-10 h-10 rounded-full',
          'bg-card border-2 shadow-sm transition-all',
          selected 
            ? 'border-primary' 
            : 'border-cyan-500/50 hover:border-cyan-500'
        )}
      >
        <Infinity className="h-4 w-4 text-cyan-500" />
        
        {/* Output Handle - 连接到子图内的节点 */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-cyan-500! border-0! transition-transform group-hover:scale-150"
        />
      </div>
      
      {/* 输出变量标签 */}
      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] text-muted-foreground">
        <span className="font-mono">{displayText}</span>
      </div>
    </div>
  )
}

// 退出循环节点 - 作为循环容器内的退出节点
interface LoopExitNodeProps {
  id: string
  selected?: boolean
  data: {
    type: string
    label: string
    parentLoopId: string
    config: Record<string, unknown>
    [key: string]: unknown
  }
}

export function LoopExitNode({ selected }: LoopExitNodeProps) {
  const t = useTranslations('workflow')
  return (
    <div className="group relative">
      {/* 退出循环节点 - 圆形 */}
      <div 
        className={cn(
          'relative flex items-center justify-center',
          'w-10 h-10 rounded-full',
          'bg-card border-2 shadow-sm transition-all',
          selected 
            ? 'border-primary' 
            : 'border-orange-500/50 hover:border-orange-500'
        )}
      >
        <LogOut className="h-4 w-4 text-orange-500" />
        
        {/* Input Handle - 从子图内节点连接过来 */}
        <Handle
          type="target"
          position={Position.Left}
          className="w-2! h-2! rounded-full! bg-orange-500! border-0! transition-transform group-hover:scale-150"
        />
      </div>
      
      {/* 标签 */}
      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] text-muted-foreground">
        {t('nodesCommon.exitLoop')}
      </div>
    </div>
  )
}
