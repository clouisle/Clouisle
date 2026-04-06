'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { CheckCircle2 } from 'lucide-react'
import { CHART_SURFACE_COLORS } from '@/lib/chart-theme'

interface StatusData {
  status: string
  count: number
  [key: string]: string | number
}

interface WorkflowStatusChartProps {
  data: StatusData[]
  isLoading?: boolean
}

const COLORS = CHART_SURFACE_COLORS

function WorkflowStatusChartComponent({ data, isLoading }: WorkflowStatusChartProps) {
  const t = useTranslations('dashboard')

  const getStatusLabel = (status: string) => {
    const key = `status.${status}` as const
    return t.has(key) ? t(key) : status
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
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5" />
            {t('analytics.workflowStatus')}
          </CardTitle>
          <CardDescription>{t('analytics.workflowStatusDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="h-[240px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.loading')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5" />
            {t('analytics.workflowStatus')}
          </CardTitle>
          <CardDescription>{t('analytics.workflowStatusDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="h-[240px] flex items-center justify-center">
            <div className="text-muted-foreground">{t('common.noData')}</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5" />
          {t('analytics.workflowStatus')}
        </CardTitle>
        <CardDescription>{t('analytics.workflowStatusDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={64}
              outerRadius={84}
              fill="#8884d8"
              dataKey="count"
              nameKey="status"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as StatusData
                  const percentage = totalCount > 0 ? ((data.count / totalCount) * 100).toFixed(2) : '0'
                  return (
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                      <div className="font-semibold mb-2">{getStatusLabel(data.status)}</div>
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

export const WorkflowStatusChart = React.memo(WorkflowStatusChartComponent)
