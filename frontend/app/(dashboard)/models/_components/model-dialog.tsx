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
import { Textarea } from '@/components/ui/textarea'
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
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { cn } from '@/lib/utils'

import { modelsApi, type Model, type ModelCreateInput } from '@/lib/api/admin/models'
import type { ProviderInfo, ModelTypeInfo } from '@/lib/api/models'

// 供应商分组
const PROVIDER_GROUPS = {
  international: ['openai', 'anthropic', 'google', 'xai', 'azure_openai', 'runway', 'luma', 'stability'],
  domestic: ['deepseek', 'moonshot', 'zhipu', 'qwen', 'baichuan', 'minimax'],
  other: ['ollama', 'custom'],
}

const DEFAULT_IMAGE_SIZE_OPTIONS = [
  { value: '1024x1024', label: '1024×1024' },
  { value: '1792x1024', label: '1792×1024' },
  { value: '1024x1792', label: '1024×1792' },
  { value: '512x512', label: '512×512' },
  { value: '256x256', label: '256×256' },
] as const

const RUNWAY_LUMA_IMAGE_SIZE_OPTIONS = [
  { value: '1080x1080', label: '1080×1080 (1:1)' },
  { value: '1920x1080', label: '1920×1080 (16:9)' },
  { value: '1080x1920', label: '1080×1920 (9:16)' },
  { value: '1440x1080', label: '1440×1080 (4:3)' },
  { value: '1080x1440', label: '1080×1440 (3:4)' },
  { value: '2112x912', label: '2112×912 (21:9)' },
] as const

