'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Bot, GitBranch } from 'lucide-react'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AdminAgentsPanel, AdminWorkflowsPanel } from './_components'

type AppsTab = 'agents' | 'workflows'

export default function AppsManagementPage() {
  const t = useTranslations('apps.admin')
  const router = useRouter()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<AppsTab>('agents')

  useEffect(() => {
    setActiveTab(searchParams.get('tab') === 'workflows' ? 'workflows' : 'agents')
  }, [searchParams])

  const handleTabChange = (value: string) => {
    const nextTab: AppsTab = value === 'workflows' ? 'workflows' : 'agents'
    setActiveTab(nextTab)
    router.replace(nextTab === 'agents' ? '/apps' : '/apps?tab=workflows', { scroll: false })
  }

  return (
    <RoutePermissionGuard>
      <div className="flex h-full flex-col">
        <Header />
        <div className="flex flex-1 flex-col gap-4 overflow-auto p-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t('title')}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
          </div>

          <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
            <TabsList>
              <TabsTrigger value="agents">
                <Bot className="mr-2 h-4 w-4" />
                {t('tabs.agents')}
              </TabsTrigger>
              <TabsTrigger value="workflows">
                <GitBranch className="mr-2 h-4 w-4" />
                {t('tabs.workflows')}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="agents" className="space-y-4">
              <AdminAgentsPanel />
            </TabsContent>

            <TabsContent value="workflows" className="space-y-4">
              <AdminWorkflowsPanel />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
