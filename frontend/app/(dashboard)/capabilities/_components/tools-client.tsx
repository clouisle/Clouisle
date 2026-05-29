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
    Zap,
    Clock3,
    Calculator,
    FolderOpen,
    Link,
    ChartColumn,
    Upload,
    Download,
} from 'lucide-react'
import { toast } from 'sonner'
import {
    type Tool,
    type ToolType,
    isPresetToolCategory,
    type PresetToolCategory,
    type ToolFilterOption,
    type ToolDetail,
    type ToolCreateInput,
    type ToolUpdateInput,
    type PageData,
} from '@/lib/api'
import { adminToolsApi, teamsApi as adminTeamsApi, type Team } from '@/lib/api/admin'
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
import { HttpToolDialog } from '@/app/(platform)/app/capabilities/_components/http-tool-dialog'
import { McpToolDialog } from '@/app/(platform)/app/capabilities/_components/mcp-tool-dialog'
import { DeleteToolDialog } from './delete-tool-dialog'
import { ToolShareDialog } from './tool-share-dialog'
import { ToolConfigDialog } from '@/app/(platform)/app/capabilities/_components/tool-config-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { ImportPackageDialog } from '@/components/packages/import-package-dialog'
import { adminPackagesApi, downloadBlob } from '@/lib/api/packages'
import { useUrlSearchState } from '@/hooks/use-url-search-state'

// 工具类型图标映射
const toolTypeIcons: Record<ToolType, React.ReactNode> = {
    builtin: <Wrench className="h-4 w-4" />,
    custom: <Code className="h-4 w-4" />,
    mcp: <Server className="h-4 w-4" />,
    skill: <Zap className="h-4 w-4" />,
}

// 工具分类图标映射
const categoryIcons: Record<PresetToolCategory, React.ReactNode> = {
    time: <Clock3 className="h-4 w-4" />,
    math: <Calculator className="h-4 w-4" />,
    search: <Search className="h-4 w-4" />,
    web: <Globe className="h-4 w-4" />,
    file: <FolderOpen className="h-4 w-4" />,
    code: <Code className="h-4 w-4" />,
    sandbox: <Code className="h-4 w-4" />,
    api: <Link className="h-4 w-4" />,
    data: <ChartColumn className="h-4 w-4" />,
    other: <Wrench className="h-4 w-4" />,
}

