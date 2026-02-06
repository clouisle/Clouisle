'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Variable, MoreHorizontal, Home, ArrowRight, Ban, Edit3, Plus } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 赋值操作类型
export type AssignmentOperation = 'overwrite' | 'clear' | 'set' | 'append'

// 单个赋值项
export interface AssignmentItem {
  id: string
  targetVariable: string           // 目标对话变量名
  targetVariableLabel?: string     // 目标变量显示名
  targetVariableNodeLabel?: string // 目标变量所属节点标签
  operation: AssignmentOperation   // 赋值操作
  // 值来源（overwrite/append 用 variableRef，set 用 constantValue）
  variableRef?: string             // 变量引用 {{node.var}}
  variableRefNodeLabel?: string    // 来源节点标签
  constantValue?: string           // 常量值
}

// 变量赋值配置
export interface VariableAssignmentConfig {
  assignments: AssignmentItem[]
}

// 默认配置
export const defaultVariableAssignmentConfig: VariableAssignmentConfig = {
  assignments: [],
}

// 操作类型配置（静态部分）
export const assignmentOperationConfig: Record<AssignmentOperation, {
  shortLabel: string
  icon: React.ComponentType<{ className?: string }>
}> = {
  overwrite: {
    shortLabel: '←',
    icon: ArrowRight,
  },
  clear: {
    shortLabel: '∅',
    icon: Ban,
  },
  set: {
    shortLabel: '=',
    icon: Edit3,
  },
  append: {
    shortLabel: '+',
    icon: Plus,
  },
}

// 获取带翻译的操作类型配置
export function getAssignmentOperationConfig(t: (key: string) => string): Record<AssignmentOperation, {
  label: string
  shortLabel: string
  description: string
  icon: React.ComponentType<{ className?: string }>
}> {
  return {
    overwrite: {
      label: t('nodesVariableAssignment.opOverwrite'),
      shortLabel: '←',
      description: t('nodesVariableAssignment.opOverwriteDesc'),
      icon: ArrowRight,
    },
    clear: {
      label: t('nodesVariableAssignment.opClear'),
      shortLabel: '∅',
      description: t('nodesVariableAssignment.opClearDesc'),
      icon: Ban,
    },
    set: {
      label: t('nodesVariableAssignment.opSet'),
      shortLabel: '=',
      description: t('nodesVariableAssignment.opSetDesc'),
      icon: Edit3,
    },
    append: {
      label: t('nodesVariableAssignment.opAppend'),
      shortLabel: '+',
      description: t('nodesVariableAssignment.opAppendDesc'),
      icon: Plus,
    },
  }
}

interface VariableAssignmentNodeData {
  type: string
  label: string
  variableAssignmentConfig?: VariableAssignmentConfig
  config: Record<string, unknown>
  [key: string]: unknown
}

interface VariableAssignmentNodeProps {
  id: string
  selected?: boolean
  data: VariableAssignmentNodeData
}

// 从变量字符串中提取变量名
const extractVariableName = (variable: string) => {
  const match = variable.match(/\{\{(.+?)\}\}/)
  if (match) {
    const parts = match[1].split('.')
    return parts[parts.length - 1]
  }
  return variable
}

// 截断显示常量值
const truncateValue = (value: string, maxLen = 10) => {
  if (!value) return '""'
  if (value.length <= maxLen) return value
  return value.slice(0, maxLen) + '...'
}

export function VariableAssignmentNode({ selected, data }: VariableAssignmentNodeProps) {
  const t = useTranslations('workflow')
  const config = data.variableAssignmentConfig || defaultVariableAssignmentConfig
  const assignments = config.assignments || []
  const hasAssignments = assignments.length > 0

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesVariableAssignment.label')}</span>
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
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-500 text-white">
            <Variable className="h-3.5 w-3.5" />
          </div>

          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodesVariableAssignment.label')}
          </span>

          {/* Count badge */}
          {hasAssignments && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-600 dark:text-teal-400 font-medium">
              {t('nodesVariableAssignment.itemCount', { n: assignments.length })}
            </span>
          )}
        </div>

        {/* Assignments List */}
        <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
          {hasAssignments ? (
            assignments.slice(0, 3).map((assignment) => {
              const opConfig = assignmentOperationConfig[assignment.operation]

              return (
                <div
                  key={assignment.id}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1.5 bg-teal-500/10"
                >
                  {/* 目标变量 */}
                  <div className="flex items-center gap-0.5">
                    <span className="text-teal-500/80 text-[10px] font-mono">{'{x}'}</span>
                    <span className="text-[11px] text-foreground/80 max-w-14 truncate font-medium">
                      {assignment.targetVariableLabel || extractVariableName(assignment.targetVariable)}
                    </span>
                  </div>

                  {/* 操作符 */}
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {opConfig.shortLabel}
                  </span>

                  {/* 值 */}
                  {(assignment.operation === 'overwrite' || assignment.operation === 'append') && assignment.variableRef && (
                    <div className="flex items-center gap-0.5 text-[10px]">
                      <Home className="h-2.5 w-2.5 text-muted-foreground" />
                      <span className="text-muted-foreground max-w-10 truncate">
                        {assignment.variableRefNodeLabel || t('nodesCommon.unknown')}
                      </span>
                      <span className="text-muted-foreground/50">/</span>
                      <span className="text-foreground/80 max-w-10 truncate">
                        {extractVariableName(assignment.variableRef)}
                      </span>
                    </div>
                  )}
                  {assignment.operation === 'set' && (
                    <span className="text-[10px] text-teal-600 dark:text-teal-400 font-mono max-w-16 truncate">
                      {truncateValue(assignment.constantValue || '')}
                    </span>
                  )}
                  {assignment.operation === 'clear' && (
                    <span className="text-[10px] text-muted-foreground italic">{t('nodesVariableAssignment.empty')}</span>
                  )}
                </div>
              )
            })
          ) : (
            <div className="flex items-center justify-center py-2 text-[11px] text-muted-foreground">
              {t('nodesVariableAssignment.clickToConfigure')}
            </div>
          )}

          {/* 更多指示 */}
          {assignments.length > 3 && (
            <div className="text-[10px] text-muted-foreground text-center py-0.5">
              {t('nodesVariableAssignment.moreAssignments', { n: assignments.length - 3 })}
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
