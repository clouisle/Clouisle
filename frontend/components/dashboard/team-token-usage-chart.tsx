'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Building2 } from 'lucide-react'
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_HOVER_CURSOR, CHART_SURFACE_COLORS } from '@/lib/chart-theme'

interface TeamTokenUsage {
  team_id: string
  name: string
  total_tokens: number
  conversations: number
  messages: number
}

interface TeamTokenUsageChartProps {
  data: TeamTokenUsage[]
  isLoading?: boolean
}

const COLORS = CHART_SURFACE_COLORS

export function TeamTokenUsageChart({ data, isLoading }: TeamTokenUsageChartProps) {
  const t = useTranslations('dashboard')

  const formatNumber = (num: number | undefined) => {
    if (num === undefined || num === null) return '0'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  // Filter out teams with no token usage
  const filteredData = data?.filter(team => team.total_tokens > 0) || []

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            {t('models.teamRanking')}
          </CardTitle>
          <CardDescription>{t('models.teamRankingDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.loading')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!filteredData || filteredData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            {t('models.teamRanking')}
          </CardTitle>
          <CardDescription>{t('models.teamRankingDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.noData')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-5 w-5" />
          {t('models.teamRanking')}
        </CardTitle>
        <CardDescription>{t('models.teamRankingDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={filteredData}
            margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
          >
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
            <XAxis
              dataKey="name"
              className="text-xs"
              tick={{ fill: CHART_AXIS_COLOR, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis hide />
            <Tooltip
              cursor={CHART_HOVER_CURSOR}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as TeamTokenUsage
                  return (
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                      <div className="font-semibold mb-2">{data.name}</div>
                      <div className="text-sm space-y-1">
                        <div>
                          {t('common.tokenUsage')}: {formatNumber(data.total_tokens)}
                        </div>
                        <div>
                          {t('common.conversations')}: {data.conversations.toLocaleString()}
                        </div>
                        <div>
                          {t('common.messages')}: {data.messages.toLocaleString()}
                        </div>
                      </div>
                    </div>
                  )
                }
                return null
              }}
            />
            <Bar dataKey="total_tokens" radius={[8, 8, 0, 0]} fillOpacity={0.82}>
              {filteredData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
