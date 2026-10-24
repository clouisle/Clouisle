'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { integrationsApi, type LoginSettings } from '@/lib/api/admin/integrations'

export function LoginSettingsCard({ settings, onSettingsChange, canUpdate }: {
  settings: LoginSettings
  onSettingsChange: (settings: LoginSettings) => void
  canUpdate: boolean
}) {
  const t = useTranslations('siteSettings')
  const tLogin = useTranslations('sso')
  const [saving, setSaving] = React.useState(false)
  const controls = [
    ['sso_enabled', 'enableSSO', 'enableSSODescription'],
    ['sso_allow_password_login', 'allowPasswordLogin', 'allowPasswordLoginDescription'],
    ['sso_auto_create_users', 'autoCreateUsers', 'autoCreateUsersDescription'],
    ['sso_require_approval', 'ssoRequireApproval', 'ssoRequireApprovalDescription'],
    ['sso_match_by_email', 'matchByEmail', 'matchByEmailDescription'],
  ] as const

  const save = async () => {
    if (!canUpdate) return
    setSaving(true)
    try {
      onSettingsChange(await integrationsApi.updateLoginSettings(settings))
      toast.success(t('saveSuccess'))
    } catch {
      // API interceptor handles backend errors.
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>{t('ssoSettings')}</CardTitle><CardDescription>{t('ssoSettingsDescription')}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {controls.map(([key, label, description]) => (
          <div key={key} className="flex items-center justify-between gap-4">
            <div className="space-y-0.5"><Label htmlFor={key}>{t(label)}</Label><p className="text-sm text-muted-foreground">{t(description)}</p></div>
            <Switch id={key} checked={settings[key]} disabled={!canUpdate || saving || (key !== 'sso_enabled' && !settings.sso_enabled)} onCheckedChange={(checked) => onSettingsChange({ ...settings, [key]: checked })} />
          </div>
        ))}
        {canUpdate && <div className="flex justify-end"><Button disabled={saving} onClick={save}>{saving ? tLogin('saving') : t('saveChanges')}</Button></div>}
      </CardContent>
    </Card>
  )
}