export function ToolsClient() {
    const t = useTranslations('tools')
    const packageT = useTranslations('packages')
    const commonT = useTranslations('common')
    const router = useRouter()
    const { canPerform } = useCanPerform()

    // 数据状态
    const [tools, setTools] = React.useState<Tool[]>([])
    const [teams, setTeams] = React.useState<Team[]>([])
    const [currentTeamId, setCurrentTeamId] = React.useState<string>('')  // 用于创建工具时的默认团队
    const [categoryOptions, setCategoryOptions] = React.useState<ToolFilterOption[]>([])
    const [creatorOptions, setCreatorOptions] = React.useState<ToolFilterOption[]>([])
    const [teamOptions, setTeamOptions] = React.useState<ToolFilterOption[]>([])
    const [isLoading, setIsLoading] = React.useState(true)
    const [page, setPage] = React.useState(1)
    const [pageSize, setPageSize] = React.useState(10)
    const [pageData, setPageData] = React.useState<PageData<Tool> | null>(null)

    // 筛选状态
    const [searchQuery, setSearchQuery] = useUrlSearchState()
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
    const [configDialogOpen, setConfigDialogOpen] = React.useState(false)
    const [configuringTool, setConfiguringTool] = React.useState<Tool | null>(null)
    const [importDialogOpen, setImportDialogOpen] = React.useState(false)

    // 加载团队列表
    React.useEffect(() => {
        const loadTeams = async () => {
            try {
                const data = await adminTeamsApi.getTeams(1, 100)
                setTeams(data.items)
                if (data.items.length > 0 && !currentTeamId) {
                    setCurrentTeamId(data.items[0].id)
                }
            } catch {
                // 忽略错误
            }
        }
        loadTeams()
    }, [currentTeamId])

    const selectedTypes = React.useMemo(() => Array.from(typeFilter), [typeFilter])
    const selectedCategories = React.useMemo(() => Array.from(categoryFilter), [categoryFilter])
    const selectedStatuses = React.useMemo(() => Array.from(enabledFilter), [enabledFilter])
    const selectedCreators = React.useMemo(() => Array.from(creatorFilter), [creatorFilter])
    const selectedTeams = React.useMemo(() => Array.from(teamFilter), [teamFilter])

    const loadTools = React.useCallback(async () => {
        setIsLoading(true)
        try {
            const [toolsData, filterOptions] = await Promise.all([
                adminToolsApi.listPage({
                    page,
                    pageSize,
                    search: searchQuery || undefined,
                    type: selectedTypes.length > 0 ? selectedTypes : undefined,
                    category: selectedCategories.length > 0 ? selectedCategories : undefined,
                    status: selectedStatuses.length > 0 ? selectedStatuses : undefined,
                    team_id: selectedTeams.length > 0 ? selectedTeams : undefined,
                    creator: selectedCreators.length > 0 ? selectedCreators : undefined,
                }),
                adminToolsApi.getFilterOptions(),
            ])
            setTools(toolsData.items)
            setPageData(toolsData)
            setCategoryOptions(filterOptions.categories)
            setCreatorOptions(filterOptions.creators)
            setTeamOptions(filterOptions.teams)
        } catch {
            // 错误已由 API 客户端处理
        } finally {
            setIsLoading(false)
        }
    }, [page, pageSize, searchQuery, selectedTypes, selectedCategories, selectedStatuses, selectedTeams, selectedCreators])

    React.useEffect(() => {
        loadTools()
    }, [loadTools])

    const filteredTools = tools
    const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1

    const isFiltered =
        searchQuery || typeFilter.size > 0 || categoryFilter.size > 0 || enabledFilter.size > 0 || creatorFilter.size > 0 || teamFilter.size > 0

    const handleTypeFilterChange = (values: Set<string>) => {
        setTypeFilter(values)
        setPage(1)
        setSelectedTools(new Set())
    }

    const handleCategoryFilterChange = (values: Set<string>) => {
        setCategoryFilter(values)
        setPage(1)
        setSelectedTools(new Set())
    }

    const handleEnabledFilterChange = (values: Set<string>) => {
        setEnabledFilter(values)
        setPage(1)
        setSelectedTools(new Set())
    }

    const handleCreatorFilterChange = (values: Set<string>) => {
        setCreatorFilter(values)
        setPage(1)
        setSelectedTools(new Set())
    }

    const handleTeamFilterChange = (values: Set<string>) => {
        setTeamFilter(values)
        setPage(1)
        setSelectedTools(new Set())
    }

    const resetFilters = () => {
        setSearchQuery('')
        setTypeFilter(new Set())
        setCategoryFilter(new Set())
        setEnabledFilter(new Set())
        setCreatorFilter(new Set())
        setTeamFilter(new Set())
        setPage(1)
        setSelectedTools(new Set())
    }

    const typeOptions = [
        { value: 'builtin', label: t('filters.builtin'), icon: toolTypeIcons.builtin },
        { value: 'custom', label: t('filters.custom'), icon: toolTypeIcons.custom },
        { value: 'mcp', label: t('filters.mcp'), icon: toolTypeIcons.mcp },
    ]

    const categoryFilterOptions = categoryOptions.map((option) => {
        const icon = isPresetToolCategory(option.value) ? categoryIcons[option.value] : categoryIcons.other
        return {
            value: option.value,
            label: isPresetToolCategory(option.value) ? t(`categories.${option.value}`) : option.label,
            icon: <span className="text-sm">{icon}</span>,
        }
    })

    const enabledOptions = [
        { value: 'enabled', label: t('enabled') },
        { value: 'disabled', label: t('disabled') },
    ]

    const selectableTools = filteredTools.filter((tool) => tool.type !== 'builtin')

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
        router.push(`/capabilities/code?teamId=${currentTeamId}`)
    }

    // 创建 MCP 工具
    const handleCreateMcpTool = () => {
        setEditingMcpTool(null)
        setMcpDialogOpen(true)
    }

    // 配置内置工具
    const handleConfigureTool = (tool: Tool) => {
        setConfiguringTool(tool)
        setConfigDialogOpen(true)
    }

    // 编辑工具
    const handleEdit = async (tool: Tool) => {
        if (!tool.id) {
            if (tool.requires_config) {
                handleConfigureTool(tool)
            }
            return
        }

        // 对于代码工具，直接跳转
        if (tool.type === 'custom' && tool.custom_type === 'code') {
            router.push(`/capabilities/code?id=${tool.id}`)
            return
        }

        try {
            const detail = await adminToolsApi.getById(tool.id)

            if (detail.type === 'mcp') {
                setEditingMcpTool(detail)
                setMcpDialogOpen(true)
            } else if (detail.type === 'custom') {
                if (detail.custom_type === 'http') {
                    setEditingHttpTool(detail)
                    setHttpDialogOpen(true)
                } else if (detail.custom_type === 'code') {
                    router.push(`/capabilities/code?id=${tool.id}`)
                } else {
                    // 未知的自定义工具类型，尝试根据配置判断
                    if (detail.http_config && Object.keys(detail.http_config).length > 0) {
                        setEditingHttpTool(detail)
                        setHttpDialogOpen(true)
                    } else if (detail.code_config && Object.keys(detail.code_config).length > 0) {
                        router.push(`/capabilities/code?id=${tool.id}`)
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
                await adminToolsApi.update(editingHttpTool.id, data as ToolUpdateInput)
                toast.success(t('toolUpdated'))
            } else {
                await adminToolsApi.create(currentTeamId, data as ToolCreateInput)
                toast.success(t('toolCreated'))
            }
            setHttpDialogOpen(false)
            setEditingHttpTool(null)
            loadTools()
        } catch (error) {
            console.error('Failed to save tool:', error)
            throw error
        }
    }

    // 保存 MCP 工具
    const handleSaveMcpTool = async (data: ToolCreateInput | ToolUpdateInput) => {
        if (!currentTeamId) return

        try {
            if (editingMcpTool?.id) {
                await adminToolsApi.update(editingMcpTool.id, data as ToolUpdateInput)
                toast.success(t('toolUpdated'))
            } else {
                await adminToolsApi.create(currentTeamId, data as ToolCreateInput)
                toast.success(t('toolCreated'))
            }
            setMcpDialogOpen(false)
            setEditingMcpTool(null)
            loadTools()
        } catch (error) {
            console.error('Failed to save tool:', error)
            throw error
        }
    }

    // 保存内置工具配置
    const handleSaveConfig = async (config: Record<string, string>) => {
        if (!currentTeamId || !configuringTool) return

        try {
            let configExists = false
            try {
                await adminToolsApi.getConfig(configuringTool.name, currentTeamId)
                configExists = true
            } catch (error: unknown) {
                const apiError = error as { response?: { status?: number } }
                if (apiError?.response?.status !== 404) {
                    throw error
                }
            }

            if (configExists) {
                await adminToolsApi.updateConfig(configuringTool.name, config, currentTeamId)
            } else {
                await adminToolsApi.createConfig(configuringTool.name, config, currentTeamId)
            }

            toast.success(t('configSaved'))
            setConfigDialogOpen(false)
            setConfiguringTool(null)
        } catch (error) {
            console.error('Failed to save config:', error)
            throw error
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
            await adminToolsApi.toggle(tool.id)
            toast.success(tool.is_enabled ? t('toolDisabled') : t('toolEnabled'))
            loadTools()
        } catch {
            // 错误已由 API 客户端处理
        }
    }

    // 复制工具
    const handleDuplicate = async (tool: Tool) => {
        if (!tool.id) return
        try {
            await adminToolsApi.duplicate(tool.id)
            toast.success(t('toolDuplicated'))
            loadTools()
        } catch {
            // 错误已由 API 客户端处理
        }
    }

    const handleExport = async (tool: Tool) => {
        if (!tool.id) return
        try {
            const { blob, filename } = await adminPackagesApi.export('tool', tool.id)
            downloadBlob(blob, filename)
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
        loadTools()
    }

    // Dialog 成功回调
    const handleDialogSuccess = () => {
        loadTools()
        setSelectedTools(new Set())
    }

    // 批量删除
    const handleBulkDelete = () => {
        setBulkDeleteDialogOpen(true)
    }

    // 确认批量删除
    const confirmBulkDelete = async () => {
        try {
            const promises = Array.from(selectedTools).map((id) => adminToolsApi.delete(id))
            await Promise.all(promises)
            toast.success(t('bulkDeleted', { count: selectedTools.size }))
            setSelectedTools(new Set())
            loadTools()
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
            skill: 'bg-sky-500/10 text-sky-500 hover:bg-sky-500/20',
        }
        return (
            <Badge variant="secondary" className={variants[type]}>
                {toolTypeIcons[type]}
                <span className="ml-1">{t(`filters.${type}`)}</span>
            </Badge>
        )
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
                    {canPerform('admin:capability:create') && currentTeamId && (
                        <Button variant="outline" onClick={() => setImportDialogOpen(true)}>
                            <Upload className="mr-2 h-4 w-4" />
                            {packageT('import')}
                        </Button>
                    )}
                    <PermissionGuard permission="admin:capability:create">
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
                    onSelectionChange={handleTypeFilterChange}
                />

                <DataTableFacetedFilter
                    title={t('category')}
                    options={categoryFilterOptions}
                    selectedValues={categoryFilter}
                    onSelectionChange={handleCategoryFilterChange}
                />

                <DataTableFacetedFilter
                    title={commonT('status')}
                    options={enabledOptions}
                    selectedValues={enabledFilter}
                    onSelectionChange={handleEnabledFilterChange}
                />

                {teamOptions.length > 1 && (
                    <DataTableFacetedFilter
                        title={commonT('team')}
                        options={teamOptions}
                        selectedValues={teamFilter}
                        onSelectionChange={handleTeamFilterChange}
                        searchable
                    />
                )}

                {creatorOptions.length > 0 && (
                    <DataTableFacetedFilter
                        title={commonT('createdBy')}
                        options={creatorOptions}
                        selectedValues={creatorFilter}
                        onSelectionChange={handleCreatorFilterChange}
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
                        ) : filteredTools.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                                    {t('noTools')}
                                </TableCell>
                            </TableRow>
                        ) : (
                            filteredTools.map((tool) => {
                                const teamName = tool.owner_team_name || teams.find((team) => team.id === tool.team_id)?.name || '-'
                                return (
                                    <TableRow
                                        key={`${tool.type}-${tool.id || tool.name}`}
                                        data-state={tool.id && selectedTools.has(tool.id) ? 'selected' : undefined}
                                    >
                                        <TableCell>
                                            {tool.type !== 'builtin' && tool.id && (
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
                                                <span className="font-medium">{tool.display_name}</span>
                                            </div>
                                        </TableCell>
                                        <TableCell>{getTypeBadge(tool.type)}</TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-1">
                                                <span className="text-sm">{isPresetToolCategory(tool.category) ? categoryIcons[tool.category] : categoryIcons.other}</span>
                                                <span>{isPresetToolCategory(tool.category) ? t(`categories.${tool.category}`) : tool.category}</span>
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
                                            {((tool.type !== 'builtin' && tool.id && (canPerform('admin:capability:read') || canPerform('admin:capability:update') || canPerform('admin:capability:delete'))) ||
                                                (tool.type === 'builtin' && tool.requires_config && canPerform('admin:capability:update'))) && (
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                                                            <MoreHorizontal className="h-4 w-4" />
                                                            <span className="sr-only">{t('common.openMenu')}</span>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end">
                                                            {canPerform('admin:capability:update') && (
                                                                <>
                                                                    <DropdownMenuItem onClick={() => handleEdit(tool)}>
                                                                        <Pencil className="mr-2 h-4 w-4" />
                                                                        {commonT('edit')}
                                                                    </DropdownMenuItem>

                                                                    {tool.type !== 'builtin' && tool.id && (
                                                                        <>
                                                                            <DropdownMenuItem onClick={() => handleDuplicate(tool)}>
                                                                                <Copy className="mr-2 h-4 w-4" />
                                                                                {t('duplicate')}
                                                                            </DropdownMenuItem>

                                                                            {canPerform('admin:capability:read') && (
                                                                                <DropdownMenuItem onClick={() => handleExport(tool)}>
                                                                                    <Download className="mr-2 h-4 w-4" />
                                                                                    {packageT('export')}
                                                                                </DropdownMenuItem>
                                                                            )}

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
                                                                </>
                                                            )}

                                                            {tool.type !== 'builtin' && tool.id && canPerform('admin:capability:delete') && (
                                                                <>
                                                                    <DropdownMenuSeparator />
                                                                    <DropdownMenuItem
                                                                        variant="destructive"
                                                                        onClick={() => handleDelete(tool)}
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
            {pageData && pageData.total > 0 && (
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
                teams={teams}
                selectedTeamId={currentTeamId}
                onSelectedTeamChange={(teamId) => setCurrentTeamId(teamId ?? '')}
            />

            {/* MCP 工具对话框 */}
            <McpToolDialog
                tool={editingMcpTool}
                open={mcpDialogOpen}
                onOpenChange={setMcpDialogOpen}
                onSave={handleSaveMcpTool}
                teams={teams}
                selectedTeamId={currentTeamId}
                onSelectedTeamChange={(teamId) => setCurrentTeamId(teamId ?? '')}
            />

            <ToolConfigDialog
                tool={configuringTool}
                open={configDialogOpen}
                onOpenChange={setConfigDialogOpen}
                onSave={handleSaveConfig}
            />

            <ImportPackageDialog
                open={importDialogOpen}
                onOpenChange={setImportDialogOpen}
                teamId={currentTeamId}
                teams={teams}
                expectedResourceType="tool"
                onImported={handleDialogSuccess}
                api={adminPackagesApi}
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
            {selectedTools.size > 0 && canPerform('admin:capability:delete') && (
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
