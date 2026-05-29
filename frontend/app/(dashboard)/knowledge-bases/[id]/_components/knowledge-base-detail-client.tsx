'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Upload,
  Link,
  Settings,
  FileText,
  Layers,
  HardDrive,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Search,
  Cpu,
  ArrowUpDown,
} from 'lucide-react'
import { adminKnowledgeBasesApi, type KnowledgeBase, type KnowledgeBaseStats } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { DocumentsTable } from './documents-table'
import { UploadDocumentDialog } from './upload-document-dialog'
import { ImportUrlDialog } from './import-url-dialog'
import { KnowledgeBaseDialog } from '../../_components/knowledge-base-dialog'
import { PermissionGuard } from '@/components/permission-guard'

interface KnowledgeBaseDetailClientProps {
  knowledgeBaseId: string
}

export function KnowledgeBaseDetailClient({ knowledgeBaseId }: KnowledgeBaseDetailClientProps) {
  const t = useTranslations('knowledgeBases')
  const router = useRouter()
  
  // 数据状态
  const [knowledgeBase, setKnowledgeBase] = React.useState<KnowledgeBase | null>(null)
  const [stats, setStats] = React.useState<KnowledgeBaseStats | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Dialog 状态
  const [uploadDialogOpen, setUploadDialogOpen] = React.useState(false)
  const [importUrlDialogOpen, setImportUrlDialogOpen] = React.useState(false)
  const [settingsDialogOpen, setSettingsDialogOpen] = React.useState(false)
  
  // 文档刷新触发器
  const [refreshTrigger, setRefreshTrigger] = React.useState(0)
  
  // 加载知识库详情 (showLoading 参数控制是否显示加载状态)
  const loadKnowledgeBase = React.useCallback(async (showLoading = true) => {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      const [kbData, statsData] = await Promise.all([
        adminKnowledgeBasesApi.getKnowledgeBase(knowledgeBaseId),
        adminKnowledgeBasesApi.getStats(knowledgeBaseId),
      ])
      setKnowledgeBase(kbData)
      setStats(statsData)
    } catch {
      // 错误已由 API 客户端处理
      router.push('/knowledge-bases')
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }, [knowledgeBaseId, router])
  
  React.useEffect(() => {
    loadKnowledgeBase()
  }, [loadKnowledgeBase])
  
  // 刷新文档列表 (静默刷新统计，不显示加载状态)
  const refreshDocuments = () => {
    setRefreshTrigger(prev => prev + 1)
    loadKnowledgeBase(false) // 静默刷新统计
  }
  
  if (isLoading || !knowledgeBase) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }
  
  return (
    <div className="flex flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => router.push('/knowledge-bases')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">{knowledgeBase.name}</h1>
              {knowledgeBase.status === 'active' ? (
                <Badge variant="default" className="bg-emerald-500/10 text-emerald-500">
                  {t('active')}
                </Badge>
              ) : knowledgeBase.status === 'archived' ? (
                <Badge variant="outline" className="text-muted-foreground">
                  {t('archived')}
                </Badge>
              ) : null}
            </div>
            <div className="flex items-center gap-2 text-muted-foreground">
              {knowledgeBase.team && (
                <span className="text-sm">{knowledgeBase.team.name}</span>
              )}
              {knowledgeBase.team && knowledgeBase.description && (
                <span className="text-sm">·</span>
              )}
            {knowledgeBase.description && (
              <span className="text-sm">{knowledgeBase.description}</span>
            )}
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => router.push(`/knowledge-bases/${knowledgeBaseId}/search`)}>
            <Search className="mr-2 h-4 w-4" />
            {t('searchTest')}
          </Button>
          <PermissionGuard permission="kb:update">
            <Button variant="outline" onClick={() => setImportUrlDialogOpen(true)}>
              <Link className="mr-2 h-4 w-4" />
              {t('importUrl')}
            </Button>
            <Button onClick={() => setUploadDialogOpen(true)}>
              <Upload className="mr-2 h-4 w-4" />
              {t('uploadDocument')}
            </Button>
            <Button variant="ghost" size="icon" onClick={() => setSettingsDialogOpen(true)}>
              <Settings className="h-4 w-4" />
            </Button>
          </PermissionGuard>
        </div>
      </div>
      
      {/* 统计卡片 */}
      {stats && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('totalDocuments')}</CardTitle>
              <FileText className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.document_count}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('totalChunks')}</CardTitle>
              <Layers className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_chunks.toLocaleString()}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('totalTokens')}</CardTitle>
              <HardDrive className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{(stats.total_tokens ?? 0).toLocaleString()}</div>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{t('processingStatus')}</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 text-sm">
                <div className="flex items-center gap-1">
                  <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                  <span>{stats.documents_by_status?.completed ?? 0}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin" />
                  <span>{(stats.documents_by_status?.processing ?? 0) + (stats.documents_by_status?.pending ?? 0)}</span>
                </div>
                <div className="flex items-center gap-1">
                  <XCircle className="h-3.5 w-3.5 text-destructive" />
                  <span>{stats.documents_by_status?.error ?? 0}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      
      {/* 文档列表 */}
      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>{t('documents')}</CardTitle>
            <CardDescription>{t('documentsDescription')}</CardDescription>
          </div>
          {(knowledgeBase.embedding_model || knowledgeBase.rerank_model) && (
            <div className="flex w-full flex-col gap-1 text-xs md:w-auto md:max-w-sm md:items-end">
              {knowledgeBase.embedding_model && (
                <div className="flex min-w-0 items-center gap-1.5 md:max-w-sm md:justify-end">
                  <Cpu className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="shrink-0 text-muted-foreground">{t('embeddingModel')}:</span>
                  <span className="min-w-0 truncate text-foreground/90">
                    {knowledgeBase.embedding_model.name}
                  </span>
                  <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {knowledgeBase.embedding_model.provider}
                  </span>
                </div>
              )}
              {knowledgeBase.rerank_model && (
                <div className="flex min-w-0 items-center gap-1.5 md:max-w-sm md:justify-end">
                  <ArrowUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="shrink-0 text-muted-foreground">{t('rerankModel')}:</span>
                  <span className="min-w-0 truncate text-foreground/90">
                    {knowledgeBase.rerank_model.name}
                  </span>
                  <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                    {knowledgeBase.rerank_model.provider}
                  </span>
                </div>
              )}
            </div>
          )}
        </CardHeader>
        <CardContent>
          <DocumentsTable 
            knowledgeBaseId={knowledgeBaseId} 
            refreshTrigger={refreshTrigger}
            onRefresh={refreshDocuments}
          />
        </CardContent>
      </Card>
      
      {/* 上传文档 Dialog */}
      <UploadDocumentDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        knowledgeBaseId={knowledgeBaseId}
        onSuccess={refreshDocuments}
      />
      
      {/* 导入 URL Dialog */}
      <ImportUrlDialog
        open={importUrlDialogOpen}
        onOpenChange={setImportUrlDialogOpen}
        knowledgeBaseId={knowledgeBaseId}
        onSuccess={refreshDocuments}
      />
      
      {/* 设置 Dialog */}
      <KnowledgeBaseDialog
        open={settingsDialogOpen}
        onOpenChange={setSettingsDialogOpen}
        knowledgeBase={knowledgeBase}
        onSuccess={loadKnowledgeBase}
      />
    </div>
  )
}
