'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { adminKnowledgeBasesApi, type Document, type DocumentChunk, type PageData } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface DocumentChunksDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBaseId: string
  document: Document | null
}

export function DocumentChunksDialog({
  open,
  onOpenChange,
  knowledgeBaseId,
  document,
}: DocumentChunksDialogProps) {
  const t = useTranslations('knowledgeBases')
  
  const [chunks, setChunks] = React.useState<DocumentChunk[]>([])
  const [isLoading, setIsLoading] = React.useState(false)
  const [page, setPage] = React.useState(1)
  const [pageData, setPageData] = React.useState<PageData<DocumentChunk> | null>(null)
  const pageSize = 10
  
  // 加载分块
  const loadChunks = React.useCallback(async () => {
    if (!document) return
    
    setIsLoading(true)
    try {
      const data = await adminKnowledgeBasesApi.getDocumentChunks(
        knowledgeBaseId,
        document.id,
        { page, pageSize }
      )
      setChunks(data.items)
      setPageData(data)
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
    }
  }, [open])
  
  const totalPages = pageData ? Math.ceil(pageData.total / pageSize) : 1
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>{t('documentChunks')}</DialogTitle>
          <DialogDescription>
            {document?.name} - {t('totalChunksCount', { count: document?.chunk_count || 0 })}
          </DialogDescription>
        </DialogHeader>
        
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : chunks.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            {t('noChunks')}
          </div>
        ) : (
          <>
            <ScrollArea className="h-[400px] pr-4">
              <div className="space-y-4">
                {chunks.map((chunk) => (
                  <div key={chunk.id} className="rounded-lg border p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="outline">#{chunk.chunk_index + 1}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {chunk.token_count} tokens
                      </span>
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{chunk.content}</p>
                  </div>
                ))}
              </div>
            </ScrollArea>
            
            {/* 分页 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t">
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
      </DialogContent>
    </Dialog>
  )
}
