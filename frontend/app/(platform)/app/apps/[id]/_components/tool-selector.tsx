'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Plus,
  Wrench,
  Trash2,
  AlertCircle,
  Search,
  Check,
  Clock3,
  Calculator,
  Globe,
  FolderOpen,
  Code2,
  Link,
  ChartColumn,
} from 'lucide-react'
import { type Skill, type Tool, type ToolConfig, type ToolCategory, type ToolParameter, type ToolType, toolsApi, skillsApi } from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

// 分类图标和颜色映射
const categoryConfig: Record<ToolCategory, { icon: React.ReactNode; color: string }> = {
  time: {
    icon: <Clock3 className="h-4 w-4" />,
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  },
  math: {
    icon: <Calculator className="h-4 w-4" />,
    color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  },
  search: {
    icon: <Search className="h-4 w-4" />,
    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  },
  web: {
    icon: <Globe className="h-4 w-4" />,
    color: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
  },
  file: {
    icon: <FolderOpen className="h-4 w-4" />,
    color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  },
  code: {
    icon: <Code2 className="h-4 w-4" />,
    color: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
  },
  api: {
    icon: <Link className="h-4 w-4" />,
    color: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
  },
  data: {
    icon: <ChartColumn className="h-4 w-4" />,
    color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300',
  },
  other: {
    icon: <Wrench className="h-4 w-4" />,
    color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
  },
}

// 类型标签配置
const typeConfig: Record<ToolType, { color: string }> = {
  builtin: {
    color: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300',
  },
  custom: {
    color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300',
  },
  mcp: {
    color: 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-300',
  },
  skill: {
    color: 'bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-300',
  },
}

interface AddToolButtonProps {
  availableTools: Tool[]
  selectedToolNames: string[]  // for builtin tools
  selectedToolIds: (string | undefined)[]  // for custom tools
  selectedMcpServerIds: (string | undefined)[]  // for mcp tools
  selectedSkillIds: (string | undefined)[]  // for skills
  onAdd: (tool: Tool) => void
  onRemove: (tool: Tool) => void
}

