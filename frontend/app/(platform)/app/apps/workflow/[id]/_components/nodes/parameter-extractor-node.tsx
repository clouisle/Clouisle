'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Braces, MoreHorizontal, Play, Bot, Code, FileJson, Type, Hash, ToggleLeft, List } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'

// 提取方式
export type ExtractionMethod = 'llm' | 'regex' | 'json_path'

// 参数类型
export type ExtractedParamType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 参数定义
export interface ExtractedParameter {
  id: string
  name: string                   // 参数名（输出键名）
  type: ExtractedParamType       // 参数类型
  description: string            // 参数描述（LLM模式用于理解语义）
  required: boolean              // 是否必填
  // 不同提取方式的配置
  pattern?: string               // 正则表达式
  jsonPath?: string              // JSON Path 表达式
  defaultValue?: string          // 默认值（提取失败时使用）
  // LLM JSON Schema 扩展字段
  enum?: string[]                // 枚举值（限制可选值）
  arrayItemType?: ExtractedParamType  // 数组元素类型
}

// 参数提取器配置
export interface ParameterExtractorConfig {
  extractionMethod: ExtractionMethod
  // 源文本
  sourceVariable: string
  sourceNodeLabel?: string
  // LLM 模式配置
  modelId?: string
  modelName?: string             // 模型名称（用于显示）
  useJsonSchema?: boolean        // 是否启用 JSON Schema（结构化输出）
  systemPrompt?: string          // 自定义系统提示词
  // 参数列表（每个参数就是一个输出变量）
  parameters: ExtractedParameter[]
}

// 默认配置
export const defaultParameterExtractorConfig: ParameterExtractorConfig = {
  extractionMethod: 'llm',
  sourceVariable: '',
  sourceNodeLabel: '',
  modelId: '',
  modelName: '',
  useJsonSchema: true,
  systemPrompt: '',
  parameters: [],
}

// 从参数列表生成 JSON Schema
export function generateJsonSchema(parameters: ExtractedParameter[]): object {
  const properties: Record<string, object> = {}
  const required: string[] = []

  for (const param of parameters) {
    const prop: Record<string, unknown> = {
      description: param.description || undefined,
    }

    switch (param.type) {
      case 'string':
        prop.type = 'string'
        if (param.enum && param.enum.length > 0) {
          prop.enum = param.enum
        }
        break
      case 'number':
        prop.type = 'number'
        break
      case 'boolean':
        prop.type = 'boolean'
        break
      case 'array':
        prop.type = 'array'
        if (param.arrayItemType) {
          prop.items = { type: param.arrayItemType }
        }
        break
      case 'object':
        prop.type = 'object'
        break
    }

    properties[param.name] = prop

    if (param.required) {
      required.push(param.name)
    }
  }

  return {
    name: 'extracted_parameters',
    strict: true,
    schema: {
      type: 'object',
      properties,
      required,
      additionalProperties: false,
    },
  }
}

// 提取方式配置（静态部分）
export const extractionMethodConfigStatic: Record<ExtractionMethod, {
  shortLabel: string
  icon: React.ComponentType<{ className?: string }>
  supportedTypes: ExtractedParamType[]  // 该方式支持的参数类型
  defaultType: ExtractedParamType       // 默认类型
  sourceVariableTypes: string[]         // 源变量支持的类型
}> = {
  llm: {
    shortLabel: 'LLM',
    icon: Bot,
    supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
    defaultType: 'string',
    sourceVariableTypes: ['String', 'Object', 'Array'],  // LLM 可处理文本和对象
  },
  regex: {
    shortLabel: 'Regex',
    icon: Code,
    supportedTypes: ['string', 'number', 'array'],
    defaultType: 'string',
    sourceVariableTypes: ['String'],  // 正则只处理文本
  },
  json_path: {
    shortLabel: 'JSON',
    icon: FileJson,
    supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
    defaultType: 'object',
    sourceVariableTypes: ['String', 'Object', 'Array'],  // JSON Path 可处理字符串、对象、数组
  },
}

