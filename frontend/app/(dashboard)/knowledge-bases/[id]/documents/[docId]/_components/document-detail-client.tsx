'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Play,
  RefreshCw,
  Trash2,
  Settings2,
  FileText,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  ChevronLeft,
  ChevronRight,
  Save,
  RotateCcw,
  Plus,
  GripVertical,
  AlertTriangle,
  Eye,
} from 'lucide-react'
import {
  adminKnowledgeBasesApi,
  type Document,
  type DocumentChunk,
  type PageData,
  type ProcessInput,
  type KnowledgeBase,
  type ChunkPreviewItem,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Switch } from '@/components/ui/switch'

interface DocumentDetailClientProps {
  knowledgeBaseId: string
  documentId: string
}

interface EditableChunk extends DocumentChunk {
  isEditing?: boolean
  editContent?: string
}

export function DocumentDetailClient({ knowledgeBaseId, documentId }: DocumentDetailClientProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const router = useRouter()

  // 数据状态
  const [knowledgeBase, setKnowledgeBase] = React.useState<KnowledgeBase | null>(null)
  const [document, setDocument] = React.useState<Document | null>(null)
  const [chunks, setChunks] = React.useState<EditableChunk[]>([])
  const [pageData, setPageData] = React.useState<PageData<DocumentChunk> | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isLoadingChunks, setIsLoadingChunks] = React.useState(false)
  const [page, setPage] = React.useState(1)
  const pageSize = 20

  // 操作状态
  const [isProcessing, setIsProcessing] = React.useState(false)
  const [isSaving, setIsSaving] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deleteChunkId, setDeleteChunkId] = React.useState<string | null>(null)

  // 预览状态
  const [isPreviewMode, setIsPreviewMode] = React.useState(false)
  const [isPreviewing, setIsPreviewing] = React.useState(false)
  const [previewChunks, setPreviewChunks] = React.useState<ChunkPreviewItem[]>([])
  const [previewStats, setPreviewStats] = React.useState<{
    total_chunks: number
    total_tokens: number
    total_chars: number
  } | null>(null)

  // 分块设置
  const [settings, setSettings] = React.useState<ProcessInput>({
    chunk_size: 1000,
    chunk_overlap: 100,
    separator: '',
    clean_text: true,
  })

  // 加载知识库和文档信息
  const loadData = React.useCallback(async () => {
    setIsLoading(true)
    try {
      const [kbData, docData] = await Promise.all([
        adminKnowledgeBasesApi.getKnowledgeBase(knowledgeBaseId),
        adminKnowledgeBasesApi.getDocument(knowledgeBaseId, documentId),
      ])
      setKnowledgeBase(kbData)
      setDocument(docData)
      
      // 从知识库设置或文档 metadata 初始化分块设置
      const kbSettings = kbData.settings
      const docMeta = docData.metadata as Record<string, unknown> | null
      setSettings({
        chunk_size: (docMeta?.chunk_size as number) || kbSettings?.chunk_size || 1000,
        chunk_overlap: (docMeta?.chunk_overlap as number) || kbSettings?.chunk_overlap || 100,
        separator: (docMeta?.separator as string) || kbSettings?.separator || '',
        clean_text: docMeta?.clean_text !== undefined ? (docMeta.clean_text as boolean) : true,
      })
    } catch {
      router.push(`/knowledge-bases/${knowledgeBaseId}`)
    } finally {
      setIsLoading(false)
    }
  }, [knowledgeBaseId, documentId, router])

  // 加载分块
  const loadChunks = React.useCallback(async () => {
    if (!document || document.status !== 'completed') return

    setIsLoadingChunks(true)
    try {
      const data = await adminKnowledgeBasesApi.getDocumentChunks(
        knowledgeBaseId,
        documentId,
        { page, pageSize }
      )
      setChunks(data.items.map(c => ({ ...c, isEditing: false, editContent: c.content })))
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsLoadingChunks(false)
    }
  }, [knowledgeBaseId, documentId, document, page])

  React.useEffect(() => {
    loadData()
  }, [loadData])

  React.useEffect(() => {
    if (document?.status === 'completed') {
      loadChunks()
    }
  }, [document?.status, loadChunks])

  // 自动刷新处理中的文档
  React.useEffect(() => {
    if (document?.status === 'processing' || document?.status === 'pending') {
      const timer = setInterval(async () => {
        try {
          const docData = await adminKnowledgeBasesApi.getDocument(knowledgeBaseId, documentId)
          setDocument(docData)
          if (docData.status === 'completed') {
            toast.success(t('documentProcessed'))
          } else if (docData.status === 'error') {
            toast.error(t('documentProcessFailed'))
          }
        } catch {
          // ignore
        }
      }, 3000)
      return () => clearInterval(timer)
    }
  }, [document?.status, knowledgeBaseId, documentId, t])

  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1

  // 获取状态 Badge
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 gap-1">
            <CheckCircle className="h-3 w-3" />
            {t('statusCompleted')}
          </Badge>
        )
      case 'processing': {
        const progress = document?.metadata?.embed_progress as { embedded?: number; total?: number } | undefined
        return (
          <Badge variant="default" className="bg-blue-500/10 text-blue-500 gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {progress?.total
              ? t('embeddingProgress', { embedded: progress.embedded ?? 0, total: progress.total })
              : t('statusProcessing')}
          </Badge>
        )
      }
      case 'pending':
        return (
          <Badge variant="outline" className="text-muted-foreground gap-1">
            <Clock className="h-3 w-3" />
            {t('statusPending')}
          </Badge>
        )
      case 'error':
        return (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            {t('statusFailed')}
          </Badge>
        )
      default:
        return null
    }
  }

  // 格式化文件大小
  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // 开始处理
  const handleProcess = async () => {
    if (!document) return

    setIsProcessing(true)
    try {
      await adminKnowledgeBasesApi.processDocument(
        knowledgeBaseId,
        documentId,
        {
          chunk_size: settings.chunk_size,
          chunk_overlap: settings.chunk_overlap,
          separator: settings.separator || undefined,
          clean_text: settings.clean_text,
        }
      )
      toast.success(t('processStartedSingle'))
      setIsPreviewMode(false)
      setPreviewChunks([])
      setPreviewStats(null)
      await loadData()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsProcessing(false)
    }
  }

  // 预览分块效果
  const handlePreview = async () => {
    if (!document) return

    setIsPreviewing(true)
    try {
      const result = await adminKnowledgeBasesApi.previewChunks(
        knowledgeBaseId,
        documentId,
        {
          chunk_size: settings.chunk_size || 1000,
          chunk_overlap: settings.chunk_overlap || 100,
          separator: settings.separator || undefined,
          clean_text: settings.clean_text,
        }
      )
      setPreviewChunks(result.chunks)
      setPreviewStats({
        total_chunks: result.total_chunks,
        total_tokens: result.total_tokens,
        total_chars: result.total_chars,
      })
      setIsPreviewMode(true)
      toast.success(t('previewGenerated'))
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsPreviewing(false)
    }
  }

  // 退出预览模式
  const exitPreviewMode = () => {
    setIsPreviewMode(false)
    setPreviewChunks([])
    setPreviewStats(null)
  }

  // 重新处理 - 跳转到预览编辑器页面
  const handleReprocess = () => {
    if (!document) return
    router.push(`/knowledge-bases/${knowledgeBaseId}/documents/preview?docs=${documentId}`)
  }

  // 重试失败分段
  const handleRetryFailedChunks = async () => {
    try {
      await adminKnowledgeBasesApi.retryFailedChunks(knowledgeBaseId, documentId)
      toast.success(t('retryStarted'))
      loadData()
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // 删除文档
  const handleDelete = async () => {
    try {
      await adminKnowledgeBasesApi.deleteDocument(knowledgeBaseId, documentId)
      toast.success(t('documentDeleted'))
      router.push(`/knowledge-bases/${knowledgeBaseId}`)
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  // 分块编辑功能
  const startEditing = (chunkId: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, isEditing: true } : c
    ))
  }

  const cancelEditing = (chunkId: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, isEditing: false, editContent: c.content } : c
    ))
  }

  const updateEditContent = (chunkId: string, content: string) => {
    setChunks(prev => prev.map(c =>
      c.id === chunkId ? { ...c, editContent: content } : c
    ))
  }

  const saveChunk = async (chunk: EditableChunk) => {
    if (!chunk.editContent || chunk.editContent === chunk.content) {
      cancelEditing(chunk.id)
      return
    }

    setIsSaving(true)
    try {
      const updated = await adminKnowledgeBasesApi.updateChunk(
        knowledgeBaseId,
        documentId,
        chunk.id,
        { content: chunk.editContent }
      )
      setChunks(prev => prev.map(c =>
        c.id === chunk.id ? { ...updated, isEditing: false, editContent: updated.content } : c
      ))
      toast.success(t('chunkUpdated'))
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  const deleteChunk = async () => {
    if (!deleteChunkId) return

    setIsSaving(true)
    try {
      await adminKnowledgeBasesApi.deleteChunk(knowledgeBaseId, documentId, deleteChunkId)
      toast.success(t('chunkDeleted'))
      setDeleteChunkId(null)
      // Refresh chunks list to get accurate data
      await loadChunks()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  const addNewChunk = async (afterIndex: number) => {
    setIsSaving(true)
    try {
      await adminKnowledgeBasesApi.createChunk(
        knowledgeBaseId,
        documentId,
        { content: t('newChunkPlaceholder') },
        afterIndex
      )
      await loadChunks()
      toast.success(t('chunkCreated'))
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading || !document || !knowledgeBase) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const isPending = document.status === 'pending'
  const isCompleted = document.status === 'completed'
  const isFailed = document.status === 'error'
  const isProcessingStatus = document.status === 'processing'

  return (
    <div className="flex h-full overflow-hidden gap-4 p-4">
      {/* 左侧：分块列表 */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden rounded-xl border bg-card">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 bg-muted/30">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <Button variant="ghost" size="icon" className="shrink-0" onClick={() => router.push(`/knowledge-bases/${knowledgeBaseId}`)}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
                <h1 className="text-lg font-semibold truncate" title={document.name}>
                  {document.name}
                </h1>
                {getStatusBadge(document.status)}
              </div>
              <p className="text-sm text-muted-foreground truncate">
                {knowledgeBase.name} · {formatSize(document.file_size || 0)}
                {isCompleted && ` · ${document.chunk_count} ${t('chunks')}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {(isCompleted || isFailed) && (
              <Button variant="outline" size="sm" onClick={handleReprocess}>
                <RefreshCw className="h-4 w-4 mr-2" />
                {t('reprocess')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              className="text-destructive hover:text-destructive"
              onClick={() => setDeleteDialogOpen(true)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* 分块内容区 */}
        <div className="flex-1 min-w-0 overflow-hidden">
          {isPending && !isPreviewMode && (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <Clock className="h-12 w-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium mb-2">{t('documentPending')}</h3>
              <p className="text-muted-foreground mb-4 max-w-md">
                {t('documentPendingDescription')}
              </p>
            </div>
          )}

          {isPending && isPreviewMode && (
            <>
              {previewChunks.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <FileText className="h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium mb-2">{t('noPreviewChunks')}</h3>
                </div>
              ) : (
                <ScrollArea className="h-full">
                  <div className="p-4 space-y-3">
                    {/* 预览统计信息 */}
                    {previewStats && (
                      <div className="flex items-center gap-4 p-3 rounded-lg bg-blue-500/10 border border-blue-500/30 mb-4">
                        <Eye className="h-4 w-4 text-blue-500" />
                        <span className="text-sm text-blue-600 dark:text-blue-400 font-medium">
                          {t('previewMode')}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {t('previewStats', {
                            chunks: previewStats.total_chunks,
                            tokens: previewStats.total_tokens,
                          })}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="ml-auto"
                          onClick={exitPreviewMode}
                        >
                          {t('exitPreview')}
                        </Button>
                      </div>
                    )}

                    {previewChunks.map((chunk) => (
                      <div
                        key={chunk.chunk_index}
                        className="rounded-lg border bg-card overflow-hidden"
                      >
                        {/* 分块头部 */}
                        <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary">#{chunk.chunk_index + 1}</Badge>
                            <span className="text-xs text-muted-foreground">
                              {chunk.token_count} tokens · {chunk.char_count} chars
                            </span>
                          </div>
                        </div>

                        {/* 分块内容 */}
                        <div className="p-4 overflow-hidden">
                          <p className="text-sm whitespace-pre-wrap break-all [overflow-wrap:anywhere]">
                            {chunk.content}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </>
          )}

          {isProcessingStatus && (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <Loader2 className="h-12 w-12 text-blue-500 animate-spin mb-4" />
              <h3 className="text-lg font-medium mb-2">{t('documentProcessingTitle')}</h3>
              {(() => {
                const progress = document.metadata?.embed_progress as { embedded?: number; failed?: number; total?: number } | undefined
                if (progress?.total) {
                  return (
                    <p className="text-sm text-blue-500 font-medium mb-2">
                      {t('embeddingProgress', { embedded: progress.embedded ?? 0, total: progress.total })}
                    </p>
                  )
                }
                return null
              })()}
              <p className="text-muted-foreground max-w-md">
                {t('documentProcessingDescription')}
              </p>
            </div>
          )}

          {isFailed && (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <XCircle className="h-12 w-12 text-destructive mb-4" />
              <h3 className="text-lg font-medium mb-2">{t('documentFailedTitle')}</h3>
              <p className="text-muted-foreground mb-2 max-w-md">
                {t('documentFailedDescription')}
              </p>
              {document.error_message && (
                <p className="text-sm text-destructive bg-destructive/10 rounded-lg p-3 max-w-md mb-4">
                  {document.error_message}
                </p>
              )}
              <Button variant="outline" size="sm" onClick={handleRetryFailedChunks}>
                <RotateCcw className="h-4 w-4 mr-2" />
                {t('retryFailedChunks')}
              </Button>
            </div>
          )}

          {isCompleted && (
            <>
              {isLoadingChunks ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : chunks.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <FileText className="h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium mb-2">{t('noChunks')}</h3>
                  <Button variant="outline" onClick={() => addNewChunk(-1)} disabled={isSaving}>
                    <Plus className="h-4 w-4 mr-2" />
                    {t('addFirstChunk')}
                  </Button>
                </div>
              ) : (
                <ScrollArea className="h-full w-full">
                  <div className="p-4 space-y-3 w-full overflow-hidden">
                    {chunks.map((chunk) => (
                      <div
                        key={chunk.id}
                        className="group rounded-lg border bg-card hover:border-primary/50 transition-colors overflow-hidden"
                      >
                        {/* 分块头部 */}
                        <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
                          <div className="flex items-center gap-2">
                            <GripVertical className="h-4 w-4 text-muted-foreground" />
                            <Badge variant="secondary">#{chunk.chunk_index + 1}</Badge>
                            <span className="text-xs text-muted-foreground">
                              {chunk.token_count} tokens
                            </span>
                            {chunk.status === 'failed' && (
                              <Badge variant="destructive" className="text-xs gap-1">
                                <XCircle className="h-3 w-3" />
                                {t('chunkStatusFailed')}
                              </Badge>
                            )}
                            {chunk.status === 'pending' && (
                              <Badge variant="outline" className="text-xs text-muted-foreground gap-1">
                                <Clock className="h-3 w-3" />
                                {t('chunkStatusPending')}
                              </Badge>
                            )}
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
                        <div className="p-4 overflow-hidden">
                          {chunk.isEditing ? (
                            <Textarea
                              value={chunk.editContent}
                              onChange={(e) => updateEditContent(chunk.id, e.target.value)}
                              className="min-h-30 font-mono text-sm"
                              placeholder={t('chunkContentPlaceholder')}
                            />
                          ) : (
                            <p
                              className="text-sm whitespace-pre-wrap break-all [overflow-wrap:anywhere] cursor-pointer hover:bg-muted/50 rounded p-2 -m-2 transition-colors"
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
              )}

              {/* 分页 */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between p-4 bg-muted/30">
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
        </div>
      </div>

      {/* 右侧：设置面板 */}
      <div className="w-80 shrink-0 min-h-0 flex flex-col rounded-xl border bg-card overflow-hidden">
        <div className="p-4 bg-muted/30">
          <h2 className="font-semibold flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            {t('chunkSettings')}
          </h2>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-4 space-y-5">
            {/* 分块参数 */}
            <div className="space-y-4">
              <div className="grid gap-2">
                <Label htmlFor="chunk_size">{t('chunkSize')}</Label>
                <Input
                  id="chunk_size"
                  min={100}
                  max={2000}
                  value={settings.chunk_size}
                  onChange={(e) => setSettings(prev => ({
                    ...prev,
                    chunk_size: parseInt(e.target.value) || 1000
                  }))}
                  disabled={!isPending}
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
                  value={settings.chunk_overlap}
                  onChange={(e) => setSettings(prev => ({
                    ...prev,
                    chunk_overlap: parseInt(e.target.value) || 100
                  }))}
                  disabled={!isPending}
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
                  value={settings.separator || ''}
                  onChange={(e) => setSettings(prev => ({
                    ...prev,
                    separator: e.target.value
                  }))}
                  disabled={!isPending}
                />
                <p className="text-xs text-muted-foreground">
                  {t('separatorHint')}
                </p>
              </div>

              <div className="flex items-center justify-between py-2">
                <div className="space-y-0.5">
                  <Label htmlFor="clean_text">{t('cleanText')}</Label>
                  <p className="text-xs text-muted-foreground">
                    {t('cleanTextHint')}
                  </p>
                </div>
                <Switch
                  id="clean_text"
                  checked={settings.clean_text ?? true}
                  onCheckedChange={(checked) => setSettings(prev => ({
                    ...prev,
                    clean_text: checked
                  }))}
                  disabled={!isPending}
                />
              </div>
            </div>

            {isPending && (
              <>
                {/* 提示信息 */}
                <div className="rounded-lg p-3 bg-blue-500/10 border border-blue-500/20">
                  <div className="flex gap-2">
                    <AlertTriangle className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-muted-foreground">
                      {t('processHint')}
                    </p>
                  </div>
                </div>

                {/* 预览按钮 */}
                <Button
                  variant="outline"
                  onClick={handlePreview}
                  disabled={isPreviewing || isProcessing}
                  className="w-full"
                >
                  {isPreviewing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('previewing')}
                    </>
                  ) : (
                    <>
                      <Eye className="mr-2 h-4 w-4" />
                      {t('previewChunks')}
                    </>
                  )}
                </Button>

                {/* 开始处理按钮 */}
                <Button
                  onClick={handleProcess}
                  disabled={isProcessing || isPreviewing}
                  className="w-full"
                  size="lg"
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('processing')}
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 h-4 w-4" />
                      {t('startProcessing')}
                    </>
                  )}
                </Button>
              </>
            )}

            {isCompleted && (
              <>
                {/* 重新分块提示 */}
                <div className="rounded-lg p-3 bg-amber-500/10 border border-amber-500/20">
                  <div className="flex gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
                        {t('rechunkWarningTitle')}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {t('rechunkWarningDescription')}
                      </p>
                    </div>
                  </div>
                </div>

                <p className="text-xs text-muted-foreground text-center">
                  {t('settingsReadOnly')}
                </p>
              </>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* 删除文档确认 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteDocumentConfirm', { name: document.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 删除分块确认 */}
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
    </div>
  )
}
