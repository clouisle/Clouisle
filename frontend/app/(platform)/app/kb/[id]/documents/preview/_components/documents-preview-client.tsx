'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Play,
  FileText,
  Loader2,
  Settings2,
  Eye,
  AlertTriangle,
  CheckCircle2,
  X,
  Pencil,
  Check,
  Trash2,
  Plus,
} from 'lucide-react'
import {
  knowledgeBasesApi,
  type Document,
  type ProcessInput,
  type KnowledgeBase,
  type ChunkPreviewItem,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface DocumentsPreviewClientProps {
  knowledgeBaseId: string
  documentIds: string[]
}

interface DocumentPreviewState {
  document: Document | null
  previewChunks: ChunkPreviewItem[]
  previewStats: {
    total_chunks: number
    total_tokens: number
    total_chars: number
  } | null
  isPreviewing: boolean
  isProcessing: boolean
  error: string | null
}

export function DocumentsPreviewClient({ knowledgeBaseId, documentIds }: DocumentsPreviewClientProps) {
  const t = useTranslations('knowledgeBases')
  const router = useRouter()

  // 知识库信息
  const [knowledgeBase, setKnowledgeBase] = React.useState<KnowledgeBase | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  // 各文档的状态
  const [documentsState, setDocumentsState] = React.useState<Record<string, DocumentPreviewState>>({})
  
  // 当前选中的文档 tab
  const [activeDocId, setActiveDocId] = React.useState<string>(documentIds[0] || '')

  // 编辑状态：记录正在编辑的分块 { docId: chunkIndex }
  const [editingChunk, setEditingChunk] = React.useState<{ docId: string; chunkIndex: number } | null>(null)
  const [editingContent, setEditingContent] = React.useState<string>('')

  // 统一的分块设置
  const [settings, setSettings] = React.useState<ProcessInput>({
    chunk_size: 1000,
    chunk_overlap: 100,
    separator: '',
    clean_text: true,
  })

  // 当设置变更时清除所有预览（用户需要重新预览）
  const handleSettingsChange = React.useCallback((newSettings: ProcessInput | ((prev: ProcessInput) => ProcessInput)) => {
    setSettings(newSettings)
    // 清除所有文档的预览分块
    setDocumentsState(prev => {
      const updated: Record<string, DocumentPreviewState> = {}
      Object.entries(prev).forEach(([docId, state]) => {
        updated[docId] = {
          ...state,
          previewChunks: [],
          previewStats: null,
        }
      })
      return updated
    })
  }, [])

  // 加载知识库和文档信息
  const loadData = React.useCallback(async () => {
    if (documentIds.length === 0) {
      router.push(`/app/kb/${knowledgeBaseId}`)
      return
    }

    setIsLoading(true)
    try {
      // 加载知识库信息
      const kbData = await knowledgeBasesApi.getKnowledgeBase(knowledgeBaseId)
      setKnowledgeBase(kbData)

      // 从知识库设置初始化分块设置
      const kbSettings = kbData.settings
      setSettings({
        chunk_size: kbSettings?.chunk_size ?? 1000,
        chunk_overlap: kbSettings?.chunk_overlap ?? 100,
        separator: kbSettings?.separator ?? '',
        clean_text: true,
      })

      // 并行加载所有文档
      const docsPromises = documentIds.map(id => 
        knowledgeBasesApi.getDocument(knowledgeBaseId, id).catch(() => null)
      )
      const docs = await Promise.all(docsPromises)

      // 初始化每个文档的状态
      const initialState: Record<string, DocumentPreviewState> = {}
      docs.forEach((doc, idx) => {
        if (doc) {
          initialState[documentIds[idx]] = {
            document: doc,
            previewChunks: [],
            previewStats: null,
            isPreviewing: false,
            isProcessing: false,
            error: null,
          }
        }
      })
      setDocumentsState(initialState)

      // 设置默认选中第一个有效文档
      const firstValidId = documentIds.find(id => initialState[id])
      if (firstValidId) {
        setActiveDocId(firstValidId)
      }
    } catch {
      router.push(`/app/kb/${knowledgeBaseId}`)
    } finally {
      setIsLoading(false)
    }
  }, [knowledgeBaseId, documentIds, router])

  React.useEffect(() => {
    loadData()
  }, [loadData])

  // 预览单个文档
  const handlePreviewDocument = async (docId: string) => {
    setDocumentsState(prev => ({
      ...prev,
      [docId]: { ...prev[docId], isPreviewing: true, error: null }
    }))

    try {
      const result = await knowledgeBasesApi.previewChunks(
        knowledgeBaseId,
        docId,
        {
          chunk_size: settings.chunk_size ?? 1000,
          chunk_overlap: settings.chunk_overlap ?? 100,
          separator: settings.separator || undefined,
          clean_text: settings.clean_text,
        }
      )
      setDocumentsState(prev => ({
        ...prev,
        [docId]: {
          ...prev[docId],
          previewChunks: result.chunks,
          previewStats: {
            total_chunks: result.total_chunks,
            total_tokens: result.total_tokens,
            total_chars: result.total_chars,
          },
          isPreviewing: false,
        }
      }))
    } catch (error) {
      setDocumentsState(prev => ({
        ...prev,
        [docId]: {
          ...prev[docId],
          isPreviewing: false,
          error: error instanceof Error ? error.message : t('previewFailed'),
        }
      }))
    }
  }

  // 预览全部文档
  const handlePreviewAll = async () => {
    // 获取所有可处理的文档（排除 processing 状态）
    const pendingDocs = Object.entries(documentsState)
      .filter(([, state]) => state.document && state.document.status !== 'processing')
      .map(([id]) => id)

    // 标记所有待处理的文档为预览中
    setDocumentsState(prev => {
      const newState = { ...prev }
      pendingDocs.forEach(id => {
        newState[id] = { ...newState[id], isPreviewing: true, error: null }
      })
      return newState
    })

    // 并行预览所有文档
    await Promise.all(pendingDocs.map(docId => handlePreviewDocument(docId)))
    toast.success(t('batchPreviewGenerated'))
  }

  // 处理单个文档 - 使用前端已编辑的分块
  const handleProcessDocument = async (docId: string) => {
    const docState = documentsState[docId]
    
    // 如果没有预览分块，先生成预览
    if (!docState?.previewChunks || docState.previewChunks.length === 0) {
      toast.error(t('noPreviewChunks'))
      return
    }

    setDocumentsState(prev => ({
      ...prev,
      [docId]: { ...prev[docId], isProcessing: true }
    }))

    try {
      // 使用前端已编辑的分块直接提交
      const chunks = docState.previewChunks.map(chunk => ({
        content: chunk.content,
        chunk_index: chunk.chunk_index,
      }))

      const result = await knowledgeBasesApi.processDocumentWithChunks(
        knowledgeBaseId,
        docId,
        chunks
      )

      // 更新文档状态 - API 返回的状态可能是 processing（因为 Celery 任务是异步的）
      setDocumentsState(prev => ({
        ...prev,
        [docId]: {
          ...prev[docId],
          document: result,
          isProcessing: false,
        }
      }))
      
      // 检查返回的文档状态
      if (result.status === 'error') {
        toast.error(result.error_message || t('documentProcessFailed'))
      } else {
        // processing 或其他状态都表示任务已提交
        toast.success(t('documentProcessingStarted'))
      }
    } catch {
      // 获取最新文档状态以显示错误信息
      try {
        const docData = await knowledgeBasesApi.getDocument(knowledgeBaseId, docId)
        setDocumentsState(prev => ({
          ...prev,
          [docId]: { ...prev[docId], document: docData, isProcessing: false }
        }))
        toast.error(docData.error_message || t('documentProcessFailed'))
      } catch {
        setDocumentsState(prev => ({
          ...prev,
          [docId]: { ...prev[docId], isProcessing: false }
        }))
        toast.error(t('documentProcessFailed'))
      }
    }
  }

  // 处理全部文档
  const handleProcessAll = async () => {
    // 处理有预览分块的文档（pending, completed, error 状态都可以）
    // 只跳过 processing 状态的文档
    const docsToProcess = Object.entries(documentsState)
      .filter(([, state]) => 
        state.document?.status !== 'processing' && 
        state.previewChunks && 
        state.previewChunks.length > 0
      )
      .map(([id]) => id)

    if (docsToProcess.length === 0) {
      toast.error(t('noPreviewChunks'))
      return
    }

    // 标记所有文档为处理中
    setDocumentsState(prev => {
      const newState = { ...prev }
      docsToProcess.forEach(id => {
        newState[id] = { ...newState[id], isProcessing: true }
      })
      return newState
    })

    // 并行处理所有文档
    await Promise.all(docsToProcess.map(docId => handleProcessDocument(docId)))
    toast.success(t('processStarted', { count: docsToProcess.length }))

    // 跳转到知识库页面（中台路径）
    router.push(`/app/kb/${knowledgeBaseId}`)
  }

  // 移除文档
  const handleRemoveDocument = (docId: string) => {
    setDocumentsState(prev => {
      const newState = { ...prev }
      delete newState[docId]
      return newState
    })

    // 如果移除的是当前选中的文档，切换到第一个
    if (activeDocId === docId) {
      const remainingIds = Object.keys(documentsState).filter(id => id !== docId)
      if (remainingIds.length > 0) {
        setActiveDocId(remainingIds[0])
      } else {
        router.push(`/app/kb/${knowledgeBaseId}`)
      }
    }
  }

  // 开始编辑分块
  const handleStartEdit = (docId: string, chunkIndex: number, content: string) => {
    setEditingChunk({ docId, chunkIndex })
    setEditingContent(content)
  }

  // 保存编辑的分块
  const handleSaveEdit = () => {
    if (!editingChunk) return

    const { docId, chunkIndex } = editingChunk
    const newContent = editingContent.trim()
    
    if (!newContent) {
      // 内容为空则删除该分块
      handleDeleteChunk(docId, chunkIndex)
    } else {
      // 更新分块内容
      setDocumentsState(prev => {
        const docState = prev[docId]
        if (!docState) return prev

        const newChunks = docState.previewChunks.map((chunk) => {
          if (chunk.chunk_index === chunkIndex) {
            return {
              ...chunk,
              content: newContent,
              char_count: newContent.length,
              token_count: Math.ceil(newContent.length / 4),
            }
          }
          return chunk
        })

        // 重新计算统计
        const totalChunks = newChunks.length
        const totalTokens = newChunks.reduce((sum, c) => sum + c.token_count, 0)
        const totalChars = newChunks.reduce((sum, c) => sum + c.char_count, 0)

        return {
          ...prev,
          [docId]: {
            ...docState,
            previewChunks: newChunks,
            previewStats: {
              total_chunks: totalChunks,
              total_tokens: totalTokens,
              total_chars: totalChars,
            },
          },
        }
      })
    }

    setEditingChunk(null)
    setEditingContent('')
  }

  // 取消编辑
  const handleCancelEdit = () => {
    setEditingChunk(null)
    setEditingContent('')
  }

  // 删除分块
  const handleDeleteChunk = (docId: string, chunkIndex: number) => {
    setDocumentsState(prev => {
      const docState = prev[docId]
      if (!docState) return prev

      // 删除分块并重新编号
      const newChunks = docState.previewChunks
        .filter(chunk => chunk.chunk_index !== chunkIndex)
        .map((chunk, idx) => ({ ...chunk, chunk_index: idx }))

      // 重新计算统计
      const totalChunks = newChunks.length
      const totalTokens = newChunks.reduce((sum, c) => sum + c.token_count, 0)
      const totalChars = newChunks.reduce((sum, c) => sum + c.char_count, 0)

      return {
        ...prev,
        [docId]: {
          ...docState,
          previewChunks: newChunks,
          previewStats: {
            total_chunks: totalChunks,
            total_tokens: totalTokens,
            total_chars: totalChars,
          },
        },
      }
    })

    // 如果正在编辑该分块，取消编辑状态
    if (editingChunk?.docId === docId && editingChunk?.chunkIndex === chunkIndex) {
      setEditingChunk(null)
      setEditingContent('')
    }
  }

  // 添加新分块（在指定位置之后）
  const handleAddChunk = (docId: string, afterIndex: number) => {
    setDocumentsState(prev => {
      const docState = prev[docId]
      if (!docState) return prev

      const newChunk: ChunkPreviewItem = {
        chunk_index: afterIndex + 1,
        content: '',
        char_count: 0,
        token_count: 0,
        overlap_length: 0,
      }

      // 插入新分块并重新编号
      const newChunks: ChunkPreviewItem[] = []
      docState.previewChunks.forEach(chunk => {
        newChunks.push(chunk)
        if (chunk.chunk_index === afterIndex) {
          newChunks.push(newChunk)
        }
      })

      // 重新编号
      const reindexedChunks = newChunks.map((chunk, idx) => ({ ...chunk, chunk_index: idx }))

      // 重新计算统计
      const totalChunks = reindexedChunks.length
      const totalTokens = reindexedChunks.reduce((sum, c) => sum + c.token_count, 0)
      const totalChars = reindexedChunks.reduce((sum, c) => sum + c.char_count, 0)

      return {
        ...prev,
        [docId]: {
          ...docState,
          previewChunks: reindexedChunks,
          previewStats: {
            total_chunks: totalChunks,
            total_tokens: totalTokens,
            total_chars: totalChars,
          },
        },
      }
    })

    // 立即进入编辑模式
    setTimeout(() => {
      handleStartEdit(docId, afterIndex + 1, '')
    }, 0)
  }

  // 可处理的文档数量（pending、completed、error 状态，排除 processing）
  const pendingCount = Object.values(documentsState).filter(
    state => state.document && state.document.status !== 'processing'
  ).length

  // 有预览分块且可处理的文档数量（可以直接处理）
  const readyToProcessCount = Object.values(documentsState).filter(
    state => state.document?.status !== 'processing' && state.previewChunks && state.previewChunks.length > 0
  ).length

  const validDocuments = Object.entries(documentsState).filter(([, state]) => state.document)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (validDocuments.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium mb-2">{t('noDocuments')}</h3>
          <Button onClick={() => router.push(`/app/kb/${knowledgeBaseId}`)}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            {t('backToKnowledgeBase')}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex gap-4 p-4">
      {/* 左侧：文档 Tab 和预览内容 */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col rounded-xl border bg-card overflow-hidden">
        {/* 头部 */}
        <div className="shrink-0 flex items-center justify-between p-4 bg-muted/30">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <Button 
              variant="ghost" 
              size="icon" 
              className="shrink-0" 
              onClick={() => router.push(`/app/kb/${knowledgeBaseId}`)}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-semibold">
                {t('batchPreviewTitle')}
              </h1>
              <p className="text-sm text-muted-foreground">
                {knowledgeBase?.name} · {validDocuments.length} {t('documentsCount')}
              </p>
            </div>
          </div>
        </div>

        {/* 文档 Tab 栏 */}
        <div className="shrink-0 border-t px-4 overflow-x-auto bg-muted/20">
          <div className="flex h-12 items-center gap-1">
            {validDocuments.map(([docId, state]) => (
              <button
                key={docId}
                onClick={() => setActiveDocId(docId)}
                className={cn(
                  "group relative flex items-center gap-2 px-4 py-2 rounded-t-lg border-b-2 transition-colors",
                  activeDocId === docId
                    ? "bg-background border-primary"
                    : "border-transparent hover:bg-muted/50"
                )}
              >
                <FileText className="h-4 w-4" />
                <span className="max-w-32 truncate text-sm">{state.document?.name}</span>
                {state.previewStats && (
                  <Badge variant="secondary" className="ml-1">
                    {state.previewStats.total_chunks}
                  </Badge>
                )}
                {state.isPreviewing && (
                  <Loader2 className="h-3 w-3 animate-spin" />
                )}
                {state.document?.status !== 'pending' && (
                  <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                )}
                <span
                  role="button"
                  tabIndex={0}
                  className="inline-flex items-center justify-center h-5 w-5 ml-1 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleRemoveDocument(docId)
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.stopPropagation()
                      handleRemoveDocument(docId)
                    }
                  }}
                >
                  <X className="h-3 w-3" />
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 预览内容区 - 可滚动 */}
        <div className="flex-1 min-h-0 overflow-auto">
          {(() => {
            const state = documentsState[activeDocId]
            if (!state) return null

            if (state.isPreviewing) {
              return (
                <div className="flex flex-col items-center justify-center h-full">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">{t('previewing')}</p>
                </div>
              )
            }
            
            if (state.error) {
              return (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
                  <h3 className="text-lg font-medium mb-2">{t('previewFailed')}</h3>
                  <p className="text-muted-foreground mb-4">{state.error}</p>
                  <Button onClick={() => handlePreviewDocument(activeDocId)}>
                    <Eye className="h-4 w-4 mr-2" />
                    {t('retryPreview')}
                  </Button>
                </div>
              )
            }
            
            if (state.previewChunks.length === 0) {
              return (
                <div className="flex flex-col items-center justify-center h-full text-center p-8">
                  <Eye className="h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium mb-2">{t('noPreviewYet')}</h3>
                  <p className="text-muted-foreground mb-4">{t('clickPreviewHint')}</p>
                  <Button onClick={() => handlePreviewDocument(activeDocId)}>
                    <Eye className="h-4 w-4 mr-2" />
                    {t('previewChunks')}
                  </Button>
                </div>
              )
            }

            return (
              <div className="p-4 space-y-3">
                {/* 预览统计信息 */}
                {state.previewStats && (
                  <div className="flex items-center gap-4 p-3 rounded-lg bg-blue-500/10 border border-blue-500/30 mb-4">
                    <Eye className="h-4 w-4 text-blue-500" />
                    <span className="text-sm text-blue-600 dark:text-blue-400 font-medium">
                      {t('previewMode')}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {t('previewStats', {
                        chunks: state.previewStats.total_chunks,
                        tokens: state.previewStats.total_tokens,
                      })}
                    </span>
                  </div>
                )}

                {state.previewChunks.map((chunk) => {
                  const isEditing = editingChunk?.docId === activeDocId && editingChunk?.chunkIndex === chunk.chunk_index

                  return (
                    <div
                      key={chunk.chunk_index}
                      className="rounded-lg border bg-card overflow-hidden group"
                    >
                      {/* 分块头部 */}
                      <div className="flex items-center justify-between w-full px-4 py-2 bg-muted/30">
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary">#{chunk.chunk_index + 1}</Badge>
                          <span className="text-xs text-muted-foreground">
                            {chunk.token_count} tokens · {chunk.char_count} {t('chars')}
                            {chunk.overlap_length > 0 && (
                              <> · <span className="text-yellow-600 dark:text-yellow-400">{t('overlapChars', { count: chunk.overlap_length })}</span></>
                            )}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          {/* 编辑/删除按钮 - 悬停时显示 */}
                          {!isEditing && (
                            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => handleStartEdit(activeDocId, chunk.chunk_index, chunk.content)}
                              >
                                <Pencil className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-destructive hover:text-destructive"
                                onClick={() => handleDeleteChunk(activeDocId, chunk.chunk_index)}
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => handleAddChunk(activeDocId, chunk.chunk_index)}
                                title={t('addChunkAfter')}
                              >
                                <Plus className="h-3 w-3" />
                              </Button>
                            </div>
                          )}
                        </div>
                      </div>
                      {/* 分块内容 */}
                      <div className="p-4 overflow-hidden border-t">
                        {isEditing ? (
                          <div className="space-y-3">
                            <Textarea
                              value={editingContent}
                              onChange={(e) => setEditingContent(e.target.value)}
                              className="min-h-50 text-sm font-mono"
                              placeholder={t('chunkContentPlaceholder')}
                              autoFocus
                            />
                            <div className="flex items-center justify-between">
                              <span className="text-xs text-muted-foreground">
                                {editingContent.length} chars · ~{Math.ceil(editingContent.length / 4)} tokens
                              </span>
                              <div className="flex items-center gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={handleCancelEdit}
                                >
                                  <X className="h-3 w-3 mr-1" />
                                  {t('cancel')}
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={handleSaveEdit}
                                >
                                  <Check className="h-3 w-3 mr-1" />
                                  {t('save')}
                                </Button>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <p className="text-sm whitespace-pre-wrap break-all wrap-anywhere">
                            {chunk.overlap_length > 0 ? (
                              <>
                                <span className="bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200">{chunk.content.slice(0, chunk.overlap_length)}</span>
                                {chunk.content.slice(chunk.overlap_length)}
                              </>
                            ) : (
                              chunk.content
                            )}
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
      </div>

      {/* 右侧：设置面板 - 固定 */}
      <div className="w-80 shrink-0 min-h-0 flex flex-col rounded-xl border bg-card overflow-hidden">
        <div className="shrink-0 p-4 bg-muted/30">
          <h2 className="font-semibold flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            {t('chunkSettings')}
          </h2>
        </div>

        <div className="flex-1 min-h-0 overflow-auto p-4 space-y-5">
          {/* 分块参数 */}
          <div className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="chunk_size">{t('chunkSize')}</Label>
              <Input
                id="chunk_size"
                type="number"
                min={100}
                max={2000}
                value={settings.chunk_size}
                onChange={(e) => handleSettingsChange(prev => ({
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
                type="number"
                min={0}
                max={500}
                value={settings.chunk_overlap}
                onChange={(e) => {
                  const val = parseInt(e.target.value)
                  handleSettingsChange(prev => ({
                    ...prev,
                    chunk_overlap: isNaN(val) ? 0 : val
                  }))
                }}
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
                onChange={(e) => handleSettingsChange(prev => ({
                  ...prev,
                  separator: e.target.value
                }))}
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
                onCheckedChange={(checked) => handleSettingsChange(prev => ({
                  ...prev,
                  clean_text: checked
                }))}
              />
            </div>
          </div>

          {/* 提示信息 */}
          <div className="rounded-lg p-3 bg-blue-500/10 border border-blue-500/20">
            <div className="flex gap-2">
              <AlertTriangle className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
              <p className="text-xs text-muted-foreground">
                {t('batchProcessHint')}
              </p>
            </div>
          </div>

          {/* 预览全部按钮 */}
          <Button
            variant="outline"
            onClick={handlePreviewAll}
            disabled={pendingCount === 0 || Object.values(documentsState).some(s => s.isPreviewing)}
            className="w-full"
          >
            <Eye className="mr-2 h-4 w-4" />
            {t('previewAll')} ({pendingCount})
          </Button>

          {/* 开始处理全部按钮 */}
          <Button
            onClick={handleProcessAll}
            disabled={readyToProcessCount === 0 || Object.values(documentsState).some(s => s.isProcessing)}
            className="w-full"
            size="lg"
          >
            {Object.values(documentsState).some(s => s.isProcessing) ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('processing')}
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                {t('startProcessingAll')} ({readyToProcessCount})
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
