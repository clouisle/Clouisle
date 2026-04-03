'use client'

import * as React from 'react'
import { Handle, Position, NodeResizeControl } from '@xyflow/react'
import { RefreshCw, LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslations } from 'next-intl'

// 迭代类型
export type IteratorType = 'array' | 'object'

// 迭代配置
export interface IterationConfig {
  iteratorVariable: string        // 要迭代的变量，如 {{items}}
  iteratorSource?: string         // 变量来源节点
  iteratorType: IteratorType      // 迭代类型：数组或对象
  // 数组迭代输出变量
  itemVariable: string            // 当前项变量名，如 item
  indexVariable: string           // 索引变量名，如 index
  // 对象迭代输出变量
  keyVariable: string             // 键名变量名，如 key
  valueVariable: string           // 键值变量名，如 value
  // 并行配置
  parallel: boolean               // 是否并行执行
  maxParallel?: number            // 最大并行数
  // 输出结果配置
  outputVariable: string          // 迭代结果输出变量名，如 results
}

// 默认迭代配置
export const defaultIterationConfig: IterationConfig = {
  iteratorVariable: '',
  iteratorSource: '',
  iteratorType: 'array',
  itemVariable: 'item',
  indexVariable: 'index',
  keyVariable: 'key',
  valueVariable: 'value',
  parallel: false,
  maxParallel: 10,
  outputVariable: 'results',
}

interface IterationNodeData {
  type: string
  label: string
  iterationConfig?: IterationConfig
  config: Record<string, unknown>
  [key: string]: unknown
}

interface IterationNodeProps {
  id: string
  selected?: boolean
  data: IterationNodeData
  width?: number
  height?: number
}

// 迭代容器节点 - 作为父节点容纳子节点
export function IterationNode({ selected, data, width, height }: IterationNodeProps) {
  const t = useTranslations('workflow')
  const config = data.iterationConfig || defaultIterationConfig

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
        {config.outputVariable}[]
      </div>
      
      {/* Node Label - 顶部标签 */}
      <div className="flex items-center justify-between px-3 pt-2 h-8">
        <div className="flex items-center gap-1.5">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-cyan-500 text-white">
            <RefreshCw className="h-2.5 w-2.5" />
          </div>
          <span className="text-xs font-medium">{data.label || t('nodesIteration.label')}</span>
        </div>
        <div className="flex items-center gap-1" />
      </div>
      
      {/* 内部子图区域 */}
      <div
        className="absolute left-3 right-3 bottom-3 top-10 rounded-xl border border-dashed border-border/50 bg-muted/50"
      />
      
      {/* 并行标记 */}
      {config.parallel && (
        <div className="absolute top-2 right-12 text-[10px] text-cyan-500 bg-cyan-500/10 px-1.5 py-0.5 rounded">
          {t('nodesIteration.parallel')} {config.maxParallel && `×${config.maxParallel}`}
        </div>
      )}
    </div>
  )
}

// 迭代开始节点 - 作为迭代容器内的起始节点
interface IterationStartNodeProps {
  id: string
  selected?: boolean
  data: {
    type: string
    label: string
    parentIterationId: string
    iterationConfig?: IterationConfig
    config: Record<string, unknown>
    [key: string]: unknown
  }
}

export function IterationStartNode({ selected, data }: IterationStartNodeProps) {
  const config = data.iterationConfig || defaultIterationConfig
  
  return (
    <div className="group relative">
      {/* 迭代开始节点 - 圆形 */}
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
        <RefreshCw className="h-4 w-4 text-cyan-500" />
        
        {/* Output Handle - 连接到子图内的节点 */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-cyan-500! border-0! transition-transform group-hover:scale-150"
        />
      </div>
      
      {/* 输出变量标签 */}
      <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[9px] text-muted-foreground">
        {config.iteratorType === 'object' ? (
          <span className="font-mono">{config.keyVariable}, {config.valueVariable}</span>
        ) : (
          <span className="font-mono">{config.itemVariable}, {config.indexVariable}</span>
        )}
      </div>
    </div>
  )
}

// 退出循环节点 - 作为迭代容器内的退出节点
interface IterationExitNodeProps {
  id: string
  selected?: boolean
  data: {
    type: string
    label: string
    parentIterationId: string
    config: Record<string, unknown>
    [key: string]: unknown
  }
}

export function IterationExitNode({ selected }: IterationExitNodeProps) {
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

