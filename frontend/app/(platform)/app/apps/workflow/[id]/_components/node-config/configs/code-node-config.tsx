'use client'

import * as React from 'react'
import { Plus, Trash2, Info } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Collapsible, CollapsibleContent } from '@/components/ui/collapsible'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { isValidVariableName } from '../utils'
import { CodeEditor } from '../components/code-editor'
import { 
  CodeConfig, 
  CodeLanguage,
  CodeOutputVariable,
  OutputVariableType,
  ErrorHandlingType,
  pythonTemplate, 
  javascriptTemplate,
  defaultRetryConfig,
  defaultErrorHandlingConfig,
} from '../../nodes/code-node'

interface CodeNodeConfigProps {
  config: CodeConfig
  onConfigChange: (config: CodeConfig) => void
  onAddInput: () => void
}

// 输出变量类型选项
const outputTypeOptions: { value: OutputVariableType; label: string }[] = [
  { value: 'string', label: 'String' },
  { value: 'number', label: 'Number' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'array', label: 'Array' },
  { value: 'object', label: 'Object' },
]

// 异常处理类型选项
const errorHandlingOptions: { value: ErrorHandlingType; label: string; description: string }[] = [
  { value: 'none', label: '无', description: '当发生异常且未处理时，节点将停止运行' },
  { value: 'default_value', label: '默认值', description: '当发生异常时，指定默认输出内容。' },
  { value: 'error_branch', label: '异常分支', description: '当发生异常时，将执行异常分支' },
]

