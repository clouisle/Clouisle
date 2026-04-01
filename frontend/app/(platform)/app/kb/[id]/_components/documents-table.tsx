'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
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
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
  X,
  Settings2,
  Play,
  Download,
  ExternalLink,
} from 'lucide-react'
import { toast } from 'sonner'
import { knowledgeBasesApi, type Document, type PageData, type DocumentStatus, type DocumentType } from '@/lib/api'
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
}

// 文档类型图标映射
const docTypeIcons: Record<string, React.ReactNode> = {
  pdf: <FileType className="h-4 w-4 text-red-500" />,
  docx: <FileType className="h-4 w-4 text-blue-500" />,
  doc: <FileType className="h-4 w-4 text-blue-500" />,
  txt: <FileText className="h-4 w-4 text-gray-500" />,
  md: <FileText className="h-4 w-4 text-gray-500" />,
  html: <FileType className="h-4 w-4 text-orange-500" />,
  csv: <FileType className="h-4 w-4 text-green-500" />,
  xlsx: <FileType className="h-4 w-4 text-green-600" />,
  xls: <FileType className="h-4 w-4 text-green-600" />,
  json: <FileType className="h-4 w-4 text-yellow-500" />,
  url: <Link className="h-4 w-4 text-purple-500" />,
}

export function DocumentsTable({ knowledgeBaseId, refreshTrigger, onRefresh }: DocumentsTableProps) {
  const t = useTranslations('knowledgeBases')
  const commonT = useTranslations('common')
  const router = useRouter()
  const { canPerform } = useCanPerform()
  const canUpdateKb = canPerform('kb:update')
  const canDeleteKb = canPerform('kb:delete')
  
  // 数据状态
  const [documents, setDocuments] = React.useState<Document[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(10)
  const [pageData, setPageData] = React.useState<PageData<Document> | null>(null)
  
  // 筛选状态
  const [searchQuery, setSearchQuery] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState<Set<string>>(new Set())
  const [typeFilter, setTypeFilter] = React.useState<Set<string>>(new Set())
  
  // 选择状态
  const [selectedDocs, setSelectedDocs] = React.useState<Set<string>>(new Set())
  
  // Dialog 状态
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)
  const [selectedDoc, setSelectedDoc] = React.useState<Document | null>(null)
  
  // 加载文档列表
  const loadDocuments = React.useCallback(async (showLoading = true) => {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      const params: {
        page: number
        pageSize: number
        search?: string
        status?: DocumentStatus
        doc_type?: DocumentType
      } = { page, pageSize }
      
      if (searchQuery) params.search = searchQuery
      if (statusFilter.size === 1) params.status = Array.from(statusFilter)[0] as DocumentStatus
      if (typeFilter.size === 1) params.doc_type = Array.from(typeFilter)[0] as DocumentType
      
      const data = await knowledgeBasesApi.getDocuments(knowledgeBaseId, params)
      setDocuments(data.items)
      setPageData(data)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }, [knowledgeBaseId, page, pageSize, searchQuery, statusFilter, typeFilter])
  
  React.useEffect(() => {
    loadDocuments()
  }, [loadDocuments, refreshTrigger])
  
  // 自动刷新处理中的文档
  React.useEffect(() => {
    const hasProcessing = documents.some(doc => doc.status === 'processing' || doc.status === 'pending')
    if (hasProcessing) {
      const timer = setInterval(() => {
        loadDocuments(false)
      }, 5000)
      return () => clearInterval(timer)
    }
  }, [documents, loadDocuments])
  
  // 筛选条件变化时重置到第一页
  React.useEffect(() => {
    setPage(1)
  }, [searchQuery, statusFilter, typeFilter])
  
  // 检查是否有筛选条件
  const isFiltered = searchQuery || statusFilter.size > 0 || typeFilter.size > 0
  
  // 重置筛选
  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setTypeFilter(new Set())
    setPage(1)
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
    { value: 'txt', label: 'TXT' },
    { value: 'md', label: 'Markdown' },
    { value: 'html', label: 'HTML' },
    { value: 'csv', label: 'CSV' },
    { value: 'xlsx', label: 'XLSX' },
    { value: 'xls', label: 'XLS' },
    { value: 'json', label: 'JSON' },
    { value: 'url', label: 'URL' },
  ]
  
  // 计算分页信息
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  // 选择操作
  const toggleSelectAll = () => {
    if (selectedDocs.size === documents.length) {
      setSelectedDocs(new Set())
    } else {
      setSelectedDocs(new Set(documents.map(d => d.id)))
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
  
  // 配置文档
  const handleConfigure = (doc: Document) => {
    router.push(`/app/kb/${knowledgeBaseId}/documents/${doc.id}`)
  }
  
  // 快速处理
  const handleQuickProcess = async (doc: Document) => {
    try {
      await knowledgeBasesApi.processDocument(knowledgeBaseId, doc.id)
      toast.success(t('processStartedSingle'))
      loadDocuments()
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
    switch (status) {
      case 'completed':
        return (
          <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 gap-1">
            <CheckCircle className="h-3 w-3" />
            {t('statusCompleted')}
          </Badge>
        )
      case 'processing': {
        const progress = doc?.metadata?.embed_progress as { embedded?: number; failed?: number; total?: number } | undefined
        const badge = (
          <Badge variant="default" className="bg-blue-500/10 text-blue-500 gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {progress?.total
              ? t('embeddingProgress', { embedded: progress.embedded ?? 0, total: progress.total })
              : t('statusProcessing')}
          </Badge>
        )
        if (progress?.total) {
          return (
            <Tooltip>
              <TooltipTrigger className="bg-blue-500/10 text-blue-500 gap-1 inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold">
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
  
  return (
    <div className="flex flex-col gap-4">
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
              <TableHead className="w-10">
                <Checkbox
                  checked={selectedDocs.size === documents.length && documents.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
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
                <TableCell colSpan={8} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="h-24 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <FileText className="h-8 w-8 text-muted-foreground/50" />
                    <p>{t('noDocuments')}</p>
                    <p className="text-sm">{t('uploadDocumentHint')}</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              documents.map((doc) => (
                <TableRow key={doc.id} data-state={selectedDocs.has(doc.id) ? 'selected' : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selectedDocs.has(doc.id)}
                      onCheckedChange={() => toggleSelectDoc(doc.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {docTypeIcons[doc.doc_type] || <FileText className="h-4 w-4" />}
                      <span className="font-medium truncate max-w-50" title={doc.name}>
                        {doc.name}
                      </span>
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
                    <Badge variant="outline" className="uppercase text-xs">
                      {doc.doc_type}
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
                    {new Date(doc.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">{t('common.openMenu')}</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {doc.status === 'pending' && canUpdateKb && (
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

                        {doc.status === 'completed' && (
                          <DropdownMenuItem onClick={() => handleViewChunks(doc)}>
                            <Eye className="mr-2 h-4 w-4" />
                            {t('viewChunks')}
                          </DropdownMenuItem>
                        )}

                        {(doc.status === 'error' || doc.status === 'completed') && canUpdateKb && (
                          <DropdownMenuItem onClick={() => handleReprocess(doc)}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            {t('reprocess')}
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

                        {canDeleteKb && (
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
      
      {/* 分页 */}
      {pageData && pageData.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Select value={String(pageSize)} onValueChange={(v) => { if (v) { setPageSize(Number(v)); setPage(1) } }}>
              <SelectTrigger className="w-17.5 h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent side="top" alignItemWithTrigger={false}>
                <SelectItem value="10">10</SelectItem>
                <SelectItem value="20">20</SelectItem>
                <SelectItem value="50">50</SelectItem>
              </SelectContent>
            </Select>
            <span>{t('rowsPerPage')}</span>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {t('pageInfo', { page, total: totalPages })}
            </span>
            
            <div className="flex items-center gap-1">
              <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setPage(1)} disabled={page === 1}>
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => setPage(totalPages)} disabled={page >= totalPages}>
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
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
                  onClick={() => {
                    const pendingDocIds = documents
                      .filter(d => selectedDocs.has(d.id) && d.status === 'pending')
                      .map(d => d.id)
                      .join(',')
                    router.push(`/app/kb/${knowledgeBaseId}/documents/preview?docs=${pendingDocIds}`)
                  }}
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-primary hover:text-primary hover:bg-primary/10"
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  }
                />
                <TooltipContent>{t('batchProcess')}</TooltipContent>
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
