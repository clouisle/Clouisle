'use client'

import * as React from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Activity, MessageSquare, Users, Workflow } from 'lucide-react'
import { StatCard } from '@/components/dashboard/stat-card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { conversationsApi, type ConversationStats } from '@/lib/api/admin/conversations'
import { workflowsApi } from '@/lib/api'
import { type WorkflowRunStats } from '@/lib/api/workflows'
import { ConversationsTable } from './conversations-table'
import { WorkflowRunsTable } from './workflow-runs-table'

export function ActivitiesClient() {
  const t = useTranslations('activities')
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = React.useState<'conversations' | 'workflows'>(() => {
    const tab = searchParams.get('tab')
    return tab === 'workflows' ? 'workflows' : 'conversations'
  })
  const [loading, setLoading] = React.useState(true)
  const [conversationStats, setConversationStats] = React.useState<ConversationStats | null>(null)
  const [workflowStats, setWorkflowStats] = React.useState<WorkflowRunStats | null>(null)

  const handleTabChange = (tab: string) => {
    const next = tab as 'conversations' | 'workflows'
    setActiveTab(next)
    const nextParams = new URLSearchParams(searchParams.toString())
    if (next === 'conversations') {
      nextParams.delete('tab')
    } else {
      nextParams.set('tab', 'workflows')
    }
    const query = nextParams.toString()
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
  }

  // Load statistics
  React.useEffect(() => {
    const loadStats = async () => {
      try {
        setLoading(true)

        // Load conversation stats with fallback
        const convStats = await conversationsApi.getStats().catch((error) => {
          console.error('Failed to load conversation stats:', error)
          return null
        })

        // Load workflow stats with fallback
        const wfStats = await workflowsApi.getWorkflowRunStats().catch((error) => {
          console.error('Failed to load workflow stats:', error)
          return null
        })

        setConversationStats(convStats)
        setWorkflowStats(wfStats)
      } catch (error) {
        console.error('Failed to load statistics:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
     
  }, [])

  // Keep the active tab in sync with the URL (back/forward navigation)
  React.useEffect(() => {
    const tab = searchParams.get('tab')
    setActiveTab(tab === 'workflows' ? 'workflows' : 'conversations')
  }, [searchParams])

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
        <p className="text-muted-foreground">{t('description')}</p>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title={t('stats.totalConversations')}
          value={conversationStats?.total_conversations ?? 0}
          icon={MessageSquare}
          tone="blue"
          isLoading={loading}
        />
        <StatCard
          title={t('stats.totalWorkflowRuns')}
          value={workflowStats?.total_runs ?? 0}
          icon={Workflow}
          tone="purple"
          isLoading={loading}
        />
        <StatCard
          title={t('stats.todayActivities')}
          value={0}
          icon={Activity}
          tone="green"
          isLoading={loading}
        />
        <StatCard
          title={t('stats.activeUsers')}
          value={conversationStats?.active_users ?? 0}
          icon={Users}
          tone="orange"
          isLoading={loading}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="conversations">
            <MessageSquare className="mr-2 h-4 w-4" />
            {t('conversations')}
          </TabsTrigger>
          <TabsTrigger value="workflows">
            <Workflow className="mr-2 h-4 w-4" />
            {t('workflowRuns')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="conversations" className="mt-6">
          <ConversationsTable />
        </TabsContent>

        <TabsContent value="workflows" className="mt-6">
          <WorkflowRunsTable />
        </TabsContent>
      </Tabs>
    </div>
  )
}
