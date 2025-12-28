'use client'

import { useTranslations } from 'next-intl'
import { Tool, ToolCategory, ToolType } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertCircle,
  MoreVertical,
  Pencil,
  Trash2,
  Play,
  Settings,
} from 'lucide-react'

interface ToolCardProps {
  tool: Tool
  onSelect?: (tool: Tool) => void
  onTest?: (tool: Tool) => void
  onEdit?: (tool: Tool) => void
  onDelete?: (tool: Tool) => void
  onConfigure?: (tool: Tool) => void
}

// 分类图标和颜色映射
const categoryConfig: Record<ToolCategory, { icon: string; color: string }> = {
  time: {
    icon: '🕐',
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  },
  math: {
    icon: '🔢',
    color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  },
  search: {
    icon: '🔍',
    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  },
  web: {
    icon: '🌐',
    color: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
  },
  file: {
    icon: '📁',
    color: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  },
  code: {
    icon: '💻',
    color: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
  },
  api: {
    icon: '🔗',
    color: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
  },
  data: {
    icon: '📊',
    color: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300',
  },
  other: {
    icon: '⚙️',
    color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
  },
}

// 类型颜色配置
const typeColorConfig: Record<ToolType, string> = {
  builtin: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300',
  custom: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300',
  mcp: 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-300',
}

export function ToolCard({
  tool,
  onSelect,
  onTest,
  onEdit,
  onDelete,
  onConfigure,
}: ToolCardProps) {
  const t = useTranslations('platform.tools')
  const tCommon = useTranslations('common')
  const category = categoryConfig[tool.category] || categoryConfig.other
  const typeColor = typeColorConfig[tool.type]
  const isEditable = tool.type === 'custom' || tool.type === 'mcp'
  const needsConfig = tool.type === 'builtin' && tool.requires_config

  // 类型标签映射（使用 i18n）
  const typeLabels: Record<ToolType, string> = {
    builtin: t('filters.builtin'),
    custom: t('filters.custom'),
    mcp: t('filters.mcp'),
  }

  // 分类标签映射（使用 i18n）
  const categoryLabels: Record<ToolCategory, string> = {
    time: t('categories.time'),
    math: t('categories.math'),
    search: t('categories.search'),
    web: t('categories.web'),
    file: t('categories.file'),
    code: t('categories.code'),
    api: t('categories.api'),
    data: t('categories.data'),
    other: t('categories.other'),
  }

  return (
    <Card
      size="sm"
      className={cn(
        'group cursor-pointer transition-all hover:shadow-md hover:border-primary/50 py-0! h-36',
        !tool.is_enabled && 'opacity-60'
      )}
      onClick={() => onSelect?.(tool)}
    >
      <CardContent className="flex flex-col justify-between h-full px-2.5 py-3">
        {/* 上半部分：图标、标题、描述 */}
        <div className="flex items-start gap-2">
          {/* 图标 */}
          <div className="shrink-0 w-8 h-8 rounded-lg bg-muted flex items-center justify-center text-base">
            {tool.icon || category.icon}
          </div>

          {/* 内容 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <CardTitle className="text-sm font-medium truncate">
                {tool.display_name}
              </CardTitle>
              {tool.requires_config && (
                <span title={t('requiresConfig')}>
                  <AlertCircle className="h-3 w-3 text-amber-500 shrink-0" />
                </span>
              )}
            </div>

            <CardDescription className="text-xs line-clamp-2 mt-0.5">
              {tool.description}
            </CardDescription>
          </div>
        </div>

        {/* 下半部分：标签和操作按钮 */}
        <div className="flex items-center justify-between border-t pt-2 mt-auto">
          {/* 标签 */}
          <div className="flex items-center gap-1 flex-wrap">
            <Badge
              variant="outline"
              className={cn('text-xs px-1.5 py-0', typeColor)}
            >
              {typeLabels[tool.type]}
            </Badge>
            <Badge
              variant="outline"
              className={cn('text-xs px-1.5 py-0', category.color)}
            >
              {categoryLabels[tool.category] || tool.category}
            </Badge>
          </div>

          {/* 操作按钮 */}
          <div className="shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={(e) => {
                e.stopPropagation()
                onTest?.(tool)
              }}
            >
              <Play className="h-3.5 w-3.5" />
            </Button>

            {needsConfig && (
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                title={t('requiresConfig')}
                onClick={(e) => {
                  e.stopPropagation()
                  onConfigure?.(tool)
                }}
              >
                <Settings className="h-3.5 w-3.5" />
              </Button>
            )}

            {isEditable && (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical className="h-3.5 w-3.5" />
                    </Button>
                  }
                />
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      onEdit?.(tool)
                    }}
                  >
                    <Pencil className="h-4 w-4 mr-2" />
                    {tCommon('edit')}
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDelete?.(tool)
                    }}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    {tCommon('delete')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default ToolCard
