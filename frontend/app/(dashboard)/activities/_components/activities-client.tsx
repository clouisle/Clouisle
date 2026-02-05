'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Activity, MessageSquare, Workflow } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { conversationsApi, workflowsApi, type ConversationStats, type WorkflowRunStats } from '@/lib/api'
import { ConversationsTable } from './conversations-table'
import { WorkflowRunsTable } from './workflow-runs-table'

export function ActivitiesClient() {
  const t = useTranslations('activities')
  const [activeTab, setActiveTab] = React.useState<'conversations' | 'workflows'>('conversations')
  const [conversationStats, setConversationStats] = React.useState<ConversationStats | null>(null)
  const [workflowStats, setWorkflowStats] = React.useState<WorkflowRunStats | null>(null)
  const [loading, setLoading] = React.useState(true)

  // Load statistics
  React.useEffect(() => {
    const loadStats = async () => {
      try {
        setLoading(true)

        // Load conversation stats with fallback
        const convStats = await conversationsApi.getStats().catch((error) => {
          console.error('Failed to load conversation stats:', error)
          return {
            total_conversations: 0,
            total_messages: 0,
            active_users: 0,
            conversations_by_agent: [],
            conversations_by_team: [],
          }
        })

        // Load workflow stats with fallback
        const wfStats = await workflowsApi.getWorkflowRunStats().catch((error) => {
          console.error('Failed to load workflow stats:', error)
          return {
            total_runs: 0,
            runs_by_status: {},
            runs_by_workflow: [],
            avg_duration_ms: 0,
          }
        })

        setConversationStats(convStats)
        setWorkflowStats(wfStats)
      } catch (error) {
        console.error('Failed to load statistics:', error)
        toast.error('Failed to load some statistics')
      } finally {
        setLoading(false)
      }
    }

    loadStats()
  }, [])

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
        <p className="text-muted-foreground">{t('description')}</p>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t('stats.totalConversations')}</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '...' : conversationStats?.total_conversations.toLocaleString() || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t('stats.totalWorkflowRuns')}</CardTitle>
            <Workflow className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '...' : workflowStats?.total_runs.toLocaleString() || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t('stats.todayActivities')}</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '...' : calculateTodayActivities(conversationStats, workflowStats)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t('stats.activeUsers')}</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? '...' : conversationStats?.active_users || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'conversations' | 'workflows')}>
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

// Helper to calculate today's activities
function calculateTodayActivities(
  conversationStats: ConversationStats | null,
  workflowStats: WorkflowRunStats | null
): number {
  // This is a simplified calculation - in a real app, you'd want to filter by today's date
  // For now, we'll just return 0 as a placeholder
  return 0
}
