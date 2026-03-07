'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2 } from 'lucide-react'
import { siteSettingsApi, type SecuritySettings } from '@/lib/api/admin/site-settings'
import { rolesApi, type Role } from '@/lib/api/admin/roles'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

export default function SiteSettingsSecurityPage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')
  
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [roles, setRoles] = React.useState<Role[]>([])
  const [settings, setSettings] = React.useState<SecuritySettings>({
    allow_registration: true,
    require_approval: false,
    email_verification: true,
    allow_account_deletion: true,
    default_role_id: '',
    min_password_length: 8,
    require_uppercase: true,
    require_number: true,
    require_special_char: false,
    session_timeout_days: 30,
    single_session: false,
    max_login_attempts: 5,
    lockout_duration_minutes: 15,
    enable_captcha: false,
    sso_enabled: false,
    sso_allow_password_login: true,
    sso_auto_create_users: true,
    sso_require_approval: false,
    sso_match_by_email: true,
    password_expiration_enabled: false,
    password_expiration_days: 90,
    password_expiration_warning_days: 7,
    password_history_count: 5,
    password_min_age_days: 0,
    force_password_change_first_login: false,
  })

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const [data, rolesData] = await Promise.all([
        siteSettingsApi.getSecurity(),
        rolesApi.getRoles(),
      ])
      setRoles(rolesData.items)
      // 确保所有布尔值字段都有明确的值
      setSettings({
        allow_registration: data.allow_registration ?? true,
        require_approval: data.require_approval ?? false,
        email_verification: data.email_verification ?? true,
        allow_account_deletion: data.allow_account_deletion ?? true,
        default_role_id: data.default_role_id ?? '',
        min_password_length: data.min_password_length ?? 8,
        require_uppercase: data.require_uppercase ?? true,
        require_number: data.require_number ?? true,
        require_special_char: data.require_special_char ?? false,
        session_timeout_days: data.session_timeout_days ?? 30,
        single_session: data.single_session ?? false,
        max_login_attempts: data.max_login_attempts ?? 5,
        lockout_duration_minutes: data.lockout_duration_minutes ?? 15,
        enable_captcha: data.enable_captcha ?? false,
        sso_enabled: data.sso_enabled ?? false,
        sso_allow_password_login: data.sso_allow_password_login ?? true,
        sso_auto_create_users: data.sso_auto_create_users ?? true,
        sso_require_approval: data.sso_require_approval ?? false,
        sso_match_by_email: data.sso_match_by_email ?? true,
        password_expiration_enabled: data.password_expiration_enabled ?? false,
        password_expiration_days: data.password_expiration_days ?? 90,
        password_expiration_warning_days: data.password_expiration_warning_days ?? 7,
        password_history_count: data.password_history_count ?? 5,
        password_min_age_days: data.password_min_age_days ?? 0,
        force_password_change_first_login: data.force_password_change_first_login ?? false,
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
      await siteSettingsApi.updateSecurity(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const updateSetting = <K extends keyof SecuritySettings>(key: K, value: SecuritySettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {[1, 2, 3].map((i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-48" />
            </CardHeader>
            <CardContent className="space-y-4">
              <Skeleton className="h-10 w-32" />
              <Skeleton className="h-10 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('registration')}</CardTitle>
          <CardDescription>{t('registrationDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('allowRegistration')}</Label>
              <p className="text-sm text-muted-foreground">{t('allowRegistrationDescription')}</p>
            </div>
            <Switch
              checked={settings.allow_registration}
              onCheckedChange={(checked) => updateSetting('allow_registration', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('requireApproval')}</Label>
              <p className="text-sm text-muted-foreground">{t('requireApprovalDescription')}</p>
            </div>
            <Switch
              checked={settings.require_approval}
              onCheckedChange={(checked) => updateSetting('require_approval', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('emailVerification')}</Label>
              <p className="text-sm text-muted-foreground">{t('emailVerificationDescription')}</p>
            </div>
            <Switch
              checked={settings.email_verification}
              onCheckedChange={(checked) => updateSetting('email_verification', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('allowAccountDeletion')}</Label>
              <p className="text-sm text-muted-foreground">{t('allowAccountDeletionDescription')}</p>
            </div>
            <Switch
              checked={settings.allow_account_deletion}
              onCheckedChange={(checked) => updateSetting('allow_account_deletion', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('defaultRole')}</Label>
              <p className="text-sm text-muted-foreground">{t('defaultRoleDescription')}</p>
            </div>
            <Select
              value={settings.default_role_id}
              onValueChange={(value) => updateSetting('default_role_id', value ?? '')}
              disabled={!canUpdate}
            >
              <SelectTrigger className="w-48">
                <SelectValue>
                  {roles.find((r) => r.id === settings.default_role_id)?.name}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.id}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('passwordPolicy')}</CardTitle>
          <CardDescription>{t('passwordPolicyDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="minLength">{t('minPasswordLength')}</Label>
            <Input
              id="minLength"
              type="number"
              value={settings.min_password_length}
              onChange={(e) => updateSetting('min_password_length', parseInt(e.target.value) || 8)}
              min={6}
              max={32}
              className="w-32"
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('requireUppercase')}</Label>
              <p className="text-sm text-muted-foreground">{t('requireUppercaseDescription')}</p>
            </div>
            <Switch
              checked={settings.require_uppercase}
              onCheckedChange={(checked) => updateSetting('require_uppercase', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('requireNumber')}</Label>
              <p className="text-sm text-muted-foreground">{t('requireNumberDescription')}</p>
            </div>
            <Switch
              checked={settings.require_number}
              onCheckedChange={(checked) => updateSetting('require_number', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('requireSpecialChar')}</Label>
              <p className="text-sm text-muted-foreground">{t('requireSpecialCharDescription')}</p>
            </div>
            <Switch
              checked={settings.require_special_char}
              onCheckedChange={(checked) => updateSetting('require_special_char', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('passwordExpiration')}</CardTitle>
          <CardDescription>{t('passwordExpirationDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('passwordExpirationEnabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('passwordExpirationEnabledDescription')}</p>
            </div>
            <Switch
              checked={settings.password_expiration_enabled}
              onCheckedChange={(checked) => updateSetting('password_expiration_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>
          {settings.password_expiration_enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="expirationDays">{t('passwordExpirationDays')}</Label>
                <p className="text-sm text-muted-foreground">{t('passwordExpirationDaysDescription')}</p>
                <div className="flex items-center gap-2">
                  <Input
                    id="expirationDays"
                    type="number"
                    value={settings.password_expiration_days}
                    onChange={(e) => updateSetting('password_expiration_days', parseInt(e.target.value) || 90)}
                    min={1}
                    max={365}
                    className="w-32"
                    disabled={!canUpdate}
                  />
                  <span className="text-sm text-muted-foreground">{t('days')}</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="warningDays">{t('passwordExpirationWarningDays')}</Label>
                <p className="text-sm text-muted-foreground">{t('passwordExpirationWarningDaysDescription')}</p>
                <div className="flex items-center gap-2">
                  <Input
                    id="warningDays"
                    type="number"
                    value={settings.password_expiration_warning_days}
                    onChange={(e) => updateSetting('password_expiration_warning_days', parseInt(e.target.value) || 7)}
                    min={1}
                    max={30}
                    className="w-32"
                    disabled={!canUpdate}
                  />
                  <span className="text-sm text-muted-foreground">{t('days')}</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="historyCount">{t('passwordHistoryCount')}</Label>
                <p className="text-sm text-muted-foreground">{t('passwordHistoryCountDescription')}</p>
                <Input
                  id="historyCount"
                  type="number"
                  value={settings.password_history_count}
                  onChange={(e) => updateSetting('password_history_count', parseInt(e.target.value) || 5)}
                  min={0}
                  max={24}
                  className="w-32"
                  disabled={!canUpdate}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="minAgeDays">{t('passwordMinAgeDays')}</Label>
                <p className="text-sm text-muted-foreground">{t('passwordMinAgeDaysDescription')}</p>
                <div className="flex items-center gap-2">
                  <Input
                    id="minAgeDays"
                    type="number"
                    value={settings.password_min_age_days}
                    onChange={(e) => updateSetting('password_min_age_days', parseInt(e.target.value) || 0)}
                    min={0}
                    max={30}
                    className="w-32"
                    disabled={!canUpdate}
                  />
                  <span className="text-sm text-muted-foreground">{t('days')}</span>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>{t('forcePasswordChangeFirstLogin')}</Label>
                  <p className="text-sm text-muted-foreground">{t('forcePasswordChangeFirstLoginDescription')}</p>
                </div>
                <Switch
                  checked={settings.force_password_change_first_login}
                  onCheckedChange={(checked) => updateSetting('force_password_change_first_login', checked)}
                  disabled={!canUpdate}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('sessionSettings')}</CardTitle>
          <CardDescription>{t('sessionSettingsDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sessionTimeout">{t('sessionTimeout')}</Label>
            <div className="flex items-center gap-2">
              <Input
                id="sessionTimeout"
                type="number"
                value={settings.session_timeout_days}
                onChange={(e) => updateSetting('session_timeout_days', parseInt(e.target.value) || 30)}
                min={1}
                className="w-32"
                disabled={!canUpdate}
              />
              <span className="text-sm text-muted-foreground">{t('days')}</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('singleSession')}</Label>
              <p className="text-sm text-muted-foreground">{t('singleSessionDescription')}</p>
            </div>
            <Switch
              checked={settings.single_session}
              onCheckedChange={(checked) => updateSetting('single_session', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('loginSecurity')}</CardTitle>
          <CardDescription>{t('loginSecurityDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="maxAttempts">{t('maxLoginAttempts')}</Label>
            <Input
              id="maxAttempts"
              type="number"
              value={settings.max_login_attempts}
              onChange={(e) => updateSetting('max_login_attempts', parseInt(e.target.value) || 5)}
              min={3}
              max={10}
              className="w-32"
              disabled={!canUpdate}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="lockoutDuration">{t('lockoutDuration')}</Label>
            <div className="flex items-center gap-2">
              <Input
                id="lockoutDuration"
                type="number"
                value={settings.lockout_duration_minutes}
                onChange={(e) => updateSetting('lockout_duration_minutes', parseInt(e.target.value) || 15)}
                min={1}
                className="w-32"
                disabled={!canUpdate}
              />
              <span className="text-sm text-muted-foreground">{t('minutes')}</span>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('enableCaptcha')}</Label>
              <p className="text-sm text-muted-foreground">{t('enableCaptchaDescription')}</p>
            </div>
            <Switch
              checked={settings.enable_captcha}
              onCheckedChange={(checked) => updateSetting('enable_captcha', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('ssoSettings')}</CardTitle>
          <CardDescription>{t('ssoSettingsDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('enableSSO')}</Label>
              <p className="text-sm text-muted-foreground">{t('enableSSODescription')}</p>
            </div>
            <Switch
              checked={settings.sso_enabled}
              onCheckedChange={(checked) => updateSetting('sso_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('allowPasswordLogin')}</Label>
              <p className="text-sm text-muted-foreground">{t('allowPasswordLoginDescription')}</p>
            </div>
            <Switch
              checked={settings.sso_allow_password_login}
              onCheckedChange={(checked) => updateSetting('sso_allow_password_login', checked)}
              disabled={!settings.sso_enabled || !canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('autoCreateUsers')}</Label>
              <p className="text-sm text-muted-foreground">{t('autoCreateUsersDescription')}</p>
            </div>
            <Switch
              checked={settings.sso_auto_create_users}
              onCheckedChange={(checked) => updateSetting('sso_auto_create_users', checked)}
              disabled={!settings.sso_enabled || !canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('ssoRequireApproval')}</Label>
              <p className="text-sm text-muted-foreground">{t('ssoRequireApprovalDescription')}</p>
            </div>
            <Switch
              checked={settings.sso_require_approval}
              onCheckedChange={(checked) => updateSetting('sso_require_approval', checked)}
              disabled={!settings.sso_enabled || !canUpdate}
            />
          </div>
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('matchByEmail')}</Label>
              <p className="text-sm text-muted-foreground">{t('matchByEmailDescription')}</p>
            </div>
            <Switch
              checked={settings.sso_match_by_email}
              onCheckedChange={(checked) => updateSetting('sso_match_by_email', checked)}
              disabled={!settings.sso_enabled || !canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      <PermissionGuard permission="admin:settings:update">
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('saveChanges')}
          </Button>
        </div>
      </PermissionGuard>
    </div>
  )
}
