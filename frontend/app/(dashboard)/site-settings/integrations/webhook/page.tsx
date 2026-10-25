'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { useCanPerform } from '@/components/permission-guard'
import { integrationsApi, type Integration } from '@/lib/api/admin/integrations'
import type { WebhookSettings } from '@/lib/api/site-settings'
import { WebhookSettingsTab } from '../_components'

export default function WebhookIntegrationPage() {
  const t = useTranslations('siteSettings')
  const tCommon = useTranslations('common')
  const { canPerform } = useCanPerform()
  const [settings, setSettings] = React.useState<WebhookSettings | null>(null)
  const [integration, setIntegration] = React.useState<Integration | null>(null)

  React.useEffect(() => {
    void Promise.all([integrationsApi.getWebhook(), integrationsApi.list()])
      .then(([webhook, instances]) => {
        setSettings(webhook)
        setIntegration(instances.find((instance) => instance.provider_type === 'webhook') ?? null)
      })
      .catch(() => {
        // API interceptor handles backend errors.
      })
  }, [])

  return <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-semibold">{t('integrations.webhook')}</h1>
      <Link href="/site-settings/integrations">{t('integrations.back')}</Link>
    </div>
    {settings
      ? <WebhookSettingsTab
          settings={settings}
          onSettingsChange={setSettings}
          canUpdate={canPerform('admin:integrations:settings:update')}
          credentialsConfigured={integration?.credentials_configured}
        />
      : <p className="text-muted-foreground">{tCommon('loading')}</p>}
  </div>
}
