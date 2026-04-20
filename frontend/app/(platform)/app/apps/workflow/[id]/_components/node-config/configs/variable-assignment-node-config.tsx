'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'
import {
  VariableAssignmentConfig,
  AssignmentItem,
  AssignmentOperation,
  getAssignmentOperationConfig,
  defaultVariableAssignmentConfig,
} from '../../nodes/variable-assignment-node'

interface VariableAssignmentNodeConfigProps {
  config: VariableAssignmentConfig
  variables: AvailableVariable[]
  conversationVariables: AvailableVariable[]  // 对话变量（可写入的目标）
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: VariableAssignmentConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function VariableAssignmentNodeConfig({
  config,
  variables,
  conversationVariables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: VariableAssignmentNodeConfigProps) {
  const t = useTranslations('workflow')
  const assignmentOperationConfig = getAssignmentOperationConfig(t)

  // 确保 config 有默认值
  const safeConfig: VariableAssignmentConfig = {
    ...defaultVariableAssignmentConfig,
    ...config,
    assignments: config.assignments || [],
  }

  // 过滤变量
  const filterVariables = (vars: AvailableVariable[], search: string) => {
    if (!search) return vars
    return vars.filter(v => 
      v.name.toLowerCase().includes(search.toLowerCase())
    )
  }

  // 分组变量
  const groupVariables = (vars: AvailableVariable[]) => {
    const groups = vars.reduce((acc, v) => {
      if (!acc[v.group]) {
        acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
      }
      acc[v.group].items.push(v)
      return acc
    }, {} as Record<string, { label: string; isSystem: boolean; items: AvailableVariable[] }>)
    
    const entries = Object.entries(groups)
    entries.sort((a, b) => {
      if (a[1].isSystem && !b[1].isSystem) return 1
      if (!a[1].isSystem && b[1].isSystem) return -1
      return 0
    })
    
    return entries
  }

  // 添加赋值项
  const handleAddAssignment = () => {
    const newAssignment: AssignmentItem = {
      id: `assign_${Date.now()}`,
      targetVariable: '',
      operation: 'set',
      constantValue: '',
    }
    onConfigChange({
      ...safeConfig,
      assignments: [...safeConfig.assignments, newAssignment],
    })
  }

  // 更新赋值项
  const handleUpdateAssignment = (id: string, updates: Partial<AssignmentItem>) => {
    onConfigChange({
      ...safeConfig,
      assignments: safeConfig.assignments.map(a => 
        a.id === id ? { ...a, ...updates } : a
      ),
    })
  }

  // 删除赋值项
  const handleDeleteAssignment = (id: string) => {
    onConfigChange({
      ...safeConfig,
      assignments: safeConfig.assignments.filter(a => a.id !== id),
    })
  }

  // 渲染目标变量选择器（对话变量）
  const renderTargetVariableSelector = (assignment: AssignmentItem) => {
    const popoverId = `target-var-${assignment.id}`
    
    return (
      <Popover 
        open={openVariablePopover === popoverId}
        onOpenChange={(isOpen) => {
          onOpenVariablePopoverChange(isOpen ? popoverId : null)
          if (!isOpen) onVariableSearchChange('')
        }}
      >
        <PopoverTrigger
          className={cn(
            'w-full h-9 flex items-center justify-start gap-1 px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {assignment.targetVariable ? (
            <>
              <span className="text-teal-500/80 font-mono text-xs">{'{x}'}</span>
              <span className="text-xs truncate">
                {assignment.targetVariableNodeLabel && <span className="text-muted-foreground">{assignment.targetVariableNodeLabel} / </span>}
                {assignment.targetVariableLabel || assignment.targetVariable}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">{t('configVariableAssignment.selectTargetVariable')}</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder={t('configVariableAssignment.searchConversationVariables')}
                value={variableSearch}
                onChange={(e) => onVariableSearchChange(e.target.value)}
                className="h-8 pl-8 text-xs"
              />
            </div>
          </div>
          <ScrollArea className="h-50">
            <div className="p-1">
              {(() => {
                const filtered = filterVariables(conversationVariables, variableSearch)
                
                if (filtered.length === 0) {
                  return (
                    <div className="py-4 text-center text-xs text-muted-foreground">
                      {conversationVariables.length === 0
                        ? t('configVariableAssignment.noConversationVariables')
                        : t('configCommon.noMatchingVariables')}
                    </div>
                  )
                }
                
                return filtered.map(variable => (
                  <button
                    key={variable.id}
                    className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                    onClick={() => {
                      handleUpdateAssignment(assignment.id, {
                        targetVariable: variable.id,
                        targetVariableLabel: variable.name,
                        targetVariableNodeLabel: variable.groupLabel,
                      })
                      onOpenVariablePopoverChange(null)
                      onVariableSearchChange('')
                    }}
                  >
                    <span className="flex items-center gap-1.5">
                      <span className="text-teal-500/80 font-mono">{'{x}'}</span>
                      <span>{variable.name}</span>
                    </span>
                    <span className="text-muted-foreground">{variable.type}</span>
                  </button>
                ))
              })()}
            </div>
          </ScrollArea>
        </PopoverContent>
      </Popover>
    )
  }

  // 渲染源变量选择器（用于覆盖操作）
  const renderSourceVariableSelector = (assignment: AssignmentItem) => {
    const popoverId = `source-var-${assignment.id}`
    
    return (
      <Popover 
        open={openVariablePopover === popoverId}
        onOpenChange={(isOpen) => {
          onOpenVariablePopoverChange(isOpen ? popoverId : null)
          if (!isOpen) onVariableSearchChange('')
        }}
      >
        <PopoverTrigger
          className={cn(
            'w-full h-9 flex items-center justify-start gap-1 px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {assignment.variableRef ? (
            <>
              <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
              <span className="text-xs truncate">
                {assignment.variableRefNodeLabel && <span className="text-muted-foreground">{assignment.variableRefNodeLabel} / </span>}
                {extractVariableDisplayName(assignment.variableRef)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">{t('configVariableAssignment.selectSourceVariable')}</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder={t('configCommon.searchVariable')}
                value={variableSearch}
                onChange={(e) => onVariableSearchChange(e.target.value)}
                className="h-8 pl-8 text-xs"
              />
            </div>
          </div>
          <ScrollArea className="h-50">
            <div className="p-1">
              {(() => {
                const filtered = filterVariables(variables, variableSearch)
                const groupEntries = groupVariables(filtered)

                if (groupEntries.length === 0) {
                  return (
                    <div className="py-4 text-center text-xs text-muted-foreground">
                      {t('configCommon.noMatchingVariables')}
                    </div>
                  )
                }
                
                return groupEntries.map(([groupId, group]) => (
                  <div key={groupId} className="mb-1">
                    <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                      {group.label}
                    </div>
                    {group.items.map(variable => (
                      <button
                        key={variable.id}
                        className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                        onClick={() => {
                          // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
                          handleUpdateAssignment(assignment.id, {
                            variableRef: `{{${variable.id}}}`,
                            variableRefNodeLabel: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel,
                          })
                          onOpenVariablePopoverChange(null)
                          onVariableSearchChange('')
                        }}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className={cn(
                            'font-mono',
                            variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                          )}>{'{x}'}</span>
                          <span>{variable.name}</span>
                        </span>
                        <span className="text-muted-foreground">{variable.type}</span>
                      </button>
                    ))}
                  </div>
                ))
              })()}
            </div>
          </ScrollArea>
        </PopoverContent>
      </Popover>
    )
  }

  return (
    <div className="space-y-4">
      {/* 赋值列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configVariableAssignment.assignmentOperations')}</Label>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleAddAssignment}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.assignments.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center bg-muted/30 rounded-md">
            {t('configVariableAssignment.noAssignments')}
          </p>
        ) : (
          <div className="space-y-3">
            {safeConfig.assignments.map((assignment, index) => {
              const opConfig = assignmentOperationConfig[assignment.operation]
              const OpIcon = opConfig.icon
              
              return (
                <div
                  key={assignment.id}
                  className="bg-muted/30 rounded-lg p-3 space-y-3"
                >
                  {/* 头部：序号 + 删除 */}
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-muted-foreground">
                      {t('configVariableAssignment.assignmentIndex', { index: index + 1 })}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-destructive"
                      onClick={() => handleDeleteAssignment(assignment.id)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                  
                  {/* 目标变量 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t('configVariableAssignment.targetVariable')}</Label>
                    {renderTargetVariableSelector(assignment)}
                  </div>
                  
                  {/* 操作类型 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">{t('configVariableAssignment.operation')}</Label>
                    <Select
                      value={assignment.operation}
                      onValueChange={(v) => {
                        const updates: Partial<AssignmentItem> = { operation: v as AssignmentOperation }
                        // 切换操作时清空相关字段
                        if (v === 'clear') {
                          updates.variableRef = undefined
                          updates.variableRefNodeLabel = undefined
                          updates.constantValue = undefined
                        } else if (v === 'overwrite' || v === 'append') {
                          updates.constantValue = undefined
                        } else if (v === 'set') {
                          updates.variableRef = undefined
                          updates.variableRefNodeLabel = undefined
                        }
                        handleUpdateAssignment(assignment.id, updates)
                      }}
                    >
                      <SelectTrigger className="w-full h-9 text-xs">
                        <SelectValue>
                          <span className="flex items-center gap-2">
                            <OpIcon className="h-3.5 w-3.5" />
                            {opConfig.label}
                          </span>
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(assignmentOperationConfig).map(([key, cfg]) => {
                          const Icon = cfg.icon
                          return (
                            <SelectItem key={key} value={key} className="text-xs">
                              <span className="flex items-center gap-2">
                                <Icon className="h-3.5 w-3.5" />
                                {cfg.label}
                              </span>
                            </SelectItem>
                          )
                        })}
                      </SelectContent>
                    </Select>
                    <p className="text-[10px] text-muted-foreground">{opConfig.description}</p>
                  </div>
                  
                  {/* 值配置 - 根据操作类型显示不同内容 */}
                  {(assignment.operation === 'overwrite' || assignment.operation === 'append') && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">
                        {assignment.operation === 'append' ? t('configVariableAssignment.appendValue') : t('configVariableAssignment.sourceVariable')}
                      </Label>
                      {renderSourceVariableSelector(assignment)}
                    </div>
                  )}
                  
                  {assignment.operation === 'set' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">{t('configVariableAssignment.constantValue')}</Label>
                      <Textarea
                        value={assignment.constantValue || ''}
                        onChange={(e) => handleUpdateAssignment(assignment.id, { constantValue: e.target.value })}
                        placeholder={t('configVariableAssignment.setValuePlaceholder')}
                        className="min-h-20 text-xs font-mono resize-none"
                      />
                      <p className="text-[10px] text-muted-foreground">
                        {t('configVariableAssignment.jsonFormatHint')}
                      </p>
                    </div>
                  )}

                  {assignment.operation === 'clear' && (
                    <div className="text-xs text-muted-foreground bg-muted/50 rounded-md p-2">
                      {t('configVariableAssignment.clearHint')}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 提示信息 */}
      <div className="text-[10px] text-muted-foreground bg-muted/30 rounded-md p-2 space-y-1">
        <p>{t('configVariableAssignment.hintOverwrite')}</p>
        <p>{t('configVariableAssignment.hintClear')}</p>
        <p>{t('configVariableAssignment.hintSet')}</p>
        <p>{t('configVariableAssignment.hintAppend')}</p>
      </div>
    </div>
  )
}
