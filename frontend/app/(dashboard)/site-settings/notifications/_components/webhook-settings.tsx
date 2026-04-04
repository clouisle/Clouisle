'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Loader2 } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { siteSettingsApi, type WebhookSettings } from '@/lib/api/admin/site-settings'

interface WebhookSettingsTabProps {
  settings: WebhookSettings
  onSettingsChange: (settings: WebhookSettings) => void
  canUpdate: boolean
}

export function WebhookSettingsTab({ settings, onSettingsChange, canUpdate }: WebhookSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [sendingTest, setSendingTest] = React.useState(false)
  const [headersText, setHeadersText] = React.useState(
    JSON.stringify(settings.webhook_headers || {}, null, 2)
  )

  const updateSetting = <K extends keyof WebhookSettings>(key: K, value: WebhookSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
  }

  const handleHeadersChange = (text: string) => {
    setHeadersText(text)
    try {
      const parsed = JSON.parse(text)
      updateSetting('webhook_headers', parsed)
    } catch {
      // Invalid JSON, don't update
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateWebhook(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save webhook settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestWebhook()
      toast.success(t('webhook.testSent'))
    } catch (error) {
      console.error('Failed to send test webhook:', error)
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 基础设置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('webhook.basicSettings')}</CardTitle>
          <CardDescription>{t('webhook.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>{t('webhook.enabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('webhook.enabledDesc')}</p>
            </div>
            <Switch
              checked={settings.webhook_enabled}
              onCheckedChange={(checked) => updateSetting('webhook_enabled', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      {/* Webhook 配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('webhook.endpointSettings')}</CardTitle>
          <CardDescription>{t('webhook.endpointSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="webhook-url">{t('webhook.url')}</Label>
            <Input
              id="webhook-url"
              type="url"
              placeholder="https://example.com/webhook"
              value={settings.webhook_url}
              onChange={(e) => updateSetting('webhook_url', e.target.value)}
              disabled={!canUpdate}
            />
            <p className="text-sm text-muted-foreground">{t('webhook.urlDesc')}</p>
          </div>

          <div className="space-y-2">
            <Label>{t('webhook.method')}</Label>
            <Select
              value={settings.webhook_method}
              onValueChange={(value) => value && updateSetting('webhook_method', value as 'POST' | 'GET')}
              disabled={!canUpdate}
            >
              <SelectTrigger className="min-w-[180px]">
                <SelectValue>{settings.webhook_method}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="POST">POST</SelectItem>
                <SelectItem value="GET">GET</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="webhook-secret">{t('webhook.secret')}</Label>
            <Input
              id="webhook-secret"
              type="password"
              placeholder={t('webhook.secretPlaceholder')}
              value={settings.webhook_secret}
              onChange={(e) => updateSetting('webhook_secret', e.target.value)}
              disabled={!canUpdate}
            />
            <p className="text-sm text-muted-foreground">{t('webhook.secretDesc')}</p>
          </div>
        </CardContent>
      </Card>

      {/* 高级配置 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('webhook.advancedSettings')}</CardTitle>
          <CardDescription>{t('webhook.advancedSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="webhook-headers">{t('webhook.headers')}</Label>
            <Textarea
              id="webhook-headers"
              placeholder='{"Authorization": "Bearer xxx"}'
              value={headersText}
              onChange={(e) => handleHeadersChange(e.target.value)}
              className="font-mono text-sm"
              rows={4}
              disabled={!canUpdate}
            />
            <p className="text-sm text-muted-foreground">{t('webhook.headersDesc')}</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="webhook-body-template">{t('webhook.bodyTemplate')}</Label>
            <Textarea
              id="webhook-body-template"
              placeholder='{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}'
              value={settings.webhook_body_template}
              onChange={(e) => updateSetting('webhook_body_template', e.target.value)}
              className="font-mono text-sm"
              rows={6}
              disabled={!canUpdate}
            />
            <p className="text-sm text-muted-foreground">{t('webhook.bodyTemplateDesc')}</p>
            <div className="rounded-md bg-muted p-3 text-sm">
              <p className="font-medium mb-2">{t('webhook.availablePlaceholders')}</p>
              <ul className="space-y-1 text-muted-foreground">
                <li><code className="bg-background px-1 rounded">{'{{title}}'}</code> - {t('webhook.placeholderTitle')}</li>
                <li><code className="bg-background px-1 rounded">{'{{content}}'}</code> - {t('webhook.placeholderContent')}</li>
                <li><code className="bg-background px-1 rounded">{'{{link_url}}'}</code> - {t('webhook.placeholderLinkUrl')}</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 测试消息 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('webhook.testMessage')}</CardTitle>
          <CardDescription>{t('webhook.testMessageDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={handleSendTest}
            disabled={sendingTest || !settings.webhook_enabled || !canUpdate}
            variant="outline"
          >
            {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('webhook.sendTest')}
          </Button>
        </CardContent>
      </Card>

      {/* 保存按钮 */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving || !canUpdate}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('save')}
        </Button>
      </div>
    </div>
  )
}
