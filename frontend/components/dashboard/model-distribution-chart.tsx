'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Cpu } from 'lucide-react'
import type { ModelDistribution } from '@/lib/api/admin/dashboard'
import { CHART_SURFACE_COLORS } from '@/lib/chart-theme'

interface ModelDistributionChartProps {
  data: ModelDistribution[]
  isLoading?: boolean
}

const COLORS = CHART_SURFACE_COLORS

export function ModelDistributionChart({ data, isLoading }: ModelDistributionChartProps) {
  const t = useTranslations('dashboard')

  const formatNumber = (num: number | undefined) => {
    if (num === undefined || num === null) return '0'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            {t('charts.modelDistribution')}
          </CardTitle>
          <CardDescription>{t('charts.modelDistributionDesc')}</CardDescription>
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
            <Cpu className="h-5 w-5" />
            {t('charts.modelDistribution')}
          </CardTitle>
          <CardDescription>{t('charts.modelDistributionDesc')}</CardDescription>
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
    <Card className="flex h-full flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="h-5 w-5" />
          {t('charts.modelDistribution')}
        </CardTitle>
        <CardDescription>{t('charts.modelDistributionDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <div className="min-h-[300px] flex-1">
          <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data as Array<ModelDistribution & Record<string, unknown>>}
              cx="50%"
              cy="50%"
              innerRadius={76}
              outerRadius={96}
              fill="#8884d8"
              dataKey="count"
              nameKey="model"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const data = payload[0].payload as ModelDistribution
                  return (
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                      <div className="font-semibold mb-2">{data.model || t('common.unknown')}</div>
                      <div className="text-sm space-y-1">
                        <div>
                          {t('common.usageCount')}: {formatNumber(data.count)}
                        </div>
                        <div className="font-medium">
                          {t('common.percentage')}: {data.percentage.toFixed(2)}%
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
        </div>
      </CardContent>
    </Card>
  )
}
