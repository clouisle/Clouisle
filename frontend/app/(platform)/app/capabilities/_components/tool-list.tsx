'use client'

import { useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Tool, ToolType, isPresetToolCategory } from '@/lib/api'
import { ToolCard } from './tool-card'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Search, Wrench } from 'lucide-react'

interface ToolListProps {
  tools: Tool[]
  onSelect?: (tool: Tool) => void
  onTest?: (tool: Tool) => void
  onEdit?: (tool: Tool) => void
  onDelete?: (tool: Tool) => void
  onConfigure?: (tool: Tool) => void
  onShare?: (tool: Tool) => void
}

type FilterType = 'all' | ToolType

export function ToolList({ tools, onSelect, onTest, onEdit, onDelete, onConfigure, onShare }: ToolListProps) {
  const t = useTranslations('platform.tools')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<FilterType>('all')

  // 按分类分组
  const groupedTools = useMemo(() => {
    let filtered = tools

    // 搜索过滤
    if (search) {
      const query = search.toLowerCase()
      filtered = filtered.filter(
        (tool) =>
          tool.name.toLowerCase().includes(query) ||
          tool.display_name.toLowerCase().includes(query) ||
          tool.description.toLowerCase().includes(query)
      )
    }

    // 类型过滤
    if (filter !== 'all') {
      filtered = filtered.filter((tool) => tool.type === filter)
    }

    // 按分类分组
    const groups: Record<string, Tool[]> = {}
    filtered.forEach((tool) => {
      const category = tool.category
      if (!groups[category]) {
        groups[category] = []
      }
      groups[category].push(tool)
    })

    return groups
  }, [tools, search, filter])

  const categoryLabel = (category: string) => isPresetToolCategory(category) ? t(`categories.${category}`) : category

  // 统计各类型数量
  const typeCounts = useMemo(() => {
    return {
      all: tools.length,
      builtin: tools.filter((t) => t.type === 'builtin').length,
      custom: tools.filter((t) => t.type === 'custom').length,
      mcp: tools.filter((t) => t.type === 'mcp').length,
    }
  }, [tools])

  const isEmpty = Object.keys(groupedTools).length === 0

  return (
    <div className="space-y-4">
      {/* 搜索和过滤 */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterType)}>
          <TabsList>
            <TabsTrigger value="all">
              {t('filters.all')} ({typeCounts.all})
            </TabsTrigger>
            <TabsTrigger value="builtin">
              {t('filters.builtin')} ({typeCounts.builtin})
            </TabsTrigger>
            <TabsTrigger value="custom" disabled={typeCounts.custom === 0}>
              {t('filters.custom')} ({typeCounts.custom})
            </TabsTrigger>
            <TabsTrigger value="mcp" disabled={typeCounts.mcp === 0}>
              {t('filters.mcp')} ({typeCounts.mcp})
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* 工具列表 */}
      {isEmpty ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <Wrench className="h-12 w-12 mb-4" />
          <p>{search ? t('noSearchResults') : t('noTools')}</p>
        </div>
      ) : (
        <div className="space-y-6">
          {Object.entries(groupedTools).map(([category, categoryTools]) => (
            <div key={category}>
              <h3 className="text-sm font-medium text-muted-foreground mb-3">
                {categoryLabel(category)}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {categoryTools.map((tool) => (
                  <ToolCard
                    key={tool.id || tool.name}
                    tool={tool}
                    onSelect={onSelect}
                    onTest={onTest}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onConfigure={onConfigure}
                    onShare={onShare}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ToolList
