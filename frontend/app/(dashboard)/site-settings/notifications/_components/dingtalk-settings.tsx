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
import { siteSettingsApi, type DingTalkSettings } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

interface DingTalkSettingsTabProps {
  settings: DingTalkSettings
  onSettingsChange: (settings: DingTalkSettings) => void
  canUpdate: boolean
}

export function DingTalkSettingsTab({ settings, onSettingsChange, canUpdate }: DingTalkSettingsTabProps) {
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
    () => getValidationSummaryEntries(fieldErrors, ['dingtalk_webhook_url', 'dingtalk_app_key', 'dingtalk_app_secret', 'dingtalk_agent_id']),
    [fieldErrors]
  )

  const updateSetting = <K extends keyof DingTalkSettings>(key: K, value: DingTalkSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
    setFieldErrors((prev) => clearValidationError(prev, key))
  }

  const validateSettings = () => {
    const nextErrors: Record<string, string> = {}

    if (!settings.dingtalk_enabled) {
      return nextErrors
    }

    if (settings.dingtalk_notification_type === 'webhook') {
      if (!settings.dingtalk_webhook_url.trim()) {
        nextErrors.dingtalk_webhook_url = t('required')
      }
    } else {
      if (!settings.dingtalk_app_key.trim()) nextErrors.dingtalk_app_key = t('required')
      if (!settings.dingtalk_app_secret.trim()) nextErrors.dingtalk_app_secret = t('required')
      if (!settings.dingtalk_agent_id.trim()) nextErrors.dingtalk_agent_id = t('required')
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
      await siteSettingsApi.updateDingTalk(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save dingtalk settings:', error)
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
      await siteSettingsApi.sendTestDingTalk()
      toast.success(t('dingtalk.testSent'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...errors }))
      }
      console.error('Failed to send test dingtalk:', error)
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
          <CardTitle>{t('dingtalk.basicSettings')}</CardTitle>
          <CardDescription>{t('dingtalk.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('dingtalk.enabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('dingtalk.enabledDesc')}</p>
            </div>
            <Switch
              checked={settings.dingtalk_enabled}
              onCheckedChange={(checked) => updateSetting('dingtalk_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('dingtalk.notificationType')}</Label>
            <Select
              value={settings.dingtalk_notification_type}
              onValueChange={(value) => value && updateSetting('dingtalk_notification_type', value as 'webhook' | 'app')}
              disabled={!canUpdate}
            >
              <SelectTrigger className="min-w-[180px]">
                <SelectValue>
                  {settings.dingtalk_notification_type === 'webhook' && t('dingtalk.typeWebhook')}
                  {settings.dingtalk_notification_type === 'app' && t('dingtalk.typeApp')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="webhook">{t('dingtalk.typeWebhook')}</SelectItem>
                <SelectItem value="app">{t('dingtalk.typeApp')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">{t('dingtalk.notificationTypeDesc')}</p>
          </div>
        </CardContent>
      </Card>

      {/* Webhook 配置 */}
      {settings.dingtalk_notification_type === 'webhook' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('dingtalk.webhookSettings')}</CardTitle>
            <CardDescription>
              {t('dingtalk.webhookSettingsDesc')}
              <a
                href="https://open.dingtalk.com/document/robots/custom-robot-access"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('dingtalk.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dingtalk-webhook-url">{t('dingtalk.webhookUrl')}</Label>
              <Input
                id="dingtalk-webhook-url"
                type="url"
                placeholder="https://oapi.dingtalk.com/robot/send?access_token=..."
                value={settings.dingtalk_webhook_url}
                onChange={(e) => updateSetting('dingtalk_webhook_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.dingtalk_webhook_url}
              />
              <FieldError>{fieldErrors.dingtalk_webhook_url}</FieldError>
              <p className="text-sm text-muted-foreground">{t('dingtalk.webhookUrlDesc')}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dingtalk-secret">{t('dingtalk.secret')}</Label>
              <Input
                id="dingtalk-secret"
                type="password"
                placeholder={t('dingtalk.secretPlaceholder')}
                value={settings.dingtalk_secret}
                onChange={(e) => updateSetting('dingtalk_secret', e.target.value)}
                disabled={!canUpdate}
              />
              <p className="text-sm text-muted-foreground">{t('dingtalk.secretDesc')}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 企业应用配置 */}
      {settings.dingtalk_notification_type === 'app' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('dingtalk.appSettings')}</CardTitle>
            <CardDescription>
              {t('dingtalk.appSettingsDesc')}
              <a
                href="https://open.dingtalk.com/document/orgapp/develop-org-internal-apps"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('dingtalk.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="dingtalk-app-key">{t('dingtalk.appKey')}</Label>
              <Input
                id="dingtalk-app-key"
                placeholder={t('dingtalk.appKeyPlaceholder')}
                value={settings.dingtalk_app_key}
                onChange={(e) => updateSetting('dingtalk_app_key', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.dingtalk_app_key}
              />
              <FieldError>{fieldErrors.dingtalk_app_key}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dingtalk-app-secret">{t('dingtalk.appSecret')}</Label>
              <Input
                id="dingtalk-app-secret"
                type="password"
                placeholder={t('dingtalk.appSecretPlaceholder')}
                value={settings.dingtalk_app_secret}
                onChange={(e) => updateSetting('dingtalk_app_secret', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.dingtalk_app_secret}
              />
              <FieldError>{fieldErrors.dingtalk_app_secret}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dingtalk-agent-id">{t('dingtalk.agentId')}</Label>
              <Input
                id="dingtalk-agent-id"
                placeholder={t('dingtalk.agentIdPlaceholder')}
                value={settings.dingtalk_agent_id}
                onChange={(e) => updateSetting('dingtalk_agent_id', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.dingtalk_agent_id}
              />
              <FieldError>{fieldErrors.dingtalk_agent_id}</FieldError>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 测试消息 */}
      {canUpdate && (
        <Card>
          <CardHeader>
            <CardTitle>{t('dingtalk.testMessage')}</CardTitle>
            <CardDescription>{t('dingtalk.testMessageDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={handleSendTest}
              disabled={sendingTest || !settings.dingtalk_enabled}
              variant="outline"
            >
              {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('dingtalk.sendTest')}
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
