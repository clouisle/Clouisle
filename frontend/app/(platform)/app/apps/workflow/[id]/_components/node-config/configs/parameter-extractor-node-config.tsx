'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2, Search, ChevronDown, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue, SelectEmpty } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { isValidVariableName } from '../utils'
import { extractVariableDisplayName } from '../types'
import type { AvailableVariable } from '../types'
import {
  ParameterExtractorConfig,
  ExtractedParameter,
  ExtractionMethod,
  ExtractedParamType,
  getExtractionMethodConfig,
  extractedParamTypeConfig,
  defaultParameterExtractorConfig,
  generateJsonSchema,
} from '../../nodes/parameter-extractor-node'

interface ParameterExtractorNodeConfigProps {
  config: ParameterExtractorConfig
  variables: AvailableVariable[]
  variableSearch: string
  openVariablePopover: string | null
  onConfigChange: (config: ParameterExtractorConfig) => void
  onVariableSearchChange: (search: string) => void
  onOpenVariablePopoverChange: (id: string | null) => void
}

export function ParameterExtractorNodeConfig({
  config,
  variables,
  variableSearch,
  openVariablePopover,
  onConfigChange,
  onVariableSearchChange,
  onOpenVariablePopoverChange,
}: ParameterExtractorNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  
  // 模型数据
  const [teamChatModels, setTeamChatModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)

  // 确保 config 有默认值
  const safeConfig: ParameterExtractorConfig = {
    ...defaultParameterExtractorConfig,
    ...config,
    parameters: config.parameters || [],
  }

  const extractionMethodConfig = React.useMemo(() => getExtractionMethodConfig(t), [t])
  const methodConfig = extractionMethodConfig[safeConfig.extractionMethod]

  // 加载模型列表
  React.useEffect(() => {
    const loadModels = async () => {
      if (!currentTeam) return
      
      setIsLoadingModels(true)
      try {
        const models = await teamModelsApi.getTeamModels(currentTeam.id, 'chat')
        setTeamChatModels(models.filter(m => m.is_enabled))
      } catch {
        // 忽略错误
      } finally {
        setIsLoadingModels(false)
      }
    }
    loadModels()
  }, [currentTeam])

  // 获取选中的模型名称
  const selectedModelName = React.useMemo(() => {
    if (!safeConfig.modelId) return null
    const tm = teamChatModels.find(m => m.id === safeConfig.modelId)
    if (tm) return tm.model.name
    return safeConfig.modelId // 如果找不到，显示原始 ID
  }, [safeConfig.modelId, teamChatModels])

  // 过滤变量（根据搜索词和当前提取方式支持的源变量类型）
  const filterVariables = (search: string) => {
    const supportedTypes = methodConfig.sourceVariableTypes
    let filtered = variables.filter(v => supportedTypes.includes(v.type))
    
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

  // 添加参数
  const handleAddParameter = () => {
    const newParam: ExtractedParameter = {
      id: `param_${Date.now()}`,
      name: `param${safeConfig.parameters.length + 1}`,
      type: methodConfig.defaultType,
      description: '',
      required: false,
    }
    onConfigChange({
      ...safeConfig,
      parameters: [...safeConfig.parameters, newParam],
    })
  }

  // 更新参数
  const handleUpdateParameter = (id: string, updates: Partial<ExtractedParameter>) => {
    onConfigChange({
      ...safeConfig,
      parameters: safeConfig.parameters.map(p => 
        p.id === id ? { ...p, ...updates } : p
      ),
    })
  }

  // 删除参数
  const handleDeleteParameter = (id: string) => {
    onConfigChange({
      ...safeConfig,
      parameters: safeConfig.parameters.filter(p => p.id !== id),
    })
  }

  // 渲染源变量选择器
  const renderSourceVariableSelector = () => {
    const popoverId = 'source-var'
    
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
          {safeConfig.sourceVariable ? (
            <>
              <span className="text-primary/80 font-mono text-xs">{'{x}'}</span>
              <span className="text-xs truncate">
                {safeConfig.sourceNodeLabel && <span className="text-muted-foreground">{safeConfig.sourceNodeLabel} / </span>}
                {extractVariableDisplayName(safeConfig.sourceVariable)}
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-xs">{t('configParameterExtractor.selectSourceTextVariable')}</span>
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
                        onClick={() => {
                          // 使用 variable.id（格式为 nodeId.paramName）而不是 variable.name
                          onConfigChange({
                            ...safeConfig,
                            sourceVariable: `{{${variable.id}}}`,
                            sourceNodeLabel: variable.isSystem ? t('nodesCommon.system') : variable.groupLabel,
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
      {/* 提取方式 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configParameterExtractor.extractionMethod')}</Label>
          <span className="text-destructive">*</span>
        </div>
        <Select
          value={safeConfig.extractionMethod}
          onValueChange={(v) => {
            const newMethod = v as ExtractionMethod
            const newMethodConfig = extractionMethodConfig[newMethod]
            // 切换方式时，自动调整不兼容的参数类型
            const updatedParams = safeConfig.parameters.map(p => {
              if (!newMethodConfig.supportedTypes.includes(p.type)) {
                return { ...p, type: newMethodConfig.defaultType }
              }
              return p
            })
            onConfigChange({ 
              ...safeConfig, 
              extractionMethod: newMethod,
              parameters: updatedParams,
            })
          }}
        >
          <SelectTrigger className="w-full h-9 text-xs">
            <SelectValue>
              <span className="flex items-center gap-2">
                {React.createElement(methodConfig.icon, { className: "h-3.5 w-3.5" })}
                {methodConfig.label}
              </span>
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(extractionMethodConfig).map(([key, cfg]) => (
              <SelectItem key={key} value={key} className="text-xs">
                <span className="flex items-center gap-2">
                  {React.createElement(cfg.icon, { className: "h-3.5 w-3.5" })}
                  {cfg.label}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[10px] text-muted-foreground">{methodConfig.description}</p>
      </div>

      {/* 源文本变量 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">{t('configParameterExtractor.sourceText')}</Label>
          <span className="text-destructive">*</span>
        </div>
        {renderSourceVariableSelector()}
        <p className="text-[10px] text-muted-foreground">{t('configParameterExtractor.sourceTextHint')}</p>
      </div>

      {/* LLM 模式配置 */}
      {safeConfig.extractionMethod === 'llm' && (
        <>
          <div className="space-y-2">
            <Label className="text-xs font-medium">{t('configCommon.model')}</Label>
            <Select
              value={safeConfig.modelId || ''}
              onValueChange={(v) => {
                const model = teamChatModels.find(m => m.id === v)
                onConfigChange({ 
                  ...safeConfig, 
                  modelId: v || undefined,
                  modelName: model?.model.name,
                })
              }}
              disabled={isLoadingModels}
            >
              <SelectTrigger className="w-full h-9 text-xs">
                <SelectValue>
                  {isLoadingModels ? (
                    <span className="flex items-center gap-2 text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {t('configCommon.loading')}
                    </span>
                  ) : (
                    selectedModelName || t('configCommon.selectModel')
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {teamChatModels.length > 0 ? (
                  teamChatModels.map((tm) => (
                    <SelectItem key={tm.id} value={tm.id} className="text-xs">
                      {tm.model.name}
                    </SelectItem>
                  ))
                ) : (
                  <SelectEmpty>{t('configCommon.noAvailableModels')}</SelectEmpty>
                )}
              </SelectContent>
            </Select>
          </div>
          
          {/* JSON Schema 开关 */}
          <div className="flex items-center justify-between py-2">
            <div className="space-y-0.5">
              <Label className="text-xs font-medium">{t('configParameterExtractor.structuredOutput')}</Label>
              <p className="text-[10px] text-muted-foreground">{t('configParameterExtractor.structuredOutputHint')}</p>
            </div>
            <Checkbox
              checked={safeConfig.useJsonSchema !== false}
              onCheckedChange={(checked) => onConfigChange({ ...safeConfig, useJsonSchema: !!checked })}
            />
          </div>
        </>
      )}

      {/* 参数列表 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <Label className="text-xs font-medium">{t('configParameterExtractor.extractionParameters')}</Label>
            <span className="text-destructive">*</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={handleAddParameter}
          >
            <Plus className="h-3 w-3" />
          </Button>
        </div>
        
        {safeConfig.parameters.length === 0 ? (
          <p className="text-xs text-muted-foreground py-4 text-center bg-muted/30 rounded-md">
            {t('configParameterExtractor.noParameters')}
          </p>
        ) : (
          <div className="space-y-2">
            {safeConfig.parameters.map((param, index) => (
              <div
                key={param.id}
                className="bg-muted/30 rounded-lg p-3 space-y-2"
              >
                {/* 头部：序号 + 删除 */}
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t('configParameterExtractor.parameterIndex', { index: index + 1 })}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-muted-foreground hover:text-destructive"
                    onClick={() => handleDeleteParameter(param.id)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
                
                {/* 参数名 + 类型 */}
                <div className="flex gap-2">
                  <div className="flex-1 space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.parameterName')}</Label>
                    <Input
                      value={param.name}
                      onChange={(e) => handleUpdateParameter(param.id, { name: e.target.value })}
                      placeholder={t('configParameterExtractor.parameterName')}
                      className={cn(
                        'h-8 text-xs font-mono',
                        param.name && !isValidVariableName(param.name) && 'border-destructive!'
                      )}
                    />
                  </div>
                  <div className="w-24 space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{t('configCommon.type')}</Label>
                    <Select
                      value={param.type}
                      onValueChange={(v) => handleUpdateParameter(param.id, { type: v as ExtractedParamType })}
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {methodConfig.supportedTypes.map((typeKey) => (
                          <SelectItem key={typeKey} value={typeKey} className="text-xs">
                            {t(extractedParamTypeConfig[typeKey].labelKey)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                {/* 描述（LLM 模式） */}
                {safeConfig.extractionMethod === 'llm' && (
                  <>
                    <div className="space-y-1">
                      <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.descriptionHelpLLM')}</Label>
                      <Input
                        value={param.description}
                        onChange={(e) => handleUpdateParameter(param.id, { description: e.target.value })}
                        placeholder={t('configParameterExtractor.descriptionPlaceholder')}
                        className="h-8 text-xs"
                      />
                    </div>
                    
                    {/* 枚举值（仅 string 类型） */}
                    {param.type === 'string' && (
                      <div className="space-y-1">
                        <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.enumValues')}</Label>
                        <Input
                          value={param.enum?.join(', ') || ''}
                          onChange={(e) => {
                            const val = e.target.value.trim()
                            const enumValues = val ? val.split(',').map(s => s.trim()).filter(Boolean) : undefined
                            handleUpdateParameter(param.id, { enum: enumValues })
                          }}
                          placeholder={t('configParameterExtractor.enumPlaceholder')}
                          className="h-8 text-xs"
                        />
                      </div>
                    )}
                    
                    {/* 数组元素类型（仅 array 类型） */}
                    {param.type === 'array' && (
                      <div className="space-y-1">
                        <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.arrayItemType')}</Label>
                        <Select
                          value={param.arrayItemType || 'string'}
                          onValueChange={(v) => handleUpdateParameter(param.id, { arrayItemType: v as ExtractedParamType })}
                        >
                          <SelectTrigger className="h-8 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="string" className="text-xs">{t(extractedParamTypeConfig.string.labelKey)}</SelectItem>
                            <SelectItem value="number" className="text-xs">{t(extractedParamTypeConfig.number.labelKey)}</SelectItem>
                            <SelectItem value="boolean" className="text-xs">{t(extractedParamTypeConfig.boolean.labelKey)}</SelectItem>
                            <SelectItem value="object" className="text-xs">{t(extractedParamTypeConfig.object.labelKey)}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                  </>
                )}
                
                {/* 正则表达式（regex 模式） */}
                {safeConfig.extractionMethod === 'regex' && (
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.regexPattern')}</Label>
                    <Input
                      value={param.pattern || ''}
                      onChange={(e) => handleUpdateParameter(param.id, { pattern: e.target.value })}
                      placeholder={t('configParameterExtractor.regexPlaceholder')}
                      className="h-8 text-xs font-mono"
                    />
                  </div>
                )}
                
                {/* JSON Path（json_path 模式） */}
                {safeConfig.extractionMethod === 'json_path' && (
                  <div className="space-y-1">
                    <Label className="text-[10px] text-muted-foreground">{t('configParameterExtractor.jsonPathLabel')}</Label>
                    <Input
                      value={param.jsonPath || ''}
                      onChange={(e) => handleUpdateParameter(param.id, { jsonPath: e.target.value })}
                      placeholder={t('configParameterExtractor.jsonPathPlaceholder')}
                      className="h-8 text-xs font-mono"
                    />
                  </div>
                )}
                
                {/* 必填 + 默认值 */}
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={`required-${param.id}`}
                      checked={param.required}
                      onCheckedChange={(checked) => handleUpdateParameter(param.id, { required: !!checked })}
                    />
                    <Label htmlFor={`required-${param.id}`} className="text-xs text-muted-foreground cursor-pointer">
                      {t('configCommon.required')}
                    </Label>
                  </div>
                  <div className="flex-1 flex items-center gap-2">
                    <Label className="text-xs text-muted-foreground shrink-0">{t('configParameterExtractor.defaultValueLabel')}</Label>
                    <Input
                      value={param.defaultValue || ''}
                      onChange={(e) => handleUpdateParameter(param.id, { defaultValue: e.target.value })}
                      placeholder={t('configCommon.none')}
                      className="h-7 text-xs flex-1"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* 参数名校验提示 */}
        {safeConfig.parameters.some(p => p.name && !isValidVariableName(p.name)) && (
          <p className="text-[10px] text-destructive">{t('configParameterExtractor.invalidParamName')}</p>
        )}
        {(() => {
          const names = safeConfig.parameters.map(p => p.name).filter(Boolean)
          const hasDuplicates = new Set(names).size !== names.length
          return hasDuplicates && (
            <p className="text-[10px] text-destructive">{t('configParameterExtractor.duplicateParamName')}</p>
          )
        })()}
      </div>
      
      {/* JSON Schema 预览 */}
      {safeConfig.extractionMethod === 'llm' && safeConfig.useJsonSchema !== false && safeConfig.parameters.length > 0 && (
        <Collapsible>
          <CollapsibleTrigger className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground">
            <ChevronDown className="h-3 w-3" />
            <span>{t('configParameterExtractor.viewJsonSchema')}</span>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-2">
            <pre className="text-[10px] bg-muted/50 rounded-lg p-2 overflow-x-auto max-h-40 overflow-y-auto">
              {JSON.stringify(generateJsonSchema(safeConfig.parameters), null, 2)}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
