'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Zap } from 'lucide-react'

interface TriggerData {
  type: string
  count: number
  [key: string]: string | number
}

interface WorkflowTriggerChartProps {
  data: TriggerData[]
  isLoading?: boolean
}

const COLORS = [
  'color-mix(in srgb, var(--chart-1) 70%, transparent)',
  'color-mix(in srgb, var(--chart-2) 70%, transparent)',
  'color-mix(in srgb, var(--chart-3) 70%, transparent)',
  'color-mix(in srgb, var(--chart-4) 70%, transparent)',
  'color-mix(in srgb, var(--chart-5) 70%, transparent)',
]

export function WorkflowTriggerChart({ data, isLoading }: WorkflowTriggerChartProps) {
  const t = useTranslations('dashboard')

  const getTriggerLabel = (type: string) => {
    const key = `triggers.${type}` as const
    return t.has(key) ? t(key) : type
  }

  const formatNumber = (num: number | undefined) => {
    if (num === undefined || num === null) return '0'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  const totalCount = data.reduce((sum, item) => sum + item.count, 0)

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            {t('analytics.workflowTriggers')}
          </CardTitle>
          <CardDescription>{t('analytics.workflowTriggersDesc')}</CardDescription>
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
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            {t('analytics.workflowTriggers')}
          </CardTitle>
          <CardDescription>{t('analytics.workflowTriggersDesc')}</CardDescription>
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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          {t('analytics.workflowTriggers')}
        </CardTitle>
        <CardDescription>{t('analytics.workflowTriggersDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              outerRadius={100}
              fill="#8884d8"
              dataKey="count"
              nameKey="type"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as TriggerData
                  const percentage = totalCount > 0 ? ((data.count / totalCount) * 100).toFixed(2) : '0'
                  return (
                    <div className="rounded-lg border bg-background p-3 shadow-md">
                      <div className="font-semibold mb-2">{getTriggerLabel(data.type)}</div>
                      <div className="text-sm space-y-1">
                        <div>
                          {t('common.count')}: {formatNumber(data.count)}
                        </div>
                        <div className="font-medium">
                          {t('common.percentage')}: {percentage}%
                        </div>
                      </div>
                    </div>
                  )
                }
                return null
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
