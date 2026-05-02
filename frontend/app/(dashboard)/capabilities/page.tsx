'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { PackageOpen, Wrench } from 'lucide-react'
import { RoutePermissionGuard } from '@/components/auth/permission-guard'
import { Header } from '@/components/layout/header'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AdminSkillsPanel, ToolsClient } from './_components'

type CapabilityTab = 'tools' | 'skills'

export default function CapabilitiesPage() {
  const t = useTranslations('platform.tools')
  const router = useRouter()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<CapabilityTab>('tools')

  useEffect(() => {
    setActiveTab(searchParams.get('tab') === 'skills' ? 'skills' : 'tools')
  }, [searchParams])

  const handleTabChange = (value: string) => {
    const nextTab: CapabilityTab = value === 'skills' ? 'skills' : 'tools'
    setActiveTab(nextTab)
    router.replace(nextTab === 'tools' ? '/capabilities' : '/capabilities?tab=skills', { scroll: false })
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
            <TabsTrigger value="tools">
              <Wrench className="mr-2 h-4 w-4" />
              {t('tabs.tools')}
            </TabsTrigger>
            <TabsTrigger value="skills">
              <PackageOpen className="mr-2 h-4 w-4" />
              {t('tabs.skills')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="tools" className="space-y-4">
            <ToolsClient />
          </TabsContent>

          <TabsContent value="skills" className="space-y-4">
            <AdminSkillsPanel />
          </TabsContent>
        </Tabs>
        </div>
      </div>
    </RoutePermissionGuard>
  )
}
