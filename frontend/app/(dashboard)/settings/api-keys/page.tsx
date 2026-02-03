'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Plus,
  Key,
  Trash2,
  Copy,
  Check,
  AlertTriangle,
  MoreHorizontal,
  Pencil,
} from 'lucide-react'
import { formatDateTime } from '@/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { apiKeysApi, type APIKey } from '@/lib/api'
import { APIKeyDialog } from '@/app/(dashboard)/api-keys/_components/api-key-dialog'

export default function SettingsAPIKeysPage() {
  const t = useTranslations('settings')
  const apiKeysT = useTranslations('apiKeys')
  const commonT = useTranslations('common')

  const [loading, setLoading] = React.useState(true)
  const [apiKeys, setApiKeys] = React.useState<APIKey[]>([])

  // Dialog 状态
  const [keyDialogOpen, setKeyDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [showKeyDialogOpen, setShowKeyDialogOpen] = React.useState(false)
  const [selectedKey, setSelectedKey] = React.useState<APIKey | null>(null)
  const [newKeyValue, setNewKeyValue] = React.useState<string | null>(null)

  // 表单状态
  const [deleting, setDeleting] = React.useState(false)
  const [copied, setCopied] = React.useState(false)

  React.useEffect(() => {
    loadAPIKeys()
  }, [])

  const loadAPIKeys = async () => {
    try {
      setLoading(true)
      const data = await apiKeysApi.getAPIKeys({ pageSize: 100 })
      setApiKeys(data.items)
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = () => {
    setSelectedKey(null)
    setKeyDialogOpen(true)
  }

  const handleEdit = (apiKey: APIKey) => {
    setSelectedKey(apiKey)
    setKeyDialogOpen(true)
  }

  const handleDialogSuccess = (key?: string) => {
    loadAPIKeys()
    if (key) {
      setNewKeyValue(key)
      setShowKeyDialogOpen(true)
    }
  }

  const handleDelete = async () => {
    if (!selectedKey) return
    
    try {
      setDeleting(true)
      await apiKeysApi.deleteAPIKey(selectedKey.id)
      toast.success(apiKeysT('keyDeleted'))
      setDeleteDialogOpen(false)
      setSelectedKey(null)
      loadAPIKeys()
    } catch {
      // 错误已由 API 客户端处理
    } finally {
      setDeleting(false)
    }
  }

  const handleCopy = async () => {
    if (!newKeyValue) return
    
    try {
      await navigator.clipboard.writeText(newKeyValue)
      setCopied(true)
      toast.success(apiKeysT('copied'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(apiKeysT('copyFailed'))
    }
  }

  const openDeleteDialog = (apiKey: APIKey) => {
    setSelectedKey(apiKey)
    setDeleteDialogOpen(true)
  }

  const getStatusBadge = (apiKey: APIKey) => {
    const now = new Date()
    const isExpired = apiKey.expires_at && new Date(apiKey.expires_at) < now
    
    if (isExpired) {
      return <Badge variant="outline" className="text-orange-500 border-orange-500/50">{apiKeysT('expired')}</Badge>
    }
    if (apiKey.is_active) {
      return <Badge variant="default" className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">{apiKeysT('active')}</Badge>
    }
    return <Badge variant="outline" className="text-muted-foreground">{apiKeysT('inactive')}</Badge>
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-4 w-48 mt-1" />
        </div>
        <Separator />
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-48" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">{t('apiKeys')}</h3>
        <p className="text-sm text-muted-foreground">{t('apiKeysDescription')}</p>
      </div>
      <Separator />
      
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{t('yourApiKeys')}</CardTitle>
              <CardDescription>{t('yourApiKeysDescription')}</CardDescription>
            </div>
            <Button onClick={handleCreate}>
              <Plus className="mr-2 h-4 w-4" />
              {apiKeysT('createKey')}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {apiKeys.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Key className="mx-auto h-12 w-12 mb-4 opacity-50" />
              <p>{t('noApiKeys')}</p>
              <p className="text-sm mt-1">{t('createFirstKey')}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {apiKeys.map((apiKey) => (
                <div
                  key={apiKey.id}
                  className="flex items-center justify-between p-4 rounded-lg border bg-card"
                >
                  <div className="flex items-center gap-4">
                    <Key className="h-5 w-5 text-muted-foreground" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{apiKey.name}</span>
                        {getStatusBadge(apiKey)}
                      </div>
                      <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                        <code className="bg-muted px-2 py-0.5 rounded text-xs">
                          {apiKey.key_prefix}...
                        </code>
                        <span>
                          {apiKeysT('rateLimit')}: {apiKey.rate_limit > 0 ? `${apiKey.rate_limit}/min` : apiKeysT('unlimited')}
                        </span>
                        <span>
                          {t('created')}: {formatDateTime(apiKey.created_at)}
                        </span>
                        {apiKey.last_used_at && (
                          <span>
                            {t('lastUsed')}: {formatDateTime(apiKey.last_used_at)}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <DropdownMenu>
                    <DropdownMenuTrigger className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-9 w-9">
                      <MoreHorizontal className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => handleEdit(apiKey)}>
                        <Pencil className="mr-2 h-4 w-4" />
                        {commonT('edit')}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() => openDeleteDialog(apiKey)}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {commonT('delete')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 创建/编辑 API Key Dialog */}
      <APIKeyDialog
        open={keyDialogOpen}
        onOpenChange={setKeyDialogOpen}
        apiKey={selectedKey}
        onSuccess={handleDialogSuccess}
      />

      {/* 显示新创建的 Key */}
      <Dialog open={showKeyDialogOpen} onOpenChange={setShowKeyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{apiKeysT('keyCreatedTitle')}</DialogTitle>
            <DialogDescription>
              {apiKeysT('keyCreatedDescription')}
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <Alert variant="warning">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {apiKeysT('keyWarning')}
              </AlertDescription>
            </Alert>
            
            <div className="flex gap-2">
              <Input
                readOnly
                value={newKeyValue || ''}
                className="font-mono text-sm"
              />
              <Button
                variant="outline"
                size="icon"
                onClick={handleCopy}
              >
                {copied ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
          
          <DialogFooter>
            <Button onClick={() => setShowKeyDialogOpen(false)}>
              {commonT('close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{apiKeysT('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {apiKeysT('deleteKeyConfirm', { name: selectedKey?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? commonT('deleting') : commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
