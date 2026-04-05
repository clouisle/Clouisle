'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
    Search,
    MoreHorizontal,
    Pencil,
    Trash2,
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
    X,
    Brain,
    User,
    ArrowRight,
    ArrowLeft,
} from 'lucide-react'
import { toast } from 'sonner'
import { memoriesApi, type MemoryEntity, type PageData } from '@/lib/api/admin/memories'
import { formatDateTime } from '@/lib/utils'
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
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { EntityDialog } from './entity-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export function MemoriesClient() {
    const t = useTranslations('memories')
    const commonT = useTranslations('common')
    const { canPerform } = useCanPerform()

    // Data state
    const [entities, setEntities] = React.useState<MemoryEntity[]>([])
    const [isLoading, setIsLoading] = React.useState(true)
    const [page, setPage] = React.useState(1)
    const [pageSize, setPageSize] = React.useState(20)
    const [pageData, setPageData] = React.useState<PageData<MemoryEntity> | null>(null)

    // Filter state
    const [searchQuery, setSearchQuery] = React.useState('')
    const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())

    // Selection state
    const [selectedEntities, setSelectedEntities] = React.useState<Set<string>>(new Set())

    // Dialog state
    const [entityDialogOpen, setEntityDialogOpen] = React.useState(false)
    const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
    const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
    const [selectedEntity, setSelectedEntity] = React.useState<MemoryEntity | null>(null)

    // Load entities
    const loadEntities = React.useCallback(async () => {
        setIsLoading(true)
        try {
            const data = await memoriesApi.getEntities({
                page,
                page_size: pageSize,
                search: searchQuery || undefined,
                entity_type: typeFilter.size > 0 ? Array.from(typeFilter) : undefined,
            })
            setEntities(data.items)
            setPageData(data)
        } catch {
            // Error handled by API client
        } finally {
            setIsLoading(false)
        }
    }, [page, pageSize, searchQuery, typeFilter])

    React.useEffect(() => {
        loadEntities()
    }, [loadEntities])

    // Reset filters
    const resetFilters = () => {
        setSearchQuery('')
        setTypeFilter(new Set())
        setPage(1)
        setSelectedEntities(new Set())
    }

    // Check if filtered
    const isFiltered = searchQuery || typeFilter.size > 0

    // Entity type options
    const typeOptions = [
        { value: 'person', label: t('types.person'), icon: <User className="h-4 w-4" /> },
        { value: 'preference', label: t('types.preference'), icon: <Brain className="h-4 w-4" /> },
        { value: 'skill', label: t('types.skill'), icon: <Brain className="h-4 w-4" /> },
        { value: 'project', label: t('types.project'), icon: <Brain className="h-4 w-4" /> },
        { value: 'goal', label: t('types.goal'), icon: <Brain className="h-4 w-4" /> },
        { value: 'fact', label: t('types.fact'), icon: <Brain className="h-4 w-4" /> },
        { value: 'concept', label: t('types.concept'), icon: <Brain className="h-4 w-4" /> },
        { value: 'organization', label: t('types.organization'), icon: <Brain className="h-4 w-4" /> },
        { value: 'location', label: t('types.location'), icon: <Brain className="h-4 w-4" /> },
        { value: 'custom', label: t('types.custom'), icon: <Brain className="h-4 w-4" /> },
    ]

    // Pagination
    const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1

    // Selection
    const toggleSelectAll = () => {
        if (selectedEntities.size === entities.length) {
            setSelectedEntities(new Set())
        } else {
            setSelectedEntities(new Set(entities.map(e => e.id)))
        }
    }

    const toggleSelectEntity = (entityId: string) => {
        const newSelected = new Set(selectedEntities)
        if (newSelected.has(entityId)) {
            newSelected.delete(entityId)
        } else {
            newSelected.add(entityId)
        }
        setSelectedEntities(newSelected)
    }

    // Edit entity
    const handleEdit = (entity: MemoryEntity) => {
        setSelectedEntity(entity)
        setEntityDialogOpen(true)
    }

    // Delete entity
    const handleDelete = (entity: MemoryEntity) => {
        setSelectedEntity(entity)
        setDeleteDialogOpen(true)
    }

    const confirmDelete = async () => {
        if (!selectedEntity) return

        try {
            await memoriesApi.deleteEntity(selectedEntity.id)
            toast.success(t('deleteEntity'))
            setDeleteDialogOpen(false)
            setSelectedEntity(null)
            loadEntities()
        } catch {
            // Error handled by API client
        }
    }

    // Bulk delete
    const handleBulkDelete = () => {
        if (selectedEntities.size === 0) return
        setBulkDeleteDialogOpen(true)
    }

    const confirmBulkDelete = async () => {
        try {
            await Promise.all(
                Array.from(selectedEntities).map(id => memoriesApi.deleteEntity(id))
            )
            toast.success(commonT('deleteSuccess'))
            setBulkDeleteDialogOpen(false)
            setSelectedEntities(new Set())
            loadEntities()
        } catch {
            // Error handled by API client
        }
    }

    // Get entity type badge color
    const getTypeBadgeColor = (type: string) => {
        const colors: Record<string, string> = {
            person: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
            preference: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
            skill: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
            project: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
            goal: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
            fact: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
            concept: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
            organization: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
            location: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300',
            custom: 'bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-300',
        }
        return colors[type] || colors.custom
    }

    return (
        <PermissionGuard permission="admin:memory:read">
            <div className="space-y-4">
                {/* Header */}
                <div>
                    <h1 className="text-2xl font-semibold">{t('title')}</h1>
                    <p className="text-sm text-muted-foreground">{t('description')}</p>
                </div>

                {/* Filters */}
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            placeholder={t('searchPlaceholder')}
                            value={searchQuery}
                            onChange={(e) => {
                                setSearchQuery(e.target.value)
                                setPage(1)
                                setSelectedEntities(new Set())
                            }}
                            className="pl-8 w-[200px] h-9"
                        />
                    </div>

                    <DataTableFacetedFilter
                        title={t('entityType')}
                        options={typeOptions}
                        selectedValues={typeFilter}
                        onSelectionChange={(values) => {
                            setTypeFilter(values)
                            setPage(1)
                            setSelectedEntities(new Set())
                        }}
                        searchable
                    />

                    {isFiltered && (
                        <Button
                            variant="ghost"
                            onClick={resetFilters}
                            className="h-9 px-2 lg:px-3"
                        >
                            {commonT('reset')}
                            <X className="ml-2 h-4 w-4" />
                        </Button>
                    )}
                </div>

                {/* Table */}
                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-12">
                                    <Checkbox
                                        checked={entities.length > 0 && selectedEntities.size === entities.length}
                                        onCheckedChange={toggleSelectAll}
                                    />
                                </TableHead>
                                <TableHead>{t('user')}</TableHead>
                                <TableHead>{t('entityName')}</TableHead>
                                <TableHead>{t('entityType')}</TableHead>
                                <TableHead>{t('description')}</TableHead>
                                <TableHead>{t('relations')}</TableHead>
                                <TableHead>{t('lastAccessed')}</TableHead>
                                <TableHead>{t('createdAt')}</TableHead>
                                <TableHead className="w-12">{t('actions')}</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {isLoading ? (
                                <TableRow>
                                    <TableCell colSpan={9} className="h-24 text-center">
                                        {commonT('loading')}
                                    </TableCell>
                                </TableRow>
                            ) : entities.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={9} className="h-24 text-center">
                                        {commonT('noData')}
                                    </TableCell>
                                </TableRow>
                            ) : (
                                entities.map((entity) => (
                                    <TableRow key={entity.id} data-state={selectedEntities.has(entity.id) ? 'selected' : undefined}>
                                        <TableCell>
                                            <Checkbox
                                                checked={selectedEntities.has(entity.id)}
                                                onCheckedChange={() => toggleSelectEntity(entity.id)}
                                            />
                                        </TableCell>
                                        <TableCell>
                                            <span className="text-sm">{entity.user_name}</span>
                                        </TableCell>
                                        <TableCell className="font-medium">{entity.name}</TableCell>
                                        <TableCell>
                                            <Badge className={getTypeBadgeColor(entity.entity_type)}>
                                                {t(`types.${entity.entity_type}`)}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            {entity.description ? (
                                                <Tooltip>
                                                    <TooltipTrigger>
                                                        <div className="line-clamp-1 max-w-[200px] text-sm text-muted-foreground">
                                                            {entity.description}
                                                        </div>
                                                    </TooltipTrigger>
                                                    <TooltipContent className="max-w-[400px]">
                                                        {entity.description}
                                                    </TooltipContent>
                                                </Tooltip>
                                            ) : (
                                                <span className="text-sm text-muted-foreground">{t('noDescription')}</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <div className="flex items-center gap-1 text-sm">
                                                {entity.outgoing_relations_count ? (
                                                    <Badge variant="outline" className="gap-1">
                                                        {entity.outgoing_relations_count}
                                                        <ArrowRight className="h-3 w-3" />
                                                    </Badge>
                                                ) : null}
                                                {entity.incoming_relations_count ? (
                                                    <Badge variant="outline" className="gap-1">
                                                        <ArrowLeft className="h-3 w-3" />
                                                        {entity.incoming_relations_count}
                                                    </Badge>
                                                ) : null}
                                                {!entity.outgoing_relations_count && !entity.incoming_relations_count && (
                                                    <span className="text-muted-foreground">-</span>
                                                )}
                                            </div>
                                        </TableCell>
                                        <TableCell className="text-sm text-muted-foreground">
                                            {entity.last_accessed_at ? formatDateTime(entity.last_accessed_at) : t('neverAccessed')}
                                        </TableCell>
                                        <TableCell className="text-sm text-muted-foreground">
                                            {formatDateTime(entity.created_at)}
                                        </TableCell>
                                        <TableCell>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger
                                                    render={(props) => (
                                                        <Button {...props} variant="ghost" size="icon" className="h-8 w-8">
                                                            <MoreHorizontal className="h-4 w-4" />
                                                        </Button>
                                                    )}
                                                />
                                                <DropdownMenuContent align="end">
                                                    {canPerform('admin:memory:update') && (
                                                        <DropdownMenuItem onClick={() => handleEdit(entity)}>
                                                            <Pencil className="mr-2 h-4 w-4" />
                                                            {t('edit')}
                                                        </DropdownMenuItem>
                                                    )}
                                                    {canPerform('admin:memory:delete') && (
                                                        <DropdownMenuItem
                                                            variant="destructive"
                                                            onClick={() => handleDelete(entity)}
                                                        >
                                                            <Trash2 className="mr-2 h-4 w-4" />
                                                            {t('delete')}
                                                        </DropdownMenuItem>
                                                    )}
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </div>

                {/* Pagination */}
                {pageData && pageData.total > 0 && (
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                {commonT('rowsPerPage')}
                            </span>
                            <Select
                                value={pageSize.toString()}
                                onValueChange={(value) => {
                                    setPageSize(Number(value))
                                    setPage(1)
                                }}
                            >
                                <SelectTrigger className="h-8 w-16">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="10">10</SelectItem>
                                    <SelectItem value="20">20</SelectItem>
                                    <SelectItem value="50">50</SelectItem>
                                    <SelectItem value="100">100</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="flex items-center gap-2">
                            <span className="text-sm text-muted-foreground">
                                {commonT('page')} {page} {commonT('of')} {totalPages}
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
                                    onClick={() => setPage(page - 1)}
                                    disabled={page === 1}
                                >
                                    <ChevronLeft className="h-4 w-4" />
                                </Button>
                                <Button
                                    variant="outline"
                                    size="icon"
                                    className="h-8 w-8"
                                    onClick={() => setPage(page + 1)}
                                    disabled={page === totalPages}
                                >
                                    <ChevronRight className="h-4 w-4" />
                                </Button>
                                <Button
                                    variant="outline"
                                    size="icon"
                                    className="h-8 w-8"
                                    onClick={() => setPage(totalPages)}
                                    disabled={page === totalPages}
                                >
                                    <ChevronsRight className="h-4 w-4" />
                                </Button>
                            </div>
                        </div>
                    </div>
                )}

                {/* 批量操作浮动工具栏 */}
                {selectedEntities.size > 0 && canPerform('admin:memory:delete') && (
                    <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
                        <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={() => setSelectedEntities(new Set())}
                            >
                                <X className="h-4 w-4" />
                            </Button>

                            <Badge variant="secondary" className="px-2 py-1">
                                {selectedEntities.size} {t('entitiesSelected')}
                            </Badge>

                            <Tooltip>
                                <TooltipTrigger
                                    onClick={handleBulkDelete}
                                    render={
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
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

                {/* Dialogs */}
                {entityDialogOpen && (
                    <EntityDialog
                        entity={selectedEntity}
                        open={entityDialogOpen}
                        onOpenChange={setEntityDialogOpen}
                        onSuccess={() => {
                            loadEntities()
                            setEntityDialogOpen(false)
                            setSelectedEntity(null)
                        }}
                    />
                )}

                {/* Delete confirmation */}
                <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>{t('deleteEntity')}</AlertDialogTitle>
                            <AlertDialogDescription>
                                {t('deleteConfirm')}
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
                            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
                                {commonT('delete')}
                            </AlertDialogAction>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>

                {/* Bulk delete confirmation */}
                <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>{t('deleteSelected')}</AlertDialogTitle>
                            <AlertDialogDescription>
                                {commonT('confirmBulkDelete', { count: selectedEntities.size })}
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
        </PermissionGuard>
    )
}
