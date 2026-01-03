'use client'

import * as React from 'react'
import { Plus, Trash2, Search, GripVertical, Type, Hash, ToggleLeft, Brackets, Braces, File, FileQuestion, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import type { AvailableVariable } from '../types'
import { 
  type AnswerNodeConfig as AnswerNodeConfigData, 
  type OutputVariable,
  defaultAnswerNodeConfig,
} from '../../nodes/answer-node'

// 输出变量类型配置
const outputTypeConfig = {
  string: { label: '文本', icon: Type },
  number: { label: '数字', icon: Hash },
  boolean: { label: '布尔', icon: ToggleLeft },
  array: { label: '数组', icon: Brackets },
  object: { label: '对象', icon: Braces },
  file: { label: '文件', icon: File },
  any: { label: '任意', icon: FileQuestion },
} as const

// 变量类型到输出类型的映射
const varTypeToOutputType: Record<string, OutputVariable['type']> = {
  'String': 'string',
  'Number': 'number',
  'Boolean': 'boolean',
  'Array': 'array',
  'Object': 'object',
  'File': 'file',
  'Any': 'any',
}

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
  // 确保 config 有默认值
  const safeConfig: AnswerNodeConfigData = {
    ...defaultAnswerNodeConfig,
    ...config,
    outputs: config.outputs || [],
    streaming: config.streaming || { enabled: false },
  }

  // 过滤变量
  const filterVariables = (search: string, filterStringOnly?: boolean) => {
    let filtered = variables
    if (filterStringOnly) {
      filtered = filtered.filter(v => v.type === 'String')
    }
    if (search) {
      filtered = filtered.filter(v => 
        v.name.toLowerCase().includes(search.toLowerCase())
      )
    }
    return filtered
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
      name: `output${safeConfig.outputs.length + 1}`,
      sourceVariable: '',
      sourceNodeLabel: '',
      type: 'string',
      description: '',
    }
    onConfigChange({
      ...safeConfig,
      outputs: [...safeConfig.outputs, newOutput],
    })
  }

  // 更新输出变量
  const handleUpdateOutput = (id: string, updates: Partial<OutputVariable>) => {
    onConfigChange({
      ...safeConfig,
      outputs: safeConfig.outputs.map(o => 
        o.id === id ? { ...o, ...updates } : o
      ),
    })
  }

  // 删除输出变量
  const handleDeleteOutput = (id: string) => {
    const newOutputs = safeConfig.outputs.filter(o => o.id !== id)
    // 如果删除的是流式输出变量，清除流式配置
    const deletedOutput = safeConfig.outputs.find(o => o.id === id)
    const streaming = { ...safeConfig.streaming }
    if (deletedOutput && streaming.variable === deletedOutput.sourceVariable) {
      streaming.variable = undefined
    }
    onConfigChange({
      ...safeConfig,
      outputs: newOutputs,
      streaming,
    })
  }

  // 选择源变量
  const handleSelectSourceVariable = (outputId: string, variable: AvailableVariable) => {
    const outputType = varTypeToOutputType[variable.type] || 'any'
    
    // variable.id 格式为 nodeId.paramName（如 user_input-123.query）
    // variable.name 是参数名（如 query）
    handleUpdateOutput(outputId, {
      sourceVariable: `{{${variable.id}}}`, // 传到后端用
      sourceNodeLabel: variable.isSystem ? 'SYSTEM' : variable.groupLabel, // 显示用
      sourceVariableName: variable.name, // 显示用（只显示参数名）
      type: outputType,
      name: variable.name, // 默认使用源变量名
    })
    onOpenVariablePopoverChange(null)
    onVariableSearchChange('')
  }

  // 渲染变量选择器
  const renderVariableSelector = (outputId: string, currentValue: string, currentLabel?: string, currentVarName?: string) => {
    const popoverId = `output-var-${outputId}`
    // 显示名称：优先用 sourceVariableName，否则从 sourceVariable 提取最后一部分
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
            <span className="text-muted-foreground">选择源变量...</span>
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

  // 获取可用于流式输出的变量（String 类型）
  const getStreamingVariables = () => {
    return safeConfig.outputs
      .filter(o => o.type === 'string' && o.sourceVariable)
      .map(o => ({
        id: o.id,
        label: o.name,
        value: o.sourceVariable,
      }))
  }

  return (
    <div className="space-y-4">
      {/* 流式输出配置 */}
      <div className="space-y-3 p-3 bg-muted/30 rounded-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-emerald-500" />
            <Label className="text-xs font-medium">流式输出</Label>
          </div>
          <Switch
            checked={safeConfig.streaming.enabled}
            onCheckedChange={(checked) => 
              onConfigChange({
                ...safeConfig,
                streaming: { ...safeConfig.streaming, enabled: checked },
              })
            }
          />
        </div>
        
        {safeConfig.streaming.enabled && (
          <div className="space-y-1.5">
            <Label className="text-[10px] text-muted-foreground">流式输出变量</Label>
            <Select
              value={safeConfig.streaming.variable || ''}
              onValueChange={(v) => 
                onConfigChange({
                  ...safeConfig,
                  streaming: { ...safeConfig.streaming, variable: v || undefined },
                })
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue>
                  {safeConfig.streaming.variable 
                    ? getStreamingVariables().find(v => v.value === safeConfig.streaming.variable)?.label || safeConfig.streaming.variable
                    : '选择流式输出变量...'
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {getStreamingVariables().map((v) => (
                  <SelectItem key={v.id} value={v.value} className="text-xs">
                    {v.label}
                  </SelectItem>
                ))}
                {getStreamingVariables().length === 0 && (
                  <div className="py-2 px-2 text-xs text-muted-foreground">
                    请先添加 String 类型的输出变量
                  </div>
                )}
              </SelectContent>
            </Select>
            <p className="text-[10px] text-muted-foreground">
              选择一个 String 类型的输出变量作为流式输出
            </p>
          </div>
        )}
      </div>

      {/* 输出变量列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">输出变量</Label>
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
            暂无输出变量，点击 + 添加
          </p>
        ) : (
          <div className="space-y-2">
            {safeConfig.outputs.map((output, index) => (
              <div
                key={output.id}
                className="bg-muted/30 rounded-lg p-3 space-y-2"
              >
                {/* 头部：序号 + 删除 */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GripVertical className="h-3.5 w-3.5 text-muted-foreground cursor-grab" />
                    <span className="text-xs font-medium text-emerald-500">
                      输出 {index + 1}
                    </span>
                  </div>
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
                  <Label className="text-[10px] text-muted-foreground">源变量</Label>
                  {renderVariableSelector(output.id, output.sourceVariable, output.sourceNodeLabel, output.sourceVariableName)}
                </div>
                
                {/* 输出名称 */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">输出名称</Label>
                  <Input
                    value={output.name}
                    onChange={(e) => handleUpdateOutput(output.id, { name: e.target.value })}
                    placeholder="输出变量名"
                    className={cn(
                      'h-8 text-xs',
                      output.name && !isValidVariableName(output.name) && 'border-destructive!'
                    )}
                  />
                </div>
                
                {/* 输出类型 */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">类型</Label>
                  <Select
                    value={output.type}
                    onValueChange={(v) => handleUpdateOutput(output.id, { type: v as OutputVariable['type'] })}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(outputTypeConfig).map(([value, cfg]) => {
                        const TypeIcon = cfg.icon
                        return (
                          <SelectItem key={value} value={value} className="text-xs">
                            <div className="flex items-center gap-2">
                              <TypeIcon className="h-3 w-3" />
                              <span>{cfg.label}</span>
                            </div>
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
                
                {/* 描述（可选） */}
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">描述（可选）</Label>
                  <Textarea
                    value={output.description || ''}
                    onChange={(e) => handleUpdateOutput(output.id, { description: e.target.value })}
                    placeholder="输出变量的描述..."
                    className="min-h-[40px] text-xs resize-none"
                  />
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* 变量名校验提示 */}
        {safeConfig.outputs.some(o => o.name && !isValidVariableName(o.name)) && (
          <p className="text-[10px] text-destructive">输出名称格式无效（只能包含字母、数字、下划线，不能以数字开头）</p>
        )}
        {(() => {
          const names = safeConfig.outputs.map(o => o.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">存在重复的输出名称</p>
          )
        })()}
        
        <p className="text-[10px] text-muted-foreground">
          定义工作流的输出结果，可选择上游节点的变量作为输出
        </p>
      </div>
    </div>
  )
}
