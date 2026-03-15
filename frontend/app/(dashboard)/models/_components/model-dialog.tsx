'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Eye, EyeOff, Loader2, CheckCircle2, XCircle, Zap, Check } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import { modelsApi, type Model, type ModelCreateInput } from '@/lib/api/admin/models'
import type { ProviderInfo, ModelTypeInfo } from '@/lib/api/models'

// 供应商分组
const PROVIDER_GROUPS = {
  international: ['openai', 'anthropic', 'google', 'xai', 'azure_openai'],
  domestic: ['deepseek', 'moonshot', 'zhipu', 'qwen', 'baichuan', 'minimax'],
  other: ['ollama', 'custom'],
}

// 模型类型分类（仅包含已实现适配器的类型）
const MODEL_CATEGORIES = {
  text: ['chat', 'embedding'],
  rerank: ['rerank'],
  image: ['text_to_image'],
  audio: ['tts', 'stt'],
}

function getModelCategory(modelType: string): keyof typeof MODEL_CATEGORIES | null {
  for (const [category, types] of Object.entries(MODEL_CATEGORIES)) {
    if (types.includes(modelType)) {
      return category as keyof typeof MODEL_CATEGORIES
    }
  }
  return null
}

function isChatOnly(modelType: string): boolean {
  return modelType === 'chat'
}

function requiresApiKey(provider: string): boolean {
  return provider !== 'ollama'
}

// 分隔线组件 - 移到组件外部避免重新创建
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 text-sm font-medium text-muted-foreground">
      <span className="h-px flex-1 bg-border" />
      <span>{children}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  )
}

interface ModelDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  model?: Model | null
  onSuccess: () => void
  providers: ProviderInfo[]
  modelTypes: ModelTypeInfo[]
}

