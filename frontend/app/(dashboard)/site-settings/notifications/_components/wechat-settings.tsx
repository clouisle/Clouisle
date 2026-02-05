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
import { siteSettingsApi, type WeChatSettings } from '@/lib/api'

interface WeChatSettingsTabProps {
  settings: WeChatSettings
  onSettingsChange: (settings: WeChatSettings) => void
}

export function WeChatSettingsTab({ settings, onSettingsChange }: WeChatSettingsTabProps) {
  const t = useTranslations('siteSettings')
  const [saving, setSaving] = React.useState(false)
  const [sendingTest, setSendingTest] = React.useState(false)

  const updateSetting = <K extends keyof WeChatSettings>(key: K, value: WeChatSettings[K]) => {
    onSettingsChange({ ...settings, [key]: value })
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      await siteSettingsApi.updateWeChat(settings)
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save wechat settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleSendTest = async () => {
    try {
      setSendingTest(true)
      await siteSettingsApi.sendTestWeChat()
      toast.success(t('wechat.testSent'))
    } catch (error) {
      console.error('Failed to send test wechat:', error)
    } finally {
      setSendingTest(false)
    }
  }

  return (
    <div className="space-y-6">
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
            />
          </div>

          <div className="space-y-2">
            <Label>{t('wechat.notificationType')}</Label>
            <Select
              value={settings.wechat_notification_type}
              onValueChange={(value) => value && updateSetting('wechat_notification_type', value as 'webhook' | 'app')}
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
              />
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
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="wechat-agent-id">{t('wechat.agentId')}</Label>
              <Input
                id="wechat-agent-id"
                placeholder={t('wechat.agentIdPlaceholder')}
                value={settings.wechat_agent_id}
                onChange={(e) => updateSetting('wechat_agent_id', e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="wechat-secret">{t('wechat.secret')}</Label>
              <Input
                id="wechat-secret"
                type="password"
                placeholder={t('wechat.secretPlaceholder')}
                value={settings.wechat_secret}
                onChange={(e) => updateSetting('wechat_secret', e.target.value)}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* 测试消息 */}
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
