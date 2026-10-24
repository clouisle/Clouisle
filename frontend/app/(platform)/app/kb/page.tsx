'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useSearchParams, useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { 
  Database, 
  Plus, 
  FileText, 
  Layers, 
  MoreHorizontal,
  Pencil,
  Trash2,
  Search,
  Upload,
  Download,
  Share2,
} from 'lucide-react'
import { useTeam } from '@/contexts/team-context'
import { useRequireTeam } from '@/hooks/use-require-team'
import { usePermissions } from '@/hooks/use-permissions'
import { useDebounce } from '@/hooks/use-debounce'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { knowledgeBasesApi, teamsApi, type KnowledgeBase, type UserTeamInfo } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { KnowledgeBaseDialog } from './_components/kb-dialog'
import { KnowledgeBaseShareDialog } from './_components/kb-share-dialog'
import { useCanPerform } from '@/components/permission-guard'
import { ImportPackageDialog } from '@/components/packages/import-package-dialog'
import { downloadBlob, packagesApi } from '@/lib/api/packages'

const PAGE_SIZE = 20

// 格式化 token 数量
function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M tokens`
  }
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K tokens`
  }
  return `${tokens} tokens`
}

export default function KnowledgeBasePage() {
  const t = useTranslations('platform')
  const kbT = useTranslations('knowledgeBases')
  const packageT = useTranslations('packages')
  const commonT = useTranslations('common')
  const { currentTeam } = useTeam()
  const { user } = usePermissions()
  const { canPerform } = useCanPerform()
  const searchParams = useSearchParams()
  const router = useRouter()

  // 没有团队时重定向到首页
  useRequireTeam()
  
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [page, setPage] = React.useState(1)
  const [hasMore, setHasMore] = React.useState(false)
  const [isInitialLoading, setIsInitialLoading] = React.useState(true)
  const [isLoadingMore, setIsLoadingMore] = React.useState(false)
  const [loadError, setLoadError] = React.useState(false)
  const [searchQuery, setSearchQuery] = React.useState('')
  const debouncedSearch = useDebounce(searchQuery.trim(), 300)
  const requestIdRef = React.useRef(0)
  const hasLoadedOnceRef = React.useRef(false)
  const inFlightRef = React.useRef(false)
  const failedRequestRef = React.useRef<{ page: number; append: boolean } | null>(null)
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [importDialogOpen, setImportDialogOpen] = React.useState(false)
  const [editingKb, setEditingKb] = React.useState<KnowledgeBase | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingKb, setDeletingKb] = React.useState<KnowledgeBase | null>(null)
  const [isDeleting, setIsDeleting] = React.useState(false)
  const [shareDialogOpen, setShareDialogOpen] = React.useState(false)
  const [sharingKb, setSharingKb] = React.useState<KnowledgeBase | null>(null)
  const [availableTeams, setAvailableTeams] = React.useState<UserTeamInfo[]>([])

  const teamId = currentTeam?.id ?? null

  const fetchPage = React.useCallback(async (pageToLoad: number, append: boolean) => {
    if (append && inFlightRef.current) return

    const requestId = ++requestIdRef.current
    inFlightRef.current = true
    failedRequestRef.current = null

    if (!teamId) {
      setKnowledgeBases([])
      setHasMore(false)
      setIsLoadingMore(false)
      inFlightRef.current = false
      return
    }

    setLoadError(false)
    if (append) {
      setIsLoadingMore(true)
    } else {
      setIsInitialLoading(true)
      setIsLoadingMore(false)
      setHasMore(false)
    }

    try {
      const data = await knowledgeBasesApi.getKnowledgeBases({
        teamId,
        includeShared: true,
        page: pageToLoad,
        pageSize: PAGE_SIZE,
        search: debouncedSearch || undefined,
      })
      if (requestId !== requestIdRef.current) return

      const incoming = data.items.filter(
        (kb) => kb.team.id === teamId || kb.is_owned === false
      )
      setKnowledgeBases((previous) => {
        if (!append) return incoming
        const merged = [...previous]
        const seen = new Set(previous.map((kb) => kb.id))
        for (const kb of incoming) {
          if (seen.has(kb.id)) continue
          seen.add(kb.id)
          merged.push(kb)
        }
        return merged
      })
      setPage(pageToLoad)
      setHasMore(pageToLoad * data.page_size < data.total)
    } catch (error) {
      if (requestId !== requestIdRef.current) return
      console.error('Failed to fetch knowledge bases:', error)
      failedRequestRef.current = { page: pageToLoad, append }
      setLoadError(true)
      setHasMore(false)
      if (!append) {
        setKnowledgeBases([])
      }
    } finally {
      if (requestId === requestIdRef.current) {
        inFlightRef.current = false
        if (append) {
          setIsLoadingMore(false)
        } else {
          hasLoadedOnceRef.current = true
          setIsInitialLoading(false)
        }
      }
    }
  }, [teamId, debouncedSearch])

  React.useEffect(() => {
    void fetchPage(1, false)
    return () => {
      requestIdRef.current += 1
    }
  }, [fetchPage])

  const reload = React.useCallback(() => {
    void fetchPage(1, false)
  }, [fetchPage])

  const loadMore = React.useCallback(() => {
    if (inFlightRef.current || loadError || isLoadingMore || isInitialLoading || !hasMore) return
    void fetchPage(page + 1, true)
  }, [fetchPage, hasMore, isInitialLoading, isLoadingMore, loadError, page])

  const sentinelRef = useInfiniteScroll({
    hasMore: hasMore && !loadError,
    loading: isInitialLoading || isLoadingMore,
    onLoadMore: loadMore,
  })

  const handleRetry = () => {
    const failed = failedRequestRef.current
    if (inFlightRef.current || !failed) return
    void fetchPage(failed.page, failed.append)
  }

  React.useEffect(() => {
    const loadTeams = async () => {
      try {
        const teams = await teamsApi.getMyTeams()
        setAvailableTeams(teams)
      } catch (error) {
        console.error('Failed to load teams:', error)
      }
    }
    loadTeams()
  }, [])

  // Auto-open create dialog when navigated with ?action=create
  React.useEffect(() => {
    const actionParam = searchParams.get('action')
    if (actionParam === 'create') {
      setDialogOpen(true)
      // Clear URL params to avoid re-opening on refresh
      const params = new URLSearchParams(searchParams.toString())
      params.delete('action')
      const queryString = params.toString()
      router.replace(window.location.pathname + (queryString ? `?${queryString}` : ''), { scroll: false })
    }
  }, [searchParams, router])

  const handleCreate = () => {
    setEditingKb(null)
    setDialogOpen(true)
  }

  const handleEdit = (kb: KnowledgeBase) => {
    setEditingKb(kb)
    setDialogOpen(true)
  }

  const handleDeleteClick = (kb: KnowledgeBase) => {
    setDeletingKb(kb)
    setDeleteDialogOpen(true)
  }

  const handleShareClick = (kb: KnowledgeBase) => {
    setSharingKb(kb)
    setShareDialogOpen(true)
  }

  const handleExport = async (kb: KnowledgeBase) => {
    try {
      const { blob, filename } = await packagesApi.export('knowledge_base', kb.id)
      downloadBlob(blob, filename)
    } catch {
      // Error handled by API client
    }
  }

  const handleDelete = async () => {
    if (!deletingKb) return
    
    setIsDeleting(true)
    try {
      await knowledgeBasesApi.deleteKnowledgeBase(deletingKb.id)
      toast.success(kbT('kbDeleted'))
      setDeleteDialogOpen(false)
      setDeletingKb(null)
      reload()
    } catch {
      // Error handled by API client
    } finally {
      setIsDeleting(false)
    }
  }

  const isTeamAdmin = Boolean(user?.is_superuser || currentTeam?.role === 'owner' || currentTeam?.role === 'admin')
  const isKbOwner = (kb: KnowledgeBase) => Boolean(user?.id && kb.created_by?.id === user.id)
  const canEditKb = (kb: KnowledgeBase) => kb.is_owned !== false && (isTeamAdmin || isKbOwner(kb))
  const canExportKb = (kb: KnowledgeBase) => isTeamAdmin || isKbOwner(kb)
  const canDeleteKb = (kb?: KnowledgeBase) => (kb ? kb.is_owned !== false && isTeamAdmin : isTeamAdmin)
  const canShareKb = (kb: KnowledgeBase) => kb.is_owned !== false && isTeamAdmin

  // Loading state
  if (isInitialLoading && !hasLoadedOnceRef.current) {
    return (
      <div className="py-6 px-8 h-full overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Skeleton className="h-9 w-32" />
            <Skeleton className="h-5 w-64 mt-1" />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="py-6 px-8 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('kb.title')}</h1>
          <p className="text-muted-foreground mt-1">
            {t('kb.description')}
          </p>
        </div>
        {currentTeam && canPerform('kb:create') && (
          <Button data-testid="kb-import-button" variant="outline" onClick={() => setImportDialogOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            {packageT('import')}
          </Button>
        )}
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 mb-6">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={kbT('searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 w-64 h-9"
          />
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {/* Create New Card */}
        {canPerform('kb:create') && (
          <Card
            data-testid="kb-create-card"
            size="sm"
            className="border-dashed cursor-pointer hover:border-primary/50 hover:bg-muted/50 transition-colors group py-0! h-36"
            onClick={handleCreate}
          >
            <CardContent className="flex flex-col items-center justify-center h-full text-muted-foreground group-hover:text-primary transition-colors">
              <div className="rounded-full bg-muted p-1.5 mb-1 group-hover:bg-primary/10 transition-colors">
                <Plus className="h-4 w-4" />
              </div>
              <span className="text-xs font-medium">{t('kb.createKb')}</span>
            </CardContent>
          </Card>
        )}

        {/* Knowledge Base Cards */}
        {knowledgeBases.map((kb) => (
          <Card key={kb.id} size="sm" className="group relative hover:shadow-md transition-shadow py-0! h-36">
            <Link href={`/app/kb/${kb.id}`} className="flex flex-col justify-between px-2.5 py-4 h-full">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Database className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-sm font-medium truncate">{kb.name}</span>
                    {kb.visibility === 'private' && (
                      <Badge
                        variant="outline"
                        className="text-[10px] px-1.5 py-0 border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300 shrink-0"
                      >
                        {kbT('visibilityPrivate')}
                      </Badge>
                    )}
                    {kb.is_owned === false && (
                      <Badge
                        variant="outline"
                        className="text-[10px] px-1.5 py-0 border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/50 dark:text-blue-300 shrink-0"
                      >
                        {kb.owner_team_name
                          ? t('kb.sharedFrom', { teamName: kb.owner_team_name })
                          : t('kb.shared')}
                      </Badge>
                    )}
                    {kb.is_owned !== false && (kb.shared_with_count ?? 0) > 0 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0 shrink-0">
                        {t('kb.sharedCount', { count: kb.shared_with_count || 0 })}
                      </Badge>
                    )}
                  </div>
                  {kb.created_by && (
                    <p className="text-xs text-muted-foreground">
                      {kbT('createdBy')}：{kb.created_by.username}
                    </p>
                  )}
                </div>
              </div>
              {kb.description && (
                <p className="line-clamp-2 mt-1 text-xs text-muted-foreground leading-relaxed">
                  {kb.description}
                </p>
              )}
              <div className="flex items-center gap-3 text-xs text-muted-foreground border-t mt-1.5 pt-1.5">
                <div className="flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  <span>{kb.document_count} {kbT('documents')}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Layers className="h-3 w-3" />
                  <span>{kb.total_chunks} {kbT('chunks')}</span>
                </div>
                <div className="flex-1 text-right">
                  <span>{formatTokens(kb.total_tokens)}</span>
                </div>
              </div>
            </Link>
            
            {/* Actions Menu */}
            <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={(props) => (
                    <Button {...props} variant="ghost" size="icon" className="h-7 w-7">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  )}
                />
                <DropdownMenuContent align="end">
                  {canEditKb(kb) && (
                    <DropdownMenuItem onClick={(e) => { e.preventDefault(); handleEdit(kb) }}>
                      <Pencil className="mr-2 h-4 w-4" />
                      {commonT('edit')}
                    </DropdownMenuItem>
                  )}
                  <Link href={`/app/kb/${kb.id}/search`}>
                    <DropdownMenuItem>
                      <Search className="mr-2 h-4 w-4" />
                      {kbT('searchTest')}
                    </DropdownMenuItem>
                  </Link>
                  {canExportKb(kb) && (
                    <DropdownMenuItem onClick={(e) => { e.preventDefault(); handleExport(kb) }}>
                      <Download className="mr-2 h-4 w-4" />
                      {packageT('export')}
                    </DropdownMenuItem>
                  )}
                  {canShareKb(kb) && (
                    <DropdownMenuItem onClick={(e) => { e.preventDefault(); handleShareClick(kb) }}>
                      <Share2 className="mr-2 h-4 w-4" />
                      {t('kb.shareAction')}
                    </DropdownMenuItem>
                  )}
                  {canDeleteKb(kb) && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        variant="destructive"
                        onClick={(e) => { e.preventDefault(); handleDeleteClick(kb) }}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {commonT('delete')}
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </Card>
        ))}
      </div>

      {isLoadingMore && (
        <div className="py-4 text-center text-sm text-muted-foreground">
          {commonT('loadingMore')}
        </div>
      )}

      {loadError && (
        <div className="flex flex-col items-center gap-2 py-4 text-sm text-muted-foreground">
          <p>{commonT('loadFailed')}</p>
          <Button variant="outline" size="sm" onClick={handleRetry}>
            {commonT('retry')}
          </Button>
        </div>
      )}

      <div ref={sentinelRef} aria-hidden="true" className="h-px" />

      {/* Empty State (when no knowledge bases or no search results) */}
      {knowledgeBases.length === 0 && !loadError && !searchQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('kb.noKbs')}</p>
          <p className="text-sm mt-1">{t('kb.createKbHint')}</p>
        </div>
      )}
      {knowledgeBases.length === 0 && !loadError && searchQuery && (
        <div className="text-center py-12 text-muted-foreground">
          <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{kbT('noSearchResults')}</p>
          <Button variant="outline" className="mt-4" onClick={() => setSearchQuery('')}>
            {commonT('clearFilters')}
          </Button>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <KnowledgeBaseDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        knowledgeBase={editingKb}
        onSuccess={reload}
      />

      {currentTeam && (
        <ImportPackageDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          teamId={currentTeam.id}
          expectedResourceType="knowledge_base"
          onImported={reload}
        />
      )}


      <KnowledgeBaseShareDialog
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        knowledgeBase={sharingKb}
        currentTeamId={currentTeam?.id || ''}
        availableTeams={availableTeams}
        onSuccess={reload}
      />
      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{kbT('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {kbT('deleteKbConfirm', { name: deletingKb?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>
              {commonT('cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? commonT('loading') : commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