export function ModelDialog({
  open,
  onOpenChange,
  model,
  onSuccess,
  providers,
  modelTypes,
}: ModelDialogProps) {
  const t = useTranslations('models')
  const commonT = useTranslations('common')
  
  const isEditing = !!model
  
  // 基本信息
  const [name, setName] = React.useState('')
  const [provider, setProvider] = React.useState('')
  const [modelId, setModelId] = React.useState('')
  const [modelType, setModelType] = React.useState('')
  const [baseUrl, setBaseUrl] = React.useState('')
  const [apiKey, setApiKey] = React.useState('')
  const [showApiKey, setShowApiKey] = React.useState(false)
  
  // 参数
  const [contextLength, setContextLength] = React.useState('')
  const [maxOutputTokens, setMaxOutputTokens] = React.useState('')
  const [inputPrice, setInputPrice] = React.useState('')
  const [outputPrice, setOutputPrice] = React.useState('')
  
  // 推理参数
  const [temperature, setTemperature] = React.useState('')
  const [topP, setTopP] = React.useState('')
  const [frequencyPenalty, setFrequencyPenalty] = React.useState('')
  const [presencePenalty, setPresencePenalty] = React.useState('')
  const [maxTokens, setMaxTokens] = React.useState('')
  
  // 能力
  const [supportsVision, setSupportsVision] = React.useState(false)
  const [supportsFunctionCall, setSupportsFunctionCall] = React.useState(false)
  const [supportsStreaming, setSupportsStreaming] = React.useState(true)
  const [supportsJsonMode, setSupportsJsonMode] = React.useState(false)
  
  // 状态
  const [isEnabled, setIsEnabled] = React.useState(true)
  const [isDefault, setIsDefault] = React.useState(false)
  
  // 图像生成参数
  const [defaultImageSize, setDefaultImageSize] = React.useState('')
  const [defaultImageStyle, setDefaultImageStyle] = React.useState('')
  const [defaultImageQuality, setDefaultImageQuality] = React.useState('')
  
  // 音频参数
  const [defaultVoice, setDefaultVoice] = React.useState('')
  const [defaultSpeed, setDefaultSpeed] = React.useState('')
  
  // Azure 配置
  const [apiVersion, setApiVersion] = React.useState('')
  const [deploymentName, setDeploymentName] = React.useState('')

  // Thinking/Reasoning 配置
  const [thinkingEnabled, setThinkingEnabled] = React.useState(false)
  const [thinkingBudget, setThinkingBudget] = React.useState('')
  const [reasoningEffort, setReasoningEffort] = React.useState('')

  const [isLoading, setIsLoading] = React.useState(false)
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  
  // 测试状态
  const [isTesting, setIsTesting] = React.useState(false)
  const [testResult, setTestResult] = React.useState<{
    success: boolean
    message: string
    latency_ms?: number
  } | null>(null)
  
  // 重置表单
  const resetForm = React.useCallback(() => {
    if (model) {
      setName(model.name)
      setProvider(model.provider)
      setModelId(model.model_id)
      setModelType(model.model_type)
      setBaseUrl(model.base_url || '')
      setApiKey('')
      setContextLength(model.context_length?.toString() || '')
      setMaxOutputTokens(model.max_output_tokens?.toString() || '')
      setInputPrice(model.input_price?.toString() || '')
      setOutputPrice(model.output_price?.toString() || '')
      setIsEnabled(model.is_enabled)
      setIsDefault(model.is_default)
      
      const params = model.default_params || {}
      setTemperature((params.temperature as number)?.toString() || '')
      setTopP((params.top_p as number)?.toString() || '')
      setFrequencyPenalty((params.frequency_penalty as number)?.toString() || '')
      setPresencePenalty((params.presence_penalty as number)?.toString() || '')
      setMaxTokens((params.max_tokens as number)?.toString() || '')
      setDefaultImageSize((params.size as string) || '')
      setDefaultImageStyle((params.style as string) || '')
      setDefaultImageQuality((params.quality as string) || '')
      setDefaultVoice((params.voice as string) || '')
      setDefaultSpeed((params.speed as number)?.toString() || '')
      
      const caps = model.capabilities || {}
      setSupportsVision(!!caps.vision)
      setSupportsFunctionCall(!!caps.function_call)
      setSupportsStreaming(caps.streaming !== false)
      setSupportsJsonMode(!!caps.json_mode)
      
      const config = model.config || {}
      setApiVersion((config.api_version as string) || '')
      setDeploymentName((config.deployment_name as string) || '')

      // Thinking 配置
      const thinking = config.thinking as Record<string, unknown> | boolean | undefined
      if (typeof thinking === 'boolean') {
        setThinkingEnabled(thinking)
        setThinkingBudget('')
        setReasoningEffort('')
      } else if (thinking && typeof thinking === 'object') {
        setThinkingEnabled(thinking.enabled !== false)
        setThinkingBudget((thinking.budget_tokens as number)?.toString() || (thinking.budget as number)?.toString() || '')
        setReasoningEffort((thinking.effort as string) || (thinking.reasoning_effort as string) || '')
      } else {
        setThinkingEnabled(false)
        setThinkingBudget('')
        setReasoningEffort('')
      }
    } else {
      setName('')
      setProvider('')
      setModelId('')
      setModelType('')
      setBaseUrl('')
      setApiKey('')
      setContextLength('')
      setMaxOutputTokens('')
      setInputPrice('')
      setOutputPrice('')
      setIsEnabled(true)
      setIsDefault(false)
      setTemperature('')
      setTopP('')
      setFrequencyPenalty('')
      setPresencePenalty('')
      setMaxTokens('')
      setSupportsVision(false)
      setSupportsFunctionCall(false)
      setSupportsStreaming(true)
      setSupportsJsonMode(false)
      setDefaultImageSize('')
      setDefaultImageStyle('')
      setDefaultImageQuality('')
      setDefaultVoice('')
      setDefaultSpeed('')
      setApiVersion('')
      setDeploymentName('')
      setThinkingEnabled(false)
      setThinkingBudget('')
      setReasoningEffort('')
    }
    setShowApiKey(false)
    setErrors({})
    setTestResult(null)
  }, [model])
  
  React.useEffect(() => {
    if (open) resetForm()
  }, [open, resetForm])
  
  // 测试模型配置
  const handleTestConnection = async () => {
    // 验证必填字段
    if (
      !provider ||
      !modelId.trim() ||
      !modelType ||
      (requiresApiKey(provider) && !apiKey.trim())
    ) {
      toast.error(t('fillRequiredFieldsFirst'))
      return
    }
    
    setIsTesting(true)
    setTestResult(null)
    
    try {
      const config: Record<string, unknown> = {}
      if (apiVersion) config.api_version = apiVersion
      if (deploymentName) config.deployment_name = deploymentName
      
      const result = await modelsApi.testModelConfig({
        provider,
        model_id: modelId.trim(),
        model_type: modelType,
        base_url: baseUrl.trim() || null,
        api_key: apiKey || null,
        config: Object.keys(config).length > 0 ? config : null,
      })
      
      setTestResult(result)
      
      if (result.success) {
        toast.success(t('testSuccess'))
      } else {
        toast.error(result.message)
      }
    } catch {
      setTestResult({
        success: false,
        message: t('testFailed'),
      })
    } finally {
      setIsTesting(false)
    }
  }
  
  const handleProviderChange = (value: string) => {
    setProvider(value)
    setTestResult(null) // 重置测试结果
    if (!baseUrl) {
      const providerInfo = providers.find(p => p.code === value)
      if (providerInfo?.base_url) setBaseUrl(providerInfo.base_url)
    }
  }
  
  const handleModelTypeChange = (value: string | null) => {
    if (value) {
      setModelType(value)
      const newCategory = getModelCategory(value)
      const currentCategory = getModelCategory(modelType)
      if (newCategory !== currentCategory) {
        setProvider('')
        setBaseUrl('')
      }
    }
  }
  
  // 根据模型类型过滤供应商
  const filteredProviders = React.useMemo(() => {
    if (!modelType) return providers
    const category = getModelCategory(modelType)
    if (!category) return providers
    
    const providersByCategory: Record<string, string[]> = {
      text: ['openai', 'anthropic', 'google', 'xai', 'azure_openai', 'deepseek', 'moonshot', 'zhipu', 'qwen', 'baichuan', 'minimax', 'ollama', 'custom'],
      rerank: ['openai', 'anthropic', 'google', 'xai', 'azure_openai', 'deepseek', 'moonshot', 'zhipu', 'qwen', 'baichuan', 'minimax', 'ollama', 'custom'],
      image: ['openai', 'azure_openai', 'custom'],
      audio: ['openai', 'azure_openai', 'custom'],
    }
    
    const allowedProviders = providersByCategory[category] || []
    return providers.filter(p => allowedProviders.includes(p.code))
  }, [modelType, providers])

  // 分组过滤后的供应商
  const groupedProviders = React.useMemo(() => {
    const codes = new Set(filteredProviders.map(p => p.code))
    return {
      international: PROVIDER_GROUPS.international.filter(p => codes.has(p)),
      domestic: PROVIDER_GROUPS.domestic.filter(p => codes.has(p)),
      other: PROVIDER_GROUPS.other.filter(p => codes.has(p)),
    }
  }, [filteredProviders])

  // 供应商选择 Popover 状态
  const [providerPopoverOpen, setProviderPopoverOpen] = React.useState(false)
  
  // 提交表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrors({})
    
    const newErrors: Record<string, string> = {}
    if (!name.trim()) newErrors.name = t('nameRequired')
    if (!provider) newErrors.provider = t('providerRequired')
    if (!modelId.trim()) newErrors.modelId = t('modelIdRequired')
    if (!modelType) newErrors.modelType = t('modelTypeRequired')
    if (!isEditing && requiresApiKey(provider) && !apiKey.trim()) {
      newErrors.apiKey = t('apiKeyRequired')
    }
    
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    
    setIsLoading(true)
    
    try {
      const defaultParams: Record<string, unknown> = {}
      const category = getModelCategory(modelType)
      
      if (category === 'text') {
        if (temperature) defaultParams.temperature = parseFloat(temperature)
        if (topP) defaultParams.top_p = parseFloat(topP)
        if (frequencyPenalty) defaultParams.frequency_penalty = parseFloat(frequencyPenalty)
        if (presencePenalty) defaultParams.presence_penalty = parseFloat(presencePenalty)
        if (maxTokens) defaultParams.max_tokens = parseInt(maxTokens)
      } else if (category === 'image') {
        if (defaultImageSize) defaultParams.size = defaultImageSize
        if (defaultImageStyle) defaultParams.style = defaultImageStyle
        if (defaultImageQuality) defaultParams.quality = defaultImageQuality
      } else if (category === 'audio') {
        if (defaultVoice) defaultParams.voice = defaultVoice
        if (defaultSpeed) defaultParams.speed = parseFloat(defaultSpeed)
      }
      
      let capabilities: Record<string, boolean> | null = null
      if (modelType === 'chat') {
        capabilities = {}
        if (supportsVision) capabilities.vision = true
        if (supportsFunctionCall) capabilities.function_call = true
        if (!supportsStreaming) capabilities.streaming = false
        if (supportsJsonMode) capabilities.json_mode = true
        if (Object.keys(capabilities).length === 0) capabilities = null
      }
      
      const config: Record<string, unknown> = {}
      if (apiVersion) config.api_version = apiVersion
      if (deploymentName) config.deployment_name = deploymentName

      // Thinking 配置
      if (thinkingEnabled) {
        const thinkingConfig: Record<string, unknown> = { enabled: true }
        if (thinkingBudget) thinkingConfig.budget_tokens = parseInt(thinkingBudget)
        if (reasoningEffort) thinkingConfig.effort = reasoningEffort
        config.thinking = thinkingConfig
      }

      if (isEditing && model) {
        await modelsApi.updateModel(model.id, {
          name: name.trim(),
          base_url: baseUrl.trim() || null,
          api_key: apiKey || undefined,
          context_length: contextLength ? parseInt(contextLength) : null,
          max_output_tokens: maxOutputTokens ? parseInt(maxOutputTokens) : null,
          input_price: inputPrice ? parseFloat(inputPrice) : null,
          output_price: outputPrice ? parseFloat(outputPrice) : null,
          default_params: Object.keys(defaultParams).length > 0 ? defaultParams : null,
          capabilities,
          config: Object.keys(config).length > 0 ? config : null,
          is_enabled: isEnabled,
          is_default: isDefault,
        })
        toast.success(t('modelUpdated'))
      } else {
        const createData: ModelCreateInput = {
          name: name.trim(),
          provider,
          model_id: modelId.trim(),
          model_type: modelType,
          base_url: baseUrl.trim() || null,
          api_key: apiKey || null,
          context_length: contextLength ? parseInt(contextLength) : null,
          max_output_tokens: maxOutputTokens ? parseInt(maxOutputTokens) : null,
          input_price: inputPrice ? parseFloat(inputPrice) : null,
          output_price: outputPrice ? parseFloat(outputPrice) : null,
          default_params: Object.keys(defaultParams).length > 0 ? defaultParams : null,
          capabilities,
          config: Object.keys(config).length > 0 ? config : null,
          is_enabled: isEnabled,
          is_default: isDefault,
        }
        await modelsApi.createModel(createData)
        toast.success(t('modelCreated'))
      }
      
      onOpenChange(false)
      onSuccess()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }
  
  const category = modelType ? getModelCategory(modelType) : null
  const showAdvancedTab = modelType && (isChatOnly(modelType) || provider === 'azure_openai')
  const showParamsTab = category === 'text'
  const tabCount = 1 + (showParamsTab ? 1 : 0) + (showAdvancedTab ? 1 : 0)
  const showTabs = tabCount > 1
  
  // ========== 基本信息内容 ==========
  const basicInfoContent = (
    <>
      {/* 模型标识 */}
      <div className="space-y-4">
        <SectionTitle>{t('modelIdentity')}</SectionTitle>
        
        <div className="space-y-2">
          <Label htmlFor="name">{t('modelName')} *</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('modelNamePlaceholder')}
          />
          {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>{t('modelType')} *</Label>
            <Select value={modelType} onValueChange={handleModelTypeChange} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue>{modelType ? t(`modelTypes.${modelType}`) : t('selectModelType')}</SelectValue>
              </SelectTrigger>
              <SelectContent side="bottom" alignItemWithTrigger={false}>
                {modelTypes.map((mt) => (
                  <SelectItem key={mt.code} value={mt.code}>
                    {t(`modelTypes.${mt.code}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.modelType && <p className="text-sm text-destructive">{errors.modelType}</p>}
          </div>
          
          <div className="space-y-2">
            <Label>{t('provider')} *</Label>
            <Popover open={providerPopoverOpen} onOpenChange={setProviderPopoverOpen}>
              <PopoverTrigger
                render={(props) => (
                  <Button
                    {...props}
                    type="button"
                    variant="outline"
                    role="combobox"
                    aria-expanded={providerPopoverOpen}
                    className={cn(
                      "w-full justify-between font-normal",
                      !provider && "text-muted-foreground"
                    )}
                    disabled={isEditing || !modelType}
                  >
                    {provider ? t(`providers.${provider}`) : t('selectProvider')}
                    <svg className="ml-2 h-4 w-4 shrink-0 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </Button>
                )}
              />
              <PopoverContent className="w-[340px] p-0" align="start">
                <div className="p-3 space-y-3 max-h-[320px] overflow-y-auto">
                  {/* 国际供应商 */}
                  {groupedProviders.international.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground px-1">{t('providerGroups.international')}</div>
                      <div className="grid grid-cols-3 gap-1.5">
                        {groupedProviders.international.map((code) => (
                          <Tooltip key={code}>
                            <TooltipTrigger
                              render={(props) => (
                                <button
                                  {...props}
                                  type="button"
                                  onClick={() => {
                                    handleProviderChange(code)
                                    setProviderPopoverOpen(false)
                                  }}
                                  className={cn(
                                    "flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-sm transition-colors cursor-pointer",
                                    provider === code
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-transparent bg-muted/50 hover:bg-muted"
                                  )}
                                >
                                  {provider === code && <Check className="h-3 w-3 shrink-0" />}
                                  <span className="truncate">{t(`providers.${code}`)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {t(`providers.${code}`)}
                            </TooltipContent>
                          </Tooltip>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 国内供应商 */}
                  {groupedProviders.domestic.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground px-1">{t('providerGroups.domestic')}</div>
                      <div className="grid grid-cols-3 gap-1.5">
                        {groupedProviders.domestic.map((code) => (
                          <Tooltip key={code}>
                            <TooltipTrigger
                              render={(props) => (
                                <button
                                  {...props}
                                  type="button"
                                  onClick={() => {
                                    handleProviderChange(code)
                                    setProviderPopoverOpen(false)
                                  }}
                                  className={cn(
                                    "flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-sm transition-colors cursor-pointer",
                                    provider === code
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-transparent bg-muted/50 hover:bg-muted"
                                  )}
                                >
                                  {provider === code && <Check className="h-3 w-3 shrink-0" />}
                                  <span className="truncate">{t(`providers.${code}`)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {t(`providers.${code}`)}
                            </TooltipContent>
                          </Tooltip>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* 其他 */}
                  {groupedProviders.other.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground px-1">{t('providerGroups.other')}</div>
                      <div className="grid grid-cols-3 gap-1.5">
                        {groupedProviders.other.map((code) => (
                          <Tooltip key={code}>
                            <TooltipTrigger
                              render={(props) => (
                                <button
                                  {...props}
                                  type="button"
                                  onClick={() => {
                                    handleProviderChange(code)
                                    setProviderPopoverOpen(false)
                                  }}
                                  className={cn(
                                    "flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-sm transition-colors cursor-pointer",
                                    provider === code
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-transparent bg-muted/50 hover:bg-muted"
                                  )}
                                >
                                  {provider === code && <Check className="h-3 w-3 shrink-0" />}
                                  <span className="truncate">{t(`providers.${code}`)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {t(`providers.${code}`)}
                            </TooltipContent>
                          </Tooltip>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </PopoverContent>
            </Popover>
            {errors.provider && <p className="text-sm text-destructive">{errors.provider}</p>}
            {!modelType && <p className="text-xs text-muted-foreground">{t('selectModelTypeFirst')}</p>}
          </div>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="modelId">{t('modelId')} *</Label>
          <Input
            id="modelId"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            placeholder={t('modelIdPlaceholder')}
            disabled={isEditing}
          />
          {errors.modelId && <p className="text-sm text-destructive">{errors.modelId}</p>}
        </div>
      </div>
      
      {/* API 配置 */}
      <div className="space-y-4">
        <SectionTitle>{t('apiConfig')}</SectionTitle>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="baseUrl">{t('baseUrl')}</Label>
            <Input
              id="baseUrl"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={t('baseUrlPlaceholder')}
            />
            <p className="text-xs text-muted-foreground">{t('baseUrlHint')}</p>
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="apiKey">
              {t('apiKey')} {!isEditing && requiresApiKey(provider) && '*'}
            </Label>
            <div className="relative">
              <Input
                id="apiKey"
                type={showApiKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => { setApiKey(e.target.value); setTestResult(null) }}
                placeholder={isEditing ? t('apiKeyPlaceholderEdit') : t('apiKeyPlaceholder')}
                className="pr-10"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0 h-full px-3"
                onClick={() => setShowApiKey(!showApiKey)}
              >
                {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            {errors.apiKey && <p className="text-sm text-destructive">{errors.apiKey}</p>}
            {isEditing && model?.has_api_key && !errors.apiKey && (
              <p className="text-xs text-muted-foreground">{t('apiKeyConfigured')}</p>
            )}
          </div>
        </div>
        
        {/* 测试连接按钮和结果 */}
        <div className="flex items-center gap-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleTestConnection}
              disabled={
                isTesting ||
                !provider ||
                !modelId ||
                !modelType ||
                (requiresApiKey(provider) && !apiKey)
              }
            >
            {isTesting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Zap className="mr-2 h-4 w-4" />
            )}
            {t('testConnection')}
          </Button>
          
          {testResult && (
            <div className={`flex items-center gap-2 text-sm ${testResult.success ? 'text-green-600' : 'text-destructive'}`}>
              {testResult.success ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              <span>{testResult.message}</span>
              {testResult.latency_ms && (
                <span className="text-muted-foreground">({testResult.latency_ms}ms)</span>
              )}
            </div>
          )}
        </div>
      </div>
      
      {/* 状态 */}
      <div className="space-y-4">
        <SectionTitle>{t('status')}</SectionTitle>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
            <div className="space-y-0.5">
              <Label className="text-sm font-medium">{t('enabled')}</Label>
              <p className="text-xs text-muted-foreground">{t('enabledHint')}</p>
            </div>
            <Switch checked={isEnabled} onCheckedChange={setIsEnabled} />
          </div>
          
          <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
            <div className="space-y-0.5">
              <Label className="text-sm font-medium">{t('default')}</Label>
              <p className="text-xs text-muted-foreground">{t('defaultHint')}</p>
            </div>
            <Switch checked={isDefault} onCheckedChange={setIsDefault} />
          </div>
        </div>
      </div>
      
      {/* 图像生成参数 */}
      {category === 'image' && (
        <div className="space-y-4">
          <SectionTitle>{t('imageSettings')}</SectionTitle>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>{t('defaultImageSize')}</Label>
              <Select value={defaultImageSize} onValueChange={(v) => v && setDefaultImageSize(v)}>
                <SelectTrigger>
                  <SelectValue>{defaultImageSize || t('selectSize')}</SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="1024x1024">1024×1024</SelectItem>
                  <SelectItem value="1792x1024">1792×1024</SelectItem>
                  <SelectItem value="1024x1792">1024×1792</SelectItem>
                  <SelectItem value="512x512">512×512</SelectItem>
                  <SelectItem value="256x256">256×256</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>{t('defaultImageStyle')}</Label>
              <Select value={defaultImageStyle} onValueChange={(v) => v && setDefaultImageStyle(v)}>
                <SelectTrigger>
                  <SelectValue>{defaultImageStyle ? t(`style${defaultImageStyle.charAt(0).toUpperCase()}${defaultImageStyle.slice(1)}`) : t('selectStyle')}</SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="vivid">{t('styleVivid')}</SelectItem>
                  <SelectItem value="natural">{t('styleNatural')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label>{t('defaultImageQuality')}</Label>
              <Select value={defaultImageQuality} onValueChange={(v) => v && setDefaultImageQuality(v)}>
                <SelectTrigger>
                  <SelectValue>{defaultImageQuality ? t(`quality${defaultImageQuality.charAt(0).toUpperCase()}${defaultImageQuality.slice(1)}`) : t('selectQuality')}</SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="standard">{t('qualityStandard')}</SelectItem>
                  <SelectItem value="hd">{t('qualityHD')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      )}
      
      {/* 音频参数 */}
      {category === 'audio' && modelType === 'tts' && (
        <div className="space-y-4">
          <SectionTitle>{t('audioSettings')}</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t('defaultVoice')}</Label>
              <Select value={defaultVoice} onValueChange={(v) => v && setDefaultVoice(v)}>
                <SelectTrigger>
                  <SelectValue>{defaultVoice || t('selectVoice')}</SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="alloy">Alloy</SelectItem>
                  <SelectItem value="echo">Echo</SelectItem>
                  <SelectItem value="fable">Fable</SelectItem>
                  <SelectItem value="onyx">Onyx</SelectItem>
                  <SelectItem value="nova">Nova</SelectItem>
                  <SelectItem value="shimmer">Shimmer</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="speed">{t('defaultSpeed')}</Label>
              <Input
                id="speed"
                type="number"
                step="0.1"
                min="0.25"
                max="4"
                value={defaultSpeed}
                onChange={(e) => setDefaultSpeed(e.target.value)}
                placeholder="1.0"
              />
            </div>
          </div>
        </div>
      )}
    </>
  )
  
  // ========== 参数内容 ==========
  const paramsContent = (
    <>
      <div className="space-y-4">
        <SectionTitle>{t('contextConfig')}</SectionTitle>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="contextLength">{t('contextLength')}</Label>
            <Input
              id="contextLength"
              type="number"
              value={contextLength}
              onChange={(e) => setContextLength(e.target.value)}
              placeholder="128000"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="maxOutputTokens">{t('maxOutputTokens')}</Label>
            <Input
              id="maxOutputTokens"
              type="number"
              value={maxOutputTokens}
              onChange={(e) => setMaxOutputTokens(e.target.value)}
              placeholder="4096"
            />
          </div>
        </div>
      </div>
      
      <div className="space-y-4">
        <SectionTitle>{t('priceConfig')}</SectionTitle>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="inputPrice">{t('inputPrice')}</Label>
            <Input
              id="inputPrice"
              type="number"
              step="0.000001"
              value={inputPrice}
              onChange={(e) => setInputPrice(e.target.value)}
              placeholder="0.0"
            />
            <p className="text-xs text-muted-foreground">{t('priceUnit')}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="outputPrice">{t('outputPrice')}</Label>
            <Input
              id="outputPrice"
              type="number"
              step="0.000001"
              value={outputPrice}
              onChange={(e) => setOutputPrice(e.target.value)}
              placeholder="0.0"
            />
            <p className="text-xs text-muted-foreground">{t('priceUnit')}</p>
          </div>
        </div>
      </div>
      
      {isChatOnly(modelType) && (
        <div className="space-y-4">
          <SectionTitle>{t('inferenceParams')}</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="temperature">Temperature</Label>
              <Input
                id="temperature"
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={temperature}
                onChange={(e) => setTemperature(e.target.value)}
                placeholder="0.7"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="topP">Top P</Label>
              <Input
                id="topP"
                type="number"
                step="0.1"
                min="0"
                max="1"
                value={topP}
                onChange={(e) => setTopP(e.target.value)}
                placeholder="1.0"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="frequencyPenalty">Frequency Penalty</Label>
              <Input
                id="frequencyPenalty"
                type="number"
                step="0.1"
                min="-2"
                max="2"
                value={frequencyPenalty}
                onChange={(e) => setFrequencyPenalty(e.target.value)}
                placeholder="0"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="presencePenalty">Presence Penalty</Label>
              <Input
                id="presencePenalty"
                type="number"
                step="0.1"
                min="-2"
                max="2"
                value={presencePenalty}
                onChange={(e) => setPresencePenalty(e.target.value)}
                placeholder="0"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="maxTokens">{t('maxTokens')}</Label>
            <Input
              id="maxTokens"
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
              placeholder={t('maxTokensPlaceholder')}
            />
          </div>
        </div>
      )}
    </>
  )
  
  // ========== 高级内容 ==========
  // 支持 thinking 的供应商
  const supportsThinking = ['anthropic', 'google', 'xai', 'deepseek', 'openai'].includes(provider)
  const showReasoningEffort = provider === 'xai'
  const showThinkingBudget = ['anthropic', 'google'].includes(provider)

  const advancedContent = (
    <>
      {isChatOnly(modelType) && (
        <div className="space-y-4">
          <SectionTitle>{t('capabilities')}</SectionTitle>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('supportsVision')}</Label>
                <p className="text-xs text-muted-foreground">{t('supportsVisionHint')}</p>
              </div>
              <Switch checked={supportsVision} onCheckedChange={setSupportsVision} />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('supportsFunctionCall')}</Label>
                <p className="text-xs text-muted-foreground">{t('supportsFunctionCallHint')}</p>
              </div>
              <Switch checked={supportsFunctionCall} onCheckedChange={setSupportsFunctionCall} />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('supportsStreaming')}</Label>
                <p className="text-xs text-muted-foreground">{t('supportsStreamingHint')}</p>
              </div>
              <Switch checked={supportsStreaming} onCheckedChange={setSupportsStreaming} />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('supportsJsonMode')}</Label>
                <p className="text-xs text-muted-foreground">{t('supportsJsonModeHint')}</p>
              </div>
              <Switch checked={supportsJsonMode} onCheckedChange={setSupportsJsonMode} />
            </div>
          </div>
        </div>
      )}

      {/* Thinking/Reasoning 配置 */}
      {isChatOnly(modelType) && supportsThinking && (
        <div className="space-y-4">
          <SectionTitle>{t('thinkingConfig')}</SectionTitle>
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('thinkingEnabled')}</Label>
                <p className="text-xs text-muted-foreground">{t('thinkingEnabledHint')}</p>
              </div>
              <Switch checked={thinkingEnabled} onCheckedChange={setThinkingEnabled} />
            </div>

            {thinkingEnabled && (
              <div className="grid grid-cols-2 gap-4">
                {showThinkingBudget && (
                  <div className="space-y-2">
                    <Label htmlFor="thinkingBudget">{t('thinkingBudget')}</Label>
                    <Input
                      id="thinkingBudget"
                      type="number"
                      value={thinkingBudget}
                      onChange={(e) => setThinkingBudget(e.target.value)}
                      placeholder={t('thinkingBudgetPlaceholder')}
                    />
                    <p className="text-xs text-muted-foreground">{t('thinkingBudgetHint')}</p>
                  </div>
                )}

                {showReasoningEffort && (
                  <div className="space-y-2">
                    <Label>{t('reasoningEffort')}</Label>
                    <Select value={reasoningEffort} onValueChange={(v) => v && setReasoningEffort(v)}>
                      <SelectTrigger>
                        <SelectValue>{reasoningEffort ? t(`reasoningEffort${reasoningEffort.charAt(0).toUpperCase()}${reasoningEffort.slice(1)}`) : t('selectReasoningEffort')}</SelectValue>
                      </SelectTrigger>
                      <SelectContent side="bottom" alignItemWithTrigger={false}>
                        <SelectItem value="low">{t('reasoningEffortLow')}</SelectItem>
                        <SelectItem value="medium">{t('reasoningEffortMedium')}</SelectItem>
                        <SelectItem value="high">{t('reasoningEffortHigh')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{t('reasoningEffortHint')}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {provider === 'azure_openai' && (
        <div className="space-y-4">
          <SectionTitle>{t('azureConfig')}</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="apiVersion">{t('apiVersion')}</Label>
              <Input
                id="apiVersion"
                value={apiVersion}
                onChange={(e) => setApiVersion(e.target.value)}
                placeholder="2024-02-01"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="deploymentName">{t('deploymentName')}</Label>
              <Input
                id="deploymentName"
                value={deploymentName}
                onChange={(e) => setDeploymentName(e.target.value)}
                placeholder={t('deploymentNamePlaceholder')}
              />
            </div>
          </div>
        </div>
      )}
    </>
  )
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? t('editModel') : t('createModel')}</DialogTitle>
          <DialogDescription>
            {isEditing ? t('editModelDescription') : t('createModelDescription')}
          </DialogDescription>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="space-y-6">
          {showTabs ? (
            <Tabs defaultValue="basic" className="w-full">
              <TabsList className={`grid w-full grid-cols-${tabCount}`}>
                <TabsTrigger value="basic">{t('basicInfo')}</TabsTrigger>
                {showParamsTab && <TabsTrigger value="params">{t('parameters')}</TabsTrigger>}
                {showAdvancedTab && <TabsTrigger value="advanced">{t('advanced')}</TabsTrigger>}
              </TabsList>
              
              <TabsContent value="basic" className="space-y-6 mt-4">
                {basicInfoContent}
              </TabsContent>
              
              {showParamsTab && (
                <TabsContent value="params" className="space-y-6 mt-4">
                  {paramsContent}
                </TabsContent>
              )}
              
              {showAdvancedTab && (
                <TabsContent value="advanced" className="space-y-6 mt-4">
                  {advancedContent}
                </TabsContent>
              )}
            </Tabs>
          ) : (
            <div className="space-y-6">
              {basicInfoContent}
            </div>
          )}
          
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {commonT('cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditing ? commonT('save') : commonT('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
