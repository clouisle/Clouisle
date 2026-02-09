'use client'

import * as React from 'react'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import {
  Plus,
  Search,
  MoreHorizontal,
  Pencil,
  Trash2,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronDown,
  X,
  Copy,
  ToggleLeft,
  ToggleRight,
  Wrench,
  Code,
  Server,
  Globe,
  Plug,
  Share2,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  toolsApi,
  teamsApi,
  type Tool,
  type ToolType,
  type ToolCategory,
  type ToolListResponse,
  type UserTeamInfo,
  type ToolDetail,
  type ToolCreateInput,
  type ToolUpdateInput,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { HttpToolDialog } from './http-tool-dialog'
import { McpToolDialog } from './mcp-tool-dialog'
import { DeleteToolDialog } from './delete-tool-dialog'
import { ToolShareDialog } from './tool-share-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

// 工具类型图标映射
const toolTypeIcons: Record<ToolType, React.ReactNode> = {
  builtin: <Wrench className="h-4 w-4" />,
  custom: <Code className="h-4 w-4" />,
  mcp: <Server className="h-4 w-4" />,
}

// 工具分类图标映射
const categoryIcons: Record<ToolCategory, string> = {
  time: '🕐',
  math: '🔢',
  search: '🔍',
  web: '🌐',
  file: '📁',
  code: '💻',
  api: '🔗',
  data: '📊',
  other: '🔧',
}

export function ToolsClient() {
  const t = useTranslations('tools')
  const commonT = useTranslations('common')
  const router = useRouter()
  const { canPerform } = useCanPerform()

  // 数据状态 - 存储所有团队的工具
  const [allTeamsTools, setAllTeamsTools] = React.useState<Map<string, ToolListResponse>>(new Map())
  const [teams, setTeams] = React.useState<UserTeamInfo[]>([])
  const [currentTeamId, setCurrentTeamId] = React.useState<string>('')  // 用于创建工具时的默认团队
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)

  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())
  const [categoryFilter, setCategoryFilter] = React.useState<Set<string>>(new Set())
  const [enabledFilter, setEnabledFilter] = React.useState<Set<string>>(new Set())
  const [creatorFilter, setCreatorFilter] = React.useState<Set<string>>(new Set())
  const [teamFilter, setTeamFilter] = React.useState<Set<string>>(new Set())

  // 选择状态
  const [selectedTools, setSelectedTools] = React.useState<Set<string>>(new Set())

  // Dialog 状态
  const [httpDialogOpen, setHttpDialogOpen] = React.useState(false)
  const [mcpDialogOpen, setMcpDialogOpen] = React.useState(false)
  const [editingHttpTool, setEditingHttpTool] = React.useState<ToolDetail | null>(null)
  const [editingMcpTool, setEditingMcpTool] = React.useState<ToolDetail | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedTool, setSelectedTool] = React.useState<Tool | null>(null)
  const [shareDialogOpen, setShareDialogOpen] = React.useState(false)
  const [sharingTool, setSharingTool] = React.useState<Tool | null>(null)

  // 加载团队列表
  React.useEffect(() => {
    const loadTeams = async () => {
      try {
        const data = await teamsApi.getMyTeams()
        setTeams(data)
        if (data.length > 0 && !currentTeamId) {
          setCurrentTeamId(data[0].id)
        }
      } catch {
        // 忽略错误
      }
    }
    loadTeams()
  }, [currentTeamId])

  // 加载所有团队的工具列表
  const loadAllTools = React.useCallback(async () => {
    if (teams.length === 0) return

    setIsLoading(true)
    try {
      const toolsMap = new Map<string, ToolListResponse>()
      await Promise.all(
        teams.map(async (team) => {
          const data = await toolsApi.list(team.id)
          toolsMap.set(team.id, data)
        })
      )
      setAllTeamsTools(toolsMap)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [teams])

  React.useEffect(() => {
    loadAllTools()
  }, [loadAllTools])

  // 合并所有团队的工具并添加 type 标识
  const allTools = React.useMemo(() => {
    const result: (Tool & { _type: ToolType })[] = []
    // 内置工具只加载一次（从第一个团队）
    const firstTeamTools = allTeamsTools.values().next().value
    if (firstTeamTools) {
      firstTeamTools.builtin.forEach((tool: Tool) => result.push({ ...tool, _type: 'builtin' as const }))
    }
    // 合并所有团队的自定义和 MCP 工具
    allTeamsTools.forEach((tools) => {
      tools.custom.forEach((tool) => result.push({ ...tool, _type: 'custom' as const }))
      tools.mcp.forEach((tool) => result.push({ ...tool, _type: 'mcp' as const }))
    })
    return result
  }, [allTeamsTools])

  // 获取创建人选项
  const creatorOptions = React.useMemo(() => {
    const creators = new Set<string>()
    allTools.forEach((tool) => {
      if (tool.created_by_name) {
        creators.add(tool.created_by_name)
      }
    })
    return Array.from(creators).map((name) => ({
      value: name,
      label: name,
    }))
  }, [allTools])

  // 筛选工具
  const filteredTools = React.useMemo(() => {
    return allTools.filter((tool) => {
      // 搜索筛选
      if (searchQuery) {
        const query = searchQuery.toLowerCase()
        if (
          !tool.name.toLowerCase().includes(query) &&
          !tool.display_name.toLowerCase().includes(query) &&
          !tool.description.toLowerCase().includes(query)
        ) {
          return false
        }
      }

      // 类型筛选
      if (typeFilter.size > 0) {
        if (!typeFilter.has(tool._type)) {
          return false
        }
      }

      // 分类筛选
      if (categoryFilter.size > 0) {
        if (!categoryFilter.has(tool.category)) {
          return false
        }
      }

      // 启用状态筛选
      if (enabledFilter.size > 0) {
        const enabled = tool.is_enabled ? 'enabled' : 'disabled'
        if (!enabledFilter.has(enabled)) {
          return false
        }
      }

      // 团队筛选
      if (teamFilter.size > 0) {
        if (!tool.team_id || !teamFilter.has(tool.team_id)) {
          return false
        }
      }

      // 创建人筛选
      if (creatorFilter.size > 0) {
        if (!tool.created_by_name || !creatorFilter.has(tool.created_by_name)) {
          return false
        }
      }

      return true
    })
  }, [allTools, searchQuery, typeFilter, categoryFilter, enabledFilter, teamFilter, creatorFilter])

  // 分页
  const paginatedTools = React.useMemo(() => {
    const start = (page - 1) * pageSize
    return filteredTools.slice(start, start + pageSize)
  }, [filteredTools, page, pageSize])

  const totalPages = Math.ceil(filteredTools.length / pageSize)

  // 检查是否有筛选条件
  const isFiltered =
    searchQuery || typeFilter.size > 0 || categoryFilter.size > 0 || enabledFilter.size > 0 || creatorFilter.size > 0 || teamFilter.size > 0

  // 重置所有筛选
  const resetFilters = () => {
    setSearchQuery('')
    setTypeFilter(new Set())
    setCategoryFilter(new Set())
    setEnabledFilter(new Set())
    setCreatorFilter(new Set())
    setTeamFilter(new Set())
  }

  // 团队选项
  const teamOptions = React.useMemo(() => {
    return teams.map((team) => ({
      value: team.id,
      label: team.name,
    }))
  }, [teams])

  // 类型选项
  const typeOptions = [
    { value: 'builtin', label: t('filters.builtin'), icon: toolTypeIcons.builtin },
    { value: 'custom', label: t('filters.custom'), icon: toolTypeIcons.custom },
    { value: 'mcp', label: t('filters.mcp'), icon: toolTypeIcons.mcp },
  ]

  // 分类选项
  const categoryOptions = Object.entries(categoryIcons).map(([value, icon]) => ({
    value,
    label: t(`categories.${value}`),
    icon: <span className="text-sm">{icon}</span>,
  }))

  // 启用状态选项
  const enabledOptions = [
    { value: 'enabled', label: t('enabled') },
    { value: 'disabled', label: t('disabled') },
  ]

  // 选择操作
  const selectableTools = paginatedTools.filter((tool) => tool._type !== 'builtin')

  const toggleSelectAll = () => {
    if (selectedTools.size === selectableTools.length) {
      setSelectedTools(new Set())
    } else {
      setSelectedTools(new Set(selectableTools.filter((t) => t.id).map((t) => t.id!)))
    }
  }

  const toggleSelectTool = (toolId: string) => {
    const newSelected = new Set(selectedTools)
    if (newSelected.has(toolId)) {
      newSelected.delete(toolId)
    } else {
      newSelected.add(toolId)
    }
    setSelectedTools(newSelected)
  }

  // 创建 HTTP 工具
  const handleCreateHttpTool = () => {
    setEditingHttpTool(null)
    setHttpDialogOpen(true)
  }

  // 创建 Code 工具
  const handleCreateCodeTool = () => {
    router.push(`/tools/code?teamId=${currentTeamId}`)
  }

  // 创建 MCP 工具
  const handleCreateMcpTool = () => {
    setEditingMcpTool(null)
    setMcpDialogOpen(true)
  }

  // 编辑工具
  const handleEdit = async (tool: Tool & { _type: ToolType }) => {
    if (!tool.id) return

    // 对于代码工具，直接跳转
    if (tool._type === 'custom' && tool.custom_type === 'code') {
      router.push(`/tools/code?id=${tool.id}`)
      return
    }

    try {
      const detail = await toolsApi.getById(tool.id)

      if (detail.type === 'mcp') {
        setEditingMcpTool(detail)
        setMcpDialogOpen(true)
      } else if (detail.type === 'custom') {
        if (detail.custom_type === 'http') {
          setEditingHttpTool(detail)
          setHttpDialogOpen(true)
        } else if (detail.custom_type === 'code') {
          router.push(`/tools/code?id=${tool.id}`)
        } else {
          // 未知的自定义工具类型，尝试根据配置判断
          if (detail.http_config && Object.keys(detail.http_config).length > 0) {
            setEditingHttpTool(detail)
            setHttpDialogOpen(true)
          } else if (detail.code_config && Object.keys(detail.code_config).length > 0) {
            router.push(`/tools/code?id=${tool.id}`)
          } else {
            toast.error(t('error.unknownToolType'))
          }
        }
      }
    } catch (error) {
      console.error('Failed to load tool detail:', error)
    }
  }

  // 保存 HTTP 工具
  const handleSaveHttpTool = async (data: ToolCreateInput | ToolUpdateInput) => {
    if (!currentTeamId) return

    try {
      if (editingHttpTool?.id) {
        await toolsApi.update(editingHttpTool.id, data as ToolUpdateInput)
        toast.success(t('toolUpdated'))
      } else {
        await toolsApi.create(currentTeamId, data as ToolCreateInput)
        toast.success(t('toolCreated'))
      }
      setHttpDialogOpen(false)
      setEditingHttpTool(null)
      loadAllTools()
    } catch (error) {
      console.error('Failed to save tool:', error)
    }
  }

  // 保存 MCP 工具
  const handleSaveMcpTool = async (data: ToolCreateInput | ToolUpdateInput) => {
    if (!currentTeamId) return

    try {
      if (editingMcpTool?.id) {
        await toolsApi.update(editingMcpTool.id, data as ToolUpdateInput)
        toast.success(t('toolUpdated'))
      } else {
        await toolsApi.create(currentTeamId, data as ToolCreateInput)
        toast.success(t('toolCreated'))
      }
      setMcpDialogOpen(false)
      setEditingMcpTool(null)
      loadAllTools()
    } catch (error) {
      console.error('Failed to save tool:', error)
    }
  }

  // 打开删除 Dialog
  const handleDelete = (tool: Tool) => {
    setSelectedTool(tool)
    setDeleteDialogOpen(true)
  }

  // 切换工具状态
  const handleToggleStatus = async (tool: Tool) => {
    if (!tool.id) return
    try {
      await toolsApi.toggle(tool.id)
      toast.success(tool.is_enabled ? t('toolDisabled') : t('toolEnabled'))
      loadAllTools()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // 复制工具
  const handleDuplicate = async (tool: Tool) => {
    if (!tool.id) return
    try {
      await toolsApi.duplicate(tool.id)
      toast.success(t('toolDuplicated'))
      loadAllTools()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // 共享工具
  const handleShare = (tool: Tool) => {
    if (!tool.id) return
    setSharingTool(tool)
    setShareDialogOpen(true)
  }

  // 共享成功回调
  const handleShareSuccess = () => {
    loadAllTools() // 重新加载工具列表以更新共享计数
  }

  // Dialog 成功回调
  const handleDialogSuccess = () => {
    loadAllTools()
    setSelectedTools(new Set())
  }

  // 批量删除
  const handleBulkDelete = () => {
    setBulkDeleteDialogOpen(true)
  }

  // 确认批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedTools).map((id) => toolsApi.delete(id))
      await Promise.all(promises)
      toast.success(t('bulkDeleted', { count: selectedTools.size }))
      setSelectedTools(new Set())
      loadAllTools()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }

  // 获取类型 Badge
  const getTypeBadge = (type: ToolType) => {
    const variants: Record<ToolType, string> = {
      builtin: 'bg-blue-500/10 text-blue-500 hover:bg-blue-500/20',
      custom: 'bg-purple-500/10 text-purple-500 hover:bg-purple-500/20',
      mcp: 'bg-orange-500/10 text-orange-500 hover:bg-orange-500/20',
    }
    return (
      <Badge variant="secondary" className={variants[type]}>
        {toolTypeIcons[type]}
        <span className="ml-1">{t(`filters.${type}`)}</span>
      </Badge>
    )
  }

  // 获取内置工具的显示名称（支持多语言）
  const getToolDisplayName = (tool: Tool & { _type: ToolType }) => {
    if (tool._type === 'builtin') {
      try {
        // 尝试获取翻译，如果不存在则返回原始名称
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const translationKey = `builtinTools.${tool.name}` as any
        const translated = t(translationKey)
        // next-intl 在找不到翻译时会返回键本身
        if (translated && !translated.startsWith('builtinTools.')) {
          return translated
        }
      } catch {
        // 翻译不存在或出错，使用原始名称
      }
    }
    return tool.display_name
  }

  // 获取启用状态 Badge
  const getEnabledBadge = (enabled: boolean) => {
    if (enabled) {
      return (
        <Badge
          variant="default"
          className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20"
        >
          {t('enabled')}
        </Badge>
      )
    }
    return (
      <Badge variant="outline" className="text-muted-foreground">
        {t('disabled')}
      </Badge>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <PermissionGuard permission="tool:create">
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button>
                    <Plus className="mr-2 h-4 w-4" />
                    {t('createTool')}
                    <ChevronDown className="ml-2 h-4 w-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem onClick={handleCreateHttpTool}>
                  <Globe className="mr-2 h-4 w-4" />
                  <div className="flex flex-col">
                    <span>{t('createMenu.http')}</span>
                    <span className="text-xs text-muted-foreground">
                      {t('createMenu.httpDesc')}
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleCreateCodeTool}>
                  <Code className="mr-2 h-4 w-4" />
                  <div className="flex flex-col">
                    <span>{t('createMenu.code')}</span>
                    <span className="text-xs text-muted-foreground">
                      {t('createMenu.codeDesc')}
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleCreateMcpTool}>
                  <Plug className="mr-2 h-4 w-4" />
                  <div className="flex flex-col">
                    <span>{t('createMenu.mcp')}</span>
                    <span className="text-xs text-muted-foreground">
                      {t('createMenu.mcpDesc')}
                    </span>
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </PermissionGuard>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t('searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-9 w-50 pl-8"
          />
        </div>

        <DataTableFacetedFilter
          title={t('type')}
          options={typeOptions}
          selectedValues={typeFilter}
          onSelectionChange={setTypeFilter}
        />

        <DataTableFacetedFilter
          title={t('category')}
          options={categoryOptions}
          selectedValues={categoryFilter}
          onSelectionChange={setCategoryFilter}
          searchable
        />

        <DataTableFacetedFilter
          title={commonT('status')}
          options={enabledOptions}
          selectedValues={enabledFilter}
          onSelectionChange={setEnabledFilter}
        />

        {teamOptions.length > 1 && (
          <DataTableFacetedFilter
            title={commonT('team')}
            options={teamOptions}
            selectedValues={teamFilter}
            onSelectionChange={setTeamFilter}
            searchable
          />
        )}

        {creatorOptions.length > 0 && (
          <DataTableFacetedFilter
            title={commonT('createdBy')}
            options={creatorOptions}
            selectedValues={creatorFilter}
            onSelectionChange={setCreatorFilter}
            searchable
          />
        )}

        {isFiltered && (
          <Button variant="ghost" onClick={resetFilters} className="h-9 px-2 lg:px-3">
            {commonT('reset')}
            <X className="ml-2 h-4 w-4" />
          </Button>
        )}
      </div>

      {/* 表格 */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-10">
                <Checkbox
                  checked={
                    selectedTools.size === selectableTools.length && selectableTools.length > 0
                  }
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('name')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead>{t('category')}</TableHead>
              <TableHead>{commonT('team')}</TableHead>
              <TableHead>{commonT('createdBy')}</TableHead>
              <TableHead>{commonT('status')}</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : paginatedTools.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  {t('noTools')}
                </TableCell>
              </TableRow>
            ) : (
              paginatedTools.map((tool) => {
                const teamName = teams.find((team) => team.id === tool.team_id)?.name || '-'
                return (
                  <TableRow
                    key={`${tool._type}-${tool.id || tool.name}`}
                    data-state={tool.id && selectedTools.has(tool.id) ? 'selected' : undefined}
                  >
                    <TableCell>
                      {tool._type !== 'builtin' && tool.id && (
                        <Checkbox
                          checked={selectedTools.has(tool.id)}
                          onCheckedChange={() => toggleSelectTool(tool.id!)}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {tool.icon && (
                          tool.icon.startsWith('http') ? (
                            <div className="relative h-6 w-6 rounded overflow-hidden">
                              <Image
                                src={tool.icon}
                                alt={tool.display_name}
                                fill
                                className="object-cover"
                                loading="eager"
                                unoptimized
                              />
                            </div>
                          ) : (
                            <span className="text-lg">{tool.icon}</span>
                          )
                        )}
                        <span className="font-medium">{getToolDisplayName(tool)}</span>
                      </div>
                    </TableCell>
                    <TableCell>{getTypeBadge(tool._type)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <span className="text-sm">{categoryIcons[tool.category]}</span>
                        <span>{t(`categories.${tool.category}`)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="text-muted-foreground">{teamName}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-muted-foreground">
                        {tool.created_by_name || '-'}
                      </span>
                    </TableCell>
                    <TableCell>{getEnabledBadge(tool.is_enabled)}</TableCell>
                    <TableCell>
                      {tool._type !== 'builtin' && tool.id && (canPerform('tool:update') || canPerform('tool:delete')) && (
                        <DropdownMenu>
                          <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                            <MoreHorizontal className="h-4 w-4" />
                            <span className="sr-only">{t('common.openMenu')}</span>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {canPerform('tool:update') && (
                              <>
                                <DropdownMenuItem onClick={() => handleEdit(tool)}>
                                  <Pencil className="mr-2 h-4 w-4" />
                                  {commonT('edit')}
                                </DropdownMenuItem>

                                <DropdownMenuItem onClick={() => handleDuplicate(tool)}>
                                  <Copy className="mr-2 h-4 w-4" />
                                  {t('duplicate')}
                                </DropdownMenuItem>

                                <DropdownMenuItem onClick={() => handleShare(tool)}>
                                  <Share2 className="mr-2 h-4 w-4" />
                                  {t('share.title')}
                                </DropdownMenuItem>

                                <DropdownMenuItem onClick={() => handleToggleStatus(tool)}>
                                  {tool.is_enabled ? (
                                    <>
                                      <ToggleLeft className="mr-2 h-4 w-4" />
                                      {t('disable')}
                                    </>
                                  ) : (
                                    <>
                                      <ToggleRight className="mr-2 h-4 w-4" />
                                      {t('enable')}
                                    </>
                                  )}
                                </DropdownMenuItem>
                              </>
                            )}

                            {canPerform('tool:delete') && (
                              <>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => handleDelete(tool)}
                                  className="text-destructive focus:text-destructive"
                                >
                                  <Trash2 className="mr-2 h-4 w-4" />
                                  {commonT('delete')}
                                </DropdownMenuItem>
                              </>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* 分页 */}
      {filteredTools.length > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select
              value={String(pageSize)}
              onValueChange={(v) => {
                setPageSize(Number(v))
                setPage(1)
              }}
            >
              <SelectTrigger size="sm" className="w-18">
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top" alignItemWithTrigger={false}>
                <SelectItem value="10">10</SelectItem>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
                <SelectItem value="100">100</SelectItem>
              </SelectContent>
            </Select>
            <span>{t('rowsPerPage')}</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t('pageInfo', { page, total: totalPages })}
            </span>

            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(1)}
                disabled={page === 1}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => setPage(totalPages)}
                disabled={page >= totalPages}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* HTTP 工具对话框 */}
      <HttpToolDialog
        tool={editingHttpTool}
        open={httpDialogOpen}
        onOpenChange={setHttpDialogOpen}
        onSave={handleSaveHttpTool}
      />

      {/* MCP 工具对话框 */}
      <McpToolDialog
        tool={editingMcpTool}
        open={mcpDialogOpen}
        onOpenChange={setMcpDialogOpen}
        onSave={handleSaveMcpTool}
      />

      {/* 工具共享对话框 */}
      <ToolShareDialog
        tool={sharingTool}
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        availableTeams={teams}
        onSuccess={handleShareSuccess}
      />

      {/* 删除确认 Dialog */}
      <DeleteToolDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        tool={selectedTool}
        onSuccess={handleDialogSuccess}
      />

      {/* 批量操作浮动工具栏 */}
      {selectedTools.size > 0 && canPerform('tool:delete') && (
        <div className="fixed bottom-8 left-1/2 z-50 -translate-x-1/2">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedTools(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedTools.size} {t('toolsSelected')}
            </Badge>

            <Tooltip>
              <TooltipTrigger
                onClick={handleBulkDelete}
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                }
              />
              <TooltipContent>{commonT('delete')}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      )}

      {/* 批量删除确认 Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmBulkDelete', { count: selectedTools.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmBulkDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
