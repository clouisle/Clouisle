'use client'

import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue, SelectEmpty } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChevronDown, Image, Settings2, Loader2, Search, Info, History } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { teamModelsApi, type TeamModel } from '@/lib/api'
import { isValidVariableName } from '../utils'
import { VariableSelector } from '../variable-selector'
import { PromptTextarea } from '../components/prompt-textarea'
import type { AvailableVariable } from '../types'

// 响应格式类型
export type ResponseFormat = 'text' | 'json' | 'json_schema'

// 记忆模式类型
export type MemoryMode = 'none' | 'window' | 'token_limit'

// LLM 节点配置类型
export interface LLMNodeConfigData {
  // 模型配置
  modelId?: string            // 团队模型授权 ID
  modelName?: string          // 模型名称（显示用）
  
  // 提示词配置
  systemPrompt?: string
  userPrompt?: string
  
  // 模型参数
  temperature?: number        // 温度 0-2
  topP?: number              // Top P 0-1
  maxTokens?: number         // 最大输出 token 数
  
  // 响应格式
  responseFormat?: ResponseFormat
  jsonSchema?: string        // JSON Schema（当 responseFormat 为 json_schema 时）
  
  // 记忆/上下文配置
  memoryConfig?: {
    enabled: boolean
    mode: MemoryMode
    windowSize?: number      // 窗口模式：消息轮次
    tokenLimit?: number      // Token 限制模式：最大 token 数
  }
  
  // 多模态配置
  visionConfig?: {
    enabled: boolean
    imageVariable?: string   // 图片变量引用
    imagePosition?: 'before' | 'after'  // 图片位置：消息前/后
  }
  
  // 输出变量配置
  outputVariables?: {
    response?: string        // 模型回复
    reasoning?: string       // 推理过程
    usage?: string           // 用量统计
  }
  
  // 高级选项
  streaming?: boolean        // 是否流式输出
  timeout?: number           // 超时时间（秒）
}

export const defaultLLMNodeConfig: LLMNodeConfigData = {
  systemPrompt: '',
  userPrompt: '',
  temperature: 0.7,
  topP: 1,
  responseFormat: 'text',
  outputVariables: {
    response: 'response',
    reasoning: 'reasoning',
    usage: 'usage',
  },
  memoryConfig: {
    enabled: false,
    mode: 'none',
    windowSize: 10,
    tokenLimit: 4000,
  },
  visionConfig: {
    enabled: false,
    imagePosition: 'before',
  },
  streaming: true,
  timeout: 60,
}

interface LLMNodeConfigProps {
  config?: LLMNodeConfigData
  onChange?: (config: LLMNodeConfigData) => void
  getAvailableVariables?: (filterType?: 'iterable' | 'all') => AvailableVariable[]
}

