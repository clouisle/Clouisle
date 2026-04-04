'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Mail, MessageSquare, Globe, Hash, Bell } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import type {
  EmailSettings,
  DingTalkSettings,
  WeChatSettings,
  FeishuSettings,
  WebhookSettings,
  SlackSettings,
} from '@/lib/api/site-settings'
import {
  EmailSettingsTab,
  DingTalkSettingsTab,
  WeChatSettingsTab,
  FeishuSettingsTab,
  WebhookSettingsTab,
  SlackSettingsTab,
  AutoNotificationsSettingsTab,
} from './_components'
import { useCanPerform } from '@/components/permission-guard'

export default function SiteSettingsNotificationsPage() {
  const t = useTranslations('siteSettings')
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')

  const [loading, setLoading] = React.useState(true)

  const [emailSettings, setEmailSettings] = React.useState<EmailSettings>({
    smtp_enabled: false,
    smtp_host: '',
    smtp_port: 587,
    smtp_encryption: 'tls',
    smtp_username: '',
    smtp_password: '',
    email_from_name: 'Clouisle',
    email_from_address: '',
  })

  const [dingtalkSettings, setDingtalkSettings] = React.useState<DingTalkSettings>({
    dingtalk_enabled: false,
    dingtalk_notification_type: 'webhook',
    dingtalk_webhook_url: '',
    dingtalk_secret: '',
    dingtalk_app_key: '',
    dingtalk_app_secret: '',
    dingtalk_agent_id: '',
  })

  const [wechatSettings, setWechatSettings] = React.useState<WeChatSettings>({
    wechat_enabled: false,
    wechat_notification_type: 'webhook',
    wechat_webhook_url: '',
    wechat_corp_id: '',
    wechat_agent_id: '',
    wechat_secret: '',
  })

  const [feishuSettings, setFeishuSettings] = React.useState<FeishuSettings>({
    feishu_enabled: false,
    feishu_notification_type: 'webhook',
    feishu_webhook_url: '',
    feishu_secret: '',
    feishu_app_id: '',
    feishu_app_secret: '',
  })

  const [webhookSettings, setWebhookSettings] = React.useState<WebhookSettings>({
    webhook_enabled: false,
    webhook_url: '',
    webhook_method: 'POST',
    webhook_headers: {},
    webhook_body_template: '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
    webhook_secret: '',
  })

  const [slackSettings, setSlackSettings] = React.useState<SlackSettings>({
    slack_enabled: false,
    slack_webhook_url: '',
  })

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const [emailData, dingtalkData, wechatData, feishuData, webhookData, slackData] = await Promise.all([
        siteSettingsApi.getEmail(),
        siteSettingsApi.getDingTalk(),
        siteSettingsApi.getWeChat(),
        siteSettingsApi.getFeishu(),
        siteSettingsApi.getWebhook(),
        siteSettingsApi.getSlack(),
      ])
      setEmailSettings(emailData)
      setDingtalkSettings(dingtalkData)
      setWechatSettings(wechatData)
      setFeishuSettings(feishuData)
      setWebhookSettings(webhookData)
      setSlackSettings(slackData)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  // Enabled channels for auto notifications
  const enabledChannels = {
    email: emailSettings.smtp_enabled,
    dingtalk: dingtalkSettings.dingtalk_enabled,
    wechat: wechatSettings.wechat_enabled,
    feishu: feishuSettings.feishu_enabled,
    webhook: webhookSettings.webhook_enabled,
    slack: slackSettings.slack_enabled,
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
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <Tabs defaultValue="auto" className="space-y-6">
      <TabsList className="grid w-full grid-cols-7">
        <TabsTrigger value="auto" className="flex items-center gap-2">
          <Bell className="h-4 w-4" />
          <span className="hidden sm:inline">{t('autoNotifications.tab')}</span>
        </TabsTrigger>
        <TabsTrigger value="email" className="flex items-center gap-2">
          <Mail className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.email')}</span>
        </TabsTrigger>
        <TabsTrigger value="dingtalk" className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.dingtalk')}</span>
        </TabsTrigger>
        <TabsTrigger value="wechat" className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.wechat')}</span>
        </TabsTrigger>
        <TabsTrigger value="feishu" className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.feishu')}</span>
        </TabsTrigger>
        <TabsTrigger value="webhook" className="flex items-center gap-2">
          <Globe className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.webhook')}</span>
        </TabsTrigger>
        <TabsTrigger value="slack" className="flex items-center gap-2">
          <Hash className="h-4 w-4" />
          <span className="hidden sm:inline">{t('notifications.slack')}</span>
        </TabsTrigger>
      </TabsList>

      <TabsContent value="auto">
        <AutoNotificationsSettingsTab enabledChannels={enabledChannels} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="email">
        <EmailSettingsTab settings={emailSettings} onSettingsChange={setEmailSettings} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="dingtalk">
        <DingTalkSettingsTab settings={dingtalkSettings} onSettingsChange={setDingtalkSettings} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="wechat">
        <WeChatSettingsTab settings={wechatSettings} onSettingsChange={setWechatSettings} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="feishu">
        <FeishuSettingsTab settings={feishuSettings} onSettingsChange={setFeishuSettings} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="webhook">
        <WebhookSettingsTab settings={webhookSettings} onSettingsChange={setWebhookSettings} canUpdate={canUpdate} />
      </TabsContent>

      <TabsContent value="slack">
        <SlackSettingsTab settings={slackSettings} onSettingsChange={setSlackSettings} canUpdate={canUpdate} />
      </TabsContent>
    </Tabs>
  )
}