export function AddToolButton({ availableTools, selectedToolNames, selectedToolIds, selectedMcpServerIds, selectedSkillIds, onAdd, onRemove }: AddToolButtonProps) {
  const t = useTranslations('agents.orchestration.tools')
  const typeLabels: Record<ToolType, string> = {
    builtin: t('dialog.filters.builtin'),
    custom: t('dialog.filters.custom'),
    mcp: t('dialog.filters.mcp'),
    skill: t('dialog.filters.skill'),
  }
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState('')
  const [filter, setFilter] = React.useState<'all' | ToolType>('all')

  // 过滤工具
  const filteredTools = React.useMemo(() => {
    let tools = availableTools

    // 搜索过滤
    if (search) {
      const query = search.toLowerCase()
      tools = tools.filter(
        (tool) =>
          tool.name.toLowerCase().includes(query) ||
          tool.display_name.toLowerCase().includes(query) ||
          tool.description.toLowerCase().includes(query)
      )
    }

    // 类型过滤
    if (filter !== 'all') {
      tools = tools.filter((tool) => tool.type === filter)
    }

    return tools
  }, [availableTools, search, filter])

  // 按分类分组
  const groupedTools = React.useMemo(() => {
    const groups: Record<string, Tool[]> = {}
    filteredTools.forEach((tool) => {
      const category = tool.category
      if (!groups[category]) {
        groups[category] = []
      }
      groups[category].push(tool)
    })
    return groups
  }, [filteredTools])

  // 统计各类型数量
  const typeCounts = React.useMemo(() => {
    return {
      all: availableTools.length,
      builtin: availableTools.filter((t) => t.type === 'builtin').length,
      custom: availableTools.filter((t) => t.type === 'custom').length,
      mcp: availableTools.filter((t) => t.type === 'mcp').length,
      skill: availableTools.filter((t) => t.type === 'skill').length,
    }
  }, [availableTools])

  const handleSelectTool = (tool: Tool) => {
    // 根据工具类型判断是否已选中
    let isSelected = false
    if (tool.type === 'builtin') {
      isSelected = selectedToolNames.includes(tool.name)
    } else if (tool.type === 'custom') {
      isSelected = selectedToolIds.includes(tool.id)
    } else if (tool.type === 'mcp') {
      isSelected = selectedMcpServerIds.includes(tool.id)
    } else if (tool.type === 'skill') {
      isSelected = selectedSkillIds.includes(tool.id)
    }

    if (isSelected) {
      // 取消选中
      onRemove(tool)
    } else {
      // 添加选中
      onAdd(tool)
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 text-xs gap-1 cursor-pointer"
        onClick={() => setOpen(true)}
      >
        <Plus className="h-3 w-3" />
        {t('add')}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[70%]! max-w-[70%]! max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wrench className="h-4 w-4 text-orange-500" />
              {t('dialog.title')}
            </DialogTitle>
          </DialogHeader>

          {/* 搜索和过滤 */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('dialog.searchPlaceholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
            <Tabs value={filter} onValueChange={(v) => setFilter(v as 'all' | ToolType)}>
              <TabsList>
                <TabsTrigger value="all">
                  {t('dialog.filters.all')} ({typeCounts.all})
                </TabsTrigger>
                <TabsTrigger value="builtin">
                  {t('dialog.filters.builtin')} ({typeCounts.builtin})
                </TabsTrigger>
                <TabsTrigger value="custom" disabled={typeCounts.custom === 0}>
                  {t('dialog.filters.custom')} ({typeCounts.custom})
                </TabsTrigger>
                <TabsTrigger value="mcp" disabled={typeCounts.mcp === 0}>
                  {t('dialog.filters.mcp')} ({typeCounts.mcp})
                </TabsTrigger>
                <TabsTrigger value="skill" disabled={typeCounts.skill === 0}>
                  {t('dialog.filters.skill')} ({typeCounts.skill})
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* 工具列表 */}
          <div className="flex-1 overflow-y-auto mt-4 -mx-6 px-6 space-y-4">
            {Object.keys(groupedTools).length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Wrench className="h-12 w-12 mb-4" />
                <p>{search ? t('dialog.noSearchResults') : t('dialog.noTools')}</p>
              </div>
            ) : (
              Object.entries(groupedTools).map(([category, tools]) => (
                <div key={category}>
                  <h3 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                    <span>{categoryConfig[category as ToolCategory]?.icon || '⚙️'}</span>
                    {t(`dialog.categories.${category}`)}
                  </h3>
                  <div className="grid grid-cols-1 gap-2">
                    {tools.map((tool) => {
                      // 根据工具类型判断是否已选中
                      let isSelected = false
                      if (tool.type === 'builtin') {
                        isSelected = selectedToolNames.includes(tool.name)
                      } else if (tool.type === 'custom') {
                        isSelected = selectedToolIds.includes(tool.id)
                      } else if (tool.type === 'mcp') {
                        isSelected = selectedMcpServerIds.includes(tool.id)
                      } else if (tool.type === 'skill') {
                        isSelected = selectedSkillIds.includes(tool.id)
                      }
                      const category = categoryConfig[tool.category] || categoryConfig.other
                      const type = typeConfig[tool.type]
                      const typeLabel = typeLabels[tool.type]

                      return (
                        <div
                          key={tool.id || tool.name}
                          className={cn(
                            'flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer',
                            isSelected
                              ? 'bg-primary/5 border-primary/30'
                              : 'hover:bg-muted/50 hover:border-primary/30',
                            !tool.is_enabled && 'opacity-60'
                          )}
                          onClick={() => handleSelectTool(tool)}
                        >
                          {/* 图标 */}
                          <div className="shrink-0 w-10 h-10 rounded-lg bg-muted flex items-center justify-center text-xl">
                            {tool.icon || category.icon}
                          </div>

                          {/* 内容 */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-sm font-medium truncate">
                                {tool.display_name}
                              </span>
                              {tool.requires_config && (
                                <span title={t('dialog.requiresConfig')}>
                                  <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground line-clamp-1">
                              {tool.description}
                            </p>
                            <div className="flex items-center gap-1.5 mt-1.5">
                              <Badge
                                variant="outline"
                                className={cn('text-[10px] px-1.5 py-0', type.color)}
                              >
                                {typeLabel}
                              </Badge>
                              {tool.parameters.length > 0 && (
                                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                  {t('dialog.paramsCount', { count: tool.parameters.length })}
                                </Badge>
                              )}
                            </div>
                          </div>

                          {/* 选中状态 */}
                          <div className="shrink-0">
                            {isSelected ? (
                              <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
                                <Check className="h-3.5 w-3.5 text-primary-foreground" />
                              </div>
                            ) : (
                              <div className="w-6 h-6 rounded-full border-2 border-muted-foreground/30" />
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

interface ToolDisplayItemProps {
  tool: Tool | null
  config: ToolConfig
  onDelete: () => void
}

function ToolDisplayItem({ tool, config, onDelete }: ToolDisplayItemProps) {
  const t = useTranslations('agents.orchestration.tools')
  const [isDeleteHover, setIsDeleteHover] = React.useState(false)
  const isMissing = !tool

  // 获取显示名称
  const displayName = tool?.display_name || config.name || config.tool_id || config.server_id || t('unknownTool')

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors group',
        isMissing
          ? 'bg-destructive/10 border-destructive/50'
          : isDeleteHover
            ? 'bg-destructive/10 border-destructive/30'
            : 'bg-background hover:bg-muted/30'
      )}
    >
      {/* 图标 */}
      {isMissing ? (
        <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
      ) : (
        <Wrench className="h-4 w-4 text-orange-500 shrink-0" />
      )}

      {/* 名称 */}
      <div className="flex-1 min-w-0">
        <span className={cn('text-sm font-medium', isMissing && 'text-destructive')}>
          {displayName}
        </span>
        {isMissing && (
          <p className="text-xs text-destructive/80">{t('toolNotFound')}</p>
        )}
      </div>

      {/* 操作 */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive/10 hover:text-destructive"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          onMouseEnter={() => setIsDeleteHover(true)}
          onMouseLeave={() => setIsDeleteHover(false)}
        >
          <Trash2 className="h-3 w-3 text-muted-foreground" />
        </Button>
        <Switch checked={true} onCheckedChange={() => onDelete()} />
      </div>
    </div>
  )
}

interface ToolSelectorProps {
  toolsConfig: ToolConfig[]
  availableTools: Tool[]
  onChange: (toolsConfig: ToolConfig[]) => void
}

export function ToolSelector({
  toolsConfig,
  availableTools,
  onChange,
}: ToolSelectorProps) {
  const t = useTranslations('agents.orchestration.tools')

  // 获取已选择的工具完整信息（包括找不到的工具）
  const selectedTools = React.useMemo(() => {
    return toolsConfig.map((config) => {
      const tool = availableTools.find(
        (t) =>
          (config.type === 'builtin' && t.type === 'builtin' && t.name === config.name) ||
          (config.type === 'mcp' && t.type === 'mcp' && t.id === config.server_id) ||
          (config.type === 'custom' && t.type === 'custom' && t.id === config.tool_id) ||
          (config.type === 'skill' && t.type === 'skill' && t.id === config.skill_id)
      )
      return { config, tool: tool || null }
    })
  }, [toolsConfig, availableTools])

  const handleDeleteTool = (config: ToolConfig) => {
    onChange(
      toolsConfig.filter((c) => {
        if (c.type === 'builtin' && config.type === 'builtin') {
          return c.name !== config.name
        }
        if (c.type === 'mcp' && config.type === 'mcp') {
          return c.server_id !== config.server_id
        }
        if (c.type === 'custom' && config.type === 'custom') {
          return c.tool_id !== config.tool_id
        }
        if (c.type === 'skill' && config.type === 'skill') {
          return c.skill_id !== config.skill_id
        }
        return true
      })
    )
  }

  if (selectedTools.length === 0) {
    return (
      <p className="text-xs text-muted-foreground py-2">
        {t('empty')}
      </p>
    )
  }

  // 生成唯一 key
  const getKey = (config: ToolConfig, index: number) => {
    if (config.type === 'builtin') return `builtin-${config.name}`
    if (config.type === 'mcp') return `mcp-${config.server_id}`
    if (config.type === 'custom') return `custom-${config.tool_id}`
    if (config.type === 'skill') return `skill-${config.skill_id}`
    return `unknown-${index}`
  }

  return (
    <div className="space-y-2">
      {selectedTools.map(({ config, tool }, index) => (
        <ToolDisplayItem
          key={getKey(config, index)}
          tool={tool}
          config={config}
          onDelete={() => handleDeleteTool(config)}
        />
      ))}
    </div>
  )
}

// Hook 用于加载工具列表
function parametersFromInputSchema(inputSchema: Record<string, unknown>): ToolParameter[] {
  const properties = inputSchema.properties
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    return []
  }

  const required = Array.isArray(inputSchema.required) ? inputSchema.required : []

  return Object.entries(properties).map(([name, schema]) => {
    const field = schema && typeof schema === 'object' && !Array.isArray(schema)
      ? schema as Record<string, unknown>
      : {}
    const type = typeof field.type === 'string' ? field.type : 'string'
    const description = typeof field.description === 'string' ? field.description : undefined
    const enumValues = Array.isArray(field.enum)
      ? field.enum.filter((value): value is string => typeof value === 'string')
      : undefined

    return {
      name,
      type,
      description,
      required: required.includes(name),
      enum: enumValues,
      default: field.default,
    }
  })
}

function skillToTool(skill: Skill): Tool {
  return {
    id: skill.id,
    name: skill.name,
    display_name: skill.display_name,
    description: skill.description,
    type: 'skill',
    category: skill.category,
    icon: skill.icon || undefined,
    parameters: parametersFromInputSchema(skill.input_schema),
    is_enabled: skill.is_enabled,
    requires_config: false,
    config_fields: [],
    team_id: skill.team_id || undefined,
    created_by_name: skill.created_by_name || undefined,
  }
}

export function useTools() {
  const { currentTeam } = useTeam()
  const [tools, setTools] = React.useState<Tool[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<Error | null>(null)

  React.useEffect(() => {
    const loadTools = async () => {
      if (!currentTeam) {
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        const [toolsResponse, skillsResponse] = await Promise.all([
          toolsApi.list(currentTeam.id),
          skillsApi.list({ team_id: currentTeam.id, enabled: true }),
        ])
        const skillTools = [...skillsResponse.system, ...skillsResponse.team].map(skillToTool)
        const allTools = [
          ...toolsResponse.builtin,
          ...toolsResponse.custom,
          ...toolsResponse.mcp,
          ...skillTools,
        ]
        setTools(allTools)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to load tools'))
      } finally {
        setLoading(false)
      }
    }

    loadTools()
  }, [currentTeam])

  return { tools, loading, error, refetch: () => {} }
}
