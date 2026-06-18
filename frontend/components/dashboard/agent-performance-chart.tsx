'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Bot } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_HOVER_CURSOR, CHART_SURFACE_COLORS } from '@/lib/chart-theme'

interface TopAgent {
  agent_id: string
  name: string
  icon: string | null
  value: number
  team_name: string
}

interface AgentPerformanceChartProps {
  data: TopAgent[]
  metric: 'conversation_count' | 'message_count' | 'total_tokens'
  onMetricChange: (metric: 'conversation_count' | 'message_count' | 'total_tokens') => void
  isLoading?: boolean
}

const COLORS = CHART_SURFACE_COLORS

function isIconUrl(icon: string | null): icon is string {
  return Boolean(icon && (icon.startsWith('http') || icon.startsWith('/')))
}

function AgentPerformanceChartComponent({ data, metric, onMetricChange, isLoading }: AgentPerformanceChartProps) {
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

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5" />
                {t('analytics.agentPerformance')}
              </CardTitle>
              <CardDescription>{t('analytics.agentPerformanceDesc')}</CardDescription>
            </div>
            <Select value={metric} onValueChange={(value) => value && onMetricChange(value as 'conversation_count' | 'message_count' | 'total_tokens')}>
              <SelectTrigger className="w-[180px]">
                <span className="flex-1 text-left">{getMetricLabel()}</span>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                <SelectItem value="conversation_count">{t('metrics.conversationCount')}</SelectItem>
                <SelectItem value="message_count">{t('metrics.messageCount')}</SelectItem>
                <SelectItem value="total_tokens">{t('metrics.tokenUsage')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.loading')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5" />
                {t('analytics.agentPerformance')}
              </CardTitle>
              <CardDescription>{t('analytics.agentPerformanceDesc')}</CardDescription>
            </div>
            <Select value={metric} onValueChange={(value) => value && onMetricChange(value as 'conversation_count' | 'message_count' | 'total_tokens')}>
              <SelectTrigger className="w-[180px]">
                <span className="flex-1 text-left">{getMetricLabel()}</span>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                <SelectItem value="conversation_count">{t('metrics.conversationCount')}</SelectItem>
                <SelectItem value="message_count">{t('metrics.messageCount')}</SelectItem>
                <SelectItem value="total_tokens">{t('metrics.tokenUsage')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
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
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              {t('analytics.agentPerformance')}
            </CardTitle>
            <CardDescription>{t('analytics.agentPerformanceDesc')}</CardDescription>
          </div>
          <Select value={metric} onValueChange={(value) => value && onMetricChange(value as 'conversation_count' | 'message_count' | 'total_tokens')}>
            <SelectTrigger className="w-[180px]">
              <span className="flex-1 text-left">{getMetricLabel()}</span>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false}>
              <SelectItem value="conversation_count">{t('metrics.conversationCount')}</SelectItem>
              <SelectItem value="message_count">{t('metrics.messageCount')}</SelectItem>
              <SelectItem value="total_tokens">{t('metrics.tokenUsage')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <div className="min-h-[300px] flex-1">
          <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
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
                  const data = payload[0].payload as TopAgent
                  return (
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                      <div className="flex items-center gap-2 mb-2">
                        {data.icon ? (
                          isIconUrl(data.icon) ? (
                            <img src={data.icon} alt="" className="h-5 w-5 rounded object-cover" />
                          ) : (
                            <span className="text-xl">{data.icon}</span>
                          )
                        ) : (
                          <Bot className="h-4 w-4" />
                        )}
                        <span className="font-semibold">{data.name}</span>
                      </div>
                      <div className="mb-1 text-sm text-chart-tooltip-text/80">
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
            <Bar dataKey="value" radius={[8, 8, 0, 0]} fillOpacity={0.82}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

export const AgentPerformanceChart = React.memo(AgentPerformanceChartComponent)
