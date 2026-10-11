'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Mail, Globe } from 'lucide-react'
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import type { EmailSettings, WebhookSettings } from '@/lib/api/site-settings'
import { EmailSettingsTab, WebhookSettingsTab } from './_components'
import { useCanPerform } from '@/components/permission-guard'

export default function SiteSettingsIntegrationsPage() {
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
  const [webhookSettings, setWebhookSettings] = React.useState<WebhookSettings>({
    webhook_enabled: false,
    webhook_url: '',
    webhook_method: 'POST',
    webhook_headers: {},
    webhook_body_template: '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
    webhook_secret: '',
  })

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const [emailData, webhookData] = await Promise.all([
        siteSettingsApi.getEmail(),
        siteSettingsApi.getWebhook(),
      ])
      setEmailSettings(emailData)
      setWebhookSettings(webhookData)
    } catch (error) {
      console.error('Failed to load integration settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  if (loading) {
    return (
      <div className="grid gap-6 xl:grid-cols-2">
        {[1, 2].map((index) => (
          <Card key={index}>
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
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4" />
            <CardTitle>{t('integrations.email')}</CardTitle>
          </div>
          <CardDescription>{t('email.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <EmailSettingsTab
            settings={emailSettings}
            onSettingsChange={setEmailSettings}
            canUpdate={canUpdate}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4" />
            <CardTitle>{t('integrations.webhook')}</CardTitle>
          </div>
          <CardDescription>{t('webhook.basicSettingsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <WebhookSettingsTab
            settings={webhookSettings}
            onSettingsChange={setWebhookSettings}
            canUpdate={canUpdate}
          />
        </CardContent>
      </Card>
    </div>
  )
}
