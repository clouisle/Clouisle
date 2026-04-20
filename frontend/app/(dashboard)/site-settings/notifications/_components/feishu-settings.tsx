'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Loader2, ExternalLink } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FieldError } from '@/components/ui/field'
import { siteSettingsApi, type FeishuSettings } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

interface FeishuSettingsTabProps {
  settings: FeishuSettings
  onSettingsChange: (settings: FeishuSettings) => void
  canUpdate: boolean
}

export function FeishuSettingsTab({ settings, onSettingsChange, canUpdate }: FeishuSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
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
    () => getValidationSummaryEntries(fieldErrors, ['feishu_webhook_url', 'feishu_app_id', 'feishu_app_secret']),
    [fieldErrors]
  )

  const updateSetting = <K extends keyof FeishuSettings>(key: K, value: FeishuSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
    setFieldErrors((prev) => clearValidationError(prev, key))
  }

  const validateSettings = () => {
    const nextErrors: Record<string, string> = {}

    if (!settings.feishu_enabled) {
      return nextErrors
    }

    if (settings.feishu_notification_type === 'webhook') {
      if (!settings.feishu_webhook_url.trim()) {
        nextErrors.feishu_webhook_url = t('required')
      }
    } else {
      if (!settings.feishu_app_id.trim()) nextErrors.feishu_app_id = t('required')
      if (!settings.feishu_app_secret.trim()) nextErrors.feishu_app_secret = t('required')
    }

    return nextErrors
  }

  const handleSave = async () => {
    const nextErrors = validateSettings()
    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.updateFeishu(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save feishu settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    const nextErrors = validateSettings()
    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestFeishu()
      toast.success(t('feishu.testSent'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...errors }))
      }
      console.error('Failed to send test feishu:', error)
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
          <CardTitle>{t('feishu.basicSettings')}</CardTitle>
          <CardDescription>{t('feishu.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('feishu.enabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('feishu.enabledDesc')}</p>
            </div>
            <Switch
              checked={settings.feishu_enabled}
              onCheckedChange={(checked) => updateSetting('feishu_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('feishu.notificationType')}</Label>
            <Select
              value={settings.feishu_notification_type}
              onValueChange={(value) => value && updateSetting('feishu_notification_type', value as 'webhook' | 'app')}
              disabled={!canUpdate}
            >
              <SelectTrigger className="min-w-[180px]">
                <SelectValue>
                  {settings.feishu_notification_type === 'webhook' && t('feishu.typeWebhook')}
                  {settings.feishu_notification_type === 'app' && t('feishu.typeApp')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="webhook">{t('feishu.typeWebhook')}</SelectItem>
                <SelectItem value="app">{t('feishu.typeApp')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">{t('feishu.notificationTypeDesc')}</p>
          </div>
        </CardContent>
      </Card>

      {/* Webhook 配置 */}
      {settings.feishu_notification_type === 'webhook' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('feishu.webhookSettings')}</CardTitle>
            <CardDescription>
              {t('feishu.webhookSettingsDesc')}
              <a
                href="https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('feishu.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="feishu-webhook-url">{t('feishu.webhookUrl')}</Label>
              <Input
                id="feishu-webhook-url"
                type="url"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                value={settings.feishu_webhook_url}
                onChange={(e) => updateSetting('feishu_webhook_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.feishu_webhook_url}
              />
              <FieldError>{fieldErrors.feishu_webhook_url}</FieldError>
              <p className="text-sm text-muted-foreground">{t('feishu.webhookUrlDesc')}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="feishu-secret">{t('feishu.secret')}</Label>
              <Input
                id="feishu-secret"
                type="password"
                placeholder={t('feishu.secretPlaceholder')}
                value={settings.feishu_secret}
                onChange={(e) => updateSetting('feishu_secret', e.target.value)}
                disabled={!canUpdate}
              />
              <p className="text-sm text-muted-foreground">{t('feishu.secretDesc')}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 企业应用配置 */}
      {settings.feishu_notification_type === 'app' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('feishu.appSettings')}</CardTitle>
            <CardDescription>
              {t('feishu.appSettingsDesc')}
              <a
                href="https://open.feishu.cn/document/home/introduction-to-custom-app-development/self-built-application-development-process"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('feishu.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="feishu-app-id">{t('feishu.appId')}</Label>
              <Input
                id="feishu-app-id"
                placeholder={t('feishu.appIdPlaceholder')}
                value={settings.feishu_app_id}
                onChange={(e) => updateSetting('feishu_app_id', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.feishu_app_id}
              />
              <FieldError>{fieldErrors.feishu_app_id}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="feishu-app-secret">{t('feishu.appSecret')}</Label>
              <Input
                id="feishu-app-secret"
                type="password"
                placeholder={t('feishu.appSecretPlaceholder')}
                value={settings.feishu_app_secret}
                onChange={(e) => updateSetting('feishu_app_secret', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.feishu_app_secret}
              />
              <FieldError>{fieldErrors.feishu_app_secret}</FieldError>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 测试消息 */}
      {canUpdate && (
        <Card>
          <CardHeader>
            <CardTitle>{t('feishu.testMessage')}</CardTitle>
            <CardDescription>{t('feishu.testMessageDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={handleSendTest}
              disabled={sendingTest || !settings.feishu_enabled}
              variant="outline"
            >
              {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('feishu.sendTest')}
            </Button>
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
