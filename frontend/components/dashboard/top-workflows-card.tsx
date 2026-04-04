'use client'

import * as React from 'react'
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

function TopWorkflowsCardComponent({ data, isLoading }: TopWorkflowsCardProps) {
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
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Workflow className="h-5 w-5" />
            {t('analytics.topWorkflows')}
          </CardTitle>
          <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
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
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Workflow className="h-5 w-5" />
            {t('analytics.topWorkflows')}
          </CardTitle>
          <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="h-[300px] flex items-center justify-center">
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
          <Workflow className="h-5 w-5" />
          {t('analytics.topWorkflows')}
        </CardTitle>
        <CardDescription>{t('analytics.topWorkflowsDesc')}</CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="max-h-[240px] space-y-2 overflow-y-auto">
          {data.map((workflow, index) => (
            <div
              key={workflow.workflow_id}
              className="flex cursor-pointer items-center justify-between rounded-lg border p-2.5 transition-colors hover:bg-muted/50"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{workflow.name}</div>
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

export const TopWorkflowsCard = React.memo(TopWorkflowsCardComponent)
