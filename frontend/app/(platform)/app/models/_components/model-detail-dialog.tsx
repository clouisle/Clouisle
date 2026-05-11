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
  Calendar,
  CalendarDays,
  Hash,
  Zap,
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
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

interface ModelDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  teamModel: TeamModel | null
}

export function ModelDetailDialog({
  open,
  onOpenChange,
  teamModel,
}: ModelDetailDialogProps) {
  const t = useTranslations('models')
  const teamsT = useTranslations('teams')
  const getProviderName = React.useCallback((code: string) => {
    const key = `providers.${code}`
    return t.has(key) ? t(key) : code
  }, [t])
  const getTypeName = React.useCallback((code: string) => {
    const key = `modelTypes.${code}`
    return t.has(key) ? t(key) : code
  }, [t])

  if (!teamModel) return null

  const { model } = teamModel
  const TypeIcon = modelTypeIcons[model.model_type] || MessageSquare
  const providerColor = providerColors[model.provider] || providerColors.custom

  // 格式化数字
  const formatNumber = (num: number): string => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(2)}K`
    return String(num)
  }

  // 计算百分比
  const calcPercent = (used: number, limit: number | null): number | null => {
    if (limit === null || limit === 0) return null
    return Math.min((used / limit) * 100, 100)
  }

  // 获取进度条颜色
  const getProgressColor = (percent: number | null): string => {
    if (percent === null) return ''
    if (percent >= 90) return '[&>div]:bg-destructive'
    if (percent >= 70) return '[&>div]:bg-amber-500'
    return ''
  }

  const dailyTokenPercent = calcPercent(teamModel.daily_tokens_used, teamModel.daily_token_limit)
  const monthlyTokenPercent = calcPercent(teamModel.monthly_tokens_used, teamModel.monthly_token_limit)
  const dailyRequestPercent = calcPercent(teamModel.daily_requests_used, teamModel.daily_request_limit)
  const monthlyRequestPercent = calcPercent(teamModel.monthly_requests_used, teamModel.monthly_request_limit)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <div className={cn("rounded-lg p-2", providerColor)}>
              <TypeIcon className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="truncate">{model.name}</span>
                {!teamModel.is_enabled && (
                  <Badge variant="secondary" className="text-xs">
                    {t('disabled')}
                  </Badge>
                )}
              </div>
              <p className="text-sm font-normal text-muted-foreground truncate">
                {model.model_id}
              </p>
            </div>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6">
          {/* 基本信息 */}
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">
              {getProviderName(model.provider)}
            </Badge>
            <Badge variant="outline">
              {getTypeName(model.model_type)}
            </Badge>
            {teamModel.priority > 0 && (
              <Badge variant="secondary" className="gap-1">
                <TrendingUp className="h-3 w-3" />
                {teamsT('priority')}: {teamModel.priority}
              </Badge>
            )}
          </div>

          <Separator />

          {/* Token 配额 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium flex items-center gap-2">
              <Zap className="h-4 w-4 text-muted-foreground" />
              {teamsT('tokenQuota')}
            </h4>

            {/* 日 Token 配额 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  {teamsT('dailyTokenLimit')}
                </span>
                <span className="font-medium">
                  {teamModel.daily_token_limit ? (
                    `${formatNumber(teamModel.daily_tokens_used)} / ${formatNumber(teamModel.daily_token_limit)}`
                  ) : (
                    <span className="flex items-center gap-1">
                      {formatNumber(teamModel.daily_tokens_used)}
                      <span className="text-muted-foreground">/</span>
                      <Infinity className="h-4 w-4 text-muted-foreground" />
                    </span>
                  )}
                </span>
              </div>
              {dailyTokenPercent !== null ? (
                <Progress 
                  value={dailyTokenPercent} 
                  className={cn("h-2", getProgressColor(dailyTokenPercent))} 
                />
              ) : teamModel.daily_tokens_used > 0 ? (
                <Progress value={5} className="h-2 [&>div]:bg-emerald-500" />
              ) : (
                <div className="h-2 bg-muted rounded-full" />
              )}
              {dailyTokenPercent !== null && (
                <p className="text-xs text-muted-foreground text-right">
                  {teamsT('percentUsed', { percent: dailyTokenPercent.toFixed(1) })}
                </p>
              )}
            </div>

            {/* 月 Token 配额 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {teamsT('monthlyTokenLimit')}
                </span>
                <span className="font-medium">
                  {teamModel.monthly_token_limit ? (
                    `${formatNumber(teamModel.monthly_tokens_used)} / ${formatNumber(teamModel.monthly_token_limit)}`
                  ) : (
                    <span className="flex items-center gap-1">
                      {formatNumber(teamModel.monthly_tokens_used)}
                      <span className="text-muted-foreground">/</span>
                      <Infinity className="h-4 w-4 text-muted-foreground" />
                    </span>
                  )}
                </span>
              </div>
              {monthlyTokenPercent !== null ? (
                <Progress 
                  value={monthlyTokenPercent} 
                  className={cn("h-2", getProgressColor(monthlyTokenPercent))} 
                />
              ) : teamModel.monthly_tokens_used > 0 ? (
                <Progress value={5} className="h-2 [&>div]:bg-emerald-500" />
              ) : (
                <div className="h-2 bg-muted rounded-full" />
              )}
              {monthlyTokenPercent !== null && (
                <p className="text-xs text-muted-foreground text-right">
                  {teamsT('percentUsed', { percent: monthlyTokenPercent.toFixed(1) })}
                </p>
              )}
            </div>
          </div>

          <Separator />

          {/* 请求配额 */}
          <div className="space-y-4">
            <h4 className="text-sm font-medium flex items-center gap-2">
              <Hash className="h-4 w-4 text-muted-foreground" />
              {teamsT('requestQuota')}
            </h4>

            {/* 日请求配额 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <Calendar className="h-3.5 w-3.5" />
                  {teamsT('dailyRequestLimit')}
                </span>
                <span className="font-medium">
                  {teamModel.daily_request_limit ? (
                    `${formatNumber(teamModel.daily_requests_used)} / ${formatNumber(teamModel.daily_request_limit)}`
                  ) : (
                    <span className="flex items-center gap-1">
                      {formatNumber(teamModel.daily_requests_used)}
                      <span className="text-muted-foreground">/</span>
                      <Infinity className="h-4 w-4 text-muted-foreground" />
                    </span>
                  )}
                </span>
              </div>
              {dailyRequestPercent !== null ? (
                <Progress 
                  value={dailyRequestPercent} 
                  className={cn("h-2", getProgressColor(dailyRequestPercent))} 
                />
              ) : teamModel.daily_requests_used > 0 ? (
                <Progress value={5} className="h-2 [&>div]:bg-emerald-500" />
              ) : (
                <div className="h-2 bg-muted rounded-full" />
              )}
              {dailyRequestPercent !== null && (
                <p className="text-xs text-muted-foreground text-right">
                  {teamsT('percentUsed', { percent: dailyRequestPercent.toFixed(1) })}
                </p>
              )}
            </div>

            {/* 月请求配额 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5" />
                  {teamsT('monthlyRequestLimit')}
                </span>
                <span className="font-medium">
                  {teamModel.monthly_request_limit ? (
                    `${formatNumber(teamModel.monthly_requests_used)} / ${formatNumber(teamModel.monthly_request_limit)}`
                  ) : (
                    <span className="flex items-center gap-1">
                      {formatNumber(teamModel.monthly_requests_used)}
                      <span className="text-muted-foreground">/</span>
                      <Infinity className="h-4 w-4 text-muted-foreground" />
                    </span>
                  )}
                </span>
              </div>
              {monthlyRequestPercent !== null ? (
                <Progress 
                  value={monthlyRequestPercent} 
                  className={cn("h-2", getProgressColor(monthlyRequestPercent))} 
                />
              ) : teamModel.monthly_requests_used > 0 ? (
                <Progress value={5} className="h-2 [&>div]:bg-emerald-500" />
              ) : (
                <div className="h-2 bg-muted rounded-full" />
              )}
              {monthlyRequestPercent !== null && (
                <p className="text-xs text-muted-foreground text-right">
                  {teamsT('percentUsed', { percent: monthlyRequestPercent.toFixed(1) })}
                </p>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
