'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Wrench, AlertCircle, Clock3, Calculator, Search, Globe, FolderOpen, Code2, Link, ChartColumn } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import { isPresetToolCategory, type PresetToolCategory, type ToolCategory, type ToolType } from '@/lib/api'

type WorkflowToolType = Exclude<ToolType, 'skill'>

// 分类图标
const categoryIcons: Record<PresetToolCategory, React.ReactNode> = {
  time: <Clock3 className="h-3.5 w-3.5" />,
  math: <Calculator className="h-3.5 w-3.5" />,
  search: <Search className="h-3.5 w-3.5" />,
  web: <Globe className="h-3.5 w-3.5" />,
  file: <FolderOpen className="h-3.5 w-3.5" />,
  code: <Code2 className="h-3.5 w-3.5" />,
  sandbox: <Code2 className="h-3.5 w-3.5" />,
  api: <Link className="h-3.5 w-3.5" />,
  data: <ChartColumn className="h-3.5 w-3.5" />,
  other: <Wrench className="h-3.5 w-3.5" />,
}

// 类型标签配置
const typeColors: Record<WorkflowToolType, string> = {
  builtin: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  custom: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  mcp: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
}

// 工具节点配置
export interface ToolNodeConfig {
  toolId?: string
  toolName?: string
  toolType: WorkflowToolType
  toolDisplayName?: string
  toolDescription?: string
  toolIcon?: string
  toolCategory?: ToolCategory
  // MCP 特有：服务器中的具体工具
  mcpToolName?: string
  mcpToolDescription?: string
  parameterMappings: Array<{
    name: string
    type: string
    required: boolean
    description?: string
    source: 'variable' | 'constant'
    variableRef?: string
    variableRefNodeLabel?: string
    constantValue?: string
  }>
  outputVariable: string
}

// 默认配置
export const defaultToolNodeConfig: ToolNodeConfig = {
  toolType: 'builtin',
  parameterMappings: [],
  outputVariable: 'result',
}

interface ToolNodeData {
  type: string
  label: string
  toolConfig?: ToolNodeConfig
  config: Record<string, unknown>
}

interface ToolNodeProps {
  id: string
  selected?: boolean
  data: ToolNodeData
}

export function ToolNode({ selected, data }: ToolNodeProps) {
  const t = useTranslations('workflow')

  const config = data.toolConfig || defaultToolNodeConfig
  const hasTool = !!(config.toolId || config.toolName)
  // MCP 类型需要额外选择具体的工具
  const isMcpConfigured = config.toolType !== 'mcp' || !!config.mcpToolName
  const requiredParams = config.parameterMappings.filter(p => p.required)
  const unfilledRequired = requiredParams.filter(p => 
    p.source === 'variable' ? !p.variableRef : !p.constantValue
  )

  // 获取工具名称（显示在描述上方）
  const getToolName = () => {
    if (!hasTool) return null
    if (config.toolType === 'mcp' && config.mcpToolName) {
      return config.mcpToolName
    }
    return config.toolDisplayName
  }

  // 获取描述
  const getDescription = () => {
    if (config.toolType === 'mcp') {
      if (config.mcpToolName && config.mcpToolDescription) {
        return config.mcpToolDescription
      }
      if (!config.mcpToolName && config.toolDisplayName) {
        return t('nodesTool.selectToolFrom', { name: config.toolDisplayName })
      }
    }
    return config.toolDescription
  }

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodesTool.label')}</span>
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
          <div className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-white',
            config.toolType === 'mcp' ? 'bg-violet-500' : 'bg-emerald-500'
          )}>
            {hasTool && config.toolIcon ? (
              <span className="text-sm">{config.toolIcon}</span>
            ) : hasTool && config.toolCategory && isPresetToolCategory(config.toolCategory) ? (
              <span className="text-sm">{categoryIcons[config.toolCategory]}</span>
            ) : (
              <Wrench className="h-3.5 w-3.5" />
            )}
          </div>
          
          {/* Label - 始终显示节点名称 */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodesTool.label')}
          </span>

          {/* Type badge / Warning */}
          {hasTool && isMcpConfigured ? (
            <div className={cn(
              'flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
              typeColors[config.toolType]
            )}>
              {config.toolType === 'builtin' ? t('nodesTool.typeBuiltin') : config.toolType === 'custom' ? t('nodesTool.typeCustom') : 'MCP'}
            </div>
          ) : (
            <AlertCircle className="h-4 w-4 text-amber-500" />
          )}
        </div>

        {/* Tool Info */}
        {hasTool && (
          <div className="px-2.5 pb-2 pt-0.5">
            {/* 工具名称 */}
            {getToolName() && (
              <p className={cn(
                'text-[11px] font-medium truncate mb-0.5',
                config.toolType === 'mcp' ? 'text-violet-600 dark:text-violet-400' : 'text-emerald-600 dark:text-emerald-400'
              )}>
                {getToolName()}
              </p>
            )}
            
            {/* MCP 服务器信息 */}
            {config.toolType === 'mcp' && config.mcpToolName && config.toolDisplayName && (
              <p className="text-[10px] text-muted-foreground/70 mb-0.5">
                via {config.toolDisplayName}
              </p>
            )}
            
            {/* 描述 */}
            {getDescription() && (
              <p className="text-[10px] text-muted-foreground line-clamp-1 mb-1">
                {getDescription()}
              </p>
            )}
            
            {/* 参数状态 - 仅在 MCP 配置完成后显示 */}
            {isMcpConfigured && config.parameterMappings.length > 0 && (
              <div className="flex items-center gap-1.5 text-[10px]">
                <span className="text-muted-foreground">{t('nodesTool.parameters')}</span>
                <span className={cn(
                  unfilledRequired.length > 0 ? 'text-amber-500' : 'text-emerald-500'
                )}>
                  {t('nodesTool.configured', { n: config.parameterMappings.length - unfilledRequired.length, total: config.parameterMappings.length })}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {!hasTool && (
          <div className="px-2.5 pb-2 pt-0.5">
            <p className="text-[10px] text-muted-foreground">
              {t('nodesTool.clickToConfigure')}
            </p>
          </div>
        )}

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
