'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  MessageSquare,
  Layers,
  ArrowUpDown,
  Volume2,
  Mic,
  Image,
  Video,
  Infinity,
  TrendingUp,
} from 'lucide-react'
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

// 模型类型图标映射
const modelTypeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  chat: MessageSquare,
  embedding: Layers,
  rerank: ArrowUpDown,
  tts: Volume2,
  stt: Mic,
  text_to_image: Image,
  text_to_video: Video,
}

// 供应商颜色映射
const providerColors: Record<string, string> = {
  openai: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  anthropic: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
  google: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  xai: 'bg-neutral-500/10 text-neutral-600 dark:text-neutral-400',
  azure_openai: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  deepseek: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
  moonshot: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  zhipu: 'bg-red-500/10 text-red-600 dark:text-red-400',
  qwen: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
  baichuan: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  minimax: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
  ollama: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
  custom: 'bg-slate-500/10 text-slate-600 dark:text-slate-400',
}

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
  const TypeIcon = modelTypeIcons[model.model_type] || MessageSquare
  const providerColor = providerColors[model.provider] || providerColors.custom
  
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
        "group relative transition-all hover:shadow-md cursor-pointer py-0! h-36",
        !teamModel.is_enabled && "opacity-60"
      )}
      onClick={onClick}
    >
      <CardContent className="flex flex-col justify-between px-3 py-3 h-full">
        {/* 顶部：图标、名称、状态 */}
        <div className="flex items-start gap-2">
          <div className={cn("rounded p-1.5 shrink-0", providerColor)}>
            <TypeIcon className="h-4 w-4" />
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
        
        {/* 中部：供应商和类型标签 */}
        <div className="flex items-center gap-1.5 mt-2">
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {getProviderName(model.provider)}
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
