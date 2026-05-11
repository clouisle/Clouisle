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
import { siteSettingsApi, type WeChatSettings } from '@/lib/api/admin/site-settings'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

interface WeChatSettingsTabProps {
  settings: WeChatSettings
  onSettingsChange: (settings: WeChatSettings) => void
  canUpdate: boolean
}

export function WeChatSettingsTab({ settings, onSettingsChange, canUpdate }: WeChatSettingsTabProps) {
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
    () => getValidationSummaryEntries(fieldErrors, ['wechat_webhook_url', 'wechat_corp_id', 'wechat_agent_id', 'wechat_secret']),
    [fieldErrors]
  )

  const updateSetting = <K extends keyof WeChatSettings>(key: K, value: WeChatSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
    setFieldErrors((prev) => clearValidationError(prev, key))
  }

  const validateSettings = () => {
    const nextErrors: Record<string, string> = {}

    if (!settings.wechat_enabled) {
      return nextErrors
    }

    if (settings.wechat_notification_type === 'webhook') {
      if (!settings.wechat_webhook_url.trim()) {
        nextErrors.wechat_webhook_url = t('required')
      }
    } else {
      if (!settings.wechat_corp_id.trim()) nextErrors.wechat_corp_id = t('required')
      if (!settings.wechat_agent_id.trim()) nextErrors.wechat_agent_id = t('required')
      if (!settings.wechat_secret.trim()) nextErrors.wechat_secret = t('required')
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
      await siteSettingsApi.updateWeChat(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save wechat settings:', error)
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
      await siteSettingsApi.sendTestWeChat()
      toast.success(t('wechat.testSent'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors((prev) => ({ ...prev, ...errors }))
      }
      console.error('Failed to send test wechat:', error)
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
          <CardTitle>{t('wechat.basicSettings')}</CardTitle>
          <CardDescription>{t('wechat.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('wechat.enabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('wechat.enabledDesc')}</p>
            </div>
            <Switch
              checked={settings.wechat_enabled}
              onCheckedChange={(checked) => updateSetting('wechat_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('wechat.notificationType')}</Label>
            <Select
              value={settings.wechat_notification_type}
              onValueChange={(value) => value && updateSetting('wechat_notification_type', value as 'webhook' | 'app')}
              disabled={!canUpdate}
            >
              <SelectTrigger className="min-w-[180px]">
                <SelectValue>
                  {settings.wechat_notification_type === 'webhook' && t('wechat.typeWebhook')}
                  {settings.wechat_notification_type === 'app' && t('wechat.typeApp')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="webhook">{t('wechat.typeWebhook')}</SelectItem>
                <SelectItem value="app">{t('wechat.typeApp')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">{t('wechat.notificationTypeDesc')}</p>
          </div>
        </CardContent>
      </Card>

      {/* Webhook 配置 */}
      {settings.wechat_notification_type === 'webhook' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('wechat.webhookSettings')}</CardTitle>
            <CardDescription>
              {t('wechat.webhookSettingsDesc')}
              <a
                href="https://developer.work.weixin.qq.com/document/path/91770"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('wechat.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wechat-webhook-url">{t('wechat.webhookUrl')}</Label>
              <Input
                id="wechat-webhook-url"
                type="url"
                placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
                value={settings.wechat_webhook_url}
                onChange={(e) => updateSetting('wechat_webhook_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.wechat_webhook_url}
              />
              <FieldError>{fieldErrors.wechat_webhook_url}</FieldError>
              <p className="text-sm text-muted-foreground">{t('wechat.webhookUrlDesc')}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 企业应用配置 */}
      {settings.wechat_notification_type === 'app' && (
        <Card>
          <CardHeader>
            <CardTitle>{t('wechat.appSettings')}</CardTitle>
            <CardDescription>
              {t('wechat.appSettingsDesc')}
              <a
                href="https://developer.work.weixin.qq.com/document/path/90236"
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center text-primary hover:underline"
              >
                {t('wechat.viewDocs')}
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wechat-corp-id">{t('wechat.corpId')}</Label>
              <Input
                id="wechat-corp-id"
                placeholder={t('wechat.corpIdPlaceholder')}
                value={settings.wechat_corp_id}
                onChange={(e) => updateSetting('wechat_corp_id', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.wechat_corp_id}
              />
              <FieldError>{fieldErrors.wechat_corp_id}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="wechat-agent-id">{t('wechat.agentId')}</Label>
              <Input
                id="wechat-agent-id"
                placeholder={t('wechat.agentIdPlaceholder')}
                value={settings.wechat_agent_id}
                onChange={(e) => updateSetting('wechat_agent_id', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.wechat_agent_id}
              />
              <FieldError>{fieldErrors.wechat_agent_id}</FieldError>
            </div>

            <div className="space-y-2">
              <Label htmlFor="wechat-secret">{t('wechat.secret')}</Label>
              <Input
                id="wechat-secret"
                type="password"
                placeholder={t('wechat.secretPlaceholder')}
                value={settings.wechat_secret}
                onChange={(e) => updateSetting('wechat_secret', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.wechat_secret}
              />
              <FieldError>{fieldErrors.wechat_secret}</FieldError>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 测试消息 */}
      {canUpdate && (
        <Card>
          <CardHeader>
            <CardTitle>{t('wechat.testMessage')}</CardTitle>
            <CardDescription>{t('wechat.testMessageDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={handleSendTest}
              disabled={sendingTest || !settings.wechat_enabled}
              variant="outline"
            >
              {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('wechat.sendTest')}
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
