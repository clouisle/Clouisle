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
import { siteSettingsApi, type FeishuSettings } from '@/lib/api/admin/site-settings'

interface FeishuSettingsTabProps {
  settings: FeishuSettings
  onSettingsChange: (settings: FeishuSettings) => void
  canUpdate: boolean
}

export function FeishuSettingsTab({ settings, onSettingsChange, canUpdate }: FeishuSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [sendingTest, setSendingTest] = React.useState(false)

  const updateSetting = <K extends keyof FeishuSettings>(key: K, value: FeishuSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateFeishu(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save feishu settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestFeishu()
      toast.success(t('feishu.testSent'))
    } catch (error) {
      console.error('Failed to send test feishu:', error)
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="space-y-6">
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
              />
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
              />
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
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 测试消息 */}
      <Card>
        <CardHeader>
          <CardTitle>{t('feishu.testMessage')}</CardTitle>
          <CardDescription>{t('feishu.testMessageDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={handleSendTest}
            disabled={sendingTest || !settings.feishu_enabled || !canUpdate}
            variant="outline"
          >
            {sendingTest && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('feishu.sendTest')}
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
