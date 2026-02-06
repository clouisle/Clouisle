'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Search, AlertCircle } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { AvailableVariable } from '../types'
import { extractVariableDisplayName } from '../types'
import { IterationConfig } from '../../nodes/iteration-node'

interface IterationNodeConfigProps {
  config: IterationConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: IterationConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function IterationNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: IterationNodeConfigProps) {
  const t = useTranslations('workflow')

  // 只显示可迭代的变量
  const iterableVariables = React.useMemo(() => {
    return variables.filter(v => v.isIterable)
  }, [variables])

  // 过滤变量
  const filterVariables = (search: string, vars: AvailableVariable[]) => {
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

  // 检查节点内变量名是否重复
  const isInternalDuplicate = (varName: string): boolean => {
    if (!varName) return false
    const lowerName = varName.toLowerCase()
    const vars: string[] = []
    if (config.iteratorType === 'array') {
      if (config.itemVariable) vars.push(config.itemVariable.toLowerCase())
    } else {
      if (config.keyVariable) vars.push(config.keyVariable.toLowerCase())
      if (config.valueVariable) vars.push(config.valueVariable.toLowerCase())
    }
    if (config.indexVariable) vars.push(config.indexVariable.toLowerCase())
    if (config.outputVariable) vars.push(config.outputVariable.toLowerCase())
    return vars.filter(v => v === lowerName).length > 1
  }

  return (
    <div className="space-y-4">
      {/* 迭代对象选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configIteration.iterationObject')}</Label>
          <span className="text-destructive">*</span>
        </div>
        
        <Popover 
          open={openVariablePopover === 'iteration-source'}
          onOpenChange={(open) => {
            onOpenVariablePopoverChange(open ? 'iteration-source' : null)
            if (!open) onVariableSearchChange('')
          }}
        >
          <PopoverTrigger
            className="w-full h-9 flex items-center justify-start px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
          >
            {config.iteratorVariable ? (
              <span className="flex items-center gap-1">
                <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
                <span className="text-xs">
                  {config.iteratorSource && <span className="text-muted-foreground">{config.iteratorSource} / </span>}
                  {extractVariableDisplayName(config.iteratorVariable)}
                </span>
              </span>
            ) : (
              <span className="text-muted-foreground text-xs">{t('configIteration.selectIterableVariable')}</span>
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
                  const filtered = filterVariables(variableSearch, iterableVariables)
                  const groupEntries = groupVariables(filtered)
                  
                  if (groupEntries.length === 0) {
                    return (
                      <div className="py-4 text-center text-xs text-muted-foreground">
                        {iterableVariables.length === 0
                          ? t('configIteration.noIterableVariables')
                          : t('configCommon.noMatchingVariables')}
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
                            onConfigChange({
                              ...config,
                              iteratorVariable: `{{${variable.id}}}`,
                              iteratorSource: variable.groupLabel,
                              iteratorType: variable.isArray ? 'array' : 'object'
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
        
        {!config.iteratorVariable && (
          <p className="text-[10px] text-muted-foreground flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {t('configIteration.selectIterableHint')}
          </p>
        )}
      </div>
      
      {/* 输出变量配置 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">
            {config.iteratorType === 'array' ? t('configIteration.itemVariable') : t('configIteration.keyVariable')}
          </Label>
          <span className="text-destructive">*</span>
        </div>
        <Input
          value={config.iteratorType === 'array' ? config.itemVariable : config.keyVariable}
          onChange={(e) => onConfigChange({ 
            ...config, 
            ...(config.iteratorType === 'array' ? { itemVariable: e.target.value } : { keyVariable: e.target.value })
          })}
          placeholder={config.iteratorType === 'array' ? 'item' : 'key'}
          className={cn(
            'h-9 text-xs font-mono',
            ((config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) && 
             (!isValidVariableName(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) ||
              isInternalDuplicate(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable))) && 
            'border-destructive! ring-destructive/20!'
          )}
        />
        {(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) &&
         !isValidVariableName(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
        )}
        {(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) &&
         isInternalDuplicate(config.iteratorType === 'array' ? config.itemVariable : config.keyVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
        )}
      </div>
      
      {config.iteratorType === 'object' && (
        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configIteration.valueVariable')}</Label>
            <span className="text-destructive">*</span>
          </div>
          <Input
            value={config.valueVariable || 'value'}
            onChange={(e) => onConfigChange({ ...config, valueVariable: e.target.value })}
            placeholder="value"
            className={cn(
              'h-9 text-xs font-mono',
              (config.valueVariable && (!isValidVariableName(config.valueVariable) || isInternalDuplicate(config.valueVariable))) && 'border-destructive! ring-destructive/20!'
            )}
          />
          {config.valueVariable && !isValidVariableName(config.valueVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
          )}
          {config.valueVariable && isInternalDuplicate(config.valueVariable) && (
            <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
          )}
        </div>
      )}
      
      {/* 索引变量 */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">{t('configIteration.indexVariable')}</Label>
        <Input
          value={config.indexVariable}
          onChange={(e) => onConfigChange({ ...config, indexVariable: e.target.value })}
          placeholder="index"
          className={cn(
            'h-9 text-xs font-mono',
            (config.indexVariable && (!isValidVariableName(config.indexVariable) || isInternalDuplicate(config.indexVariable))) && 'border-destructive! ring-destructive/20!'
          )}
        />
        {config.indexVariable && !isValidVariableName(config.indexVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
        )}
        {config.indexVariable && isInternalDuplicate(config.indexVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
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
            config.outputVariable && (!isValidVariableName(config.outputVariable) || isInternalDuplicate(config.outputVariable)) && 'border-destructive! ring-destructive/20!'
          )}
        />
        {config.outputVariable && !isValidVariableName(config.outputVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.invalidVariableName')}</p>
        )}
        {config.outputVariable && isInternalDuplicate(config.outputVariable) && (
          <p className="text-[10px] text-destructive">{t('configCommon.duplicateVariableInNode')}</p>
        )}
      </div>
      
      {/* 并行执行 */}
      <div className="flex items-center justify-between py-2">
        <div className="space-y-0.5">
          <Label className="text-xs font-medium">{t('configIteration.parallelExecution')}</Label>
          <p className="text-[10px] text-muted-foreground">{t('configIteration.parallelExecutionDesc')}</p>
        </div>
        <Switch
          checked={config.parallel}
          onCheckedChange={(checked) => onConfigChange({ ...config, parallel: checked })}
        />
      </div>
      
      {config.parallel && (
        <div className="space-y-2">
          <Label className="text-xs font-medium">{t('configIteration.maxParallel')}</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={config.maxParallel || 10}
            onChange={(e) => onConfigChange({ ...config, maxParallel: parseInt(e.target.value) || 10 })}
            className="h-9 text-xs"
          />
        </div>
      )}
    </div>
  )
}