// 模型类型分类（仅包含已实现适配器的类型）
const MODEL_CATEGORIES = {
  text: ['chat', 'embedding'],
  rerank: ['rerank'],
  image: ['text_to_image'],
  video: ['text_to_video'],
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

const MANAGED_DEFAULT_PARAM_KEYS = new Set([
  'temperature',
  'top_p',
  'frequency_penalty',
  'presence_penalty',
  'max_tokens',
  'size',
  'default_width',
  'default_height',
  'style',
  'quality',
  'background',
  'output_format',
  'output_compression',
  'style_preset',
  'image_size',
  'aspect_ratio',
  'person_generation',
  'prominent_people',
  'output_mime_type',
  'output_compression_quality',
  'duration',
  'voice',
  'speed',
  'thinking',
  'reasoning_effort',
  'extra_body',
])

const MANAGED_CONFIG_KEYS = new Set([
  'api_version',
  'deployment_name',
  'thinking',
])

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function omitManagedKeys(
  source: Record<string, unknown> | null | undefined,
  managedKeys: Set<string>,
): Record<string, unknown> {
  if (!source) return {}
  return Object.fromEntries(
    Object.entries(source).filter(([key]) => !managedKeys.has(key))
  )
}

function parseJsonObject(
  value: string,
  errorMessage: string,
): { data: Record<string, unknown> | null; error?: string } {
  if (!value.trim()) {
    return { data: null }
  }

  try {
    const parsed = JSON.parse(value)
    if (!isPlainObject(parsed)) {
      return { data: null, error: errorMessage }
    }
    return { data: parsed }
  } catch {
    return { data: null, error: errorMessage }
  }
}

function parseImageSize(size: string | null | undefined): { width: number; height: number } | null {
  if (!size) return null
  const match = size.match(/^(\d+)x(\d+)$/)
  if (!match) return null
  return {
    width: parseInt(match[1], 10),
    height: parseInt(match[2], 10),
  }
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
  const getProviderName = React.useCallback((code: string) => {
    const key = `providers.${code}`
    return t.has(key) ? t(key) : code
  }, [t])
  const getModelTypeName = React.useCallback((code: string) => {
    const key = `modelTypes.${code}`
    return t.has(key) ? t(key) : code
  }, [t])
  const getReasoningEffortLabel = React.useCallback((currentProvider: string) => {
    if (currentProvider === 'openai') return t('openaiReasoningEffort')
    if (currentProvider === 'deepseek') return t('deepseekReasoningEffort')
    if (currentProvider === 'xai') return t('xaiReasoningEffort')
    return t('reasoningEffort')
  }, [t])
  const getReasoningEffortHint = React.useCallback((currentProvider: string) => {
    if (currentProvider === 'openai') return t('openaiReasoningEffortHint')
    if (currentProvider === 'deepseek') return t('deepseekReasoningEffortHint')
    if (currentProvider === 'xai') return t('xaiReasoningEffortHint')
    return t('reasoningEffortHint')
  }, [t])
  const getThinkingTitle = React.useCallback((currentProvider: string) => {
    if (currentProvider === 'anthropic') return t('anthropicThinkingConfig')
    if (currentProvider === 'google') return t('geminiThinkingConfig')
    if (currentProvider === 'deepseek') return t('deepseekThinkingConfig')
    if (currentProvider === 'moonshot') return t('moonshotThinkingConfig')
    if (currentProvider === 'ollama') return t('ollamaThinkingConfig')
    return t('thinkingConfig')
  }, [t])
  const getThinkingHint = React.useCallback((currentProvider: string) => {
    if (currentProvider === 'anthropic') return t('anthropicThinkingEnabledHint')
    if (currentProvider === 'google') return t('geminiThinkingEnabledHint')
    if (currentProvider === 'deepseek') return t('deepseekThinkingEnabledHint')
    if (currentProvider === 'moonshot') return t('moonshotThinkingEnabledHint')
    if (currentProvider === 'ollama') return t('ollamaThinkingEnabledHint')
    return t('thinkingEnabledHint')
  }, [t])

  const isEditing = !!model
  
  // 基本信息
  const [name, setName] = React.useState('')
  const [provider, setProvider] = React.useState('')
  const [modelId, setModelId] = React.useState('')
  const [modelType, setModelType] = React.useState('')
  const [baseUrl, setBaseUrl] = React.useState('')
  const [apiKey, setApiKey] = React.useState('')
  const [showApiKey, setShowApiKey] = React.useState(false)
  const reasoningEffortOptions = React.useMemo(() => {
    if (provider === 'openai') {
      return ['minimal', 'low', 'medium', 'high'] as const
    }
    if (provider === 'deepseek') {
      return ['high', 'max'] as const
    }
    return ['low', 'medium', 'high'] as const
  }, [provider])

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
  const [openaiImageBackground, setOpenaiImageBackground] = React.useState('')
  const [openaiImageOutputFormat, setOpenaiImageOutputFormat] = React.useState('')
  const [openaiImageOutputCompression, setOpenaiImageOutputCompression] = React.useState('')
  const [googleImageAspectRatio, setGoogleImageAspectRatio] = React.useState('')
  const [googleImageSize, setGoogleImageSize] = React.useState('')
  const [googlePersonGeneration, setGooglePersonGeneration] = React.useState('')
  const [googleProminentPeople, setGoogleProminentPeople] = React.useState('')
  const [googleOutputMimeType, setGoogleOutputMimeType] = React.useState('')
  const [googleOutputCompressionQuality, setGoogleOutputCompressionQuality] = React.useState('')
  const [stabilityStylePreset, setStabilityStylePreset] = React.useState('')
  const [stabilityOutputFormat, setStabilityOutputFormat] = React.useState('')

  // 视频生成参数
  const [defaultVideoDuration, setDefaultVideoDuration] = React.useState('')
  const [defaultVideoAspectRatio, setDefaultVideoAspectRatio] = React.useState('')
  
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
  const [qwenEnableSearch, setQwenEnableSearch] = React.useState(false)
  const [extraBodyText, setExtraBodyText] = React.useState('')
  const [defaultParamsExtensionText, setDefaultParamsExtensionText] = React.useState('')
  const [configExtensionText, setConfigExtensionText] = React.useState('')

  const [isLoading, setIsLoading] = React.useState(false)
  const [errors, setErrors] = React.useState<Record<string, string>>({})

  const errorPathMap = React.useMemo(() => ({
    model_id: 'modelId',
    model_type: 'modelType',
    api_key: 'apiKey',
    base_url: 'baseUrl',
    context_length: 'contextLength',
    max_output_tokens: 'maxOutputTokens',
    input_price: 'inputPrice',
    output_price: 'outputPrice',
    api_version: 'apiVersion',
    deployment_name: 'deploymentName',
    default_params: 'defaultParamsExtension',
    config: 'configExtension',
    'default_params.extra_body': 'extraBody',
    'config.api_version': 'apiVersion',
    'config.deployment_name': 'deploymentName',
  }), [])

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(errors, [
      'name',
      'provider',
      'modelId',
      'modelType',
      'baseUrl',
      'apiKey',
      'contextLength',
      'maxOutputTokens',
      'inputPrice',
      'outputPrice',
      'apiVersion',
      'deploymentName',
    ]),
    [errors]
  )

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
      const defaultImageDimensions = (
        typeof params.default_width === 'number' && typeof params.default_height === 'number'
      )
        ? `${params.default_width}x${params.default_height}`
        : ((params.size as string) || '')
      setTemperature((params.temperature as number)?.toString() || '')
      setTopP((params.top_p as number)?.toString() || '')
      setFrequencyPenalty((params.frequency_penalty as number)?.toString() || '')
      setPresencePenalty((params.presence_penalty as number)?.toString() || '')
      setMaxTokens((params.max_tokens as number)?.toString() || '')
      setDefaultImageSize(defaultImageDimensions)
      setDefaultImageStyle((params.style as string) || '')
      setDefaultImageQuality((params.quality as string) || '')
      setOpenaiImageBackground((params.background as string) || '')
      setOpenaiImageOutputFormat((params.output_format as string) || '')
      setOpenaiImageOutputCompression((params.output_compression as number)?.toString() || '')
      setGoogleImageAspectRatio((params.aspect_ratio as string) || '')
      setGoogleImageSize((params.image_size as string) || '')
      setGooglePersonGeneration((params.person_generation as string) || '')
      setGoogleProminentPeople((params.prominent_people as string) || '')
      setGoogleOutputMimeType((params.output_mime_type as string) || '')
      setGoogleOutputCompressionQuality((params.output_compression_quality as number)?.toString() || '')
      setStabilityStylePreset((params.style_preset as string) || '')
      setStabilityOutputFormat((params.output_format as string) || '')
      setDefaultVideoDuration((params.duration as number)?.toString() || '')
      setDefaultVideoAspectRatio((params.aspect_ratio as string) || '')
      setDefaultVoice((params.voice as string) || '')
      setDefaultSpeed((params.speed as number)?.toString() || '')
      setReasoningEffort(
        (params.reasoning_effort as string)
        || ((params.thinking as Record<string, unknown> | undefined)?.effort as string)
        || ((params.thinking as Record<string, unknown> | undefined)?.reasoning_effort as string)
        || ''
      )
      setQwenEnableSearch(!!params.enable_search)
      setExtraBodyText(
        params.extra_body && isPlainObject(params.extra_body)
          ? JSON.stringify(params.extra_body, null, 2)
          : ''
      )
      setDefaultParamsExtensionText(
        JSON.stringify(omitManagedKeys(params, MANAGED_DEFAULT_PARAM_KEYS), null, 2)
      )

      const caps = model.capabilities || {}
      setSupportsVision(!!caps.vision)
      setSupportsFunctionCall(!!caps.function_call)
      setSupportsStreaming(caps.streaming !== false)
      setSupportsJsonMode(!!caps.json_mode)
      
      const config = model.config || {}
      setApiVersion((config.api_version as string) || '')
      setDeploymentName((config.deployment_name as string) || '')
      setConfigExtensionText(
        JSON.stringify(omitManagedKeys(config, MANAGED_CONFIG_KEYS), null, 2)
      )

      // Thinking 配置
      const thinking = (params.thinking ?? config.thinking) as Record<string, unknown> | boolean | undefined
      if (typeof thinking === 'boolean') {
        setThinkingEnabled(thinking)
        setThinkingBudget('')
      } else if (thinking && typeof thinking === 'object') {
        setThinkingEnabled(thinking.enabled !== false)
        setThinkingBudget((thinking.budget_tokens as number)?.toString() || (thinking.budget as number)?.toString() || '')
      } else {
        setThinkingEnabled(false)
        setThinkingBudget('')
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
      setOpenaiImageBackground('')
      setOpenaiImageOutputFormat('')
      setOpenaiImageOutputCompression('')
      setGoogleImageAspectRatio('')
      setGoogleImageSize('')
      setGooglePersonGeneration('')
      setGoogleProminentPeople('')
      setGoogleOutputMimeType('')
      setGoogleOutputCompressionQuality('')
      setStabilityStylePreset('')
      setStabilityOutputFormat('')
      setDefaultVideoDuration('')
      setDefaultVideoAspectRatio('')
      setDefaultVoice('')
      setDefaultSpeed('')
      setApiVersion('')
      setDeploymentName('')
      setThinkingEnabled(false)
      setThinkingBudget('')
      setReasoningEffort('')
      setQwenEnableSearch(false)
      setExtraBodyText('')
      setDefaultParamsExtensionText('')
      setConfigExtensionText('')
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
    const newErrors: Record<string, string> = {}
    if (!provider) newErrors.provider = t('providerRequired')
    if (!modelId.trim()) newErrors.modelId = t('modelIdRequired')
    if (!modelType) newErrors.modelType = t('modelTypeRequired')
    if (requiresApiKey(provider) && !apiKey.trim()) {
      newErrors.apiKey = t('apiKeyRequired')
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors((prev) => ({ ...prev, ...newErrors }))
      setTestResult(null)
      return
    }

    const extraBodyResult = parseJsonObject(extraBodyText, commonT('invalidJSON'))
    const defaultParamsExtensionResult = parseJsonObject(defaultParamsExtensionText, commonT('invalidJSON'))
    const configExtensionResult = parseJsonObject(configExtensionText, commonT('invalidJSON'))

    if (extraBodyResult.error || defaultParamsExtensionResult.error || configExtensionResult.error) {
      setErrors((prev) => ({
        ...prev,
        ...(extraBodyResult.error ? { extraBody: extraBodyResult.error } : {}),
        ...(defaultParamsExtensionResult.error ? { defaultParamsExtension: defaultParamsExtensionResult.error } : {}),
        ...(configExtensionResult.error ? { configExtension: configExtensionResult.error } : {}),
      }))
      setTestResult(null)
      return
    }

    setIsTesting(true)
    setTestResult(null)

    try {
      const defaultParams: Record<string, unknown> = {
        ...(defaultParamsExtensionResult.data || {}),
      }
      const category = getModelCategory(modelType)
      const config: Record<string, unknown> = {
        ...(configExtensionResult.data || {}),
      }

      if (temperature) defaultParams.temperature = parseFloat(temperature)
      if (topP) defaultParams.top_p = parseFloat(topP)
      if (frequencyPenalty) defaultParams.frequency_penalty = parseFloat(frequencyPenalty)
      if (presencePenalty) defaultParams.presence_penalty = parseFloat(presencePenalty)
      if (maxTokens) defaultParams.max_tokens = parseInt(maxTokens)
      if (category === 'image') {
        const parsedImageSize = parseImageSize(defaultImageSize)
        if (parsedImageSize) {
          defaultParams.default_width = parsedImageSize.width
          defaultParams.default_height = parsedImageSize.height
        }
        if (defaultImageStyle) defaultParams.style = defaultImageStyle
        if (defaultImageQuality) defaultParams.quality = defaultImageQuality
        if (isOpenAIImageProvider) {
          if (openaiImageBackground) defaultParams.background = openaiImageBackground
          if (openaiImageOutputFormat) defaultParams.output_format = openaiImageOutputFormat
          if (openaiImageOutputCompression) defaultParams.output_compression = parseInt(openaiImageOutputCompression)
        }
        if (isGoogleImageProvider) {
          if (googleImageAspectRatio) defaultParams.aspect_ratio = googleImageAspectRatio
          if (googleImageSize) defaultParams.image_size = googleImageSize
          if (googlePersonGeneration) defaultParams.person_generation = googlePersonGeneration
          if (googleProminentPeople) defaultParams.prominent_people = googleProminentPeople
          if (googleOutputMimeType) defaultParams.output_mime_type = googleOutputMimeType
          if (googleOutputCompressionQuality) defaultParams.output_compression_quality = parseInt(googleOutputCompressionQuality)
        }
        if (isStabilityImageProvider) {
          if (stabilityStylePreset) defaultParams.style_preset = stabilityStylePreset
          if (stabilityOutputFormat) defaultParams.output_format = stabilityOutputFormat
        }
      }
      if (showReasoningEffort && reasoningEffort) defaultParams.reasoning_effort = reasoningEffort
      if (provider === 'qwen' && qwenEnableSearch) defaultParams.enable_search = true
      if (showExtraBody && extraBodyResult.data) defaultParams.extra_body = extraBodyResult.data
      if (apiVersion) config.api_version = apiVersion
      if (deploymentName) config.deployment_name = deploymentName
      if (supportsThinking) {
        const thinkingConfig: Record<string, unknown> = { enabled: thinkingEnabled }
        if (thinkingEnabled && thinkingBudget) thinkingConfig.budget_tokens = parseInt(thinkingBudget)
        config.thinking = thinkingConfig
      }

      const result = await modelsApi.testModelConfig({
        provider,
        model_id: modelId.trim(),
        model_type: modelType,
        base_url: baseUrl.trim() || null,
        api_key: apiKey || null,
        default_params: Object.keys(defaultParams).length > 0 ? defaultParams : null,
        config: Object.keys(config).length > 0 ? config : null,
      })

      setTestResult({
        ...result,
        message: result.message ? result.message.trim() : t('testFailed'),
      })

      if (result.success) {
        toast.success(t('testSuccess'))
      } else {
        toast.error(result.message ? result.message.trim() : t('testFailed'))
      }
    } catch (error) {
      const validationErrors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(validationErrors).length > 0) {
        setErrors((prev) => ({ ...prev, ...validationErrors }))
      }
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
    setErrors((prev) => clearValidationError(prev, 'provider'))
    setTestResult(null)
    if (!baseUrl) {
      const providerInfo = providers.find(p => p.code === value)
      if (providerInfo?.base_url) setBaseUrl(providerInfo.base_url)
    }
  }
  
  const handleModelTypeChange = (value: string | null) => {
    if (value) {
      setModelType(value)
      setErrors((prev) => clearValidationError(prev, 'modelType'))
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
      image: ['openai', 'google', 'azure_openai', 'custom', 'siliconflow', 'runway', 'luma', 'stability'],
      video: ['runway', 'luma'],
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
    
    const extraBodyResult = parseJsonObject(extraBodyText, commonT('invalidJSON'))
    const defaultParamsExtensionResult = parseJsonObject(defaultParamsExtensionText, commonT('invalidJSON'))
    const configExtensionResult = parseJsonObject(configExtensionText, commonT('invalidJSON'))

    if (extraBodyResult.error) newErrors.extraBody = extraBodyResult.error
    if (defaultParamsExtensionResult.error) newErrors.defaultParamsExtension = defaultParamsExtensionResult.error
    if (configExtensionResult.error) newErrors.configExtension = configExtensionResult.error

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setIsLoading(true)

    try {
      const defaultParams: Record<string, unknown> = {
        ...(defaultParamsExtensionResult.data || {}),
      }
      const category = getModelCategory(modelType)

      if (category === 'text') {
        if (temperature) defaultParams.temperature = parseFloat(temperature)
        if (topP) defaultParams.top_p = parseFloat(topP)
        if (frequencyPenalty) defaultParams.frequency_penalty = parseFloat(frequencyPenalty)
        if (presencePenalty) defaultParams.presence_penalty = parseFloat(presencePenalty)
        if (maxTokens) defaultParams.max_tokens = parseInt(maxTokens)
      } else if (category === 'image') {
        const parsedImageSize = parseImageSize(defaultImageSize)
        if (parsedImageSize) {
          defaultParams.default_width = parsedImageSize.width
          defaultParams.default_height = parsedImageSize.height
        }
        if (defaultImageStyle) defaultParams.style = defaultImageStyle
        if (defaultImageQuality) defaultParams.quality = defaultImageQuality
        if (isOpenAIImageProvider) {
          if (openaiImageBackground) defaultParams.background = openaiImageBackground
          if (openaiImageOutputFormat) defaultParams.output_format = openaiImageOutputFormat
          if (openaiImageOutputCompression) defaultParams.output_compression = parseInt(openaiImageOutputCompression)
        }
        if (isGoogleImageProvider) {
          if (googleImageAspectRatio) defaultParams.aspect_ratio = googleImageAspectRatio
          if (googleImageSize) defaultParams.image_size = googleImageSize
          if (googlePersonGeneration) defaultParams.person_generation = googlePersonGeneration
          if (googleProminentPeople) defaultParams.prominent_people = googleProminentPeople
          if (googleOutputMimeType) defaultParams.output_mime_type = googleOutputMimeType
          if (googleOutputCompressionQuality) defaultParams.output_compression_quality = parseInt(googleOutputCompressionQuality)
        }
        if (isStabilityImageProvider) {
          if (stabilityStylePreset) defaultParams.style_preset = stabilityStylePreset
          if (stabilityOutputFormat) defaultParams.output_format = stabilityOutputFormat
        }
      } else if (category === 'video') {
        if (defaultVideoDuration) defaultParams.duration = parseFloat(defaultVideoDuration)
        if (defaultVideoAspectRatio) defaultParams.aspect_ratio = defaultVideoAspectRatio
      } else if (category === 'audio') {
        if (defaultVoice) defaultParams.voice = defaultVoice
        if (defaultSpeed) defaultParams.speed = parseFloat(defaultSpeed)
      }
      if (showReasoningEffort && reasoningEffort) defaultParams.reasoning_effort = reasoningEffort
      if (provider === 'qwen' && qwenEnableSearch) defaultParams.enable_search = true
      if (showExtraBody && extraBodyResult.data) defaultParams.extra_body = extraBodyResult.data

      let capabilities: Record<string, boolean> | null = null
      if (modelType === 'chat') {
        capabilities = {}
        if (supportsVision) capabilities.vision = true
        if (supportsFunctionCall) capabilities.function_call = true
        if (!supportsStreaming) capabilities.streaming = false
        if (supportsJsonMode) capabilities.json_mode = true
        if (Object.keys(capabilities).length === 0) capabilities = null
      }

      const config: Record<string, unknown> = {
        ...(configExtensionResult.data || {}),
      }
      if (apiVersion) config.api_version = apiVersion
      if (deploymentName) config.deployment_name = deploymentName

      // Thinking 配置
      if (supportsThinking) {
        const thinkingConfig: Record<string, unknown> = { enabled: thinkingEnabled }
        if (thinkingEnabled && thinkingBudget) thinkingConfig.budget_tokens = parseInt(thinkingBudget)
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
    } catch (error) {
      const validationErrors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors)
      }
    } finally {
      setIsLoading(false)
    }
  }
  
  const category = modelType ? getModelCategory(modelType) : null
  const showAdvancedTab = modelType && (isChatOnly(modelType) || provider === 'azure_openai')
  const showParamsTab = category === 'text'
  const tabCount = 1 + (showParamsTab ? 1 : 0) + (showAdvancedTab ? 1 : 0)
  const showTabs = tabCount > 1
  const showReasoningEffort = ['openai', 'xai', 'deepseek', 'volcengine', 'siliconflow'].includes(provider)
  const showThinkingBudget = ['anthropic', 'google'].includes(provider)
  const showExtraBody = ['openai', 'anthropic', 'xai'].includes(provider)
  const isOpenAIImageProvider = ['openai', 'azure_openai', 'custom', 'siliconflow'].includes(provider)
  const isGoogleImageProvider = provider === 'google'
  const isStabilityImageProvider = provider === 'stability'
  const isRunwayOrLumaImageProvider = ['runway', 'luma'].includes(provider)
  const imageSizeOptions = isRunwayOrLumaImageProvider
    ? RUNWAY_LUMA_IMAGE_SIZE_OPTIONS
    : DEFAULT_IMAGE_SIZE_OPTIONS
  
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
            onChange={(e) => {
              setName(e.target.value)
              setErrors((prev) => clearValidationError(prev, 'name'))
            }}
            placeholder={t('modelNamePlaceholder')}
            aria-invalid={!!errors.name}
          />
          <FieldError>{errors.name}</FieldError>
        </div>
        
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>{t('modelType')} *</Label>
            <Select value={modelType} onValueChange={handleModelTypeChange} disabled={isEditing}>
              <SelectTrigger aria-invalid={!!errors.modelType}>
                <SelectValue>{modelType ? getModelTypeName(modelType) : t('selectModelType')}</SelectValue>
              </SelectTrigger>
              <SelectContent side="bottom" alignItemWithTrigger={false}>
                {modelTypes.map((mt) => (
                  <SelectItem key={mt.code} value={mt.code}>
                    {getModelTypeName(mt.code)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldError>{errors.modelType}</FieldError>
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
                    {provider ? getProviderName(provider) : t('selectProvider')}
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
                                  <span className="truncate">{getProviderName(code)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {getProviderName(code)}
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
                                  <span className="truncate">{getProviderName(code)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {getProviderName(code)}
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
                                  <span className="truncate">{getProviderName(code)}</span>
                                </button>
                              )}
                            />
                            <TooltipContent side="bottom">
                              {getProviderName(code)}
                            </TooltipContent>
                          </Tooltip>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </PopoverContent>
            </Popover>
            <FieldError>{errors.provider}</FieldError>
            {!modelType && <p className="text-xs text-muted-foreground">{t('selectModelTypeFirst')}</p>}
          </div>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="modelId">{t('modelId')} *</Label>
          <Input
            id="modelId"
            value={modelId}
            onChange={(e) => {
              setModelId(e.target.value)
              setErrors((prev) => clearValidationError(prev, 'modelId'))
            }}
            placeholder={t('modelIdPlaceholder')}
            disabled={isEditing}
            aria-invalid={!!errors.modelId}
          />
          <FieldError>{errors.modelId}</FieldError>
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
              onChange={(e) => {
                setBaseUrl(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'baseUrl'))
              }}
              placeholder={t('baseUrlPlaceholder')}
              aria-invalid={!!errors.baseUrl}
            />
            <FieldError>{errors.baseUrl}</FieldError>
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
                onChange={(e) => {
                  setApiKey(e.target.value)
                  setErrors((prev) => clearValidationError(prev, 'apiKey'))
                  setTestResult(null)
                }}
                placeholder={isEditing ? t('apiKeyPlaceholderEdit') : t('apiKeyPlaceholder')}
                className="pr-10"
                aria-invalid={!!errors.apiKey}
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
            <FieldError>{errors.apiKey}</FieldError>
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
                  {imageSizeOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
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
                  <SelectItem value="low">{t('qualityLow')}</SelectItem>
                  <SelectItem value="medium">{t('qualityMedium')}</SelectItem>
                  <SelectItem value="high">{t('qualityHigh')}</SelectItem>
                  <SelectItem value="auto">{t('qualityAuto')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {isOpenAIImageProvider && (
            <div className="space-y-4">
              <SectionTitle>{t('openaiImageSettings')}</SectionTitle>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>{t('imageBackground')}</Label>
                  <Select value={openaiImageBackground} onValueChange={(v) => v && setOpenaiImageBackground(v)}>
                    <SelectTrigger>
                      <SelectValue>{openaiImageBackground || t('selectImageBackground')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="transparent">{t('imageBackgroundTransparent')}</SelectItem>
                      <SelectItem value="opaque">{t('imageBackgroundOpaque')}</SelectItem>
                      <SelectItem value="auto">{t('imageBackgroundAuto')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('imageOutputFormat')}</Label>
                  <Select value={openaiImageOutputFormat} onValueChange={(v) => v && setOpenaiImageOutputFormat(v)}>
                    <SelectTrigger>
                      <SelectValue>{openaiImageOutputFormat || t('selectOutputFormat')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="png">PNG</SelectItem>
                      <SelectItem value="jpeg">JPEG</SelectItem>
                      <SelectItem value="webp">WebP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="openaiImageOutputCompression">{t('imageOutputCompression')}</Label>
                  <Input
                    id="openaiImageOutputCompression"
                    type="number"
                    min="0"
                    max="100"
                    value={openaiImageOutputCompression}
                    onChange={(e) => setOpenaiImageOutputCompression(e.target.value)}
                    placeholder="100"
                  />
                </div>
              </div>
            </div>
          )}

          {isGoogleImageProvider && (
            <div className="space-y-4">
              <SectionTitle>{t('googleImageSettings')}</SectionTitle>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>{t('defaultGoogleAspectRatio')}</Label>
                  <Select value={googleImageAspectRatio} onValueChange={(v) => v && setGoogleImageAspectRatio(v)}>
                    <SelectTrigger>
                      <SelectValue>{googleImageAspectRatio || t('selectAspectRatio')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="21:9">21:9</SelectItem>
                      <SelectItem value="16:9">16:9</SelectItem>
                      <SelectItem value="4:3">4:3</SelectItem>
                      <SelectItem value="3:2">3:2</SelectItem>
                      <SelectItem value="1:1">1:1</SelectItem>
                      <SelectItem value="2:3">2:3</SelectItem>
                      <SelectItem value="3:4">3:4</SelectItem>
                      <SelectItem value="9:16">9:16</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('defaultGoogleImageSize')}</Label>
                  <Select value={googleImageSize} onValueChange={(v) => v && setGoogleImageSize(v)}>
                    <SelectTrigger>
                      <SelectValue>{googleImageSize || t('selectGoogleImageSize')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="1K">1K</SelectItem>
                      <SelectItem value="2K">2K</SelectItem>
                      <SelectItem value="4K">4K</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('googlePersonGeneration')}</Label>
                  <Select value={googlePersonGeneration} onValueChange={(v) => v && setGooglePersonGeneration(v)}>
                    <SelectTrigger>
                      <SelectValue>{googlePersonGeneration || t('selectGooglePersonGeneration')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="ALLOW_ALL">{t('googlePersonGenerationAllowAll')}</SelectItem>
                      <SelectItem value="ALLOW_ADULT">{t('googlePersonGenerationAllowAdult')}</SelectItem>
                      <SelectItem value="DONT_ALLOW">{t('googlePersonGenerationDontAllow')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('googleProminentPeople')}</Label>
                  <Select value={googleProminentPeople} onValueChange={(v) => v && setGoogleProminentPeople(v)}>
                    <SelectTrigger>
                      <SelectValue>{googleProminentPeople || t('selectGoogleProminentPeople')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="ALLOW_ALL">{t('googleProminentPeopleAllowAll')}</SelectItem>
                      <SelectItem value="ALLOW_ADULT">{t('googleProminentPeopleAllowAdult')}</SelectItem>
                      <SelectItem value="DONT_ALLOW">{t('googleProminentPeopleDontAllow')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('googleOutputMimeType')}</Label>
                  <Select value={googleOutputMimeType} onValueChange={(v) => v && setGoogleOutputMimeType(v)}>
                    <SelectTrigger>
                      <SelectValue>{googleOutputMimeType || t('selectGoogleOutputMimeType')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="image/png">PNG</SelectItem>
                      <SelectItem value="image/jpeg">JPEG</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="googleOutputCompressionQuality">{t('googleOutputCompressionQuality')}</Label>
                  <Input
                    id="googleOutputCompressionQuality"
                    type="number"
                    min="0"
                    max="100"
                    value={googleOutputCompressionQuality}
                    onChange={(e) => setGoogleOutputCompressionQuality(e.target.value)}
                    placeholder="90"
                  />
                </div>
              </div>
            </div>
          )}

          {isStabilityImageProvider && (
            <div className="space-y-4">
              <SectionTitle>{t('stabilityImageSettings')}</SectionTitle>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>{t('stabilityStylePreset')}</Label>
                  <Select value={stabilityStylePreset} onValueChange={(v) => v && setStabilityStylePreset(v)}>
                    <SelectTrigger>
                      <SelectValue>{stabilityStylePreset || t('selectStabilityStylePreset')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="3d-model">3D Model</SelectItem>
                      <SelectItem value="analog-film">Analog Film</SelectItem>
                      <SelectItem value="anime">Anime</SelectItem>
                      <SelectItem value="cinematic">Cinematic</SelectItem>
                      <SelectItem value="comic-book">Comic Book</SelectItem>
                      <SelectItem value="digital-art">Digital Art</SelectItem>
                      <SelectItem value="enhance">Enhance</SelectItem>
                      <SelectItem value="fantasy-art">Fantasy Art</SelectItem>
                      <SelectItem value="isometric">Isometric</SelectItem>
                      <SelectItem value="line-art">Line Art</SelectItem>
                      <SelectItem value="low-poly">Low Poly</SelectItem>
                      <SelectItem value="modeling-compound">Modeling Compound</SelectItem>
                      <SelectItem value="neon-punk">Neon Punk</SelectItem>
                      <SelectItem value="origami">Origami</SelectItem>
                      <SelectItem value="photographic">Photographic</SelectItem>
                      <SelectItem value="pixel-art">Pixel Art</SelectItem>
                      <SelectItem value="tile-texture">Tile Texture</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('imageOutputFormat')}</Label>
                  <Select value={stabilityOutputFormat} onValueChange={(v) => v && setStabilityOutputFormat(v)}>
                    <SelectTrigger>
                      <SelectValue>{stabilityOutputFormat || t('selectOutputFormat')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      <SelectItem value="png">PNG</SelectItem>
                      <SelectItem value="jpeg">JPEG</SelectItem>
                      <SelectItem value="webp">WebP</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 视频生成参数 */}
      {category === 'video' && (
        <div className="space-y-4">
          <SectionTitle>{t('videoSettings')}</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="videoDuration">{t('defaultVideoDuration')}</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="videoDuration"
                  type="number"
                  step="1"
                  min="1"
                  max="30"
                  value={defaultVideoDuration}
                  onChange={(e) => setDefaultVideoDuration(e.target.value)}
                  placeholder="5"
                />
                <span className="text-sm text-muted-foreground whitespace-nowrap">
                  {t('videoDurationUnit')}
                </span>
              </div>
            </div>

            <div className="space-y-2">
              <Label>{t('defaultVideoAspectRatio')}</Label>
              <Select
                value={defaultVideoAspectRatio}
                onValueChange={(v) => v && setDefaultVideoAspectRatio(v)}
              >
                <SelectTrigger>
                  <SelectValue>
                    {defaultVideoAspectRatio || t('selectAspectRatio')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent side="bottom" alignItemWithTrigger={false}>
                  <SelectItem value="16:9">16:9</SelectItem>
                  <SelectItem value="9:16">9:16</SelectItem>
                  <SelectItem value="1:1">1:1</SelectItem>
                  <SelectItem value="4:3">4:3</SelectItem>
                  <SelectItem value="3:4">3:4</SelectItem>
                  <SelectItem value="21:9">21:9</SelectItem>
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
              onChange={(e) => {
                setContextLength(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'contextLength'))
              }}
              placeholder="128000"
              aria-invalid={!!errors.contextLength}
            />
            <FieldError>{errors.contextLength}</FieldError>
          </div>
          <div className="space-y-2">
            <Label htmlFor="maxOutputTokens">{t('maxOutputTokens')}</Label>
            <Input
              id="maxOutputTokens"
              type="number"
              value={maxOutputTokens}
              onChange={(e) => {
                setMaxOutputTokens(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'maxOutputTokens'))
              }}
              placeholder="4096"
              aria-invalid={!!errors.maxOutputTokens}
            />
            <FieldError>{errors.maxOutputTokens}</FieldError>
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
              onChange={(e) => {
                setInputPrice(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'inputPrice'))
              }}
              placeholder="0.0"
              aria-invalid={!!errors.inputPrice}
            />
            <FieldError>{errors.inputPrice}</FieldError>
            <p className="text-xs text-muted-foreground">{t('priceUnit')}</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="outputPrice">{t('outputPrice')}</Label>
            <Input
              id="outputPrice"
              type="number"
              step="0.000001"
              value={outputPrice}
              onChange={(e) => {
                setOutputPrice(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'outputPrice'))
              }}
              placeholder="0.0"
              aria-invalid={!!errors.outputPrice}
            />
            <FieldError>{errors.outputPrice}</FieldError>
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

          {(showReasoningEffort || provider === 'qwen' || showExtraBody) && (
            <div className="grid grid-cols-2 gap-4">
              {showReasoningEffort && (
                <div className="space-y-2">
                  <Label>{getReasoningEffortLabel(provider)}</Label>
                  <Select value={reasoningEffort} onValueChange={(v) => v && setReasoningEffort(v)}>
                    <SelectTrigger>
                      <SelectValue>{reasoningEffort ? t(`reasoningEffort${reasoningEffort.charAt(0).toUpperCase()}${reasoningEffort.slice(1)}`) : t('selectReasoningEffort')}</SelectValue>
                    </SelectTrigger>
                    <SelectContent side="bottom" alignItemWithTrigger={false}>
                      {reasoningEffortOptions.map((option) => (
                        <SelectItem key={option} value={option}>{t(`reasoningEffort${option.charAt(0).toUpperCase()}${option.slice(1)}`)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">{getReasoningEffortHint(provider)}</p>
                </div>
              )}

              {provider === 'qwen' && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="qwenEnableSearch">{t('qwenEnableSearch')}</Label>
                    <Switch
                      id="qwenEnableSearch"
                      checked={qwenEnableSearch}
                      onCheckedChange={setQwenEnableSearch}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{t('qwenEnableSearchHint')}</p>
                </div>
              )}

              {showExtraBody && (
                <div className="space-y-2 col-span-2">
                  <Label htmlFor="extraBody">{t('extraBody')}</Label>
                  <Textarea
                    id="extraBody"
                    value={extraBodyText}
                    onChange={(e) => {
                      setExtraBodyText(e.target.value)
                      setErrors((prev) => clearValidationError(prev, 'extraBody'))
                    }}
                    placeholder={`{
  "thinking": {
    "type": "enabled"
  }
}`}
                    className="font-mono text-sm"
                    rows={6}
                    aria-invalid={!!errors.extraBody}
                  />
                  <FieldError>{errors.extraBody}</FieldError>
                  <p className="text-xs text-muted-foreground">{t('extraBodyHint')}</p>
                </div>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="defaultParamsExtension">{t('defaultParamsExtension')}</Label>
            <Textarea
              id="defaultParamsExtension"
              value={defaultParamsExtensionText}
              onChange={(e) => {
                setDefaultParamsExtensionText(e.target.value)
                setErrors((prev) => clearValidationError(prev, 'defaultParamsExtension'))
              }}
              placeholder="{}"
              className="font-mono text-sm"
              rows={6}
              aria-invalid={!!errors.defaultParamsExtension}
            />
            <FieldError>{errors.defaultParamsExtension}</FieldError>
            <p className="text-xs text-muted-foreground">{t('defaultParamsExtensionHint')}</p>
          </div>
        </div>
      )}
    </>
  )
  
  // ========== 高级内容 ==========
  // 支持 thinking 的供应商
  const supportsThinking = ['anthropic', 'google', 'deepseek', 'zhipu', 'moonshot', 'ollama'].includes(provider)

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
          <SectionTitle>{getThinkingTitle(provider)}</SectionTitle>
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
              <div className="space-y-0.5">
                <Label className="text-sm font-medium">{t('thinkingEnabled')}</Label>
                <p className="text-xs text-muted-foreground">{getThinkingHint(provider)}</p>
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
                onChange={(e) => {
                  setApiVersion(e.target.value)
                  setErrors((prev) => clearValidationError(prev, 'apiVersion'))
                }}
                placeholder="2024-02-01"
                aria-invalid={!!errors.apiVersion}
              />
              <FieldError>{errors.apiVersion}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="deploymentName">{t('deploymentName')}</Label>
              <Input
                id="deploymentName"
                value={deploymentName}
                onChange={(e) => {
                  setDeploymentName(e.target.value)
                  setErrors((prev) => clearValidationError(prev, 'deploymentName'))
                }}
                placeholder={t('deploymentNamePlaceholder')}
                aria-invalid={!!errors.deploymentName}
              />
              <FieldError>{errors.deploymentName}</FieldError>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <Label htmlFor="configExtension">{t('configExtension')}</Label>
        <Textarea
          id="configExtension"
          value={configExtensionText}
          onChange={(e) => {
            setConfigExtensionText(e.target.value)
            setErrors((prev) => clearValidationError(prev, 'configExtension'))
          }}
          placeholder="{}"
          className="font-mono text-sm"
          rows={6}
          aria-invalid={!!errors.configExtension}
        />
        <FieldError>{errors.configExtension}</FieldError>
        <p className="text-xs text-muted-foreground">{t('configExtensionHint')}</p>
      </div>
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
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}

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
              {category === 'image' && (
                <div className="space-y-2">
                  <Label htmlFor="defaultParamsExtensionImage">{t('defaultParamsExtension')}</Label>
                  <Textarea
                    id="defaultParamsExtensionImage"
                    value={defaultParamsExtensionText}
                    onChange={(e) => {
                      setDefaultParamsExtensionText(e.target.value)
                      setErrors((prev) => clearValidationError(prev, 'defaultParamsExtension'))
                    }}
                    placeholder="{}"
                    className="font-mono text-sm"
                    rows={6}
                    aria-invalid={!!errors.defaultParamsExtension}
                  />
                  <FieldError>{errors.defaultParamsExtension}</FieldError>
                  <p className="text-xs text-muted-foreground">{t('defaultParamsExtensionHint')}</p>
                </div>
              )}
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
