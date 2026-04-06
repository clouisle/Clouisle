'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Workflow, TrendingUp, Clock, Bot } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { WorkflowStatusChart } from '@/components/dashboard/workflow-status-chart'
import { WorkflowTriggerChart } from '@/components/dashboard/workflow-trigger-chart'
import { TopWorkflowsCard } from '@/components/dashboard/top-workflows-card'
import { AgentPerformanceChart } from '@/components/dashboard/agent-performance-chart'
import type { DashboardStats, WorkflowSummary, TopAgent } from '@/lib/api/admin/dashboard'

interface AnalyticsTabProps {
  stats: DashboardStats
  workflowData: WorkflowSummary | null
  topAgentsData: TopAgent[]
  isLoading: boolean
  isLoadingAgents: boolean
  onMetricChange: (metric: 'conversation_count' | 'message_count' | 'total_tokens') => void
  currentMetric: 'conversation_count' | 'message_count' | 'total_tokens'
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading,
  color = 'primary',
}: {
  title: string
  value: number | string
  icon: React.ElementType
  isLoading: boolean
  color?: string
}) {
  const colorClasses = {
    primary: 'bg-primary/10 text-primary',
    blue: 'bg-blue-500/10 text-blue-500',
    purple: 'bg-purple-500/10 text-purple-500',
    green: 'bg-green-500/10 text-green-500',
    orange: 'bg-orange-500/10 text-orange-500',
    cyan: 'bg-cyan-500/10 text-cyan-500',
  }

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="py-0">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <div className="h-9 w-32 bg-muted animate-pulse rounded" />
            ) : (
              <p className="text-3xl font-bold tracking-tight">
                {typeof value === 'number' ? formatNumber(value) : value}
              </p>
            )}
          </div>
          <div className={`h-12 w-12 rounded-xl flex items-center justify-center ${colorClasses[color as keyof typeof colorClasses] || colorClasses.primary}`}>
            <Icon className="h-6 w-6" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AnalyticsTabComponent({ stats, workflowData, topAgentsData, isLoading, isLoadingAgents, onMetricChange, currentMetric }: AnalyticsTabProps) {
  const t = useTranslations('dashboard')

  const topAgent = topAgentsData.length > 0 ? topAgentsData[0].name : 'N/A'

  return (
    <div className="space-y-6">
      {/* Top Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title={t('analytics.workflowRuns')}
          value={workflowData?.total_runs || 0}
          icon={Workflow}
          isLoading={isLoading}
          color="cyan"
        />
        <StatCard
          title={t('analytics.successRate')}
          value={workflowData ? `${workflowData.success_rate.toFixed(1)}%` : '0%'}
          icon={TrendingUp}
          isLoading={isLoading}
          color="green"
        />
        <StatCard
          title={t('analytics.avgDuration')}
          value={workflowData ? formatDuration(workflowData.avg_duration_ms) : '0ms'}
          icon={Clock}
          isLoading={isLoading}
          color="orange"
        />
        <StatCard
          title={t('analytics.topAgent')}
          value={topAgent}
          icon={Bot}
          isLoading={isLoading}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          {/* Agent Performance Comparison */}
          <AgentPerformanceChart
            data={topAgentsData}
            metric={currentMetric}
            onMetricChange={onMetricChange}
            isLoading={isLoading || isLoadingAgents}
          />
        </div>

        <div className="lg:col-span-4">
          {/* Workflow Status Distribution */}
          <WorkflowStatusChart
            data={workflowData?.status_distribution || []}
            isLoading={isLoading}
          />
        </div>

        <div className="lg:col-span-8">
          {/* Workflow Trigger Distribution */}
          <WorkflowTriggerChart
            data={workflowData?.trigger_type_distribution || []}
            isLoading={isLoading}
          />
        </div>

        <div className="lg:col-span-4">
          <div className="space-y-4">
            {/* Top Workflows */}
            <TopWorkflowsCard
              data={workflowData?.top_workflows || []}
              isLoading={isLoading}
            />

            {/* System Stats */}
            <Card>
              <CardContent className="py-0">
                <div className="space-y-3">
                  <div>
                    <h3 className="mb-2 text-sm font-medium">{t('home.systemStats')}</h3>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{t('home.stats.totalMessages')}</span>
                    <span className="text-base font-semibold">{formatNumber(stats.overview.total_messages)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{t('home.stats.avgMessagesPerConv')}</span>
                    <span className="text-base font-semibold">
                      {stats.overview.total_conversations > 0
                        ? (stats.overview.total_messages / stats.overview.total_conversations).toFixed(1)
                        : '0'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">{t('home.stats.avgTokensPerMessage')}</span>
                    <span className="text-base font-semibold">
                      {stats.overview.total_messages > 0
                        ? formatNumber(Math.round(stats.overview.total_tokens / stats.overview.total_messages))
                        : '0'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}

export const AnalyticsTab = React.memo(AnalyticsTabComponent)
