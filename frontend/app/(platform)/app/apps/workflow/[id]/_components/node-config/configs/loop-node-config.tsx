'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, Pencil, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import { loopVariableTypeConfig } from '../constants'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'
import {
  LoopConfig,
  LoopVariable,
  LoopVariableType,
} from '../../nodes/loop-node'
import {
  ConditionRule,
  ConditionOperator,
  getConditionOperatorLabels,
  getConditionOperatorShortLabels,
  noValueOperators
} from '../../nodes/condition-node'

interface LoopNodeConfigProps {
  nodeId: string
  config: LoopConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: LoopConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function LoopNodeConfig({
  nodeId,
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: LoopNodeConfigProps) {
  const t = useTranslations('workflow')
  const conditionOperatorLabels = getConditionOperatorLabels(t)
  const conditionOperatorShortLabels = getConditionOperatorShortLabels(t)
  // 循环变量编辑状态
  const [editingLoopVar, setEditingLoopVar] = React.useState<LoopVariable | null>(null)
  const [isLoopVarDialogOpen, setIsLoopVarDialogOpen] = React.useState(false)
  const [loopVarForm, setLoopVarForm] = React.useState<Partial<LoopVariable>>({})

  // 验证循环变量名是否重复
  const isLoopVarNameDuplicate = (name: string): boolean => {
    const existingNames = (config.loopVariables || [])
      .filter(v => editingLoopVar ? v.id !== editingLoopVar.id : true)
      .map(v => v.name.toLowerCase())
    
    if (config.indexVariable?.toLowerCase() === name.toLowerCase()) {
      return true
    }
    
    if (config.outputVariable?.toLowerCase() === name.toLowerCase()) {
      return true
    }
    
    return existingNames.includes(name.toLowerCase())
  }

  // 检查 indexVariable 是否与节点内其他变量重复
  const isIndexVarDuplicate = (name: string): boolean => {
    if (!name) return false
    const lowerName = name.toLowerCase()
    const loopVarNames = (config.loopVariables || []).map(v => v.name.toLowerCase())
    if (config.outputVariable?.toLowerCase() === lowerName) return true
    return loopVarNames.includes(lowerName)
  }

  // 检查 outputVariable 是否与节点内其他变量重复
  const isOutputVarInternalDuplicate = (name: string): boolean => {
    if (!name) return false
    const lowerName = name.toLowerCase()
    const loopVarNames = (config.loopVariables || []).map(v => v.name.toLowerCase())
    if (config.indexVariable?.toLowerCase() === lowerName) return true
    return loopVarNames.includes(lowerName)
  }

  const loopVarNameError = (() => {
    const name = loopVarForm.name?.trim() || ''
    if (!name) return null
    if (!isValidVariableName(name)) {
      return t('configCommon.variableNameRules')
    }
    if (isLoopVarNameDuplicate(name)) {
      return t('configCommon.variableNameExists')
    }
    return null
  })()

  // 打开添加循环变量对话框
  const openAddLoopVarDialog = () => {
    setEditingLoopVar(null)
    setLoopVarForm({
      name: '',
      type: 'string',
      defaultValue: '',
      description: '',
    })
    setIsLoopVarDialogOpen(true)
  }

  // 打开编辑循环变量对话框
  const openEditLoopVarDialog = (loopVar: LoopVariable) => {
    setEditingLoopVar(loopVar)
    setLoopVarForm({ ...loopVar })
    setIsLoopVarDialogOpen(true)
  }

  // 保存循环变量
  const saveLoopVariable = () => {
    const name = loopVarForm.name?.trim()
    if (!name) return
    if (loopVarNameError) return
    
    if (editingLoopVar) {
      onConfigChange({
        ...config,
        loopVariables: (config.loopVariables || []).map(v => 
          v.id === editingLoopVar.id ? { ...v, ...loopVarForm, name } as LoopVariable : v
        )
      })
    } else {
      const newVar: LoopVariable = {
        id: `loopvar_${Date.now()}`,
        name,
        type: (loopVarForm.type as LoopVariableType) || 'string',
        defaultValue: loopVarForm.defaultValue || '',
        description: loopVarForm.description || '',
      }
      onConfigChange({
        ...config,
        loopVariables: [...(config.loopVariables || []), newVar]
      })
    }
    setIsLoopVarDialogOpen(false)
  }

  // 删除循环变量
  const removeLoopVariable = (id: string) => {
    onConfigChange({
      ...config,
      loopVariables: (config.loopVariables || []).filter(v => v.id !== id)
    })
  }

  // 退出条件相关函数
  const addExitConditionRule = () => {
    const newRule: ConditionRule = {
      id: `rule_${Date.now()}`,
      variable: '',
      variableSource: '',
      operator: 'equals',
      value: '',
    }
    onConfigChange({
      ...config,
      exitConditions: [...(config.exitConditions || []), newRule]
    })
  }

  const updateExitConditionRule = (ruleId: string, updates: Partial<ConditionRule>) => {
    onConfigChange({
      ...config,
      exitConditions: (config.exitConditions || []).map(r => 
        r.id === ruleId ? { ...r, ...updates } : r
      )
    })
  }

  const removeExitConditionRule = (ruleId: string) => {
    onConfigChange({
      ...config,
      exitConditions: (config.exitConditions || []).filter(r => r.id !== ruleId)
    })
  }

  // 过滤变量（用于退出条件）
  const filterExitConditionVariables = (search: string) => {
    const allVars = getExitConditionVariables()
    if (!search) return allVars
    return allVars.filter(v =>
      v.name.toLowerCase().includes(search.toLowerCase())
    )
  }

  // 获取 Loop 节点自己的变量（用于退出条件）
  const getLoopInternalVariables = (): AvailableVariable[] => {
    const internalVars: AvailableVariable[] = []

    // 添加 index 变量
    const indexVar = config.indexVariable || 'index'
    internalVars.push({
      id: `${nodeId}.${indexVar}`,
      name: indexVar,
      type: 'number',
      group: nodeId,
      groupLabel: t('configLoop.currentLoop'),
      isSystem: false,
      isArray: false,
      isIterable: false,
    })

    // 添加 results 变量
    const outputVar = config.outputVariable || 'results'
    internalVars.push({
      id: `${nodeId}.${outputVar}`,
      name: outputVar,
      type: 'array',
      group: nodeId,
      groupLabel: t('configLoop.currentLoop'),
      isSystem: false,
      isArray: true,
      isIterable: true,
    })

    // 添加循环变量
    const loopVars = config.loopVariables || []
    loopVars.forEach(v => {
      internalVars.push({
        id: `${nodeId}.${v.name}`,
        name: v.name,
        type: v.type,
        group: nodeId,
        groupLabel: t('configLoop.currentLoop'),
        isSystem: false,
        isArray: false,
        isIterable: false,
      })
    })

    return internalVars
  }

  // 合并上游变量和 Loop 内部变量（用于退出条件）
  const getExitConditionVariables = (): AvailableVariable[] => {
    return [...getLoopInternalVariables(), ...variables]
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
    <>
      <div className="space-y-4">
        {/* 最大循环次数 */}
        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configLoop.maxLoopIterations')}</Label>
            <span className="text-destructive">*</span>
          </div>
          <Input
            type="number"
            min={1}
            max={1000}
            value={config.maxIterations}
            onChange={(e) => onConfigChange({ ...config, maxIterations: parseInt(e.target.value) || 10 })}
            className="h-9 text-xs"
          />
          <p className="text-[10px] text-muted-foreground">{t('configLoop.maxLoopHint')}</p>
        </div>
        
        {/* 索引变量 */}
        <div className="space-y-2">
          <Label className="text-xs font-medium">{t('configIteration.indexVariable')}</Label>
          <Input
            value={config.indexVariable}
            onChange={(e) => onConfigChange({ ...config, indexVariable: e.target.value })}
            placeholder="index"
            className={cn(
              'h-9 text-xs font-mono',
              (config.indexVariable && (!isValidVariableName(config.indexVariable) || isIndexVarDuplicate(config.indexVariable))) && 'border-destructive! ring-destructive/20!'
            )}
          />
          {config.indexVariable && !isValidVariableName(config.indexVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
          )}
          {config.indexVariable && isIndexVarDuplicate(config.indexVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
          )}
          <p className="text-[10px] text-muted-foreground">{t('configLoop.indexVariableHint')}</p>
        </div>
        
        {/* 循环变量列表 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-medium">{t('configLoop.loopVariables')}</Label>
            <Button 
              variant="ghost" 
              size="sm" 
              className="h-6 px-2 text-xs"
              onClick={openAddLoopVarDialog}
            >
              <Plus className="h-3 w-3 mr-1" />
              {t('configCommon.add')}
            </Button>
          </div>

          {(!config.loopVariables || config.loopVariables.length === 0) ? (
            <p className="text-xs text-muted-foreground py-3 text-center bg-muted/30 rounded-md">
              {t('configLoop.noLoopVariables')}
            </p>
          ) : (
            <div className="space-y-1">
              {config.loopVariables.map((loopVar) => {
                const typeConfig = loopVariableTypeConfig[loopVar.type] || loopVariableTypeConfig.string
                const TypeIcon = typeConfig.icon
                return (
                  <div 
                    key={loopVar.id} 
                    className="group flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
                    onClick={() => openEditLoopVarDialog(loopVar)}
                  >
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <TypeIcon className="h-4 w-4 text-primary/70 shrink-0" />
                      <span className="text-xs font-mono font-medium truncate">{loopVar.name}</span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <span className="text-xs text-muted-foreground px-1.5 py-0.5 rounded border border-border group-hover:hidden">
                        {typeConfig.valueType}
                      </span>
                      <div className="hidden group-hover:flex items-center gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          onClick={(e) => {
                            e.stopPropagation()
                            openEditLoopVarDialog(loopVar)
                          }}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-destructive hover:text-destructive"
                          onClick={(e) => {
                            e.stopPropagation()
                            removeLoopVariable(loopVar.id)
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
        
        {/* 退出条件 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-xs font-medium">{t('configLoop.exitConditions')}</Label>
            <Button 
              variant="ghost" 
              size="sm" 
              className="h-6 px-2 text-xs"
              onClick={addExitConditionRule}
            >
              <Plus className="h-3 w-3 mr-1" />
              {t('configCommon.add')}
            </Button>
          </div>

          {(!config.exitConditions || config.exitConditions.length === 0) ? (
            <p className="text-xs text-muted-foreground py-3 text-center bg-muted/30 rounded-md">
              {t('configLoop.exitByMaxOnly')}
            </p>
          ) : (
            <div className="space-y-2">
              {config.exitConditions.map((rule, ruleIndex) => (
                <div key={rule.id} className="flex items-start gap-1.5 bg-muted/30 rounded-lg p-2">
                  <div className="shrink-0 w-5 h-7 flex items-center justify-center">
                    <span className="text-[10px] text-muted-foreground">{ruleIndex + 1}</span>
                  </div>
                  
                  <div className="flex-1 space-y-1.5">
                    {/* 变量选择 */}
                    <Popover 
                      open={openVariablePopover === `exit-${rule.id}`}
                      onOpenChange={(open) => {
                        onOpenVariablePopoverChange(open ? `exit-${rule.id}` : null)
                        if (!open) onVariableSearchChange('')
                      }}
                    >
                      <PopoverTrigger
                        className="w-full h-7 flex items-center justify-start px-2 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                      >
                        {rule.variable ? (
                          <span className="flex items-center gap-1 text-xs">
                            <span className="text-primary/80 font-mono">{'{x}'}</span>
                            <span>
                              {rule.variableSource && <span className="text-muted-foreground">{rule.variableSource} / </span>}
                              {extractVariableDisplayName(rule.variable)}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{t('configCommon.selectVariable')}</span>
                        )}
                      </PopoverTrigger>
                      <PopoverContent className="w-64 p-0" align="start">
                        <div className="p-2 border-b">
                          <div className="relative">
                            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                            <Input
                              placeholder={t('configCommon.searchVariable')}
                              value={variableSearch}
                              onChange={(e) => onVariableSearchChange(e.target.value)}
                              className="h-7 pl-7 text-xs"
                            />
                          </div>
                        </div>
                        <ScrollArea className="h-48">
                          <div className="p-1">
                            {(() => {
                              const filtered = filterExitConditionVariables(variableSearch)
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
                                  <div className="px-2 py-1 text-[10px] text-muted-foreground font-medium">
                                    {group.label}
                                  </div>
                                  {group.items.map(variable => (
                                    <button
                                      key={variable.id}
                                      className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                      onClick={() => {
                                        // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
                                        updateExitConditionRule(rule.id, {
                                          variable: `{{${variable.id}}}`,
                                          variableSource: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel
                                        })
                                        onOpenVariablePopoverChange(null)
                                        onVariableSearchChange('')
                                      }}
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
                        onValueChange={(v) => updateExitConditionRule(rule.id, { operator: v as ConditionOperator })}
                      >
                        <SelectTrigger size="xs" className="w-24 text-xs">
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
                          onChange={(e) => updateExitConditionRule(rule.id, { value: e.target.value })}
                          placeholder={t('configCommon.enterValue')}
                          className="h-7 text-xs flex-1"
                        />
                      )}
                    </div>
                  </div>
                  
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    onClick={() => removeExitConditionRule(rule.id)}
                  >
                    <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                  </Button>
                </div>
              ))}
              
              {config.exitConditions.length > 1 && (
                <div className="flex items-center gap-2 text-xs px-2">
                  <span className="text-muted-foreground">{t('configLoop.satisfy')}</span>
                  <Select
                    value={config.exitLogicOperator || 'and'}
                    onValueChange={(v) => onConfigChange({ ...config, exitLogicOperator: v as 'and' | 'or' })}
                  >
                    <SelectTrigger size="xs" className="w-16">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="and" className="text-xs">{t('configLoop.logicAll')}</SelectItem>
                      <SelectItem value="or" className="text-xs">{t('configLoop.logicAny')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <span className="text-muted-foreground">{t('configLoop.conditionsToExit')}</span>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* 输出变量 */}
        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configCommon.outputVariable')}</Label>
            <span className="text-destructive">*</span>
          </div>
          <Input
            value={config.outputVariable}
            onChange={(e) => onConfigChange({ ...config, outputVariable: e.target.value })}
            placeholder="results"
            className={cn(
              'h-9 text-xs font-mono',
              config.outputVariable && (!isValidVariableName(config.outputVariable) || isOutputVarInternalDuplicate(config.outputVariable)) && 'border-destructive! ring-destructive/20!'
            )}
          />
          {config.outputVariable && !isValidVariableName(config.outputVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
          )}
          {config.outputVariable && isOutputVarInternalDuplicate(config.outputVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
          )}
        </div>
      </div>

      {/* 循环变量编辑对话框 */}
      <Dialog open={isLoopVarDialogOpen} onOpenChange={setIsLoopVarDialogOpen}>
        <DialogContent className="sm:max-w-100 flex flex-col max-h-[85vh]">
          <DialogHeader>
            <DialogTitle className="text-sm">{editingLoopVar ? t('configLoop.editVariable') : t('configLoop.addVariable')}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto py-2 px-1 -mx-1">
            <div className="space-y-4 px-0.5">
              <div className="space-y-2">
                <Label htmlFor="loopvar-name" className="text-xs">{t('configLoop.variableNameRequired')}</Label>
                <Input
                  id="loopvar-name"
                  value={loopVarForm.name || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, name: e.target.value })}
                  placeholder={t('configLoop.loopVarNamePlaceholder')}
                  className={cn(
                    'h-9 font-mono',
                    loopVarNameError && 'border-destructive! ring-destructive/20!'
                  )}
                />
                {loopVarNameError && (
                  <p className="text-[10px] text-destructive">{loopVarNameError}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="loopvar-type" className="text-xs">{t('configCommon.type')}</Label>
                <Select
                  value={loopVarForm.type || 'string'}
                  onValueChange={(v) => setLoopVarForm({ ...loopVarForm, type: v as LoopVariableType, defaultValue: '' })}
                >
                  <SelectTrigger id="loopvar-type" size="default" className="w-full">
                    <SelectValue>
                      {(() => {
                        const currentType = loopVarForm.type || 'string'
                        const typeConfig = loopVariableTypeConfig[currentType]
                        const CurrentIcon = typeConfig.icon
                        return (
                          <span className="flex items-center gap-2">
                            <CurrentIcon className="h-3.5 w-3.5 text-muted-foreground" />
                            <span>{t(`varTypes.${typeConfig.labelKey}`)}</span>
                          </span>
                        )
                      })()}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(loopVariableTypeConfig).map(([key, typeConfig]) => {
                      const OptionIcon = typeConfig.icon
                      return (
                        <SelectItem key={key} value={key} className="text-sm">
                          <span className="flex items-center gap-2">
                            <OptionIcon className="h-3.5 w-3.5 text-muted-foreground" />
                            <span>{t(`varTypes.${typeConfig.labelKey}`)}</span>
                          </span>
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>

              {/* 默认值 - 根据类型显示不同输入 */}
              {(loopVarForm.type === 'string' || !loopVarForm.type) && (
                <div className="space-y-2">
                  <Label htmlFor="loopvar-default" className="text-xs">{t('configCommon.defaultValue')}</Label>
                  <Input
                    id="loopvar-default"
                    value={loopVarForm.defaultValue || ''}
                    onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                    placeholder={t('configCommon.optional')}
                    className="h-9"
                  />
                </div>
              )}

              {loopVarForm.type === 'number' && (
                <div className="space-y-2">
                  <Label htmlFor="loopvar-default" className="text-xs">{t('configCommon.defaultValue')}</Label>
                  <Input
                    id="loopvar-default"
                    type="number"
                    value={loopVarForm.defaultValue || ''}
                    onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                    placeholder="0"
                    className="h-9"
                  />
                </div>
              )}

              {loopVarForm.type === 'boolean' && (
                <div className="flex items-center justify-between">
                  <Label htmlFor="loopvar-default" className="text-xs">{t('configCommon.defaultValue')}</Label>
                  <Switch
                    id="loopvar-default"
                    checked={loopVarForm.defaultValue === 'true'}
                    onCheckedChange={(checked) => setLoopVarForm({ ...loopVarForm, defaultValue: checked ? 'true' : 'false' })}
                  />
                </div>
              )}

              {loopVarForm.type === 'array' && (
                <div className="space-y-2">
                  <Label htmlFor="loopvar-default" className="text-xs">{t('configCommon.defaultValueJson')}</Label>
                  <Textarea
                    id="loopvar-default"
                    value={loopVarForm.defaultValue || ''}
                    onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                    placeholder={t('configLoop.arrayExample')}
                    className="min-h-20 resize-none font-mono text-xs"
                  />
                  <p className="text-[10px] text-muted-foreground">{t('configLoop.jsonArrayFormatHint')}</p>
                </div>
              )}

              {loopVarForm.type === 'object' && (
                <div className="space-y-2">
                  <Label htmlFor="loopvar-default" className="text-xs">{t('configCommon.defaultValueJson')}</Label>
                  <Textarea
                    id="loopvar-default"
                    value={loopVarForm.defaultValue || ''}
                    onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                    placeholder={t('configLoop.objectExample')}
                    className="min-h-20 resize-none font-mono text-xs"
                  />
                  <p className="text-[10px] text-muted-foreground">{t('configLoop.jsonObjectFormatHint')}</p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="loopvar-desc" className="text-xs">{t('configCommon.description')}</Label>
                <Input
                  id="loopvar-desc"
                  value={loopVarForm.description || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, description: e.target.value })}
                  placeholder={t('configCommon.descriptionPlaceholder')}
                  className="h-9"
                />
              </div>
            </div>
          </div>
          <DialogFooter className="shrink-0">
            <Button variant="outline" size="sm" onClick={() => setIsLoopVarDialogOpen(false)}>
              {t('configCommon.cancel')}
            </Button>
            <Button size="sm" onClick={saveLoopVariable} disabled={!loopVarForm.name?.trim() || !!loopVarNameError}>
              {editingLoopVar ? t('configCommon.save') : t('configCommon.add')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
