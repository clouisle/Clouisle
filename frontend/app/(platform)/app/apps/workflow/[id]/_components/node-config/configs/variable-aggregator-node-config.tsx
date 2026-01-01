'use client'

import * as React from 'react'
import { Plus, Trash2, Search, ChevronDown, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { AvailableVariable } from '../types'
import { 
  VariableAggregatorConfig, 
  VariableMapping,
  AggregationMode,
  aggregationModeConfig,
  defaultVariableAggregatorConfig,
} from '../../nodes/variable-aggregator-node'

interface VariableAggregatorNodeConfigProps {
  config: VariableAggregatorConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: VariableAggregatorConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function VariableAggregatorNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: VariableAggregatorNodeConfigProps) {
  const [outputOpen, setOutputOpen] = React.useState(true)

  // 确保 config 有默认值
  const safeConfig: VariableAggregatorConfig = {
    ...defaultVariableAggregatorConfig,
    ...config,
    variables: config.variables || [],
  }

  const modeConfig = aggregationModeConfig[safeConfig.mode]

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

  // 添加变量
  const handleAddVariable = () => {
    const newVar: VariableMapping = {
      id: `var_${Date.now()}`,
      sourceVariable: '',
      targetKey: safeConfig.mode === 'object' ? `key${safeConfig.variables.length + 1}` : undefined,
    }
    onConfigChange({
      ...safeConfig,
      variables: [...safeConfig.variables, newVar],
    })
  }

  // 更新变量
  const handleUpdateVariable = (id: string, updates: Partial<VariableMapping>) => {
    onConfigChange({
      ...safeConfig,
      variables: safeConfig.variables.map(v => 
        v.id === id ? { ...v, ...updates } : v
      ),
    })
  }

  // 删除变量
  const handleDeleteVariable = (id: string) => {
    onConfigChange({
      ...safeConfig,
      variables: safeConfig.variables.filter(v => v.id !== id),
    })
  }

  // 渲染变量选择器
  const renderVariableSelector = (varMapping: VariableMapping) => {
    const popoverId = `aggregator-var-${varMapping.id}`
    
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
            'flex-1 h-9 flex items-center justify-start gap-1 px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {varMapping.sourceVariable ? (
            <>
              <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
              <span className="text-xs truncate">
                {varMapping.sourceNodeLabel && <span className="text-muted-foreground">{varMapping.sourceNodeLabel} / </span>}
                {varMapping.sourceVariable.replace(/\{\{|\}\}/g, '')}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">选择变量...</span>
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
                    <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                      {group.label}
                    </div>
                    {group.items.map(variable => (
                      <button
                        key={variable.id}
                        className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                        onClick={() => {
                          handleUpdateVariable(varMapping.id, {
                            sourceVariable: `{{${variable.name}}}`,
                            sourceNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel,
                            // 如果是 object 模式且没有设置 targetKey，自动从变量名推断
                            targetKey: safeConfig.mode === 'object' && !varMapping.targetKey 
                              ? variable.name.split('.').pop() || variable.name
                              : varMapping.targetKey,
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
      {/* 聚合模式 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">聚合模式</Label>
          <span className="text-destructive">*</span>
        </div>
        <Select
          value={safeConfig.mode}
          onValueChange={(v) => onConfigChange({ 
            ...safeConfig, 
            mode: v as AggregationMode,
            // 切换模式时，如果是 object 模式，为每个变量添加 targetKey
            variables: v === 'object' 
              ? safeConfig.variables.map((vr, i) => ({
                  ...vr,
                  targetKey: vr.targetKey || `key${i + 1}`,
                }))
              : safeConfig.variables,
          })}
        >
          <SelectTrigger className="h-9 text-xs">
            <SelectValue>
              {modeConfig.label}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(aggregationModeConfig).map(([key, cfg]) => (
              <SelectItem key={key} value={key} className="text-xs">
                {cfg.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground">{modeConfig.description}</p>
      </div>

      {/* 变量列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">变量列表</Label>
            <span className="text-destructive">*</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleAddVariable}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.variables.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2 text-center bg-muted/30 rounded-md">
            暂无变量，点击 + 添加
          </p>
        ) : (
          <div className="space-y-1.5">
            {safeConfig.variables.map((varMapping, index) => (
              <div
                key={varMapping.id}
                className="group flex items-center gap-2 bg-muted/30 rounded-lg p-2"
              >
                {/* 序号 */}
                <span className="text-[10px] text-muted-foreground w-4 text-center shrink-0">
                  {index + 1}
                </span>
                
                {/* object 模式显示 targetKey 输入 */}
                {safeConfig.mode === 'object' && (
                  <Input
                    value={varMapping.targetKey || ''}
                    onChange={(e) => handleUpdateVariable(varMapping.id, { targetKey: e.target.value })}
                    placeholder="键名"
                    className={cn(
                      'w-20 h-8 text-xs font-mono shrink-0',
                      varMapping.targetKey && !isValidVariableName(varMapping.targetKey) && 'border-destructive!'
                    )}
                  />
                )}
                
                {/* 变量选择器 */}
                {renderVariableSelector(varMapping)}
                
                {/* 删除按钮 */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => handleDeleteVariable(varMapping.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
        
        {/* 错误提示 */}
        {safeConfig.mode === 'object' && safeConfig.variables.some(v => v.targetKey && !isValidVariableName(v.targetKey)) && (
          <p className="text-[10px] text-destructive">键名格式无效（只能包含字母、数字、下划线，不能以数字开头）</p>
        )}
        {safeConfig.mode === 'object' && (() => {
          const keys = safeConfig.variables.map(v => v.targetKey).filter(Boolean)
          const hasDuplicates = new Set(keys).size !== keys.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">存在重复的键名</p>
          )
        })()}
      </div>

      {/* concat 模式特有配置 - 分隔符 */}
      {safeConfig.mode === 'concat' && (
        <div className="space-y-2">
          <Label className="text-xs font-medium">分隔符</Label>
          <Input
            value={safeConfig.separator || ''}
            onChange={(e) => onConfigChange({ ...safeConfig, separator: e.target.value })}
            placeholder="留空则直接拼接"
            className="h-9 text-xs"
          />
          <p className="text-[10px] text-muted-foreground">
            用于连接多个字符串的分隔符，如换行符 \n 或逗号 ,
          </p>
        </div>
      )}

      {/* merge 模式特有配置 - 合并策略 */}
      {safeConfig.mode === 'merge' && (
        <div className="space-y-2">
          <Label className="text-xs font-medium">合并策略</Label>
          <Select
            value={safeConfig.mergeStrategy || 'shallow'}
            onValueChange={(v) => onConfigChange({ ...safeConfig, mergeStrategy: v as 'shallow' | 'deep' })}
          >
            <SelectTrigger className="h-9 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="shallow" className="text-xs">浅合并</SelectItem>
              <SelectItem value="deep" className="text-xs">深合并</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[10px] text-muted-foreground">
            {safeConfig.mergeStrategy === 'deep' 
              ? '递归合并嵌套对象的属性' 
              : '仅合并顶层属性，后面的覆盖前面的'}
          </p>
        </div>
      )}
      
      {/* 输出变量 - 可折叠 */}
      <Collapsible open={outputOpen} onOpenChange={setOutputOpen}>
        <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
          <ChevronDown className={cn(
            "h-3.5 w-3.5 transition-transform",
            !outputOpen && "-rotate-90"
          )} />
          <span>输出变量</span>
          <span className="text-destructive">*</span>
        </CollapsibleTrigger>
        <CollapsibleContent className="pt-2 space-y-2">
          <Input
            value={safeConfig.outputVariable}
            onChange={(e) => onConfigChange({ ...safeConfig, outputVariable: e.target.value })}
            placeholder="result"
            className={cn(
              'h-9 text-xs font-mono',
              safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && 'border-destructive!'
            )}
          />
          {safeConfig.outputVariable && !isValidVariableName(safeConfig.outputVariable) && (
            <p className="text-[10px] text-destructive">变量名格式无效</p>
          )}
          <div className="bg-muted/30 rounded-lg p-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-medium">{safeConfig.outputVariable || 'result'}</span>
              <span className="text-xs text-muted-foreground">{modeConfig.outputType}</span>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">聚合后的结果</p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
