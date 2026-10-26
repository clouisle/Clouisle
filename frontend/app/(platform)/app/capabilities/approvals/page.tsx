'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, RefreshCw, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ApprovalsInbox } from './_components/approvals-inbox'
import { InteractionsInbox } from './_components/interactions-inbox'
import { ApprovalPoliciesPanel } from './_components/approval-policies-panel'

type InboxTab = 'approvals' | 'interactions' | 'policies'

export default function ApprovalsPage() {
  const t = useTranslations('approvals')
  const router = useRouter()
  const searchParams = useSearchParams()
  const executionFilter = searchParams.get('execution')
  const requestedTabParam = searchParams.get('tab')
  const requestedTab: InboxTab = requestedTabParam === 'interactions'
    ? 'interactions'
    : requestedTabParam === 'policies'
      ? 'policies'
      : 'approvals'
  const [activeTab, setActiveTab] = React.useState<InboxTab>(requestedTab)
  const [refreshKey, setRefreshKey] = React.useState(0)

  React.useEffect(() => {
    setActiveTab(requestedTab)
  }, [requestedTab])

  const changeTab = (value: string) => {
    const nextTab: InboxTab = value === 'interactions'
      ? 'interactions'
      : value === 'policies'
        ? 'policies'
        : 'approvals'
    setActiveTab(nextTab)
    const params = new URLSearchParams(searchParams.toString())
    if (nextTab === 'approvals') params.delete('tab')
    else params.set('tab', nextTab)
    const query = params.toString()
    router.replace(`/app/capabilities/approvals${query ? `?${query}` : ''}`, { scroll: false })
  }

  const clearExecutionFilter = () => {
    const params = new URLSearchParams(searchParams.toString())
    params.delete('execution')
    const query = params.toString()
    router.replace(`/app/capabilities/approvals${query ? `?${query}` : ''}`, { scroll: false })
    setRefreshKey((current) => current + 1)
  }

  return (
    <div className="h-full overflow-y-auto px-8 py-6">
      <div className="mb-6 space-y-3">
        <Link
          href="/app/capabilities"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {t('backToCapabilities')}
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
              <ShieldCheck className="h-7 w-7" />
              {t('title')}
            </h1>
            <p className="mt-1 max-w-3xl text-muted-foreground">{t('description')}</p>
          </div>
          <Button
            variant="outline"
            onClick={() => setRefreshKey((current) => current + 1)}
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('approval.refresh')}
          </Button>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={changeTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="approvals">{t('tabs.approvals')}</TabsTrigger>
          <TabsTrigger value="interactions">{t('tabs.interactions')}</TabsTrigger>
          <TabsTrigger value="policies">{t('tabs.policies')}</TabsTrigger>
        </TabsList>

        <TabsContent value="approvals">
          <ApprovalsInbox
            executionId={executionFilter}
            refreshKey={refreshKey}
            onClearExecutionFilter={clearExecutionFilter}
          />
        </TabsContent>
        <TabsContent value="interactions">
          <InteractionsInbox refreshKey={refreshKey} />
        </TabsContent>
        <TabsContent value="policies">
          <ApprovalPoliciesPanel refreshKey={refreshKey} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
