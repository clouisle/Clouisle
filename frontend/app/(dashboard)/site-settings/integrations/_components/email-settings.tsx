'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Loader2 } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FieldError } from '@/components/ui/field'
import { siteSettingsApi, type EmailSettings } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

interface EmailSettingsTabProps {
  settings: EmailSettings
  onSettingsChange: (settings: EmailSettings) => void
  canUpdate: boolean
}

export function EmailSettingsTab({ settings, onSettingsChange, canUpdate }: EmailSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [testEmail, setTestEmail] = React.useState('')
  const [sendingTest, setSendingTest] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})

  const errorPathMap = React.useMemo(
    () => Object.fromEntries(
      Object.keys(settings).flatMap((key) => [
        [key, key],
        [`settings.${key}`, key],
      ])
    ),
    [settings]
  )

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['smtp_host', 'email_from_address', 'testEmail']),
    [fieldErrors]
  )

  const updateSetting = <K extends keyof EmailSettings>(key: K, value: EmailSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
    setFieldErrors((prev) => clearValidationError(prev, key))
  }

  const handleSave = async () => {
    const nextErrors: Record<string, string> = {}

    if (settings.smtp_enabled) {
      if (!settings.smtp_host.trim()) nextErrors.smtp_host = t('required')
      if (!settings.email_from_address.trim()) nextErrors.email_from_address = t('required')
    }

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.updateEmail(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save email settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    if (!testEmail.trim()) {
      setFieldErrors((prev) => ({ ...clearValidationError(prev, 'testEmail'), testEmail: t('testEmailRequired') }))
      return
    }

    setFieldErrors((prev) => clearValidationError(prev, 'testEmail'))
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestEmail(testEmail)
      toast.success(t('testEmailSent'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), { email: 'testEmail' })
      if (Object.keys(errors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...errors }))
      }
      console.error('Failed to send test email:', error)
    } finally {
      setSendingTest(false)
    }
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
      {/* 基础设置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('email.basicSettings')}</CardTitle>
          <CardDescription>{t('email.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('email.smtpEnabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('email.smtpEnabledDesc')}</p>
            </div>
            <Switch
              checked={settings.smtp_enabled}
              onCheckedChange={(checked) => updateSetting('smtp_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      {/* SMTP 服务器配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('email.smtpServer')}</CardTitle>
          <CardDescription>{t('email.smtpServerDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="smtp-host">{t('email.smtpHost')}</Label>
              <Input
                id="smtp-host"
                placeholder="smtp.example.com"
                value={settings.smtp_host}
                onChange={(e) => updateSetting('smtp_host', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.smtp_host}
              />
              <FieldError>{fieldErrors.smtp_host}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="smtp-port">{t('email.smtpPort')}</Label>
              <Input
                id="smtp-port"
                placeholder="587"
                value={settings.smtp_port}
                onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value) || 587)}
                disabled={!canUpdate}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="smtp-encryption">{t('email.smtpEncryption')}</Label>
            <Select
              value={settings.smtp_encryption}
              onValueChange={(value) => value && updateSetting('smtp_encryption', value as 'none' | 'ssl' | 'tls')}
              disabled={!canUpdate}
            >
              <SelectTrigger id="smtp-encryption" className="min-w-[180px]">
                <SelectValue>
                  {settings.smtp_encryption === 'none' && t('email.encryptionNone')}
                  {settings.smtp_encryption === 'ssl' && 'SSL'}
                  {settings.smtp_encryption === 'tls' && 'TLS/STARTTLS'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('email.encryptionNone')}</SelectItem>
                <SelectItem value="ssl">SSL</SelectItem>
                <SelectItem value="tls">TLS/STARTTLS</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="smtp-username">{t('email.smtpUsername')}</Label>
              <Input
                id="smtp-username"
                placeholder={t('email.smtpUsernamePlaceholder')}
                value={settings.smtp_username}
                onChange={(e) => updateSetting('smtp_username', e.target.value)}
                disabled={!canUpdate}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="smtp-password">{t('email.smtpPassword')}</Label>
              <Input
                id="smtp-password"
                type="password"
                placeholder={t('email.smtpPasswordPlaceholder')}
                value={settings.smtp_password}
                onChange={(e) => updateSetting('smtp_password', e.target.value)}
                disabled={!canUpdate}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 发件人信息 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('email.senderInfo')}</CardTitle>
          <CardDescription>{t('email.senderInfoDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="from-name">{t('email.fromName')}</Label>
              <Input
                id="from-name"
                placeholder="Clouisle"
                value={settings.email_from_name}
                onChange={(e) => updateSetting('email_from_name', e.target.value)}
                disabled={!canUpdate}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="from-address">{t('email.fromAddress')}</Label>
              <Input
                id="from-address"
                type="email"
                placeholder="noreply@example.com"
                value={settings.email_from_address}
                onChange={(e) => updateSetting('email_from_address', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.email_from_address}
              />
              <FieldError>{fieldErrors.email_from_address}</FieldError>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 测试邮件 */}
      {canUpdate && (
        <Card>
          <CardHeader>
            <CardTitle>{t('email.testEmail')}</CardTitle>
            <CardDescription>{t('email.testEmailDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder={t('email.testEmailPlaceholder')}
                value={testEmail}
                onChange={(e) => {
                  setTestEmail(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'testEmail'))
                }}
                aria-invalid={!!fieldErrors.testEmail}
              />
              <Button onClick={handleSendTest} disabled={sendingTest}>
                {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('email.sendTest')}
              </Button>
            </div>
            <FieldError>{fieldErrors.testEmail}</FieldError>
          </CardContent>
        </Card>
      )}

      {/* 保存按钮 */}
      {canUpdate && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('save')}
          </Button>
        </div>
      )}
    </div>
  )
}
