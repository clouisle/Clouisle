'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  ChevronLeft,
  ChevronRight,
  Loader2,
  Save,
  Trash2,
  Plus,
  RotateCcw,
  Settings2,
  GripVertical,
  AlertTriangle,
} from 'lucide-react'
import { knowledgeBasesApi, type Document, type DocumentChunk, type PageData } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface ChunkEditorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBaseId: string
  document: Document | null
  onDocumentUpdated?: () => void
}

interface EditableChunk extends DocumentChunk {
  isEditing?: boolean
  editContent?: string
  isNew?: boolean
  isDeleted?: boolean
}

export function ChunkEditorDialog({
  open,
  onOpenChange,
  knowledgeBaseId,
  document,
  onDocumentUpdated,
}: ChunkEditorDialogProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')

  const [chunks, setChunks] = React.useState<EditableChunk[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [isSaving, setIsSaving] = React.useState(false)
  const [page, setPage] = React.useState(1)
  const [pageData, setPageData] = React.useState<PageData<DocumentChunk> | null>(null)
  const [activeTab, setActiveTab] = React.useState('chunks')
  const [deleteChunkId, setDeleteChunkId] = React.useState<string | null>(null)
  const [hasChanges, setHasChanges] = React.useState(false)

  // 重新分块设置
  const [rechunkSettings, setRechunkSettings] = React.useState({
    chunk_size: 1000,
    chunk_overlap: 100,
    separator: '',
  })
  const [isRechunking, setIsRechunking] = React.useState(false)

  const pageSize = 20

  // 加载分块
  const loadChunks = React.useCallback(async () => {
    if (!document) return

    setIsLoading(true)
    try {
      const data = await knowledgeBasesApi.getDocumentChunks(
        knowledgeBaseId,
        document.id,
        { page, pageSize }
      )
      setChunks(data.items.map(c => ({ ...c, isEditing: false, editContent: c.content })))
      setPageData(data)
      setHasChanges(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoading(false)
    }
  }, [knowledgeBaseId, document, page])

  React.useEffect(() => {
    if (open && document) {
      loadChunks()
    }
  }, [open, document, loadChunks])

  // 重置
  React.useEffect(() => {
    if (!open) {
      setPage(1)
      setChunks([])
      setPageData(null)
      setActiveTab('chunks')
      setHasChanges(false)
    }
  }, [open])

  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1

  // 开始编辑分块
  const startEditing = (chunkId: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, isEditing: true } : c
    ))
  }

  // 取消编辑
  const cancelEditing = (chunkId: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, isEditing: false, editContent: c.content } : c
    ))
  }

  // 更新编辑内容
  const updateEditContent = (chunkId: string, content: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, editContent: content } : c
    ))
    setHasChanges(true)
  }

  // 保存单个分块
  const saveChunk = async (chunk: EditableChunk) => {
    if (!document || !chunk.editContent || chunk.editContent === chunk.content) {
      cancelEditing(chunk.id)
      return
    }

    setIsSaving(true)
    try {
      const updated = await knowledgeBasesApi.updateChunk(
        knowledgeBaseId,
        document.id,
        chunk.id,
        { content: chunk.editContent }
      )
      setChunks(prev => prev.map(c =>
        c.id === chunk.id ? { ...updated, isEditing: false, editContent: updated.content } : c
      ))
      toast.success(t('chunkUpdated'))
      onDocumentUpdated?.()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  // 删除分块
  const deleteChunk = async () => {
    if (!document || !deleteChunkId) return

    setIsSaving(true)
    try {
      await knowledgeBasesApi.deleteChunk(knowledgeBaseId, document.id, deleteChunkId)
      toast.success(t('chunkDeleted'))
      setDeleteChunkId(null)
      // Refresh chunks list to get accurate data
      await loadChunks()
      onDocumentUpdated?.()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  // 添加新分块
  const addNewChunk = async (afterIndex: number) => {
    if (!document) return

    setIsSaving(true)
    try {
      await knowledgeBasesApi.createChunk(
        knowledgeBaseId,
        document.id,
        { content: t('newChunkPlaceholder') },
        afterIndex
      )
      // 重新加载以获取正确的顺序
      await loadChunks()
      toast.success(t('chunkCreated'))
      onDocumentUpdated?.()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  // 重新分块
  const handleRechunk = async () => {
    if (!document) return

    setIsRechunking(true)
    try {
      await knowledgeBasesApi.rechunkDocument(
        knowledgeBaseId,
        document.id,
        {
          chunk_size: rechunkSettings.chunk_size,
          chunk_overlap: rechunkSettings.chunk_overlap,
          separator: rechunkSettings.separator || undefined,
        }
      )
      toast.success(t('rechunkStarted'))
      onDocumentUpdated?.()
      onOpenChange(false)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsRechunking(false)
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-225 max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {t('chunkEditor')}
              {hasChanges && (
                <Badge variant="outline" className="text-amber-500 border-amber-500">
                  {t('unsavedChanges')}
                </Badge>
              )}
            </DialogTitle>
            <DialogDescription>
              {document?.name} - {t('totalChunksCount', { count: pageData?.total || document?.chunk_count || 0 })}
            </DialogDescription>
          </DialogHeader>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="chunks">{t('editChunks')}</TabsTrigger>
              <TabsTrigger value="settings">{t('chunkSettings')}</TabsTrigger>
            </TabsList>

            <TabsContent value="chunks" className="flex-1 flex flex-col min-h-0 mt-4">
              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : chunks.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <p>{t('noChunks')}</p>
                  <Button
                    variant="outline"
                    className="mt-4"
                    onClick={() => addNewChunk(-1)}
                    disabled={isSaving}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    {t('addFirstChunk')}
                  </Button>
                </div>
              ) : (
                <>
                  <ScrollArea className="flex-1 pr-4">
                    <div className="space-y-3">
                      {chunks.map((chunk) => (
                        <div
                          key={chunk.id}
                          className="group rounded-lg border bg-card hover:border-primary/50 transition-colors"
                        >
                          {/* 分块头部 */}
                          <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
                            <div className="flex items-center gap-2">
                              <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab" />
                              <Badge variant="secondary">#{chunk.chunk_index + 1}</Badge>
                              <span className="text-xs text-muted-foreground">
                                {chunk.token_count} tokens
                              </span>
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              {chunk.isEditing ? (
                                <>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={() => saveChunk(chunk)}
                                    disabled={isSaving}
                                  >
                                    <Save className="h-3.5 w-3.5" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={() => cancelEditing(chunk.id)}
                                  >
                                    <RotateCcw className="h-3.5 w-3.5" />
                                  </Button>
                                </>
                              ) : (
                                <>
                                  <Tooltip>
                                    <TooltipTrigger
                                      render={
                                        <Button
                                          variant="ghost"
                                          size="icon"
                                          className="h-7 w-7"
                                          onClick={() => addNewChunk(chunk.chunk_index)}
                                          disabled={isSaving}
                                        >
                                          <Plus className="h-3.5 w-3.5" />
                                        </Button>
                                      }
                                    />
                                    <TooltipContent>{t('insertChunkAfter')}</TooltipContent>
                                  </Tooltip>
                                  <Tooltip>
                                    <TooltipTrigger
                                      render={
                                        <Button
                                          variant="ghost"
                                          size="icon"
                                          className="h-7 w-7 text-destructive hover:text-destructive"
                                          onClick={() => setDeleteChunkId(chunk.id)}
                                          disabled={isSaving}
                                        >
                                          <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                      }
                                    />
                                    <TooltipContent>{t('deleteChunk')}</TooltipContent>
                                  </Tooltip>
                                </>
                              )}
                            </div>
                          </div>

                          {/* 分块内容 */}
                          <div className="p-4">
                            {chunk.isEditing ? (
                              <Textarea
                                value={chunk.editContent}
                                onChange={(e) => updateEditContent(chunk.id, e.target.value)}
                                className="min-h-30 font-mono text-sm"
                                placeholder={t('chunkContentPlaceholder')}
                              />
                            ) : (
                              <p
                                className="text-sm whitespace-pre-wrap cursor-pointer hover:bg-muted/50 rounded p-2 -m-2 transition-colors"
                                onClick={() => startEditing(chunk.id)}
                              >
                                {chunk.content}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>

                  {/* 分页 */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between pt-4 border-t mt-4">
                      <span className="text-sm text-muted-foreground">
                        {t('pageInfo', { page, total: totalPages })}
                      </span>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => setPage(p => Math.max(1, p - 1))}
                          disabled={page === 1}
                        >
                          <ChevronLeft className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                          disabled={page >= totalPages}
                        >
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </TabsContent>

            <TabsContent value="settings" className="flex-1 mt-4">
              <div className="space-y-6">
                <div className="rounded-lg border p-4 bg-amber-500/10 border-amber-500/30">
                  <div className="flex gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium text-amber-600 dark:text-amber-400">
                        {t('rechunkWarningTitle')}
                      </p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {t('rechunkWarningDescription')}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <Label htmlFor="chunk_size">{t('chunkSize')}</Label>
                    <Input
                      id="chunk_size"
                      min={100}
                      max={2000}
                      value={rechunkSettings.chunk_size}
                      onChange={(e) => setRechunkSettings(prev => ({
                        ...prev,
                        chunk_size: parseInt(e.target.value) || 1000
                      }))}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t('chunkSizeHint')}
                    </p>
                  </div>

                  <div className="grid gap-2">
                    <Label htmlFor="chunk_overlap">{t('chunkOverlap')}</Label>
                    <Input
                      id="chunk_overlap"
                      min={0}
                      max={500}
                      value={rechunkSettings.chunk_overlap}
                      onChange={(e) => setRechunkSettings(prev => ({
                        ...prev,
                        chunk_overlap: parseInt(e.target.value) || 100
                      }))}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t('chunkOverlapHint')}
                    </p>
                  </div>

                  <div className="grid gap-2">
                    <Label htmlFor="separator">{t('customSeparator')}</Label>
                    <Input
                      id="separator"
                      type="text"
                      placeholder={t('separatorPlaceholder')}
                      value={rechunkSettings.separator}
                      onChange={(e) => setRechunkSettings(prev => ({
                        ...prev,
                        separator: e.target.value
                      }))}
                    />
                    <p className="text-xs text-muted-foreground">
                      {t('separatorHint')}
                    </p>
                  </div>
                </div>

                <Separator />

                <Button
                  onClick={handleRechunk}
                  disabled={isRechunking || document?.status === 'processing'}
                  className="w-full"
                >
                  {isRechunking ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {t('rechunking')}
                    </>
                  ) : (
                    <>
                      <Settings2 className="h-4 w-4 mr-2" />
                      {t('applyRechunk')}
                    </>
                  )}
                </Button>
              </div>
            </TabsContent>
          </Tabs>

          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {commonT('close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <AlertDialog open={!!deleteChunkId} onOpenChange={(open) => !open && setDeleteChunkId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteChunkConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={deleteChunk}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
