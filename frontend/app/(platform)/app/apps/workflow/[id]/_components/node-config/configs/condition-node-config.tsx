'use client'

import * as React from 'react'
import { Plus, Trash2, ChevronDown, ChevronUp, GripVertical, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { AvailableVariable } from '../types'
import { extractVariableDisplayName } from '../types'
import { 
  ConditionBranch, 
  ConditionRule, 
  ConditionOperator, 
  conditionOperatorLabels,
  conditionOperatorShortLabels,
  noValueOperators 
} from '../../nodes/condition-node'

interface ConditionNodeConfigProps {
  branches: ConditionBranch[]
  expandedBranches: Set<string>
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onBranchesChange: (branches: ConditionBranch[]) => void
  onExpandedBranchesChange: (expanded: Set<string>) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function ConditionNodeConfig({
  branches,
  expandedBranches,
  variables,
  variableSearch,
  openVariablePopover,
  onBranchesChange,
  onExpandedBranchesChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: ConditionNodeConfigProps) {

  // 切换分支展开/收起
  const toggleBranchExpand = (branchId: string) => {
    const next = new Set(expandedBranches)
    if (next.has(branchId)) {
      next.delete(branchId)
    } else {
      next.add(branchId)
    }
    onExpandedBranchesChange(next)
  }

  // 添加 ELSE IF 分支
  const addElseIfBranch = () => {
    const elseIndex = branches.findIndex(b => b.type === 'else')
    const newBranch: ConditionBranch = {
      id: `else_if_${Date.now()}`,
      type: 'else_if',
      name: `ELIF ${branches.filter(b => b.type === 'else_if').length + 1}`,
      conditions: [],
      logicOperator: 'and',
    }
    
    const newBranches = [...branches]
    if (elseIndex !== -1) {
      newBranches.splice(elseIndex, 0, newBranch)
    } else {
      newBranches.push(newBranch)
    }
    onBranchesChange(newBranches)
    onExpandedBranchesChange(new Set(expandedBranches).add(newBranch.id))
  }

  // 删除分支
  const removeBranch = (branchId: string) => {
    onBranchesChange(branches.filter(b => b.id !== branchId))
  }

  // 更新分支名称
  const updateBranchName = (branchId: string, name: string) => {
    onBranchesChange(branches.map(b => b.id === branchId ? { ...b, name } : b))
  }

  // 更新分支逻辑操作符
  const updateBranchLogicOperator = (branchId: string, logicOperator: 'and' | 'or') => {
    onBranchesChange(branches.map(b => b.id === branchId ? { ...b, logicOperator } : b))
  }

  // 添加条件规则
  const addConditionRule = (branchId: string) => {
    const newRule: ConditionRule = {
      id: `rule_${Date.now()}`,
      variable: '',
      variableSource: '开始',
      operator: 'equals',
      value: '',
    }
    onBranchesChange(branches.map(b => 
      b.id === branchId 
        ? { ...b, conditions: [...b.conditions, newRule] }
        : b
    ))
  }

  // 更新条件规则
  const updateConditionRule = (branchId: string, ruleId: string, updates: Partial<ConditionRule>) => {
    onBranchesChange(branches.map(b => 
      b.id === branchId 
        ? { 
            ...b, 
            conditions: b.conditions.map(r => 
              r.id === ruleId ? { ...r, ...updates } : r
            ) 
          }
        : b
    ))
  }

  // 删除条件规则
  const removeConditionRule = (branchId: string, ruleId: string) => {
    onBranchesChange(branches.map(b => 
      b.id === branchId 
        ? { ...b, conditions: b.conditions.filter(r => r.id !== ruleId) }
        : b
    ))
  }

  // 选择变量
  // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
  const selectVariable = (branchId: string, ruleId: string, variableId: string, variableName: string, isSystem: boolean) => {
    updateConditionRule(branchId, ruleId, { 
      variable: `{{${variableId}}}`,
      variableSource: isSystem ? 'SYSTEM' : '开始'
    })
    onOpenVariablePopoverChange(null)
    onVariableSearchChange('')
  }

  // 过滤变量
  const filterVariables = (search: string) => {
    if (!search) return variables
    return variables.filter(v => 
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

  return (
    <div className="space-y-3">
      {/* 分支列表 */}
      {branches.map((branch) => {
        const isExpanded = expandedBranches.has(branch.id)
        const isElse = branch.type === 'else'
        const canDelete = branch.type === 'else_if'
        
        return (
          <div
            key={branch.id}
            className={cn(
              'rounded-lg border',
              isExpanded ? 'bg-muted/30' : 'bg-card'
            )}
          >
            {/* 分支头部 */}
            <div 
              className="flex items-center gap-2 px-3 py-2 cursor-pointer"
              onClick={() => toggleBranchExpand(branch.id)}
            >
              <GripVertical className="h-3.5 w-3.5 text-muted-foreground cursor-grab" />
              
              {isElse ? (
                <span className="text-xs font-semibold text-orange-500">{branch.name}</span>
              ) : (
                <Input
                  value={branch.name}
                  onChange={(e) => {
                    e.stopPropagation()
                    updateBranchName(branch.id, e.target.value)
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="h-6 w-20 text-xs font-semibold px-1.5 bg-transparent border-transparent hover:border-input focus:border-input"
                />
              )}
              
              {!isElse && branch.conditions.length > 0 && (
                <span className="text-[10px] text-muted-foreground">
                  {branch.conditions.length} 个条件
                </span>
              )}
              
              <div className="flex-1" />
              
              {canDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeBranch(branch.id)
                  }}
                >
                  <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                </Button>
              )}
              
              {isExpanded ? (
                <ChevronUp className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
            
            {/* 分支内容 */}
            {isExpanded && !isElse && (
              <div className="px-3 pb-3 space-y-2">
                {/* 逻辑操作符选择 */}
                {branch.conditions.length > 1 && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">满足</span>
                    <Select
                      value={branch.logicOperator}
                      onValueChange={(v) => updateBranchLogicOperator(branch.id, v as 'and' | 'or')}
                    >
                      <SelectTrigger className="h-7 w-16">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="and" className="text-xs">所有</SelectItem>
                        <SelectItem value="or" className="text-xs">任一</SelectItem>
                      </SelectContent>
                    </Select>
                    <span className="text-muted-foreground">条件时执行</span>
                  </div>
                )}
                
                {/* 条件规则列表 */}
                {branch.conditions.map((rule, ruleIndex) => (
                  <div key={rule.id} className="flex items-start gap-1.5">
                    {/* 条件序号 */}
                    <div className="shrink-0 w-5 h-7 flex items-center justify-center">
                      <span className="text-[10px] text-muted-foreground">{ruleIndex + 1}</span>
                    </div>
                    
                    {/* 条件内容 */}
                    <div className="flex-1 space-y-1.5">
                      {/* 变量选择 */}
                      <Popover 
                        open={openVariablePopover === `${branch.id}-${rule.id}`}
                        onOpenChange={(open) => {
                          onOpenVariablePopoverChange(open ? `${branch.id}-${rule.id}` : null)
                          if (!open) onVariableSearchChange('')
                        }}
                      >
                        <PopoverTrigger
                          className="w-full h-7 flex items-center justify-start px-2 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                        >
                          {rule.variable ? (
                            <span className="flex items-center gap-1 text-xs">
                              <span className="text-muted-foreground text-[10px]">{rule.variableSource}</span>
                              <span>/</span>
                              <span className="text-primary/80 font-mono">{'{x}'}</span>
                              <span>{extractVariableDisplayName(rule.variable)}</span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground">选择变量...</span>
                          )}
                        </PopoverTrigger>
                        <PopoverContent className="w-64 p-0" align="start">
                          {/* 搜索框 */}
                          <div className="p-2 border-b">
                            <div className="relative">
                              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                              <Input
                                placeholder="搜索变量"
                                value={variableSearch}
                                onChange={(e) => onVariableSearchChange(e.target.value)}
                                className="h-7 pl-7 text-xs"
                              />
                            </div>
                          </div>
                          {/* 变量列表 */}
                          <ScrollArea className="h-48">
                            <div className="p-1">
                              {(() => {
                                const filtered = filterVariables(variableSearch)
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
                                    <div className="px-2 py-1 text-[10px] text-muted-foreground font-medium">
                                      {group.label}
                                    </div>
                                    {group.items.map(variable => (
                                      <button
                                        key={variable.id}
                                        className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                        onClick={() => selectVariable(branch.id, rule.id, variable.id, variable.name, variable.isSystem)}
                                      >
                                        <span className="flex items-center gap-1.5">
                                          <span className={cn(
                                            'font-mono text-[10px]',
                                            variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                                          )}>{'{x}'}</span>
                                          <span>{variable.name}</span>
                                        </span>
                                        <span className="text-[10px] text-muted-foreground">{variable.type}</span>
                                      </button>
                                    ))}
                                  </div>
                                ))
                              })()}
                            </div>
                          </ScrollArea>
                        </PopoverContent>
                      </Popover>
                      
                      {/* 操作符和值 */}
                      <div className="flex items-center gap-1.5">
                        <Select
                          value={rule.operator}
                          onValueChange={(v) => updateConditionRule(branch.id, rule.id, { operator: v as ConditionOperator })}
                        >
                          <SelectTrigger className="h-7 w-24 text-xs">
                            <SelectValue>{conditionOperatorShortLabels[rule.operator]}</SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(conditionOperatorLabels).map(([key, label]) => (
                              <SelectItem key={key} value={key} className="text-xs">
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        
                        {!noValueOperators.includes(rule.operator) && (
                          <Input
                            value={rule.value}
                            onChange={(e) => updateConditionRule(branch.id, rule.id, { value: e.target.value })}
                            placeholder="输入值..."
                            className="h-7 text-xs flex-1"
                          />
                        )}
                      </div>
                    </div>
                    
                    {/* 删除按钮 */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0"
                      onClick={() => removeConditionRule(branch.id, rule.id)}
                    >
                      <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>
                ))}
                
                {/* 添加条件按钮 */}
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full h-7 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => addConditionRule(branch.id)}
                >
                  <Plus className="h-3 w-3 mr-1" />
                  添加条件
                </Button>
              </div>
            )}
            
            {/* ELSE 分支说明 */}
            {isExpanded && isElse && (
              <div className="px-3 pb-3">
                <p className="text-xs text-muted-foreground">
                  当以上所有条件都不满足时执行
                </p>
              </div>
            )}
          </div>
        )
      })}
      
      {/* 添加 ELSE IF 按钮 */}
      <Button
        variant="outline"
        size="sm"
        className="w-full h-8 text-xs border-dashed"
        onClick={addElseIfBranch}
      >
        <Plus className="h-3 w-3 mr-1" />
        添加 ELSE IF 分支
      </Button>
    </div>
  )
}
