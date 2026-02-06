'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { GitBranch, MoreHorizontal, Home } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 条件分支定义
export interface ConditionBranch {
  id: string
  type: 'if' | 'else_if' | 'else'
  name: string
  conditions: ConditionRule[]
  logicOperator: 'and' | 'or'  // 多条件之间的逻辑关系
}

// 条件规则
export interface ConditionRule {
  id: string
  variable: string        // 变量名，如 {{query}}
  variableSource?: string // 变量来源节点，如 "开始"
  operator: ConditionOperator
  value: string           // 比较值
}

// 条件操作符
export type ConditionOperator = 
  | 'equals'           // 等于
  | 'not_equals'       // 不等于
  | 'contains'         // 包含
  | 'not_contains'     // 不包含
  | 'starts_with'      // 以...开头
  | 'ends_with'        // 以...结尾
  | 'is_empty'         // 为空
  | 'is_not_empty'     // 不为空
  | 'greater_than'     // 大于
  | 'less_than'        // 小于
  | 'greater_or_equal' // 大于等于
  | 'less_or_equal'    // 小于等于


// 不需要值的操作符
export const noValueOperators: ConditionOperator[] = ['is_empty', 'is_not_empty']

// 获取条件操作符标签（带翻译）
export function getConditionOperatorLabels(t: (key: string) => string): Record<ConditionOperator, string> {
  return {
    equals: t('nodesCondition.operatorEquals'),
    not_equals: t('nodesCondition.operatorNotEquals'),
    contains: t('nodesCondition.operatorContains'),
    not_contains: t('nodesCondition.operatorNotContains'),
    starts_with: t('nodesCondition.operatorStartsWith'),
    ends_with: t('nodesCondition.operatorEndsWith'),
    is_empty: t('nodesCondition.operatorIsEmpty'),
    is_not_empty: t('nodesCondition.operatorIsNotEmpty'),
    greater_than: t('nodesCondition.operatorGreaterThan'),
    less_than: t('nodesCondition.operatorLessThan'),
    greater_or_equal: t('nodesCondition.operatorGreaterOrEqual'),
    less_or_equal: t('nodesCondition.operatorLessOrEqual'),
  }
}

// 获取条件操作符短标签（带翻译）
export function getConditionOperatorShortLabels(t: (key: string) => string): Record<ConditionOperator, string> {
  return {
    equals: t('nodesCondition.shortEquals'),
    not_equals: t('nodesCondition.shortNotEquals'),
    contains: t('nodesCondition.shortContains'),
    not_contains: t('nodesCondition.shortNotContains'),
    starts_with: t('nodesCondition.shortStartsWith'),
    ends_with: t('nodesCondition.shortEndsWith'),
    is_empty: t('nodesCondition.shortIsEmpty'),
    is_not_empty: t('nodesCondition.shortIsNotEmpty'),
    greater_than: '>',
    less_than: '<',
    greater_or_equal: '≥',
    less_or_equal: '≤',
  }
}

interface ConditionNodeData {
  type: string
  label: string
  branches?: ConditionBranch[]
  config: Record<string, unknown>
}

interface ConditionNodeProps {
  id: string
  selected?: boolean
  data: ConditionNodeData
}

// 默认分支配置
const defaultBranches: ConditionBranch[] = [
  { id: 'if', type: 'if', name: 'IF', conditions: [], logicOperator: 'and' },
  { id: 'else', type: 'else', name: 'ELSE', conditions: [], logicOperator: 'and' },
]

// 从变量字符串中提取变量名，如 {{query}} -> query
const extractVariableName = (variable: string) => {
  const match = variable.match(/\{\{(.+?)\}\}/)
  return match ? match[1] : variable
}

