'use client'

import { useTranslations } from 'next-intl'
import { Coins, MessageSquare, Cpu } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ModelDistributionChart } from '@/components/dashboard/model-distribution-chart'
import { TeamTokenUsageChart } from '@/components/dashboard/team-token-usage-chart'
import { TokenTrendChart } from '@/components/dashboard/token-trend-chart'
import { ModelDetailsCard } from '@/components/dashboard/model-details-card'
import { TopAgentsChart } from '@/components/dashboard/top-agents-chart'
import type { DashboardStats, ModelDistribution, TeamTokenUsage, TopAgent } from '@/lib/api'

interface ModelsTabProps {
  stats: DashboardStats
  modelData: ModelDistribution[]
  teamTokenData: TeamTokenUsage[]
  topAgentsData: TopAgent[]
  trendsData: Array<{
    date: string
    tokens: number
  }>
  isLoading: boolean
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
      <CardContent className="pt-6">
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

export function ModelsTab({ stats, modelData, teamTokenData, topAgentsData, trendsData, isLoading }: ModelsTabProps) {
  const t = useTranslations('dashboard')

  const avgTokensPerMessage = stats.overview.total_messages > 0
    ? Math.round(stats.overview.total_tokens / stats.overview.total_messages)
    : 0

  const mostUsedModel = modelData.length > 0 ? modelData[0].model : 'N/A'

  // Model data is already in the correct format for pie chart
  const modelChartData = modelData

  return (
    <div className="space-y-6">
      {/* Top Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          title={t('models.totalTokens')}
          value={stats.overview.total_tokens}
          icon={Coins}
          isLoading={isLoading}
          color="orange"
        />
        <StatCard
          title={t('models.avgTokensPerMessage')}
          value={avgTokensPerMessage}
          icon={MessageSquare}
          isLoading={isLoading}
          color="blue"
        />
        <StatCard
          title={t('models.totalMessages')}
          value={stats.overview.total_messages}
          icon={MessageSquare}
          isLoading={isLoading}
          color="green"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content - 2/3 width */}
        <div className="lg:col-span-2 space-y-6">
          {/* Model Distribution */}
          <ModelDistributionChart data={modelChartData} isLoading={isLoading} />

          {/* Team Token Usage Ranking */}
          <TeamTokenUsageChart data={teamTokenData} isLoading={isLoading} />

          {/* Token Usage Trend */}
          <TokenTrendChart data={trendsData} isLoading={isLoading} />
        </div>

        {/* Sidebar - 1/3 width */}
        <div className="space-y-6">
          {/* Model Details */}
          <ModelDetailsCard data={modelData} isLoading={isLoading} />

          {/* Top Agents by Tokens */}
          <TopAgentsChart
            data={topAgentsData}
            metric="total_tokens"
            isLoading={isLoading}
          />
        </div>
      </div>
    </div>
  )
}
