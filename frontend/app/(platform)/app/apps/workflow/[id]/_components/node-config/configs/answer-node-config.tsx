'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import type { AvailableVariable } from '../types'
import {
  type AnswerNodeConfig as AnswerNodeConfigData,
  type OutputVariable,
  defaultAnswerNodeConfig,
} from '../../nodes/answer-node'

interface AnswerNodeConfigProps {
  config: AnswerNodeConfigData
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: AnswerNodeConfigData) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function AnswerNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: AnswerNodeConfigProps) {
  const t = useTranslations('workflow')
  const safeConfig: AnswerNodeConfigData = {
    ...defaultAnswerNodeConfig,
    ...config,
    outputs: config.outputs || [],
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

  // 添加输出变量
  const handleAddOutput = () => {
    const newOutput: OutputVariable = {
      id: `out_${Date.now()}`,
      sourceVariable: '',
    }
    onConfigChange({
      ...safeConfig,
      outputs: [...safeConfig.outputs, newOutput],
    })
  }

  // 删除输出变量
  const handleDeleteOutput = (id: string) => {
    onConfigChange({
      ...safeConfig,
      outputs: safeConfig.outputs.filter(o => o.id !== id),
    })
  }

  // 选择源变量
  const handleSelectSourceVariable = (outputId: string, variable: AvailableVariable) => {
    onConfigChange({
      ...safeConfig,
      outputs: safeConfig.outputs.map(o =>
        o.id === outputId
          ? {
              ...o,
              sourceVariable: `{{${variable.id}}}`,
              sourceNodeLabel: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel,
              sourceVariableName: variable.name,
            }
          : o
      ),
    })
    onOpenVariablePopoverChange(null)
    onVariableSearchChange('')
  }

  // 渲染变量选择器
  const renderVariableSelector = (outputId: string, currentValue: string, currentLabel?: string, currentVarName?: string) => {
    const popoverId = `output-var-${outputId}`
    const displayVarName = currentVarName || currentValue.replace(/\{\{|\}\}/g, '').split('.').pop() || ''

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
            'w-full h-8 flex items-center justify-start gap-1 px-2 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground',
          )}
        >
          {currentValue ? (
            <>
              <span className="text-primary/80 font-mono text-[10px]">{'{x}'}</span>
              <span className="truncate">
                {currentLabel && <span className="text-muted-foreground">{currentLabel} / </span>}
                {displayVarName}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground">{t('configAnswer.selectSourceVariable')}</span>
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
                const filtered = filterVariables(variableSearch)
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
                        onClick={() => handleSelectSourceVariable(outputId, variable)}
                      >
                        <span className="flex items-center gap-1.5">
                          <span className={cn(
                            'font-mono text-[10px]',
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
      {/* 输出变量列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configAnswer.outputVariables')}</Label>
            <span className="text-destructive">*</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleAddOutput}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>

        {safeConfig.outputs.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center bg-muted/30 rounded-md">
            {t('configAnswer.noOutputVariables')}
          </p>
        ) : (
          <div className="space-y-2">
            {safeConfig.outputs.map((output, index) => (
              <div
                key={output.id}
                className="bg-muted/30 rounded-lg p-3 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-emerald-500">
                    {t('configAnswer.outputIndex', { index: index + 1 })}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDeleteOutput(output.id)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>

                {/* 源变量 */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">{t('configAnswer.sourceVariable')}</Label>
                  {renderVariableSelector(output.id, output.sourceVariable, output.sourceNodeLabel, output.sourceVariableName)}
                </div>
              </div>
            ))}
          </div>
        )}

        <p className="text-[10px] text-muted-foreground">
          {t('configAnswer.outputVariableHint')}
        </p>
      </div>
    </div>
  )
}
