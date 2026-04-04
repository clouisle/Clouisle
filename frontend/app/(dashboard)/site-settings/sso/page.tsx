'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, TestTube2, Power, PowerOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCanPerform } from '@/components/permission-guard'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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
import { Badge } from '@/components/ui/badge'
import { ssoApi, type SSOProviderAdmin } from '@/lib/api/admin/sso'
import { ProviderDialog } from './_components/provider-dialog'

export default function SSOSettingsPage() {
  const t = useTranslations('sso')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')
  const [providers, setProviders] = useState<SSOProviderAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [editProvider, setEditProvider] = useState<SSOProviderAdmin | null>(null)
  const [showDialog, setShowDialog] = useState(false)

  const loadProviders = async () => {
    try {
      setLoading(true)
      const data = await ssoApi.listProviders()
      setProviders(data)
    } catch {
      // toast handled by API interceptor
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadProviders()
  }, [])

  const handleDelete = async () => {
    if (!deleteId) return

    try {
      await ssoApi.deleteProvider(deleteId)
      toast.success(t('deleteSuccess'))
      loadProviders()
    } catch {
      // toast handled by API interceptor
    } finally {
      setDeleteId(null)
    }
  }

  const handleTest = async (id: string) => {
    try {
      const result = await ssoApi.testConnection(id)
      if (result.status === 'success') {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch {
      // toast handled by API interceptor
    }
  }

  const handleToggleEnabled = async (provider: SSOProviderAdmin) => {
    try {
      await ssoApi.updateProvider(provider.id, {
        is_enabled: !provider.is_enabled,
      })
      toast.success(
        provider.is_enabled ? t('disableSuccess') : t('enableSuccess')
      )
      loadProviders()
    } catch {
      // toast handled by API interceptor
    }
  }

  const handleEdit = (provider: SSOProviderAdmin) => {
    setEditProvider(provider)
    setShowDialog(true)
  }

  const handleCreate = () => {
    setEditProvider(null)
    setShowDialog(true)
  }

  const handleDialogClose = (success?: boolean) => {
    setShowDialog(false)
    setEditProvider(null)
    if (success) {
      loadProviders()
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t('title')}</h2>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
        <Button onClick={handleCreate} disabled={!canUpdate}>
          <Plus className="mr-2 h-4 w-4" />
          {t('addProvider')}
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('providerName')}</TableHead>
              <TableHead>{t('protocol')}</TableHead>
              <TableHead>{t('status')}</TableHead>
              <TableHead>{t('allowSignup')}</TableHead>
              <TableHead className="text-right">{t('actions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {providers.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="h-24 text-center text-muted-foreground"
                >
                  {t('noProviders')}
                </TableCell>
              </TableRow>
            ) : (
              providers.map((provider) => (
                <TableRow key={provider.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      {provider.icon_url && (
                        <img
                          src={provider.icon_url}
                          alt={provider.display_name}
                          className="h-5 w-5 rounded"
                        />
                      )}
                      {provider.display_name}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {provider.protocol.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={provider.is_enabled ? 'default' : 'secondary'}
                    >
                      {provider.is_enabled ? t('enabled') : t('disabled')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {provider.allow_signup ? t('yes') : t('no')}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleToggleEnabled(provider)}
                        disabled={!canUpdate}
                        title={
                          provider.is_enabled
                            ? t('disable')
                            : t('enable')
                        }
                      >
                        {provider.is_enabled ? (
                          <PowerOff className="h-4 w-4" />
                        ) : (
                          <Power className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleTest(provider.id)}
                        title={t('testConnection')}
                        disabled={!canUpdate}
                      >
                        <TestTube2 className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleEdit(provider)}
                        title={t('editProvider')}
                        disabled={!canUpdate}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setDeleteId(provider.id)}
                        title={t('deleteProvider')}
                        disabled={!canUpdate}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <ProviderDialog
        open={showDialog}
        provider={editProvider}
        onClose={handleDialogClose}
      />

      <AlertDialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteProvider')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteConfirm')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={!canUpdate}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
