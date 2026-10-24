'use client'

import * as React from 'react'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useCanPerform } from '@/components/permission-guard'
import { usePermissions } from '@/hooks/use-permissions'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { integrationsApi, type FeishuConfig, type Integration } from '@/lib/api/admin/integrations'
import { FeishuIntegrationTab, FeishuKnowledgeSync } from '../_components'

type FeishuSettingsTab = 'configuration' | 'directory' | 'notification' | 'agentChat' | 'knowledge'

export default function FeishuIntegrationPage() {
  const t = useTranslations('siteSettings')
  const tCommon = useTranslations('common')
  const { user } = usePermissions()
  const { canPerform } = useCanPerform()
  const [config, setConfig] = React.useState<FeishuConfig | null>(null)
  const [instances, setInstances] = React.useState<Integration[]>([])
  const [tab, setTab] = React.useState<FeishuSettingsTab>('configuration')

  React.useEffect(() => {
    void Promise.all([integrationsApi.getFeishuConfig(), integrationsApi.list()])
      .then(([feishu, list]) => {
        setConfig(feishu)
        setInstances(list)
      })
      .catch(() => {
        // API interceptor handles backend errors.
      })
  }, [])

  // Knowledge import writes into local knowledge bases, so it stays with the
  // knowledge-base audience even though the app credentials are shared here.
  const canManageKnowledge = user?.is_superuser === true && user.is_active === true
  const integration = instances.find((instance) => instance.provider_type === 'feishu') ?? null

  return <div className="space-y-6">
    <div className="flex items-center gap-3">
      <Link
        href="/site-settings/integrations"
        aria-label={t('integrations.back')}
        className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">{t('integrations.feishu')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('integrations.feishuDescription')}</p>
      </div>
    </div>
    <Tabs value={tab} onValueChange={(value) => setTab(value as FeishuSettingsTab)} className="space-y-4">
      <TabsList>
        <TabsTrigger value="configuration">{t('integrations.tabConfiguration')}</TabsTrigger>
        <TabsTrigger value="directory">{t('integrations.tabDirectory')}</TabsTrigger>
        <TabsTrigger value="notification">{t('integrations.tabNotification')}</TabsTrigger>
        <TabsTrigger value="agentChat">{t('integrations.tabAgentChat')}</TabsTrigger>
        {canManageKnowledge && <TabsTrigger value="knowledge">{t('feishuKnowledge.title')}</TabsTrigger>}
      </TabsList>
      <TabsContent value={tab} className="space-y-4">
        {tab === 'knowledge' ? (
          <FeishuKnowledgeSync />
        ) : config ? (
          <FeishuIntegrationTab
            config={config}
            onConfigChange={setConfig}
            canUpdate={canPerform('admin:integrations:settings:update')}
            integration={integration}
            canUpdateLogin={canPerform('admin:integrations:login:update')}
            onIntegrationChange={(updated) => {
              setInstances((current) => current.map((item) => item.id === updated.id ? updated : item))
              setConfig(current => current ? { ...current, is_enabled: updated.is_enabled } : current)
            }}
            tab={tab}
          />
        ) : <p className="text-muted-foreground">{tCommon('loading')}</p>}
      </TabsContent>
    </Tabs>
  </div>
}
