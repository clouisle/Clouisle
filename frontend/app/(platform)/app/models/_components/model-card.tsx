'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Infinity, TrendingUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { TeamModel } from '@/lib/api'
import { ProviderIcon } from '@/components/model-provider'
import { ModelModalities } from '@/components/model-modalities'
import { getProviderTint } from '@/lib/model-provider'

interface ModelCardProps {
  teamModel: TeamModel
  onClick?: () => void
}

export function ModelCard({ teamModel, onClick }: ModelCardProps) {
  const t = useTranslations('models')
  const teamsT = useTranslations('teams')
  const getProviderName = React.useCallback((code: string) => {
    const key = `providers.${code}`
    return t.has(key) ? t(key) : code
  }, [t])
  const getTypeName = React.useCallback((code: string) => {
    const key = `types.${code}`
    return t.has(key) ? t(key) : code
  }, [t])

  const { model } = teamModel
  const providerColor = getProviderTint(model.provider, model.model_id)
  
  // 计算配额使用百分比
  const dailyTokenPercent = teamModel.daily_token_limit 
    ? Math.min((teamModel.daily_tokens_used / teamModel.daily_token_limit) * 100, 100)
    : null
  const monthlyTokenPercent = teamModel.monthly_token_limit
    ? Math.min((teamModel.monthly_tokens_used / teamModel.monthly_token_limit) * 100, 100)
    : null
  
  // 格式化数字
  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return String(num)
  }
  
  return (
    <Card 
      size="sm"
      className={cn(
        "group relative transition-all hover:shadow-md cursor-pointer py-0! min-h-36",
        !teamModel.is_enabled && "opacity-60"
      )}
      onClick={onClick}
    >
      <CardContent className="flex flex-col justify-between px-3 py-3 h-full">
        {/* 顶部：图标、名称、状态 */}
        <div className="flex items-start gap-2">
          <div className={cn("rounded p-1.5 shrink-0", providerColor)}>
            <ProviderIcon
              provider={model.provider}
              label={model.provider_display_name || getProviderName(model.provider)}
              modelId={model.model_id}
              size={16}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium truncate">{model.name}</span>
              {!teamModel.is_enabled && (
                <Badge variant="secondary" className="text-[10px] px-1 py-0">
                  {t('disabled')}
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground truncate">
              {model.model_id}
            </p>
          </div>
        </div>
        
        {/* 中部：模态、供应商和类型 */}
        <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
          <ModelModalities capabilities={model.capabilities} modelType={model.model_type} />
          <div className="flex flex-wrap items-center justify-end gap-1.5 ml-auto">
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {model.provider_display_name || getProviderName(model.provider)}
            </Badge>
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {getTypeName(model.model_type)}
            </Badge>
            {teamModel.priority > 0 && (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 gap-0.5">
                      <TrendingUp className="h-2.5 w-2.5" />
                      {teamModel.priority}
                    </Badge>
                  }
                />
                <TooltipContent>
                  {teamsT('priorityHint')}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
        
        {/* 底部：配额使用情况 */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground border-t mt-2 pt-2">
          {/* 日配额 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[10px]">{teamsT('dailyQuota')}</span>
              <span className="text-[10px]">
                {teamModel.daily_token_limit ? (
                  `${formatNumber(teamModel.daily_tokens_used)}/${formatNumber(teamModel.daily_token_limit)}`
                ) : (
                  <>
                    {teamModel.daily_tokens_used > 0 && `${formatNumber(teamModel.daily_tokens_used)}/`}
                    <Infinity className="h-3 w-3 inline" />
                  </>
                )}
              </span>
            </div>
            {dailyTokenPercent !== null ? (
              <Progress value={dailyTokenPercent} className="h-1" />
            ) : teamModel.daily_tokens_used > 0 ? (
              <Progress value={5} className="h-1 [&>div]:bg-emerald-500" />
            ) : (
              <div className="h-1 bg-muted rounded-full" />
            )}
          </div>
          
          {/* 月配额 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[10px]">{teamsT('monthlyQuota')}</span>
              <span className="text-[10px]">
                {teamModel.monthly_token_limit ? (
                  `${formatNumber(teamModel.monthly_tokens_used)}/${formatNumber(teamModel.monthly_token_limit)}`
                ) : (
                  <>
                    {teamModel.monthly_tokens_used > 0 && `${formatNumber(teamModel.monthly_tokens_used)}/`}
                    <Infinity className="h-3 w-3 inline" />
                  </>
                )}
              </span>
            </div>
            {monthlyTokenPercent !== null ? (
              <Progress value={monthlyTokenPercent} className="h-1" />
            ) : teamModel.monthly_tokens_used > 0 ? (
              <Progress value={5} className="h-1 [&>div]:bg-emerald-500" />
            ) : (
              <div className="h-1 bg-muted rounded-full" />
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function ModelCardSkeleton() {
  return (
    <Card size="sm" className="py-0! h-36">
      <CardContent className="flex flex-col justify-between px-3 py-3 h-full">
        <div className="flex items-start gap-2">
          <Skeleton className="h-7 w-7 rounded" />
          <div className="flex-1">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-32 mt-1" />
          </div>
        </div>
        <div className="flex gap-1.5 mt-2">
          <Skeleton className="h-4 w-16 rounded" />
          <Skeleton className="h-4 w-12 rounded" />
        </div>
        <div className="flex gap-3 border-t mt-2 pt-2">
          <div className="flex-1">
            <Skeleton className="h-2.5 w-full mb-1" />
            <Skeleton className="h-1 w-full" />
          </div>
          <div className="flex-1">
            <Skeleton className="h-2.5 w-full mb-1" />
            <Skeleton className="h-1 w-full" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
