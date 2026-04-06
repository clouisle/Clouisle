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
import { siteSettingsApi, type SlackSettings } from '@/lib/api/admin/site-settings'

interface SlackSettingsTabProps {
  settings: SlackSettings
  onSettingsChange: (settings: SlackSettings) => void
  canUpdate: boolean
}

export function SlackSettingsTab({ settings, onSettingsChange, canUpdate }: SlackSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [sendingTest, setSendingTest] = React.useState(false)

  const updateSetting = <K extends keyof SlackSettings>(key: K, value: SlackSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateSlack(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save slack settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestSlack()
      toast.success(t('slack.testSent'))
    } catch (error) {
      console.error('Failed to send test slack:', error)
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 基础设置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('slack.basicSettings')}</CardTitle>
          <CardDescription>{t('slack.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('slack.enabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('slack.enabledDesc')}</p>
            </div>
            <Switch
              checked={settings.slack_enabled}
              onCheckedChange={(checked) => updateSetting('slack_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      {/* Webhook 配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('slack.webhookSettings')}</CardTitle>
          <CardDescription>
            {t('slack.webhookSettingsDesc')}
            <a
              href="https://api.slack.com/messaging/webhooks"
              target="_blank"
              rel="noopener noreferrer"
              className="ml-2 inline-flex items-center text-primary hover:underline"
            >
              {t('slack.viewDocs')}
              <ExternalLink className="ml-1 h-3 w-3" />
            </a>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="slack-webhook-url">{t('slack.webhookUrl')}</Label>
            <Input
              id="slack-webhook-url"
              type="url"
              placeholder="https://hooks.slack.com/services/..."
              value={settings.slack_webhook_url}
              onChange={(e) => updateSetting('slack_webhook_url', e.target.value)}
              disabled={!canUpdate}
            />
            <p className="text-sm text-muted-foreground">{t('slack.webhookUrlDesc')}</p>
          </div>
        </CardContent>
      </Card>

      {/* 测试消息 */}
      {canUpdate && (
        <Card>
          <CardHeader>
            <CardTitle>{t('slack.testMessage')}</CardTitle>
            <CardDescription>{t('slack.testMessageDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={handleSendTest}
              disabled={sendingTest || !settings.slack_enabled}
              variant="outline"
            >
              {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('slack.sendTest')}
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
