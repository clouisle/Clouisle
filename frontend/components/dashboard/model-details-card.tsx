'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Cpu } from 'lucide-react'

interface ModelDistribution {
  model: string
  count: number
  percentage: number
}

interface ModelDetailsCardProps {
  data: ModelDistribution[]
  isLoading?: boolean
}

export function ModelDetailsCard({ data, isLoading }: ModelDetailsCardProps) {
  const t = useTranslations('dashboard')

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5" />
            {t('models.modelDetails')}
          </CardTitle>
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
            {t('models.modelDetails')}
          </CardTitle>
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
          <Cpu className="h-5 w-5" />
          {t('models.modelDetails')}
        </CardTitle>
      </CardHeader>
      <CardContent className="py-0">
        <div className="max-h-[300px] space-y-3 overflow-y-auto">
          {data.map((model, index) => (
            <div
              key={index}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <div className="flex-1 min-w-0">
                <Tooltip>
                  <TooltipTrigger className="block w-full text-left">
                    <span className="block w-full font-medium truncate">{model.model || t('common.unknown')}</span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>{model.model || t('common.unknown')}</p>
                  </TooltipContent>
                </Tooltip>
                <div className="text-xs text-muted-foreground">{t('common.usageCount')}: {model.count.toLocaleString()}</div>
              </div>
              <div className="text-right ml-4">
                <div className="text-sm font-semibold">{model.percentage.toFixed(1)}%</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