export function CodeNodeConfig({
  config,
  onConfigChange,
  onAddInput,
}: CodeNodeConfigProps) {
  const [retryOpen, setRetryOpen] = React.useState(config.retry?.enabled || false)

  // 确保 config 有默认值
  const safeConfig: CodeConfig = {
    ...config,
    outputs: config.outputs || [{ id: 'default', name: config.outputVariable || 'result', type: 'string' }],
    retry: config.retry || defaultRetryConfig,
    errorHandling: config.errorHandling || defaultErrorHandlingConfig,
  }

  // 处理语言切换 - 总是切换到新语言的模板代码
  const handleLanguageChange = (newLang: CodeLanguage) => {
    const newCode = newLang === 'python' ? pythonTemplate : javascriptTemplate
    onConfigChange({
      ...safeConfig,
      language: newLang,
      code: newCode,
    })
  }

  // 添加输出变量
  const handleAddOutput = () => {
    const newOutput: CodeOutputVariable = {
      id: `output_${Date.now()}`,
      name: '',
      type: 'string',
    }
    onConfigChange({
      ...safeConfig,
      outputs: [...safeConfig.outputs, newOutput],
    })
  }

  // 更新输出变量
  const handleUpdateOutput = (id: string, updates: Partial<CodeOutputVariable>) => {
    onConfigChange({
      ...safeConfig,
      outputs: safeConfig.outputs.map(o => o.id === id ? { ...o, ...updates } : o),
      // 同步更新 outputVariable（兼容）
      outputVariable: safeConfig.outputs[0]?.id === id && updates.name 
        ? updates.name 
        : safeConfig.outputVariable,
    })
  }

  // 删除输出变量
  const handleDeleteOutput = (id: string) => {
    if (safeConfig.outputs.length <= 1) return // 至少保留一个
    onConfigChange({
      ...safeConfig,
      outputs: safeConfig.outputs.filter(o => o.id !== id),
    })
  }

  // 更新重试配置
  const handleRetryChange = (updates: Partial<typeof safeConfig.retry>) => {
    onConfigChange({
      ...safeConfig,
      retry: { ...safeConfig.retry, ...updates },
    })
  }

  // 更新异常处理配置
  const handleErrorHandlingChange = (updates: Partial<typeof safeConfig.errorHandling>) => {
    onConfigChange({
      ...safeConfig,
      errorHandling: { ...safeConfig.errorHandling, ...updates },
    })
  }

  return (
    <div className="space-y-4">
      {/* 输入变量 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs font-medium">输入变量</Label>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={onAddInput}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.inputs.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2 text-center bg-muted/30 rounded-md">
            暂无输入变量
          </p>
        ) : (
          <div className="space-y-1.5">
            {safeConfig.inputs.map((input) => (
              <div
                key={input.id}
                className="group flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-medium truncate">
                      {input.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 mt-0.5 text-[10px] text-muted-foreground">
                    {input.valueSource && (
                      <>
                        <span className="text-primary/70">{input.valueSource}</span>
                        <span>/</span>
                      </>
                    )}
                    <span className="text-primary/80 font-mono">{'{x}'}</span>
                    <span className="truncate">{input.value.replace(/\{\{|\}\}/g, '')}</span>
                    <span className="ml-auto text-muted-foreground/60">String</span>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive"
                  onClick={() => {
                    onConfigChange({
                      ...safeConfig,
                      inputs: safeConfig.inputs.filter(i => i.id !== input.id)
                    })
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* 代码编辑器 */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">代码</Label>
        <CodeEditor
          value={safeConfig.code}
          language={safeConfig.language}
          onChange={(code) => onConfigChange({ ...safeConfig, code })}
          onLanguageChange={handleLanguageChange}
          minHeight={200}
        />
      </div>
      
      {/* 输出变量 */}
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
        
        <div className="space-y-1.5">
          {safeConfig.outputs.map((output) => {
            // 检查当前节点内是否有重复的变量名
            const isDuplicateInNode = output.name && safeConfig.outputs.filter(o => o.name === output.name).length > 1
            const hasError = !output.name || !isValidVariableName(output.name) || isDuplicateInNode
            return (
              <div key={output.id} className="flex items-center gap-2 bg-muted/50 rounded-lg px-3 py-2">
                <Input
                  value={output.name}
                  onChange={(e) => handleUpdateOutput(output.id, { name: e.target.value })}
                  placeholder="变量名"
                  className={cn(
                    'h-8 text-xs font-mono border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 flex-1',
                    hasError && 'text-destructive'
                  )}
                />
                <Select 
                  value={output.type}
                  onValueChange={(v) => handleUpdateOutput(output.id, { type: v as OutputVariableType })}
                >
                  <SelectTrigger className="h-7 w-22 text-xs bg-background">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {outputTypeOptions.map(opt => (
                      <SelectItem key={opt.value} value={opt.value} className="text-xs">
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="h-6 w-6 text-destructive hover:text-destructive"
                  onClick={() => handleDeleteOutput(output.id)}
                  disabled={safeConfig.outputs.length <= 1}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            )
          })}
        </div>
        {safeConfig.outputs.some(o => !o.name) && (
          <p className="text-[10px] text-destructive">输出变量名不能为空</p>
        )}
        {safeConfig.outputs.some(o => o.name && !isValidVariableName(o.name)) && (
          <p className="text-[10px] text-destructive">变量名格式无效（只能包含字母、数字、下划线，不能以数字开头）</p>
        )}
        {(() => {
          const names = safeConfig.outputs.map(o => o.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">当前节点内存在重复的变量名</p>
          )
        })()}
      </div>
      
      {/* 失败时重试 */}
      <Collapsible open={retryOpen} onOpenChange={setRetryOpen}>
        <div className="flex items-center justify-between py-2">
          <Label className="text-xs font-medium">失败时重试</Label>
          <Switch
            checked={safeConfig.retry.enabled}
            onCheckedChange={(checked) => {
              handleRetryChange({ enabled: checked })
              setRetryOpen(checked)
            }}
          />
        </div>
        <CollapsibleContent className="space-y-3 pt-2">
          <div className="flex items-center gap-4">
            <div className="flex-1 space-y-1">
              <Label className="text-xs text-muted-foreground">重试次数</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={safeConfig.retry.maxRetries}
                onChange={(e) => handleRetryChange({ maxRetries: parseInt(e.target.value) || 1 })}
                className="h-8 text-xs"
              />
            </div>
            <div className="flex-1 space-y-1">
              <Label className="text-xs text-muted-foreground">重试间隔（毫秒）</Label>
              <Input
                type="number"
                min={100}
                max={60000}
                step={100}
                value={safeConfig.retry.retryInterval}
                onChange={(e) => handleRetryChange({ retryInterval: parseInt(e.target.value) || 1000 })}
                className="h-8 text-xs"
              />
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
      
      {/* 异常处理 */}
      <div className="space-y-2 pt-2 border-t">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">异常处理</Label>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger
                render={<Info className="h-3 w-3 text-muted-foreground cursor-help" />}
              />
              <TooltipContent side="right" className="max-w-[200px]">
                <p className="text-xs">配置代码执行发生异常时的处理方式</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        
        <RadioGroup
          value={safeConfig.errorHandling.type}
          onValueChange={(v) => handleErrorHandlingChange({ type: v as ErrorHandlingType })}
          className="space-y-2"
        >
          {errorHandlingOptions.map(option => (
            <div key={option.value} className="flex items-start space-x-3">
              <RadioGroupItem 
                value={option.value} 
                id={`error-${option.value}`}
                className="mt-0.5"
              />
              <div className="flex-1 space-y-0.5">
                <Label 
                  htmlFor={`error-${option.value}`}
                  className="text-xs font-medium cursor-pointer"
                >
                  {option.label}
                </Label>
                <p className="text-[10px] text-muted-foreground leading-tight">
                  {option.description}
                </p>
              </div>
            </div>
          ))}
        </RadioGroup>
        
        {/* 默认值输入 */}
        {safeConfig.errorHandling.type === 'default_value' && (
          <div className="pt-2 pl-6">
            <Label className="text-xs text-muted-foreground mb-1 block">默认输出内容</Label>
            <Textarea
              value={safeConfig.errorHandling.defaultValue || ''}
              onChange={(e) => handleErrorHandlingChange({ defaultValue: e.target.value })}
              placeholder="输入发生异常时的默认输出值"
              className="min-h-[60px] text-xs resize-none"
            />
          </div>
        )}
      </div>
    </div>
  )
}
