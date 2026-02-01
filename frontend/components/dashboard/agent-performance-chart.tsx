'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Bot } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

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

const COLORS = [
  'color-mix(in srgb, var(--chart-1) 70%, transparent)',
  'color-mix(in srgb, var(--chart-2) 70%, transparent)',
  'color-mix(in srgb, var(--chart-3) 70%, transparent)',
  'color-mix(in srgb, var(--chart-4) 70%, transparent)',
  'color-mix(in srgb, var(--chart-5) 70%, transparent)',
]

export function AgentPerformanceChart({ data, metric, onMetricChange, isLoading }: AgentPerformanceChartProps) {
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
            <div className="text-muted-foreground">加载中...</div>
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
            <div className="text-muted-foreground">暂无数据</div>
          </div>
        </CardContent>
      </Card>
    )
  }

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
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={data}
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
                  return (
                    <div className="rounded-lg border bg-background p-3 shadow-md">
                      <div className="flex items-center gap-2 mb-2">
                        {data.icon ? (
                          <span className="text-xl">{data.icon}</span>
                        ) : (
                          <Bot className="h-4 w-4" />
                        )}
                        <span className="font-semibold">{data.name}</span>
                      </div>
                      <div className="text-sm text-muted-foreground mb-1">
                        团队: {data.team_name}
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
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