// 提取方式配置（带翻译）- 用于需要翻译的场景
export function getExtractionMethodConfig(t: (key: string) => string): Record<ExtractionMethod, {
  label: string
  shortLabel: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  supportedTypes: ExtractedParamType[]
  defaultType: ExtractedParamType
  sourceVariableTypes: string[]
}> {
  return {
    llm: {
      label: t('nodesParameterExtractor.methodLlmLabel'),
      shortLabel: 'LLM',
      description: t('nodesParameterExtractor.methodLlmDesc'),
      icon: Bot,
      supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
      defaultType: 'string',
      sourceVariableTypes: ['String', 'Object', 'Array'],
    },
    regex: {
      label: t('nodesParameterExtractor.methodRegexLabel'),
      shortLabel: t('nodesParameterExtractor.methodRegexShort'),
      description: t('nodesParameterExtractor.methodRegexDesc'),
      icon: Code,
      supportedTypes: ['string', 'number', 'array'],
      defaultType: 'string',
      sourceVariableTypes: ['String'],
    },
    json_path: {
      label: 'JSON Path',
      shortLabel: 'JSON',
      description: t('nodesParameterExtractor.methodJsonPathDesc'),
      icon: FileJson,
      supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
      defaultType: 'object',
      sourceVariableTypes: ['String', 'Object', 'Array'],
    },
  }
}

// 保留旧的导出以保持向后兼容（使用静态配置）
export const extractionMethodConfig = extractionMethodConfigStatic as Record<ExtractionMethod, {
  label: string
  shortLabel: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  supportedTypes: ExtractedParamType[]
  defaultType: ExtractedParamType
  sourceVariableTypes: string[]
}>

// 参数类型配置
export const extractedParamTypeConfig: Record<ExtractedParamType, {
  label: string
  icon: React.ComponentType<{ className?: string }>
}> = {
  string: { label: 'String', icon: Type },
  number: { label: 'Number', icon: Hash },
  boolean: { label: 'Boolean', icon: ToggleLeft },
  array: { label: 'Array', icon: List },
  object: { label: 'Object', icon: Braces },
}

interface ParameterExtractorNodeData {
  type: string
  label: string
  parameterExtractorConfig?: ParameterExtractorConfig
  config: Record<string, unknown>
  [key: string]: unknown
}

interface ParameterExtractorNodeProps {
  id: string
  selected?: boolean
  data: ParameterExtractorNodeData
}

export function ParameterExtractorNode({ id, selected, data }: ParameterExtractorNodeProps) {
  const t = useTranslations('workflow')
  const config = data.parameterExtractorConfig || defaultParameterExtractorConfig
  const methodConfigMap = getExtractionMethodConfig(t)
  const methodConfig = methodConfigMap[config.extractionMethod]
  const MethodIcon = methodConfig.icon
  const parameters = config.parameters || []
  const hasParameters = parameters.length > 0

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesParameterExtractor.label')}</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background" title={t('nodesCommon.debugRun')}>
            <Play className="h-3 w-3 text-muted-foreground" />
          </button>
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>

      {/* Node Card */}
      <div
        className={cn(
          'relative flex flex-col rounded-xl border bg-card shadow-sm transition-all',
          'min-w-44 max-w-56',
          selected
            ? 'border-primary'
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white">
            <Braces className="h-3.5 w-3.5" />
          </div>

          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodesParameterExtractor.label')}
          </span>

          {/* Method badge */}
          <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <MethodIcon className="h-3 w-3" />
            <span className="text-[10px] font-medium">{methodConfig.shortLabel}</span>
          </div>
        </div>

        {/* Parameters List */}
        <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
          {hasParameters ? (
            parameters.slice(0, 3).map((param) => {
              const typeConfig = extractedParamTypeConfig[param.type]

              return (
                <div
                  key={param.id}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1.5 bg-amber-500/10"
                >
                  {/* 参数名 */}
                  <span className="text-[11px] text-foreground/80 font-medium max-w-20 truncate">
                    {param.name}
                  </span>

                  {/* 类型 */}
                  <span className="text-[10px] text-muted-foreground">
                    {typeConfig.label}
                  </span>

                  {/* 必填标记 */}
                  {param.required && (
                    <span className="text-[10px] text-amber-600 dark:text-amber-400 font-medium">
                      {t('nodesCommon.required')}
                    </span>
                  )}
                </div>
              )
            })
          ) : (
            <div className="flex items-center justify-center py-2 text-[11px] text-muted-foreground">
              {t('nodesParameterExtractor.clickToConfigure')}
            </div>
          )}

          {/* 更多指示 */}
          {parameters.length > 3 && (
            <div className="text-[10px] text-muted-foreground text-center py-0.5">
              {t('nodesParameterExtractor.moreParams', { n: parameters.length - 3 })}
            </div>
          )}
        </div>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />
      </div>
    </div>
  )
}
