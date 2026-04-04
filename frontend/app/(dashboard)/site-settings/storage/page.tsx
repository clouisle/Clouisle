'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2, Archive, Database } from 'lucide-react'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import { useCanPerform } from '@/components/permission-guard'
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

interface StorageSettings {
  audit_log_retention_days: number
  audit_log_archive_path: string
}

export default function SiteSettingsStoragePage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')

  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [archiving, setArchiving] = React.useState(false)
  const [showArchiveDialog, setShowArchiveDialog] = React.useState(false)
  const [settings, setSettings] = React.useState<StorageSettings>({
    audit_log_retention_days: 365,
    audit_log_archive_path: '/var/log/clouisle/audit_archives',
  })

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const data = await siteSettingsApi.getAll('storage')
      setSettings({
        audit_log_retention_days: (data.audit_log_retention_days as number) ?? 365,
        audit_log_archive_path: (data.audit_log_archive_path as string) ?? '/var/log/clouisle/audit_archives',
      })
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }, [t])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.bulkUpdate({
        audit_log_retention_days: settings.audit_log_retention_days,
        audit_log_archive_path: settings.audit_log_archive_path,
      })
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleArchive = async () => {
    try {
      setArchiving(true)
      await siteSettingsApi.archiveAuditLogs()
      toast.success(t('archiveSuccess'))
      setShowArchiveDialog(false)
    } catch (error) {
      console.error('Failed to archive logs:', error)
    } finally {
      setArchiving(false)
    }
  }

  const updateSetting = <K extends keyof StorageSettings>(key: K, value: StorageSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            <CardTitle>{t('auditLogStorage')}</CardTitle>
          </div>
          <CardDescription>{t('auditLogStorageDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="retentionDays">{t('auditLogRetentionDays')}</Label>
            <div className="flex items-center gap-2">
              <Input
                id="retentionDays"
                type="number"
                value={settings.audit_log_retention_days}
                onChange={(e) => updateSetting('audit_log_retention_days', parseInt(e.target.value) || 365)}
                min={30}
                max={3650}
                className="w-32"
                disabled={!canUpdate}
              />
              <span className="text-sm text-muted-foreground">{t('days')}</span>
            </div>
            <p className="text-xs text-muted-foreground">{t('auditLogRetentionDaysHint')}</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="archivePath">{t('auditLogArchivePath')}</Label>
            <Input
              id="archivePath"
              placeholder="/var/log/clouisle/audit_archives"
              value={settings.audit_log_archive_path}
              onChange={(e) => updateSetting('audit_log_archive_path', e.target.value)}
              disabled={!canUpdate}
            />
            <p className="text-xs text-muted-foreground">{t('auditLogArchivePathHint')}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Archive className="h-5 w-5" />
            <CardTitle>{t('manualArchive')}</CardTitle>
          </div>
          <CardDescription>{t('manualArchiveDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={() => setShowArchiveDialog(true)}
            disabled={archiving || !canUpdate}
            variant="outline"
          >
            {archiving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            <Archive className="mr-2 h-4 w-4" />
            {t('archiveNow')}
          </Button>
          <p className="text-xs text-muted-foreground mt-2">{t('archiveNowHint')}</p>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving || !canUpdate}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('saveChanges')}
        </Button>
      </div>

      <AlertDialog open={showArchiveDialog} onOpenChange={setShowArchiveDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmArchive')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('confirmArchiveDescription', { days: settings.audit_log_retention_days })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={archiving}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleArchive} disabled={archiving}>
              {archiving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