export function LLMNodeConfig({ config = defaultLLMNodeConfig, onChange, getAvailableVariables }: LLMNodeConfigProps) {
  const { currentTeam } = useTeam()
  
  // 模型数据
  const [teamChatModels, setTeamChatModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)
  const [modelSearch, setModelSearch] = React.useState('')
  const [modelSelectorOpen, setModelSelectorOpen] = React.useState(false)
  
  // UI 状态
  const [advancedOpen, setAdvancedOpen] = React.useState(false)
  const [visionOpen, setVisionOpen] = React.useState(config.visionConfig?.enabled || false)
  const [memoryOpen, setMemoryOpen] = React.useState(config.memoryConfig?.enabled || false)
  const [imageVarSelectorOpen, setImageVarSelectorOpen] = React.useState(false)
  
  // 确保配置有默认值
  const safeConfig: LLMNodeConfigData = {
    ...defaultLLMNodeConfig,
    ...config,
    memoryConfig: {
      enabled: config?.memoryConfig?.enabled ?? defaultLLMNodeConfig.memoryConfig!.enabled,
      mode: config?.memoryConfig?.mode ?? defaultLLMNodeConfig.memoryConfig!.mode,
      windowSize: config?.memoryConfig?.windowSize ?? defaultLLMNodeConfig.memoryConfig!.windowSize,
      tokenLimit: config?.memoryConfig?.tokenLimit ?? defaultLLMNodeConfig.memoryConfig!.tokenLimit,
    },
    visionConfig: {
      enabled: config?.visionConfig?.enabled ?? defaultLLMNodeConfig.visionConfig!.enabled,
      imageVariable: config?.visionConfig?.imageVariable,
      imagePosition: config?.visionConfig?.imagePosition ?? defaultLLMNodeConfig.visionConfig!.imagePosition,
    },
  }

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

  // 获取选中的模型信息
  const selectedModel = React.useMemo(() => {
    if (!safeConfig.modelId) return null
    return teamChatModels.find(m => m.id === safeConfig.modelId)
  }, [safeConfig.modelId, teamChatModels])

  // 判断当前选中的模型是否支持视觉/图片输入
  const modelSupportsVision = React.useMemo(() => {
    if (!selectedModel) return false
    const capabilities = selectedModel.model.capabilities as Record<string, unknown> | null | undefined
    return capabilities?.vision === true
  }, [selectedModel])

  // 过滤模型
  const filteredModels = React.useMemo(() => {
    if (!modelSearch) return teamChatModels
    const query = modelSearch.toLowerCase()
    return teamChatModels.filter(m => 
      m.model.name.toLowerCase().includes(query) ||
      m.model.provider.toLowerCase().includes(query) ||
      m.model.model_id.toLowerCase().includes(query)
    )
  }, [teamChatModels, modelSearch])

  const handleChange = (updates: Partial<LLMNodeConfigData>) => {
    onChange?.({ ...safeConfig, ...updates })
  }

  const handleMemoryChange = (updates: Partial<NonNullable<LLMNodeConfigData['memoryConfig']>>) => {
    handleChange({
      memoryConfig: { ...safeConfig.memoryConfig, ...updates } as LLMNodeConfigData['memoryConfig']
    })
  }

  const handleVisionChange = (updates: Partial<NonNullable<LLMNodeConfigData['visionConfig']>>) => {
    handleChange({
      visionConfig: { ...safeConfig.visionConfig, ...updates } as LLMNodeConfigData['visionConfig']
    })
  }

  // 获取图片类型变量
  const imageVariables = React.useMemo(() => {
    if (!getAvailableVariables) return []
    return getAvailableVariables('all').filter(v => 
      v.type === 'Image' || v.type === 'File' || v.isFile
    )
  }, [getAvailableVariables])

  // 分组模型（按供应商）
  const groupedModels = React.useMemo(() => {
    const groups: Record<string, TeamModel[]> = {}
    filteredModels.forEach(m => {
      const provider = m.model.provider
      if (!groups[provider]) groups[provider] = []
      groups[provider].push(m)
    })
    return groups
  }, [filteredModels])

  return (
    <div className="space-y-4">
      {/* 模型选择 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">模型</Label>
          <span className="text-destructive">*</span>
        </div>
        <Popover open={modelSelectorOpen} onOpenChange={setModelSelectorOpen}>
          <PopoverTrigger className="w-full">
            <div className={cn(
              'flex items-center justify-between w-full h-9 px-3 rounded-md border bg-background text-sm cursor-pointer hover:bg-muted/50 transition-colors',
              !safeConfig.modelId && 'text-muted-foreground'
            )}>
              <span className="truncate">
                {selectedModel ? selectedModel.model.name : '选择模型...'}
              </span>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </div>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-0" align="start">
            <div className="p-2 border-b">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="搜索模型"
                  value={modelSearch}
                  onChange={(e) => setModelSearch(e.target.value)}
                  className="h-8 pl-8 text-xs"
                />
              </div>
            </div>
            <ScrollArea className="h-64">
              {isLoadingModels ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : Object.keys(groupedModels).length === 0 ? (
                <div className="py-8 text-center text-muted-foreground text-xs">
                  {teamChatModels.length === 0 ? '暂无可用模型' : '未找到匹配的模型'}
                </div>
              ) : (
                <div className="p-1">
                  {Object.entries(groupedModels).map(([provider, models]) => (
                    <div key={provider} className="mb-2">
                      <div className="px-2 py-1 text-xs text-muted-foreground font-medium uppercase">
                        {provider}
                      </div>
                      {models.map(tm => (
                        <button
                          key={tm.id}
                          className={cn(
                            'w-full flex items-center gap-2 px-2 py-2 text-left hover:bg-muted rounded-md transition-colors',
                            safeConfig.modelId === tm.id && 'bg-muted'
                          )}
                          onClick={() => {
                            handleChange({ 
                              modelId: tm.id,
                              modelName: tm.model.name,
                            })
                            setModelSelectorOpen(false)
                            setModelSearch('')
                          }}
                        >
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium truncate">{tm.model.name}</div>
                            <div className="text-xs text-muted-foreground truncate">{tm.model.model_id}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </PopoverContent>
        </Popover>
      </div>
      
      {/* 系统提示词 */}
      <div className="space-y-2">
        <Label className="text-xs font-medium">系统提示词</Label>
        <PromptTextarea
          value={safeConfig.systemPrompt || ''}
          onChange={(value) => handleChange({ systemPrompt: value })}
          variables={getAvailableVariables?.('all') || []}
          placeholder="输入系统提示词，定义 AI 的角色和行为...
输入 {{ 触发变量补全"
          minHeight="min-h-20"
        />
      </div>
      
      {/* 用户提示词 */}
      <div className="space-y-2">
        <div className="flex items-center gap-1">
          <Label className="text-xs font-medium">用户提示词</Label>
          <span className="text-destructive">*</span>
        </div>
        <PromptTextarea
          value={safeConfig.userPrompt || ''}
          onChange={(value) => handleChange({ userPrompt: value })}
          variables={getAvailableVariables?.('all') || []}
          placeholder="输入用户提示词模板...
输入 {{ 触发变量补全"
          minHeight="min-h-24"
        />
      </div>

      {/* 记忆/上下文配置 */}
      <Collapsible open={memoryOpen} onOpenChange={setMemoryOpen}>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" className="w-full justify-between px-3 h-9">
            <span className="flex items-center gap-2">
              <History className="h-4 w-4" />
              <span className="text-xs">记忆（上下文）</span>
              {safeConfig.memoryConfig?.enabled && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                  已启用
                </span>
              )}
            </span>
            <ChevronDown className={cn('h-4 w-4 transition-transform', memoryOpen && 'rotate-180')} />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 pt-3 border-t mt-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label className="text-xs">启用记忆</Label>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-50">
                    <p className="text-xs">启用后将在对话中保持上下文记忆</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <Switch
              checked={safeConfig.memoryConfig?.enabled || false}
              onCheckedChange={(checked) => handleMemoryChange({ enabled: checked })}
            />
          </div>

          {safeConfig.memoryConfig?.enabled && (
            <>
              <div className="space-y-2">
                <Label className="text-xs">记忆模式</Label>
                <Select
                  value={safeConfig.memoryConfig?.mode || 'window'}
                  onValueChange={(v) => handleMemoryChange({ mode: v as MemoryMode })}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue>
                      {safeConfig.memoryConfig?.mode === 'token_limit' ? 'Token 限制' : '窗口模式'}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="window" className="text-xs">窗口模式</SelectItem>
                    <SelectItem value="token_limit" className="text-xs">Token 限制</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              {safeConfig.memoryConfig?.mode === 'window' && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">消息轮次</Label>
                    <span className="text-xs text-muted-foreground">{safeConfig.memoryConfig?.windowSize || 10}</span>
                  </div>
                  <Slider
                    value={[safeConfig.memoryConfig?.windowSize || 10]}
                    min={1}
                    max={50}
                    step={1}
                    onValueChange={(value) => {
                      const v = Array.isArray(value) ? value[0] : value
                      handleMemoryChange({ windowSize: v })
                    }}
                  />
                  <p className="text-[10px] text-muted-foreground">保留最近 N 轮对话作为上下文</p>
                </div>
              )}
              
              {safeConfig.memoryConfig?.mode === 'token_limit' && (
                <div className="space-y-2">
                  <Label className="text-xs">Token 限制</Label>
                  <Input
                    type="number"
                    min={100}
                    max={128000}
                    value={safeConfig.memoryConfig?.tokenLimit || 4000}
                    onChange={(e) => handleMemoryChange({ tokenLimit: parseInt(e.target.value) || 4000 })}
                    className="h-8 text-xs"
                  />
                  <p className="text-[10px] text-muted-foreground">限制上下文的最大 Token 数</p>
                </div>
              )}
            </>
          )}
        </CollapsibleContent>
      </Collapsible>

      {/* 多模态配置 - 仅在模型支持 vision 时显示 */}
      {modelSupportsVision && (
        <Collapsible open={visionOpen} onOpenChange={setVisionOpen}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full justify-between px-3 h-9">
              <span className="flex items-center gap-2">
                <Image className="h-4 w-4" />
                <span className="text-xs">多模态（图片输入）</span>
                {safeConfig.visionConfig?.enabled && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                    已启用
                  </span>
                )}
              </span>
              <ChevronDown className={cn('h-4 w-4 transition-transform', visionOpen && 'rotate-180')} />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-3 pt-3 border-t mt-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">启用图片输入</Label>
              <Switch
                checked={safeConfig.visionConfig?.enabled || false}
                onCheckedChange={(checked) => handleVisionChange({ enabled: checked })}
              />
            </div>

            {safeConfig.visionConfig?.enabled && (
              <>
                <div className="space-y-2">
                  <Label className="text-xs">图片变量</Label>
                  {imageVariables.length > 0 ? (
                    <VariableSelector
                      open={imageVarSelectorOpen}
                      onOpenChange={setImageVarSelectorOpen}
                      variables={imageVariables}
                      selectedValue={safeConfig.visionConfig?.imageVariable}
                      placeholder="选择图片变量"
                      onSelect={(variable) => {
                        handleVisionChange({ imageVariable: variable.id })
                        setImageVarSelectorOpen(false)
                      }}
                    />
                  ) : (
                    <div className="text-xs text-muted-foreground bg-muted rounded-md p-3">
                      暂无可用的图片变量。请在开始节点添加类型为「图片」或「文件」的参数。
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label className="text-xs">图片位置</Label>
                  <div className="flex gap-2">
                    <Button
                      variant={safeConfig.visionConfig?.imagePosition === 'before' ? 'default' : 'outline'}
                      size="sm"
                      className="flex-1 h-8 text-xs"
                      onClick={() => handleVisionChange({ imagePosition: 'before' })}
                    >
                      消息前
                    </Button>
                    <Button
                      variant={safeConfig.visionConfig?.imagePosition === 'after' ? 'default' : 'outline'}
                      size="sm"
                      className="flex-1 h-8 text-xs"
                      onClick={() => handleVisionChange({ imagePosition: 'after' })}
                    >
                      消息后
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CollapsibleContent>
        </Collapsible>
      )}

      {/* 高级设置 */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" className="w-full justify-between px-3 h-9">
            <span className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              <span className="text-xs">高级设置</span>
            </span>
            <ChevronDown className={cn('h-4 w-4 transition-transform', advancedOpen && 'rotate-180')} />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-4 pt-3 border-t mt-2">
          {/* 温度 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Label className="text-xs">温度 (Temperature)</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <Info className="h-3 w-3 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-50">
                      <p className="text-xs">控制输出的随机性。较低的值使输出更确定，较高的值使输出更多样。</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <span className="text-xs text-muted-foreground">{safeConfig.temperature?.toFixed(1)}</span>
            </div>
            <Slider
              value={[safeConfig.temperature || 0.7]}
              min={0}
              max={2}
              step={0.1}
              onValueChange={(value) => {
                const v = Array.isArray(value) ? value[0] : value
                handleChange({ temperature: v })
              }}
            />
          </div>

          {/* Top P */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Label className="text-xs">Top P</Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <Info className="h-3 w-3 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-50">
                      <p className="text-xs">核采样参数。控制累积概率阈值。</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <span className="text-xs text-muted-foreground">{safeConfig.topP?.toFixed(2)}</span>
            </div>
            <Slider
              value={[safeConfig.topP || 1]}
              min={0}
              max={1}
              step={0.01}
              onValueChange={(value) => {
                const v = Array.isArray(value) ? value[0] : value
                handleChange({ topP: v })
              }}
            />
          </div>

          {/* 最大输出 Token */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label className="text-xs">最大输出 Token</Label>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-50">
                    <p className="text-xs">限制模型生成的最大 Token 数量。留空则使用模型默认值。</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <Input
              type="number"
              min={1}
              max={128000}
              value={safeConfig.maxTokens || ''}
              onChange={(e) => handleChange({ maxTokens: e.target.value ? parseInt(e.target.value) : undefined })}
              placeholder="默认"
              className="h-8 text-xs"
            />
          </div>

          {/* 响应格式 */}
          <div className="space-y-2">
            <Label className="text-xs">响应格式</Label>
            <Select
              value={safeConfig.responseFormat || 'text'}
              onValueChange={(v) => handleChange({ responseFormat: v as ResponseFormat })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue>
                  {safeConfig.responseFormat === 'json' ? 'JSON' : 
                   safeConfig.responseFormat === 'json_schema' ? 'JSON Schema' : '文本'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="text" className="text-xs">文本</SelectItem>
                <SelectItem value="json" className="text-xs">JSON</SelectItem>
                <SelectItem value="json_schema" className="text-xs">JSON Schema</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* JSON Schema（当响应格式为 json_schema 时） */}
          {safeConfig.responseFormat === 'json_schema' && (
            <div className="space-y-2">
              <Label className="text-xs">JSON Schema</Label>
              <Textarea
                placeholder='{"type": "object", "properties": {...}}'
                className="min-h-20 text-xs font-mono resize-none"
                value={safeConfig.jsonSchema || ''}
                onChange={(e) => handleChange({ jsonSchema: e.target.value })}
              />
            </div>
          )}

          {/* 流式输出 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Label className="text-xs">流式输出</Label>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-50">
                    <p className="text-xs">启用后将逐字输出响应，提供更好的用户体验。</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <Switch
              checked={safeConfig.streaming ?? true}
              onCheckedChange={(checked) => handleChange({ streaming: checked })}
            />
          </div>

          {/* 超时时间 */}
          <div className="space-y-2">
            <Label className="text-xs">超时时间（秒）</Label>
            <Input
              type="number"
              min={10}
              max={600}
              value={safeConfig.timeout || 60}
              onChange={(e) => handleChange({ timeout: parseInt(e.target.value) || 60 })}
              className="h-8 text-xs"
            />
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* 输出变量 */}
      <div className="space-y-3 pt-2 border-t">
        <Label className="text-xs font-medium">输出变量</Label>
        
        {/* 模型回复 */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Label className="text-xs text-muted-foreground w-16 shrink-0">模型回复</Label>
            <Input
              value={safeConfig.outputVariables?.response || ''}
              onChange={(e) => handleChange({ 
                outputVariables: { 
                  ...safeConfig.outputVariables, 
                  response: e.target.value 
                } 
              })}
              placeholder="response"
              className={cn(
                'h-8 text-xs font-mono flex-1',
                safeConfig.outputVariables?.response && !isValidVariableName(safeConfig.outputVariables.response) && 'border-destructive!'
              )}
            />
            <span className="text-[10px] text-muted-foreground shrink-0">String</span>
          </div>
          {safeConfig.outputVariables?.response && !isValidVariableName(safeConfig.outputVariables.response) && (
            <p className="text-[10px] text-destructive ml-[72px]">变量名格式无效</p>
          )}
        </div>

        {/* 推理过程 */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Label className="text-xs text-muted-foreground w-16 shrink-0">推理过程</Label>
            <Input
              value={safeConfig.outputVariables?.reasoning || ''}
              onChange={(e) => handleChange({ 
                outputVariables: { 
                  ...safeConfig.outputVariables, 
                  reasoning: e.target.value 
                } 
              })}
              placeholder="reasoning"
              className={cn(
                'h-8 text-xs font-mono flex-1',
                safeConfig.outputVariables?.reasoning && !isValidVariableName(safeConfig.outputVariables.reasoning) && 'border-destructive!'
              )}
            />
            <span className="text-[10px] text-muted-foreground shrink-0">String</span>
          </div>
          {safeConfig.outputVariables?.reasoning && !isValidVariableName(safeConfig.outputVariables.reasoning) && (
            <p className="text-[10px] text-destructive ml-[72px]">变量名格式无效</p>
          )}
        </div>

        {/* 用量统计 */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Label className="text-xs text-muted-foreground w-16 shrink-0">用量统计</Label>
            <Input
              value={safeConfig.outputVariables?.usage || ''}
              onChange={(e) => handleChange({ 
                outputVariables: { 
                  ...safeConfig.outputVariables, 
                  usage: e.target.value 
                } 
              })}
              placeholder="usage"
              className={cn(
                'h-8 text-xs font-mono flex-1',
                safeConfig.outputVariables?.usage && !isValidVariableName(safeConfig.outputVariables.usage) && 'border-destructive!'
              )}
            />
            <span className="text-[10px] text-muted-foreground shrink-0">Number</span>
          </div>
          {safeConfig.outputVariables?.usage && !isValidVariableName(safeConfig.outputVariables.usage) && (
            <p className="text-[10px] text-destructive ml-[72px]">变量名格式无效</p>
          )}
        </div>

        <p className="text-[10px] text-muted-foreground">
          推理过程仅在支持思维链的模型中返回，用量统计为总 token 数
        </p>
      </div>
    </div>
  )
}
