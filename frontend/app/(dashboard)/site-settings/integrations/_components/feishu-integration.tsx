'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { ChevronDown, ChevronRight, Loader2, MessageSquareText, RefreshCw, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import type { FeishuConfig, FeishuDepartment } from '@/lib/api/admin/site-settings'
import { ApiError } from '@/lib/api/client'

/**
 * The axios interceptor already toasts backend messages, so only fill the gap it leaves:
 * validation errors (reserved for field level feedback) and non-API failures.
 */
function toastFallback(error: unknown, fallback: string) {
  if (error instanceof ApiError && !error.isValidationError()) return
  toast.error(fallback)
}

function collectDepartmentIds(department: FeishuDepartment): string[] {
  return [department.department_id, ...department.children.flatMap(collectDepartmentIds)]
}

function DepartmentRow({
  department,
  depth,
  selectedIds,
  onToggle,
}: {
  department: FeishuDepartment
  depth: number
  selectedIds: Record<string, true>
  onToggle: (department: FeishuDepartment, checked: boolean) => void
}) {
  const [expanded, setExpanded] = React.useState(true)
  const childIds = department.children.flatMap(collectDepartmentIds)
  const allIds = [department.department_id, ...childIds]
  const checkedCount = allIds.filter((id) => Boolean(selectedIds[id])).length
  const checked = checkedCount === allIds.length
  const indeterminate = checkedCount > 0 && !checked
  return (
    <div>
      <div className="flex min-h-10 items-center gap-2" style={{ paddingInlineStart: `${depth * 20}px` }}>
        {department.children.length > 0 ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            aria-label={expanded ? 'Collapse department' : 'Expand department'}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        ) : <span className="w-7 shrink-0" />}
        <Checkbox
          checked={checked || indeterminate}
          aria-label={department.name}
          onCheckedChange={(value) => onToggle(department, value === true)}
        />
        <span className="truncate text-sm">{department.name}</span>
      </div>
      {expanded && department.children.length > 0 && (
        <div role="group">
          {department.children.map((child) => (
            <DepartmentRow
              key={child.department_id}
              department={child}
              depth={depth + 1}
              selectedIds={selectedIds}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FeishuIntegrationTab({
  config,
  onConfigChange,
  canUpdate,
}: {
  config: FeishuConfig
  onConfigChange: (config: FeishuConfig) => void
  canUpdate: boolean
}) {
  const t = useTranslations('siteSettings')
  const [appId, setAppId] = React.useState(config.app_id)
  const [appSecret, setAppSecret] = React.useState('')
  const [departments, setDepartments] = React.useState<FeishuDepartment[]>([])
  const [selectedIds, setSelectedIds] = React.useState<Record<string, true>>(() => Object.fromEntries(config.department_ids.map((id) => [id, true])) as Record<string, true>)
  const [loadingDepartments, setLoadingDepartments] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [savingScope, setSavingScope] = React.useState(false)
  const [syncing, setSyncing] = React.useState(false)

  React.useEffect(() => {
    setAppId(config.app_id)
    setSelectedIds(Object.fromEntries(config.department_ids.map((id) => [id, true])) as Record<string, true>)
  }, [config.app_id, config.department_ids])

  const loadDepartments = React.useCallback(async () => {
    if (!config.app_secret_configured) return
    setLoadingDepartments(true)
    try {
      setDepartments(await siteSettingsApi.getFeishuDepartments())
    } catch (error) {
      console.error('Failed to load Feishu departments:', error)
      toastFallback(error, t('integrations.feishuDepartmentsFailed'))
    } finally {
      setLoadingDepartments(false)
    }
  }, [config.app_secret_configured, t])

  React.useEffect(() => {
    loadDepartments()
  }, [loadDepartments])

  const toggleDepartment = (department: FeishuDepartment, checked: boolean) => {
    setSelectedIds((current) => {
      const next = { ...current }
      for (const id of collectDepartmentIds(department)) {
        if (checked) next[id] = true
        else delete next[id]
      }
      return next
    })
  }

  const saveConfig = async () => {
    if (!appId.trim()) return
    setSaving(true)
    try {
      const result = await siteSettingsApi.updateFeishuConfig({
        app_id: appId.trim(),
        app_secret: appSecret.trim() || undefined,
      })
      setAppSecret('')
      onConfigChange({ ...config, ...result })
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save Feishu configuration:', error)
      toastFallback(error, t('integrations.feishuSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const saveScope = async () => {
    setSavingScope(true)
    try {
      const result = await siteSettingsApi.updateFeishuDepartmentScope(Object.keys(selectedIds))
      setSelectedIds(Object.fromEntries(result.department_ids.map((id) => [id, true])) as Record<string, true>)
      onConfigChange({ ...config, department_ids: result.department_ids })
      toast.success(t('integrations.feishuScopeSaved'))
    } catch (error) {
      console.error('Failed to save Feishu department scope:', error)
      toastFallback(error, t('integrations.feishuScopeSaveFailed'))
    } finally {
      setSavingScope(false)
    }
  }

  const sync = async () => {
    setSyncing(true)
    try {
      const result = await siteSettingsApi.syncFeishuContacts()
      toast.success(t('integrations.feishuSyncResult', { ...result, teams_created: result.teams_created }))
    } catch (error) {
      console.error('Failed to sync Feishu directory:', error)
      toastFallback(error, t('integrations.feishuSyncFailed'))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <MessageSquareText className="h-4 w-4" />
          <CardTitle>{t('integrations.feishu')}</CardTitle>
        </div>
        <CardDescription>{t('integrations.feishuDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="feishu-app-id">{t('integrations.feishuAppId')}</Label>
            <Input id="feishu-app-id" value={appId} onChange={(event) => setAppId(event.target.value)} disabled={!canUpdate} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="feishu-app-secret">{t('integrations.feishuAppSecret')}</Label>
            <Input
              id="feishu-app-secret"
              type="password"
              autoComplete="new-password"
              value={appSecret}
              onChange={(event) => setAppSecret(event.target.value)}
              placeholder={config.app_secret_configured ? t('integrations.feishuSecretConfigured') : ''}
              disabled={!canUpdate}
            />
            <p className="text-xs text-muted-foreground">{t('integrations.feishuAppSecretDesc')}</p>
          </div>
        </div>
        {canUpdate && (
          <div className="flex justify-end">
            <Button type="button" variant="outline" onClick={saveConfig} disabled={saving || !appId.trim()}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              {t('save')}
            </Button>
          </div>
        )}
        {config.app_secret_configured && (
          <section className="space-y-3 border-t pt-4" aria-labelledby="feishu-departments-title">
            <div>
              <h3 id="feishu-departments-title" className="text-sm font-medium">{t('integrations.feishuDepartments')}</h3>
              <p className="text-xs text-muted-foreground">{t('integrations.feishuDepartmentsDesc')}</p>
            </div>
            {loadingDepartments ? (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{t('integrations.feishuLoadingDepartments')}</div>
            ) : departments.length > 0 ? (
              <ScrollArea className="max-h-72 rounded-md border p-2">
                <div role="tree" aria-label={t('integrations.feishuDepartments')}>
                  {departments.map((department) => (
                    <DepartmentRow key={department.department_id} department={department} depth={0} selectedIds={selectedIds} onToggle={toggleDepartment} />
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <p className="rounded-md border p-3 text-sm text-muted-foreground">{t('integrations.feishuNoDepartments')}</p>
            )}
            {canUpdate && (
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" variant="outline" onClick={loadDepartments} disabled={loadingDepartments}>
                  {loadingDepartments ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  {t('integrations.feishuRefreshDepartments')}
                </Button>
                <Button type="button" variant="outline" onClick={saveScope} disabled={savingScope || Object.keys(selectedIds).length === 0}>
                  {savingScope && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('integrations.feishuSaveScope')}
                </Button>
                <Button type="button" onClick={sync} disabled={syncing || config.department_ids.length === 0}>
                  {syncing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                  {t('integrations.feishuSync')}
                </Button>
              </div>
            )}
          </section>
        )}
      </CardContent>
    </Card>
  )
}
