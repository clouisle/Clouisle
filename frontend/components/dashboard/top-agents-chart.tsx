'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Bot } from 'lucide-react'

interface TopAgent {
  agent_id: string
  name: string
  icon: string | null
  value: number
  team_name: string
}

interface TopAgentsChartProps {
  data: TopAgent[]
  metric: 'conversation_count' | 'message_count' | 'total_tokens'
  isLoading?: boolean
}

const COLORS = [
  'color-mix(in srgb, var(--chart-1) 70%, transparent)',
  'color-mix(in srgb, var(--chart-2) 70%, transparent)',
  'color-mix(in srgb, var(--chart-3) 70%, transparent)',
  'color-mix(in srgb, var(--chart-4) 70%, transparent)',
  'color-mix(in srgb, var(--chart-5) 70%, transparent)',
]

export function TopAgentsChart({ data, metric, isLoading }: TopAgentsChartProps) {
  const t = useTranslations('dashboard')

  const formatValue = (value: number) => {
    if (metric === 'total_tokens') {
      if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`
      if (value >= 1000) return `${(value / 1000).toFixed(1)}K`
    }
    return value.toLocaleString()
  }

  const getMetricLabel = () => {
    switch (metric) {
      case 'conversation_count':
        return t('metrics.conversationCount')
      case 'message_count':
        return t('metrics.messageCount')
      case 'total_tokens':
        return t('metrics.tokenUsage')
      default:
        return ''
    }
  }

  // Filter out agents with no value
  const filteredData = data?.filter(agent => agent.value > 0) || []

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            {t('charts.topAgents')}
          </CardTitle>
          <CardDescription>{t('charts.topAgentsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] flex items-center justify-center">
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
            <Bot className="h-5 w-5" />
            {t('charts.topAgents')}
          </CardTitle>
          <CardDescription>{t('charts.topAgentsDesc')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.noData')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="h-5 w-5" />
          {t('charts.topAgents')}
        </CardTitle>
        <CardDescription>{t('charts.topAgentsDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart
            data={filteredData}
            margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey="name"
              className="text-xs"
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis hide />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as TopAgent
                  const isIconUrl = data.icon?.startsWith('http://') || data.icon?.startsWith('https://')
                  return (
                    <div className="rounded-lg border bg-background p-3 shadow-md">
                      <div className="flex items-center gap-2 mb-2">
                        {data.icon ? (
                          isIconUrl ? (
                            <img src={data.icon} alt="" className="h-5 w-5 rounded object-cover" />
                          ) : (
                            <span className="text-xl">{data.icon}</span>
                          )
                        ) : (
                          <Bot className="h-4 w-4" />
                        )}
                        <span className="font-semibold">{data.name}</span>
                      </div>
                      <div className="text-sm text-muted-foreground mb-1">
                        {t('common.team')}: {data.team_name}
                      </div>
                      <div className="text-sm font-medium">
                        {getMetricLabel()}: {formatValue(data.value)}
                      </div>
                    </div>
                  )
                }
                return null
              }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
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
