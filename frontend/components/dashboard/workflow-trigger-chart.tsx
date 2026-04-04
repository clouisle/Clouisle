'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Zap } from 'lucide-react'
import { CHART_SURFACE_COLORS } from '@/lib/chart-theme'

interface TriggerData {
  type: string
  count: number
  [key: string]: string | number
}

interface WorkflowTriggerChartProps {
  data: TriggerData[]
  isLoading?: boolean
}

const COLORS = CHART_SURFACE_COLORS

function WorkflowTriggerChartComponent({ data, isLoading }: WorkflowTriggerChartProps) {
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
              innerRadius={76}
              outerRadius={96}
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
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
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

export const WorkflowTriggerChart = React.memo(WorkflowTriggerChartComponent)
