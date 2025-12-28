'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
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
} from 'lucide-react'
import { useTeam } from '@/contexts/team-context'
import { knowledgeBasesApi, type KnowledgeBase } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
  const commonT = useTranslations('common')
  const { currentTeam } = useTeam()
  
  const [knowledgeBases, setKnowledgeBases] = React.useState<KnowledgeBase[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [searchQuery, setSearchQuery] = React.useState('')
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [editingKb, setEditingKb] = React.useState<KnowledgeBase | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingKb, setDeletingKb] = React.useState<KnowledgeBase | null>(null)
  const [isDeleting, setIsDeleting] = React.useState(false)

  const fetchKnowledgeBases = React.useCallback(async () => {
    if (!currentTeam) return
    
    try {
      setIsLoading(true)
      const data = await knowledgeBasesApi.getKnowledgeBases()
      // 过滤当前团队的知识库
      const teamKbs = data.items.filter(kb => kb.team.id === currentTeam.id)
      setKnowledgeBases(teamKbs)
    } catch (error) {
      console.error('Failed to fetch knowledge bases:', error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam])

  React.useEffect(() => {
    fetchKnowledgeBases()
  }, [fetchKnowledgeBases])

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

  const handleDelete = async () => {
    if (!deletingKb) return
    
    setIsDeleting(true)
    try {
      await knowledgeBasesApi.deleteKnowledgeBase(deletingKb.id)
      toast.success(kbT('kbDeleted'))
      setDeleteDialogOpen(false)
      setDeletingKb(null)
      fetchKnowledgeBases()
    } catch {
      // Error handled by API client
    } finally {
      setIsDeleting(false)
    }
  }

  const handleSuccess = () => {
    fetchKnowledgeBases()
  }

  // 过滤知识库
  const filteredKnowledgeBases = React.useMemo(() => {
    if (!searchQuery) return knowledgeBases
    const query = searchQuery.toLowerCase()
    return knowledgeBases.filter(kb => 
      kb.name.toLowerCase().includes(query) ||
      (kb.description && kb.description.toLowerCase().includes(query))
    )
  }, [knowledgeBases, searchQuery])

  // Loading state
  if (isLoading) {
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
        <Card 
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

        {/* Knowledge Base Cards */}
        {filteredKnowledgeBases.map((kb) => (
          <Card key={kb.id} size="sm" className="group relative hover:shadow-md transition-shadow py-0! h-36">
            <Link href={`/app/kb/${kb.id}`} className="flex flex-col justify-between px-2.5 py-4 h-full">
              <div className="flex items-center gap-2">
                <div className="rounded bg-primary/10 p-1 shrink-0">
                  <Database className="h-3.5 w-3.5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{kb.name}</div>
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
                  <DropdownMenuItem onClick={(e) => { e.preventDefault(); handleEdit(kb) }}>
                    <Pencil className="mr-2 h-4 w-4" />
                    {commonT('edit')}
                  </DropdownMenuItem>
                  <Link href={`/app/kb/${kb.id}/search`}>
                    <DropdownMenuItem>
                      <Search className="mr-2 h-4 w-4" />
                      {kbT('searchTest')}
                    </DropdownMenuItem>
                  </Link>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={(e) => { e.preventDefault(); handleDeleteClick(kb) }}
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    {commonT('delete')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </Card>
        ))}
      </div>

      {/* Empty State (when no knowledge bases or no search results) */}
      {knowledgeBases.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>{t('kb.noKbs')}</p>
          <p className="text-sm mt-1">{t('kb.createKbHint')}</p>
        </div>
      )}
      {knowledgeBases.length > 0 && filteredKnowledgeBases.length === 0 && searchQuery && (
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
        onSuccess={handleSuccess}
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
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? commonT('loading') : commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
