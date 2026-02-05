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
import { siteSettingsApi, type EmailSettings } from '@/lib/api'

interface EmailSettingsTabProps {
  settings: EmailSettings
  onSettingsChange: (settings: EmailSettings) => void
}

export function EmailSettingsTab({ settings, onSettingsChange }: EmailSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [testEmail, setTestEmail] = React.useState('')
  const [sendingTest, setSendingTest] = React.useState(false)

  const updateSetting = <K extends keyof EmailSettings>(key: K, value: EmailSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateEmail(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save email settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    if (!testEmail) {
      toast.error(t('testEmailRequired'))
      return
    }
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestEmail(testEmail)
      toast.success(t('testEmailSent'))
    } catch (error) {
      console.error('Failed to send test email:', error)
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="space-y-6">
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
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="smtp-port">{t('email.smtpPort')}</Label>
              <Input
                id="smtp-port"
                type="number"
                placeholder="587"
                value={settings.smtp_port}
                onChange={(e) => updateSetting('smtp_port', parseInt(e.target.value) || 587)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="smtp-encryption">{t('email.smtpEncryption')}</Label>
            <Select
              value={settings.smtp_encryption}
              onValueChange={(value) => value && updateSetting('smtp_encryption', value as 'none' | 'ssl' | 'tls')}
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
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 测试邮件 */}
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
              onChange={(e) => setTestEmail(e.target.value)}
            />
            <Button onClick={handleSendTest} disabled={sendingTest}>
              {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('email.sendTest')}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('save')}
        </Button>
      </div>
    </div>
  )
}