export function ConditionNode({ selected, data }: ConditionNodeProps) {
  const t = useTranslations('workflow')

  // Helper function to get short operator label
  const getShortOperatorLabel = (op: ConditionOperator) => {
    const labels: Record<ConditionOperator, string> = {
      equals: t('nodesCondition.shortEquals'),
      not_equals: t('nodesCondition.shortNotEquals'),
      contains: t('nodesCondition.shortContains'),
      not_contains: t('nodesCondition.shortNotContains'),
      starts_with: t('nodesCondition.shortStartsWith'),
      ends_with: t('nodesCondition.shortEndsWith'),
      is_empty: t('nodesCondition.shortIsEmpty'),
      is_not_empty: t('nodesCondition.shortIsNotEmpty'),
      greater_than: '>',
      less_than: '<',
      greater_or_equal: '≥',
      less_or_equal: '≤',
    }
    return labels[op]
  }

  // 获取分支列表
  const branches = data.branches && data.branches.length > 0 ? data.branches : defaultBranches
  
  // 使用 ref 来获取实际的 DOM 位置
  const branchRefs = React.useRef<(HTMLDivElement | null)[]>([])

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesCondition.label')}</span>
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
          'min-w-52 max-w-64',
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

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-white">
            <GitBranch className="h-3.5 w-3.5" />
          </div>
          
          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodesCondition.label')}
          </span>
        </div>

        {/* Branches List */}
        <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1.5">
          {branches.map((branch, index) => {
            const isElse = branch.type === 'else'
            const branchLabel = branch.type === 'if' ? 'IF' : branch.type === 'else_if' ? 'ELIF' : 'ELSE'
            const conditionCount = branch.conditions.length
            const firstCondition = branch.conditions[0]
            const hasMultipleConditions = conditionCount > 1
            
            return (
              <div 
                key={branch.id} 
                className="relative"
                ref={el => { branchRefs.current[index] = el }}
              >
                {/* CASE 标签 */}
                {!isElse && (
                  <div className="text-[10px] text-muted-foreground mb-0.5 pl-1">
                    CASE {index + 1}
                  </div>
                )}
                
                <div className="flex items-center gap-1.5">
                  {/* 条件内容 */}
                  <div className={cn(
                    'flex-1 flex items-center gap-1 rounded-md px-2 py-1.5 min-h-[28px]',
                    isElse ? 'bg-transparent' : 'bg-blue-500/10'
                  )}>
                    {!isElse && firstCondition ? (
                      <>
                        {/* 来源节点 */}
                        <div className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                          <Home className="h-2.5 w-2.5" />
                          <span className="max-w-[50px] truncate">{firstCondition.variableSource || t('nodesCommon.start')}</span>
                        </div>
                        <span className="text-muted-foreground/50">/</span>
                        {/* 变量名 */}
                        <div className="flex items-center gap-0.5">
                          <span className="text-primary/80 text-[10px] font-mono">{'{x}'}</span>
                          <span className="text-[11px] text-foreground/80 max-w-[60px] truncate">
                            {extractVariableName(firstCondition.variable)}
                          </span>
                        </div>
                        {/* 多条件指示 */}
                        {hasMultipleConditions && (
                          <span className="text-[10px] text-blue-500 font-medium ml-0.5">
                            {branch.logicOperator === 'and' ? t('nodesCondition.and') : t('nodesCondition.or')}{conditionCount - 1}
                          </span>
                        )}
                      </>
                    ) : !isElse ? (
                      <span className="text-[11px] text-muted-foreground">{t('nodesCondition.clickToConfigure')}</span>
                    ) : null}
                  </div>
                  
                  {/* 条件值（非 ELSE） */}
                  {!isElse && firstCondition && (
                    <div className="flex items-center gap-1 text-[11px] shrink-0">
                      <span className="text-muted-foreground">
                        {getShortOperatorLabel(firstCondition.operator)}
                      </span>
                      {!noValueOperators.includes(firstCondition.operator) && (
                        <span className="text-foreground font-medium max-w-[50px] truncate">
                          {firstCondition.value || '?'}
                        </span>
                      )}
                    </div>
                  )}
                  
                  {/* 分支标签 */}
                  <span className={cn(
                    'text-[10px] font-medium shrink-0',
                    isElse ? 'text-muted-foreground' : 'text-blue-500'
                  )}>
                    {branchLabel}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
        
        {/* 所有 Branch Handles - 放在节点卡片内部，使用绝对定位 */}
        {branches.map((branch, index) => {
          const isElse = branch.type === 'else'
          // 计算位置：header(44px) + 每个分支前面的高度
          // 每个IF/ELIF分支约50px（CASE标签16px + 内容28px + gap6px）
          // ELSE分支约30px（无CASE标签）
          let top = 44 + 8 // header + padding
          for (let i = 0; i < index; i++) {
            const b = branches[i]
            if (b.type === 'else') {
              top += 30
            } else {
              top += 50
            }
          }
          // 加上当前分支内容区域的中心偏移
          if (isElse) {
            top += 14
          } else {
            top += 16 + 14 // CASE标签 + 内容中心
          }
          
          return (
            <Handle
              key={branch.id}
              type="source"
              position={Position.Right}
              id={branch.id}
              className={cn(
                '!w-2 !h-2 !rounded-full !border-0 transition-transform group-hover:scale-150',
                isElse ? '!bg-muted-foreground' : '!bg-blue-500'
              )}
              style={{ top }}
            />
          )
        })}
      </div>
    </div>
  )
}
