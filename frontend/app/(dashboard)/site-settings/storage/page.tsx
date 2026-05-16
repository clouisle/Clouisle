'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2, Archive, Database, FileText } from 'lucide-react'
import { FieldError } from '@/components/ui/field'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { useCanPerform } from '@/components/permission-guard'
import {
  KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
  KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
  KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
} from '@/lib/constants'
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
  kb_document_max_upload_size_mb: number
}

export default function SiteSettingsStoragePage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdateSettings = canPerform('admin:settings:update')
  const canArchiveAuditLogs = canPerform('audit:export')

  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [archiving, setArchiving] = React.useState(false)
  const [archiveProgress, setArchiveProgress] = React.useState<string>('')
  const [showArchiveDialog, setShowArchiveDialog] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [settings, setSettings] = React.useState<StorageSettings>({
    audit_log_retention_days: 365,
    audit_log_archive_path: '/var/log/clouisle/audit_archives',
    kb_document_max_upload_size_mb: KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
  })

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, [
      'audit_log_retention_days',
      'audit_log_archive_path',
      'kb_document_max_upload_size_mb',
    ]),
    [fieldErrors]
  )

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const data = await siteSettingsApi.getAll('storage')
      setSettings({
        audit_log_retention_days: (data.audit_log_retention_days as number) ?? 365,
        audit_log_archive_path: (data.audit_log_archive_path as string) ?? '/var/log/clouisle/audit_archives',
        kb_document_max_upload_size_mb: (data.kb_document_max_upload_size_mb as number)
          ?? KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
      })
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const handleSave = async () => {
    const nextErrors: Record<string, string> = {}

    if (!settings.audit_log_archive_path.trim()) {
      nextErrors.audit_log_archive_path = t('required')
    }
    if (settings.audit_log_retention_days < 30 || settings.audit_log_retention_days > 3650) {
      nextErrors.audit_log_retention_days = t('invalidRetentionDays')
    }
    if (
      settings.kb_document_max_upload_size_mb < KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB
      || settings.kb_document_max_upload_size_mb > KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB
    ) {
      nextErrors.kb_document_max_upload_size_mb = t('invalidKbDocumentMaxUploadSize')
    }

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.bulkUpdate({
        audit_log_retention_days: settings.audit_log_retention_days,
        audit_log_archive_path: settings.audit_log_archive_path,
        kb_document_max_upload_size_mb: settings.kb_document_max_upload_size_mb,
      })
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), {
        audit_log_retention_days: 'audit_log_retention_days',
        audit_log_archive_path: 'audit_log_archive_path',
        kb_document_max_upload_size_mb: 'kb_document_max_upload_size_mb',
        'settings.audit_log_retention_days': 'audit_log_retention_days',
        'settings.audit_log_archive_path': 'audit_log_archive_path',
        'settings.kb_document_max_upload_size_mb': 'kb_document_max_upload_size_mb',
      })
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleArchive = async () => {
    try {
      setArchiving(true)
      setArchiveProgress(t('archiveStarting'))

      const { task_id } = await siteSettingsApi.archiveAuditLogs()

      // Poll for task status
      const pollInterval = setInterval(async () => {
        try {
       const status = await siteSettingsApi.getArchiveTaskStatus(task_id)

       if (status.status === 'PENDING') {
            setArchiveProgress(t('archivePending'))
          } else if (status.status === 'STARTED') {
            setArchiveProgress(t('archiveRunning'))
          } else if (status.status === 'SUCCESS') {
            clearInterval(pollInterval)
            const archivedCount = status.result?.archived_count ?? 0
            toast.success(t('archiveSuccess', { count: archivedCount }))
            setShowArchiveDialog(false)
            setArchiving(false)
            setArchiveProgress('')
          } else if (status.status === 'FAILURE') {
            clearInterval(pollInterval)
        toast.error(t('archiveFailed'))
            setArchiving(false)
        setArchiveProgress('')
        }
        } catch (error) {
        console.error('Failed to check archive status:', error)
        }
      }, 2000) // Poll every 2 seconds

      // Timeout after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval)
        if (archiving) {
          setArchiving(false)
          setArchiveProgress('')
          toast.error(t('archiveTimeout'))
      }
      }, 300000)
    } catch (error) {
      console.error('Failed to start archive:', error)
      setArchiving(false)
      setArchiveProgress('')
    }
  }

  const updateSetting = <K extends keyof StorageSettings>(key: K, value: StorageSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
    setFieldErrors((prev) => clearValidationError(prev, key))
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
      {summaryEntries.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {summaryEntries.map(([field, message]) => (
            <FieldError key={field}>{formatValidationSummaryMessage(field, message)}</FieldError>
          ))}
        </div>
      )}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            <CardTitle>{t('knowledgeBaseDocumentUpload')}</CardTitle>
          </div>
          <CardDescription>{t('knowledgeBaseDocumentUploadDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="kbDocumentMaxUploadSize">{t('kbDocumentMaxUploadSize')}</Label>
            <div className="flex items-center gap-2">
              <Input
                id="kbDocumentMaxUploadSize"
                type="number"
                value={settings.kb_document_max_upload_size_mb}
                onChange={(e) => updateSetting(
                  'kb_document_max_upload_size_mb',
                  Number.isNaN(parseInt(e.target.value)) ? 0 : parseInt(e.target.value)
                )}
                min={KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB}
                max={KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB}
                className="w-32"
                disabled={!canUpdateSettings}
                aria-invalid={!!fieldErrors.kb_document_max_upload_size_mb}
              />
              <span className="text-sm text-muted-foreground">MB</span>
            </div>
            <FieldError>{fieldErrors.kb_document_max_upload_size_mb}</FieldError>
            <p className="text-xs text-muted-foreground">{t('kbDocumentMaxUploadSizeHint')}</p>
          </div>
        </CardContent>
      </Card>

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
                disabled={!canUpdateSettings}
                aria-invalid={!!fieldErrors.audit_log_retention_days}
              />
              <span className="text-sm text-muted-foreground">{t('days')}</span>
            </div>
            <FieldError>{fieldErrors.audit_log_retention_days}</FieldError>
            <p className="text-xs text-muted-foreground">{t('auditLogRetentionDaysHint')}</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="archivePath">{t('auditLogArchivePath')}</Label>
            <Input
              id="archivePath"
              placeholder="/var/log/clouisle/audit_archives"
              value={settings.audit_log_archive_path}
              onChange={(e) => updateSetting('audit_log_archive_path', e.target.value)}
              disabled={!canUpdateSettings}
              aria-invalid={!!fieldErrors.audit_log_archive_path}
            />
            <FieldError>{fieldErrors.audit_log_archive_path}</FieldError>
            <p className="text-xs text-muted-foreground">{t('auditLogArchivePathHint')}</p>
          </div>
        </CardContent>
      </Card>

      {canArchiveAuditLogs && (
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
              disabled={archiving}
              variant="outline"
            >
              {archiving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Archive className="mr-2 h-4 w-4" />
              {t('archiveNow')}
            </Button>
            <p className="text-xs text-muted-foreground mt-2">{t('archiveNowHint')}</p>
          </CardContent>
        </Card>
      )}

      {canUpdateSettings && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('saveChanges')}
          </Button>
        </div>
      )}

      {canArchiveAuditLogs && (
        <AlertDialog open={showArchiveDialog} onOpenChange={setShowArchiveDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{t('confirmArchive')}</AlertDialogTitle>
              <AlertDialogDescription>
                {t('confirmArchiveDescription', { days: settings.audit_log_retention_days })}
              </AlertDialogDescription>
            </AlertDialogHeader>
            {archiveProgress && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>{archiveProgress}</span>
           </div>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel disabled={archiving}>{t('cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={handleArchive} disabled={archiving}>
                {archiving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('confirm')}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  )
}
