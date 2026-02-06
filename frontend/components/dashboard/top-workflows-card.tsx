'use client'

import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Workflow } from 'lucide-react'

interface TopWorkflow {
  workflow_id: string
  name: string
  run_count: number
  success_rate: number
}

interface TopWorkflowsCardProps {
  data: TopWorkflow[]
  isLoading?: boolean
}

export function TopWorkflowsCard({ data, isLoading }: TopWorkflowsCardProps) {
  const t = useTranslations('dashboard')

  const formatNumber = (num: number | undefined) => {
    if (num === undefined || num === null) return '0'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  const getSuccessRateBadgeVariant = (rate: number) => {
    if (rate >= 90) return 'default'
    if (rate >= 70) return 'secondary'
    return 'destructive'
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Workflow className="h-5 w-5" />
            {t('analytics.topWorkflows')}
          </CardTitle>
          <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
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
            <Workflow className="h-5 w-5" />
            {t('analytics.topWorkflows')}
          </CardTitle>
          <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
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
          <Workflow className="h-5 w-5" />
          {t('analytics.topWorkflows')}
        </CardTitle>
        <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 max-h-[300px] overflow-y-auto">
          {data.map((workflow, index) => (
            <div
              key={workflow.workflow_id}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary font-semibold text-sm">
                  {index + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{workflow.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {t('common.runCount', { count: formatNumber(workflow.run_count) })}
                  </div>
                </div>
              </div>
              <Badge variant={getSuccessRateBadgeVariant(workflow.success_rate)}>
                {workflow.success_rate.toFixed(1)}%
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
