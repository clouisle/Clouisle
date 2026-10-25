'use client'

import * as React from 'react'
import { FeishuDocumentSource, isFeishuManaged } from '@/components/knowledge-bases/feishu-document-source'
import { useLocale, useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import {
  MoreHorizontal,
  Trash2,
  RefreshCw,
  Eye,
  FileText,
  FileType,
  Link,
  CheckCircle,
  XCircle,
  Loader2,
  Clock,
  Search,
  X,
  Settings2,
  Play,
  Download,
  ExternalLink,
  RotateCcw,
} from 'lucide-react'
import { toast } from 'sonner'
import { knowledgeBasesApi, type Document, type DocumentStatus, type DocumentType } from '@/lib/api'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { useDebounce } from '@/hooks/use-debounce'
import { formatDate } from '@/lib/utils'
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { useCanPerform } from '@/components/permission-guard'

interface DocumentsTableProps {
  knowledgeBaseId: string
  refreshTrigger: number
  onRefresh: () => void
  readOnly?: boolean
}

// 文档类型图标映射
const docTypeIcons: Record<string, React.ReactNode> = {
  pdf: <FileType className="h-4 w-4 text-red-500" />,
  docx: <FileType className="h-4 w-4 text-blue-500" />,
  doc: <FileType className="h-4 w-4 text-blue-500" />,
  txt: <FileText className="h-4 w-4 text-gray-500" />,
  markdown: <FileText className="h-4 w-4 text-gray-500" />,
  html: <FileType className="h-4 w-4 text-orange-500" />,
  csv: <FileType className="h-4 w-4 text-green-500" />,
  xlsx: <FileType className="h-4 w-4 text-green-600" />,
  xls: <FileType className="h-4 w-4 text-green-600" />,
  json: <FileType className="h-4 w-4 text-yellow-500" />,
  url: <Link className="h-4 w-4 text-purple-500" />,
}

const BULK_ACTION_CONCURRENCY = 3
const DOCUMENT_PAGE_SIZE = 10

type DocumentLoadOperation = 'first' | 'more' | 'refresh'

async function runBulkActions<T>(items: T[], action: (item: T) => Promise<unknown>) {
  for (let index = 0; index < items.length; index += BULK_ACTION_CONCURRENCY) {
    await Promise.allSettled(items.slice(index, index + BULK_ACTION_CONCURRENCY).map(action))
  }
}

export function DocumentsTable({ knowledgeBaseId, refreshTrigger, onRefresh, readOnly = false }: DocumentsTableProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const locale = useLocale()
  const router = useRouter()
  const { canPerform } = useCanPerform()
  const canUpdateKb = !readOnly && canPerform('kb:update')
  const canDeleteKb = !readOnly && canPerform('kb:delete')
  
  // 数据状态
  const [documents, setDocuments] = React.useState<Document[]>([])
  const [total, setTotal] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isLoadingMore, setIsLoadingMore] = React.useState(false)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [failedOperation, setFailedOperation] = React.useState<DocumentLoadOperation | null>(null)
  const loadFailed = failedOperation !== null
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const debouncedSearchQuery = useDebounce(searchQuery.trim(), 300)
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedDocs, setSelectedDocs] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedDoc, setSelectedDoc] = React.useState<Document | null>(null)
  const [isBulkActionLoading, setIsBulkActionLoading] = React.useState(false)

  const requestSeqRef = React.useRef(0)
  const pendingCountRef = React.useRef(0)
  const loadedPagesRef = React.useRef(0)
  const totalRef = React.useRef(0)

  const buildPageParams = React.useCallback((page: number) => {
    const params: {
      page: number
      pageSize: number
      search?: string
      status?: DocumentStatus[]
      doc_type?: DocumentType[]
    } = { page, pageSize: DOCUMENT_PAGE_SIZE }

    if (debouncedSearchQuery) params.search = debouncedSearchQuery
    if (statusFilter.size === 1) params.status = [Array.from(statusFilter)[0] as DocumentStatus]
    if (typeFilter.size === 1) params.doc_type = [Array.from(typeFilter)[0] as DocumentType]

    return params
  }, [debouncedSearchQuery, statusFilter, typeFilter])

  // 重新加载第一页：筛选变化、刷新触发或首次进入
  const loadFirstPage = React.useCallback(async () => {
    const seq = ++requestSeqRef.current
    pendingCountRef.current = 1
    setIsLoading(true)
    setIsLoadingMore(false)
    setIsRefreshing(false)
    setFailedOperation(null)
    // 新筛选条件读取失败时不能沿用旧筛选的条目和游标
    loadedPagesRef.current = 0
    totalRef.current = 0
    setDocuments([])
    setTotal(0)
    try {
      const data = await knowledgeBasesApi.getDocuments(knowledgeBaseId, buildPageParams(1))
      if (seq !== requestSeqRef.current) return
      setDocuments(data.items)
      setTotal(data.total)
      totalRef.current = data.total
      loadedPagesRef.current = 1
    } catch {
      // 错误已由 API 客户端处理
      if (seq === requestSeqRef.current) setFailedOperation('first')
    } finally {
      if (seq === requestSeqRef.current) {
        pendingCountRef.current = 0
        setIsLoading(false)
      }
    }
  }, [knowledgeBaseId, buildPageParams])

  // 滚动到底部时追加下一页
  const loadMore = React.useCallback(async () => {
    if (pendingCountRef.current > 0 || loadedPagesRef.current === 0) return
    if (documents.length >= totalRef.current) return

    const seq = requestSeqRef.current
    const nextPage = loadedPagesRef.current + 1
    pendingCountRef.current += 1
    setIsLoadingMore(true)
    setFailedOperation(null)
    try {
      const data = await knowledgeBasesApi.getDocuments(knowledgeBaseId, buildPageParams(nextPage))
      if (seq !== requestSeqRef.current) return
      const seen = new Set(documents.map(doc => doc.id))
      const appended: Document[] = []
      for (const doc of data.items) {
        if (seen.has(doc.id)) continue
        seen.add(doc.id)
        appended.push(doc)
      }
      const nextTotal = data.items.length === 0 ? documents.length : data.total
      setDocuments([...documents, ...appended])
      totalRef.current = nextTotal
      setTotal(nextTotal)
      loadedPagesRef.current = nextPage
    } catch {
      // 错误已由 API 客户端处理；失败不推进页码，避免跳过数据
      if (seq === requestSeqRef.current) setFailedOperation('more')
    } finally {
      if (seq === requestSeqRef.current) {
        pendingCountRef.current = Math.max(pendingCountRef.current - 1, 0)
        setIsLoadingMore(false)
      }
    }
  }, [documents, knowledgeBaseId, buildPageParams])

  // 刷新所有已加载页，保留用户已经追加的文档。
  // force=true 用于文档状态变更后刷新：即使有追加请求在途也接管本轮读取，旧响应按 seq 丢弃。
  const refreshLoadedPages = React.useCallback(async (options?: { force?: boolean }) => {
    const force = options?.force ?? false
    const pages = loadedPagesRef.current
    if (pages === 0) {
      await loadFirstPage()
      return
    }
    // 轮询保持让位给在途的追加请求，避免每 5 秒取消用户正在进行的滚动加载
    if (!force && pendingCountRef.current > 0) return

    const seq = force ? ++requestSeqRef.current : requestSeqRef.current
    pendingCountRef.current = force ? 1 : pendingCountRef.current + 1
    if (force) {
      setIsLoading(false)
      setIsLoadingMore(false)
    }
    setIsRefreshing(true)
    setFailedOperation(null)
    try {
      const merged: Document[] = []
      const seen = new Set<string>()
      let latestTotal = totalRef.current
      let nextLoadedPages = 1

      for (let page = 1; page <= pages; page += 1) {
        const data = await knowledgeBasesApi.getDocuments(knowledgeBaseId, buildPageParams(page))
        if (seq !== requestSeqRef.current) return
        latestTotal = data.total
        if (data.items.length === 0) {
          nextLoadedPages = Math.max(page - 1, 1)
          break
        }
        nextLoadedPages = page
        for (const doc of data.items) {
          if (seen.has(doc.id)) continue
          seen.add(doc.id)
          merged.push(doc)
        }
      }

      setDocuments(merged)
      loadedPagesRef.current = nextLoadedPages
      totalRef.current = latestTotal
      setTotal(latestTotal)
    } catch {
      // 错误已由 API 客户端处理
      if (seq === requestSeqRef.current) setFailedOperation('refresh')
    } finally {
      if (seq === requestSeqRef.current) {
        pendingCountRef.current = Math.max(pendingCountRef.current - 1, 0)
        setIsRefreshing(false)
      }
    }
  }, [knowledgeBaseId, buildPageParams, loadFirstPage])

  const retryLoad = React.useCallback(() => {
    const operation = failedOperation
    setFailedOperation(null)
    if (operation === 'more' && loadedPagesRef.current > 0) {
      void loadMore()
      return
    }
    if (operation === 'refresh' && loadedPagesRef.current > 0) {
      void refreshLoadedPages({ force: true })
      return
    }
    void loadFirstPage()
  }, [failedOperation, loadFirstPage, loadMore, refreshLoadedPages])

  React.useEffect(() => {
    void loadFirstPage()
  }, [loadFirstPage, refreshTrigger])

  React.useEffect(() => () => {
    // 卸载后到达的响应不再写入状态
    requestSeqRef.current += 1
  }, [])

  const hasMore = documents.length < total
  const sentinelRef = useInfiniteScroll({
    hasMore: hasMore && !loadFailed,
    loading: isLoading || isLoadingMore || isRefreshing,
    onLoadMore: () => { void loadMore() },
  })

  // 自动刷新处理中的文档：刷新全部已加载页，不清空已追加内容；失败后停止自动轮询
  const hasProcessing = documents.some(doc => doc.status === 'processing' || doc.status === 'pending')
  React.useEffect(() => {
    if (!hasProcessing || loadFailed) return
    const timer = setInterval(() => {
      void refreshLoadedPages()
    }, 5000)
    return () => clearInterval(timer)
  }, [hasProcessing, loadFailed, refreshLoadedPages])
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || statusFilter.size > 0 || typeFilter.size > 0
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setTypeFilter(new Set())
  }
  
  // 状态选项
  const statusOptions = [
    { value: 'pending', label: t('statusPending') },
    { value: 'processing', label: t('statusProcessing') },
    { value: 'completed', label: t('statusCompleted') },
    { value: 'error', label: t('statusFailed') },
  ]
  
  // 类型选项
  const typeOptions = [
    { value: 'pdf', label: 'PDF' },
    { value: 'docx', label: 'DOCX' },
    { value: 'doc', label: 'DOC' },
    { value: 'pptx', label: 'PPTX' },
    { value: 'txt', label: 'TXT' },
    { value: 'markdown', label: 'Markdown' },
    { value: 'html', label: 'HTML' },
    { value: 'csv', label: 'CSV' },
    { value: 'xlsx', label: 'XLSX' },
    { value: 'xls', label: 'XLS' },
    { value: 'json', label: 'JSON' },
    { value: 'url', label: 'URL' },
  ]
  
  // 选择操作
  const toggleSelectAll = () => {
    if (documents.filter(doc => !isFeishuManaged(doc)).every(doc => selectedDocs.has(doc.id))) {
      setSelectedDocs(new Set())
    } else {
      setSelectedDocs(new Set(documents.filter(d => !isFeishuManaged(d)).map(d => d.id)))
    }
  }
  
  const toggleSelectDoc = (docId: string) => {
    const newSelected = new Set(selectedDocs)
    if (newSelected.has(docId)) {
      newSelected.delete(docId)
    } else {
      newSelected.add(docId)
    }
    setSelectedDocs(newSelected)
  }
  
  // 删除文档
  const handleDelete = (doc: Document) => {
    setSelectedDoc(doc)
    setDeleteDialogOpen(true)
  }
  
  const confirmDelete = async () => {
    if (!selectedDoc) return
    try {
      await knowledgeBasesApi.deleteDocument(knowledgeBaseId, selectedDoc.id)
      toast.success(t('documentDeleted'))
      setDeleteDialogOpen(false)
      onRefresh()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 重新处理 - 跳转到预览编辑器页面
  const handleReprocess = (doc: Document) => {
    router.push(`/app/kb/${knowledgeBaseId}/documents/preview?docs=${doc.id}`)
  }

  // 重试失败分段
  const handleRetryFailedChunks = async (doc: Document) => {
    try {
      await knowledgeBasesApi.retryFailedChunks(knowledgeBaseId, doc.id)
      toast.success(t('retryStarted'))
      await refreshLoadedPages({ force: true })
    } catch {
      // 错误已由 API 客户端处理
    }
  }

  const handleBulkQuickProcess = async () => {
    const pendingDocs = documents.filter(doc => selectedDocs.has(doc.id) && doc.status === 'pending')
    if (pendingDocs.length === 0) return

    setIsBulkActionLoading(true)
    try {
      await runBulkActions(pendingDocs, doc => knowledgeBasesApi.processDocument(knowledgeBaseId, doc.id))
      toast.success(t('processStarted', { count: pendingDocs.length }))
      setSelectedDocs(new Set())
      await refreshLoadedPages({ force: true })
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsBulkActionLoading(false)
    }
  }

  const handleBulkRetryFailedChunks = async () => {
    const failedDocs = documents.filter(doc => selectedDocs.has(doc.id) && doc.status === 'error')
    if (failedDocs.length === 0) return

    setIsBulkActionLoading(true)
    try {
      await runBulkActions(failedDocs, doc => knowledgeBasesApi.retryFailedChunks(knowledgeBaseId, doc.id))
      toast.success(t('retryStarted'))
      setSelectedDocs(new Set())
      await refreshLoadedPages({ force: true })
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setIsBulkActionLoading(false)
    }
  }

  // 配置文档
  const handleConfigure = (doc: Document) => {
    router.push(`/app/kb/${knowledgeBaseId}/documents/${doc.id}`)
  }
  
  // 快速处理
  const handleQuickProcess = async (doc: Document) => {
    try {
      await knowledgeBasesApi.processDocument(knowledgeBaseId, doc.id)
      toast.success(t('processStartedSingle'))
      await refreshLoadedPages({ force: true })
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 查看分块
  const handleViewChunks = (doc: Document) => {
    router.push(`/app/kb/${knowledgeBaseId}/documents/${doc.id}`)
  }
  
  // 下载原文件
  const handleDownload = async (doc: Document) => {
    try {
      await knowledgeBasesApi.downloadDocument(knowledgeBaseId, doc.id, doc.name)
      toast.success(t('downloadStarted'))
    } catch {
      toast.error(t('downloadFailed'))
    }
  }
  
  // 批量删除
  const confirmBulkDelete = async () => {
    try {
      const promises = Array.from(selectedDocs).map(id => 
        knowledgeBasesApi.deleteDocument(knowledgeBaseId, id)
      )
      await Promise.all(promises)
      toast.success(t('bulkDocumentsDeleted', { count: selectedDocs.size }))
      setSelectedDocs(new Set())
      setBulkDeleteDialogOpen(false)
      onRefresh()
    } catch {
      // 错误已由 API 客户端处理
    }
  }
  
  // 格式化文件大小
  const formatSize = (bytes: number | null | undefined) => {
    if (bytes === null || bytes === undefined || bytes === 0) return '-'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }
  
  // 获取状态 Badge
  const getStatusBadge = (status: DocumentStatus, doc?: Document) => {
    const statusTestId = doc ? `kb-document-status-${status}-${doc.id}` : undefined
    switch (status) {
      case 'completed':
        return (
          <Badge data-testid={statusTestId} variant="default" className="bg-emerald-500/10 text-emerald-500 gap-1">
            <CheckCircle className="h-3 w-3" />
            {t('statusCompleted')}
          </Badge>
        )
      case 'processing': {
        const progress = doc?.metadata?.embed_progress as { embedded?: number; failed?: number; total?: number } | undefined
        const badge = (
          <Badge data-testid={statusTestId} variant="default" className="bg-blue-500/10 text-blue-500 gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {progress?.total
              ? t('embeddingProgress', { embedded: progress.embedded ?? 0, total: progress.total })
              : t('statusProcessing')}
          </Badge>
        )
        if (progress?.total) {
          return (
            <Tooltip>
              <TooltipTrigger data-testid={statusTestId} className="bg-blue-500/10 text-blue-500 gap-1 inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold">
                <Loader2 className="h-3 w-3 animate-spin" />
                {t('embeddingProgress', { embedded: progress.embedded ?? 0, total: progress.total })}
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-xs space-y-0.5">
                  <p>{t('embeddedCount', { count: progress.embedded ?? 0 })}</p>
                  {(progress.failed ?? 0) > 0 && <p className="text-destructive">{t('failedCount', { count: progress.failed ?? 0 })}</p>}
                  <p>{t('totalCount', { count: progress.total })}</p>
                </div>
              </TooltipContent>
            </Tooltip>
          )
        }
        return badge
      }
      case 'pending':
        return (
          <Badge data-testid={statusTestId} variant="outline" className="text-muted-foreground gap-1">
            <Clock className="h-3 w-3" />
            {t('statusPending')}
          </Badge>
        )
      case 'error':
        return (
          <Badge data-testid={statusTestId} variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            {t('statusFailed')}
          </Badge>
        )
      default:
        return null
    }
  }
  
  return (
    <div
      className="flex flex-col gap-4"
      data-testid="kb-documents-table"
    >
      {/* 筛选栏 */}
      <div className="flex items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t('filterDocuments')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 w-50 h-9"
          />
        </div>
        
        <DataTableFacetedFilter
          title={t('status')}
          options={statusOptions}
          selectedValues={statusFilter}
          onSelectionChange={setStatusFilter}
        />
        
        <DataTableFacetedFilter
          title={t('type')}
          options={typeOptions}
          selectedValues={typeFilter}
          onSelectionChange={setTypeFilter}
        />
        
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
              {!readOnly && (
                <TableHead className="w-10">
                  <Checkbox
                    checked={documents.some(doc => !isFeishuManaged(doc)) && documents.filter(doc => !isFeishuManaged(doc)).every(doc => selectedDocs.has(doc.id))}
                    disabled={!documents.some(doc => !isFeishuManaged(doc))}
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
              )}
              <TableHead>{t('documentName')}</TableHead>
              <TableHead>{t('type')}</TableHead>
              <TableHead>{t('size')}</TableHead>
              <TableHead>{t('chunks')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('createdAt')}</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={readOnly ? 7 : 8} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : loadFailed && documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={readOnly ? 7 : 8} className="h-24 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <p className="text-muted-foreground">{commonT('loadFailed')}</p>
                    <Button variant="outline" size="sm" onClick={retryLoad}>
                      {commonT('retry')}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ) : documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={readOnly ? 7 : 8} className="h-24 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <p>{t('noDocuments')}</p>
                    <p className="text-sm">{t('uploadDocumentHint')}</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              documents.map((doc) => (
                <TableRow key={doc.id} data-state={selectedDocs.has(doc.id) ? 'selected' : undefined}>
                  {!readOnly && (
                    <TableCell>
                      <Checkbox
                        checked={selectedDocs.has(doc.id)}
                        disabled={isFeishuManaged(doc)}
                        onCheckedChange={() => toggleSelectDoc(doc.id)}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <div className="flex min-w-0 items-center gap-2">
                      {docTypeIcons[doc.doc_type] || <FileText className="h-4 w-4 shrink-0" />}
                      <Tooltip>
                        <TooltipTrigger render={<span />} className="font-medium truncate max-w-50 cursor-default">
                          {doc.name}
                        </TooltipTrigger>
                        <TooltipContent>{doc.name}</TooltipContent>
                      </Tooltip>
                      <FeishuDocumentSource document={doc} />
                    </div>
                    {doc.error_message && (
                      <Tooltip>
                        <TooltipTrigger render={<p />} className="text-xs text-destructive mt-1 truncate max-w-62.5 cursor-default">
                          {doc.error_message}
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-sm break-all">
                          {doc.error_message}
                        </TooltipContent>
                      </Tooltip>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {typeOptions.find(option => option.value === doc.doc_type)?.label ?? doc.doc_type.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatSize(doc.file_size)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {doc.chunk_count}
                  </TableCell>
                  <TableCell>{getStatusBadge(doc.status, doc)}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(doc.created_at, locale)}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">{t('common.openMenu')}</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-48">
                        {doc.status === 'pending' && canUpdateKb && !isFeishuManaged(doc) && (
                          <>
                            <DropdownMenuItem onClick={() => handleConfigure(doc)}>
                              <Settings2 className="mr-2 h-4 w-4" />
                              {t('configure')}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleQuickProcess(doc)}>
                              <Play className="mr-2 h-4 w-4" />
                              {t('quickProcess')}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                          </>
                        )}

                        {(doc.status === 'completed' || doc.status === 'error') && (
                          <DropdownMenuItem onClick={() => handleViewChunks(doc)}>
                            <Eye className="mr-2 h-4 w-4" />
                            {t('viewChunks')}
                          </DropdownMenuItem>
                        )}

                        {(doc.status === 'error' || doc.status === 'completed') && canUpdateKb && !isFeishuManaged(doc) && (
                          <DropdownMenuItem onClick={() => handleReprocess(doc)}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            {t('reprocess')}
                          </DropdownMenuItem>
                        )}

                        {doc.status === 'error' && canUpdateKb && !isFeishuManaged(doc) && (
                          <DropdownMenuItem onClick={() => handleRetryFailedChunks(doc)}>
                            <RotateCcw className="mr-2 h-4 w-4" />
                            {t('retryFailedChunks')}
                          </DropdownMenuItem>
                        )}

                        {doc.file_path && doc.doc_type !== 'url' && (
                          <DropdownMenuItem onClick={() => handleDownload(doc)}>
                            <Download className="mr-2 h-4 w-4" />
                            {t('downloadOriginal')}
                          </DropdownMenuItem>
                        )}

                        {doc.source_url && doc.doc_type === 'url' && (
                          <DropdownMenuItem onClick={() => window.open(doc.source_url!, '_blank')}>
                            <ExternalLink className="mr-2 h-4 w-4" />
                            {t('viewSourceUrl')}
                          </DropdownMenuItem>
                        )}
                        {isFeishuManaged(doc) && typeof doc.metadata?.feishu_source_url === 'string' && /^https?:\/\//i.test(doc.metadata.feishu_source_url) && (
                          <DropdownMenuItem onClick={() => window.open(doc.metadata!.feishu_source_url as string, '_blank', 'noopener,noreferrer')}>
                            <ExternalLink className="mr-2 h-4 w-4" />
                            {t('feishuOriginal')}
                          </DropdownMenuItem>
                        )}

                        {canDeleteKb && !isFeishuManaged(doc) && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => handleDelete(doc)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              {commonT('delete')}
                            </DropdownMenuItem>
                          </>
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
      
      {/* 无限滚动：哨兵始终挂载，滚动到底部自动加载下一页 */}
      <div ref={sentinelRef} aria-hidden className="h-px w-full" />

      {isLoadingMore && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {commonT('loadingMore')}
        </div>
      )}

      {loadFailed && documents.length > 0 && (
        <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
          <span>{commonT('loadFailed')}</span>
          <Button variant="outline" size="sm" onClick={retryLoad}>
            {commonT('retry')}
          </Button>
        </div>
      )}
      
      {/* 删除确认 Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteDocumentConfirm', { name: selectedDoc?.name || '' })}
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
      
      {/* 批量操作浮动工具栏 */}
      {selectedDocs.size > 0 && (canUpdateKb || canDeleteKb) && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setSelectedDocs(new Set())}>
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedDocs.size} {t('documentsSelected')}
            </Badge>

            {/* 批量处理按钮 */}
            {canUpdateKb && documents.filter(d => selectedDocs.has(d.id) && d.status === 'pending').length > 0 && (
              <Tooltip>
                <TooltipTrigger
                  onClick={handleBulkQuickProcess}
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-primary hover:text-primary hover:bg-primary/10"
                      disabled={isBulkActionLoading}
                    >
                      {isBulkActionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                    </Button>
                  }
                />
                <TooltipContent>{t('bulkQuickProcess')}</TooltipContent>
              </Tooltip>
            )}

            {canUpdateKb && documents.filter(d => selectedDocs.has(d.id) && d.status === 'error').length > 0 && (
              <Tooltip>
                <TooltipTrigger
                  onClick={handleBulkRetryFailedChunks}
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                      disabled={isBulkActionLoading}
                    >
                      {isBulkActionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
                    </Button>
                  }
                />
                <TooltipContent>{t('bulkRetryFailedChunks')}</TooltipContent>
              </Tooltip>
            )}

            {canDeleteKb && (
              <Tooltip>
                <TooltipTrigger
                  onClick={() => setBulkDeleteDialogOpen(true)}
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
            )}
          </div>
        </div>
      )}
      
      {/* 批量删除确认 Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmBulkDocumentsDelete', { count: selectedDocs.size })}
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
