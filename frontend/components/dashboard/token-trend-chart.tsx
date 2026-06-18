'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp } from 'lucide-react'
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_HOVER_CURSOR, CHART_COLOR_ORDER } from '@/lib/chart-theme'

interface TrendData {
  date: string
  tokens: number
}

interface TokenTrendChartProps {
  data: TrendData[]
  isLoading?: boolean
}

const COLORS = CHART_COLOR_ORDER

export function TokenTrendChart({ data, isLoading }: TokenTrendChartProps) {
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
            <TrendingUp className="h-5 w-5" />
            {t('models.tokenTrend')}
          </CardTitle>
          <CardDescription>{t('models.tokenTrendDesc')}</CardDescription>
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
            <TrendingUp className="h-5 w-5" />
            {t('models.tokenTrend')}
          </CardTitle>
          <CardDescription>{t('models.tokenTrendDesc')}</CardDescription>
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
          <TrendingUp className="h-5 w-5" />
          {t('models.tokenTrend')}
        </CardTitle>
        <CardDescription>{t('models.tokenTrendDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <div className="min-h-[300px] flex-1">
          <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorTokens" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={COLORS[3]} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={COLORS[3]} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid stroke={CHART_GRID_COLOR} strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              className="text-xs"
              tick={{ fill: CHART_AXIS_COLOR }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              className="text-xs"
              tick={{ fill: CHART_AXIS_COLOR }}
              hide
            />
            <Tooltip
              cursor={CHART_HOVER_CURSOR}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="rounded-lg border border-chart-tooltip-border bg-chart-tooltip-bg p-3 text-chart-tooltip-text shadow-md">
                      <div className="font-semibold mb-2">{payload[0].payload.date}</div>
                      <div className="text-sm">
                        {t('common.tokenUsage')}: {formatNumber(payload[0].value as number)}
                      </div>
                    </div>
                  )
                }
                return null
              }}
            />
            <Area
              type="monotone"
              dataKey="tokens"
              stroke={COLORS[3]}
              fillOpacity={1}
              fill="url(#colorTokens)"
            />
          </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
