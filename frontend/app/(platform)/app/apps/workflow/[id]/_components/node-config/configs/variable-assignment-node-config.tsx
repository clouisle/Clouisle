'use client'

import * as React from 'react'
import { Plus, Trash2, Search, ChevronDown, ArrowRight, Ban, Edit3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { AvailableVariable } from '../types'
import { 
  VariableAssignmentConfig, 
  AssignmentItem,
  AssignmentOperation,
  assignmentOperationConfig,
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
                {assignment.targetVariableLabel || assignment.targetVariable}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">选择目标变量...</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="搜索对话变量"
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
                        ? '暂无对话变量，请先在开始节点添加'
                        : '未找到匹配的变量'}
                    </div>
                  )
                }
                
                return filtered.map(variable => (
                  <button
                    key={variable.id}
                    className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                    onClick={() => {
                      handleUpdateAssignment(assignment.id, {
                        targetVariable: variable.name,
                        targetVariableLabel: variable.name,
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
                {assignment.variableRef.replace(/\{\{|\}\}/g, '')}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">选择源变量...</span>
          )}
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <div className="p-2 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="搜索变量"
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
                      未找到匹配的变量
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
                          handleUpdateAssignment(assignment.id, {
                            variableRef: `{{${variable.name}}}`,
                            variableRefNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel,
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
            <Label className="text-xs font-medium">赋值操作</Label>
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
            暂无赋值操作，点击 + 添加
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
                      赋值 {index + 1}
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
                    <Label className="text-xs text-muted-foreground">目标变量</Label>
                    {renderTargetVariableSelector(assignment)}
                  </div>
                  
                  {/* 操作类型 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">操作</Label>
                    <Select
                      value={assignment.operation}
                      onValueChange={(v) => {
                        const updates: Partial<AssignmentItem> = { operation: v as AssignmentOperation }
                        // 切换操作时清空相关字段
                        if (v === 'clear') {
                          updates.variableRef = undefined
                          updates.variableRefNodeLabel = undefined
                          updates.constantValue = undefined
                        } else if (v === 'overwrite') {
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
                  {assignment.operation === 'overwrite' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">源变量</Label>
                      {renderSourceVariableSelector(assignment)}
                    </div>
                  )}
                  
                  {assignment.operation === 'set' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">常量值</Label>
                      <Textarea
                        value={assignment.constantValue || ''}
                        onChange={(e) => handleUpdateAssignment(assignment.id, { constantValue: e.target.value })}
                        placeholder="输入要设置的值..."
                        className="min-h-20 text-xs font-mono resize-none"
                      />
                      <p className="text-[10px] text-muted-foreground">
                        支持 JSON 格式，如：字符串 "hello"、数字 123、数组 [1,2,3]、对象 {`{"key":"value"}`}
                      </p>
                    </div>
                  )}
                  
                  {assignment.operation === 'clear' && (
                    <div className="text-xs text-muted-foreground bg-muted/50 rounded-md p-2">
                      将清空目标变量的值（字符串→""，数字→0，数组→[]，对象→{}）
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
        <p>• <strong>覆盖</strong>：用另一个变量的值替换目标变量</p>
        <p>• <strong>清空</strong>：将目标变量重置为空值</p>
        <p>• <strong>设置</strong>：将目标变量设为指定的常量</p>
      </div>
    </div>
  )
}
