'use client'

import * as React from 'react'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { X, Copy, Check, RefreshCw, Loader2, ChevronDown, History, RotateCcw, GitBranch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ImageUpload } from '@/components/ui/image-upload'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { workflowsApi, type Workflow, type TriggerType, type WorkflowVersionListItem, type WorkflowVisibility } from '@/lib/api/workflows'

interface WorkflowSettingsDrawerProps {
  workflow: Workflow | null
  open: boolean
  onClose: () => void
  onUpdate: (workflow: Workflow) => void
  readOnly?: boolean
}

export function WorkflowSettingsDrawer({ workflow, open, onClose, onUpdate, readOnly = false }: WorkflowSettingsDrawerProps) {
  const t = useTranslations('workflow')
  // 基本信息
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [icon, setIcon] = React.useState('')
  const [visibility, setVisibility] = React.useState<WorkflowVisibility>('private')
  
  // 触发器配置
  const [triggerType, setTriggerType] = React.useState<TriggerType>('manual')
  const [webhookToken, setWebhookToken] = React.useState('')
  const [cronExpression, setCronExpression] = React.useState('')
  
  // 定时任务配置
  const [scheduleType, setScheduleType] = React.useState<'interval' | 'daily' | 'weekly' | 'monthly' | 'custom'>('daily')
  const [intervalMinutes, setIntervalMinutes] = React.useState(60) // 间隔分钟数
  const [dailyTime, setDailyTime] = React.useState('09:00')
  const [weeklyDay, setWeeklyDay] = React.useState(1) // 1=周一
  const [weeklyTime, setWeeklyTime] = React.useState('09:00')
  const [monthlyDay, setMonthlyDay] = React.useState(1) // 每月第几天
  const [monthlyTime, setMonthlyTime] = React.useState('09:00')
  
  // UI 状态
  const [isSaving, setIsSaving] = React.useState(false)
  const [isRegenerating, setIsRegenerating] = React.useState(false)
  const [copied, setCopied] = React.useState(false)
  const [basicInfoOpen, setBasicInfoOpen] = React.useState(true)
  const [triggerOpen, setTriggerOpen] = React.useState(true)
  const [versionHistoryOpen, setVersionHistoryOpen] = React.useState(false)
  
  // 版本历史
  const [versions, setVersions] = React.useState<WorkflowVersionListItem[]>([])
  const [loadingVersions, setLoadingVersions] = React.useState(false)
  const [restoreDialogOpen, setRestoreDialogOpen] = React.useState(false)
  const [selectedVersion, setSelectedVersion] = React.useState<WorkflowVersionListItem | null>(null)
  const [isRestoring, setIsRestoring] = React.useState(false)
  
  // 记录是否有变更
  const [hasChanges, setHasChanges] = React.useState(false)

  // 从 Cron 表达式解析配置
  const parseCronToConfig = React.useCallback((cron: string) => {
    if (!cron) return
    
    const parts = cron.split(' ')
    if (parts.length !== 5) return
    
    const [minute, hour, day, , weekday] = parts
    
    // 检测间隔类型：*/N * * * * 或 0 */N * * *
    if (minute.startsWith('*/')) {
      setScheduleType('interval')
      setIntervalMinutes(parseInt(minute.slice(2)) || 60)
      return
    }
    if (hour.startsWith('*/')) {
      setScheduleType('interval')
      setIntervalMinutes((parseInt(hour.slice(2)) || 1) * 60)
      return
    }
    
    // 每月: 0 9 1 * *
    if (day !== '*' && weekday === '*') {
      setScheduleType('monthly')
      setMonthlyDay(parseInt(day) || 1)
      setMonthlyTime(`${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`)
      return
    }
    
    // 每周: 0 9 * * 1
    if (weekday !== '*') {
      setScheduleType('weekly')
      setWeeklyDay(parseInt(weekday) || 1)
      setWeeklyTime(`${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`)
      return
    }
    
    // 每天: 0 9 * * *
    if (day === '*' && weekday === '*' && !hour.includes('/') && !minute.includes('/')) {
      setScheduleType('daily')
      setDailyTime(`${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`)
      return
    }
    
    // 其他情况视为自定义
    setScheduleType('custom')
  }, [])

  // 根据配置生成 Cron 表达式
  const generateCronFromConfig = React.useCallback(() => {
    switch (scheduleType) {
      case 'interval': {
        if (intervalMinutes < 60) {
          return `*/${intervalMinutes} * * * *`
        }
        const hours = Math.floor(intervalMinutes / 60)
        return `0 */${hours} * * *`
      }
      case 'daily': {
        const [hour, minute] = dailyTime.split(':')
        return `${parseInt(minute)} ${parseInt(hour)} * * *`
      }
      case 'weekly': {
        const [hour, minute] = weeklyTime.split(':')
        return `${parseInt(minute)} ${parseInt(hour)} * * ${weeklyDay}`
      }
      case 'monthly': {
        const [hour, minute] = monthlyTime.split(':')
        return `${parseInt(minute)} ${parseInt(hour)} ${monthlyDay} * *`
      }
      case 'custom':
        return cronExpression
      default:
        return '0 0 * * *'
    }
  }, [scheduleType, intervalMinutes, dailyTime, weeklyDay, weeklyTime, monthlyDay, monthlyTime, cronExpression])

  // 初始化数据
  React.useEffect(() => {
    if (workflow) {
      setName(workflow.name)
      setDescription(workflow.description || '')
      setIcon(workflow.icon || '')
      setVisibility(workflow.visibility || 'private')
      setTriggerType(workflow.trigger_type)
      setWebhookToken(workflow.webhook_token || '')
      const savedCron = (workflow.trigger_config?.cron_expression as string) || ''
      setCronExpression(savedCron)
      parseCronToConfig(savedCron)
      setHasChanges(false)
    }
  }, [workflow, parseCronToConfig])

  // 检测变更
  React.useEffect(() => {
    if (!workflow) return
    
    const currentCron = scheduleType === 'custom' ? cronExpression : generateCronFromConfig()
    const savedCron = (workflow.trigger_config?.cron_expression as string) || ''
    
    const changed =
      name !== workflow.name ||
      description !== (workflow.description || '') ||
      icon !== (workflow.icon || '') ||
      visibility !== (workflow.visibility || 'private') ||
      triggerType !== workflow.trigger_type ||
      (triggerType === 'cron' && currentCron !== savedCron)

    setHasChanges(changed)
  }, [workflow, name, description, icon, visibility, triggerType, scheduleType, intervalMinutes, dailyTime, weeklyDay, weeklyTime, monthlyDay, monthlyTime, cronExpression, generateCronFromConfig])

  // 加载版本历史
  const loadVersions = React.useCallback(async () => {
    if (!workflow) return
    
    try {
      setLoadingVersions(true)
      const result = await workflowsApi.getWorkflowVersions(workflow.id, { pageSize: 50 })
      setVersions(result.items)
    } catch {
      // toast handled by API interceptor
    } finally {
      setLoadingVersions(false)
    }
  }, [workflow])

  // 当展开版本历史时加载
  React.useEffect(() => {
    if (versionHistoryOpen && workflow) {
      loadVersions()
    }
  }, [versionHistoryOpen, workflow, loadVersions])

  // 恢复版本
  const handleRestoreVersion = async () => {
    if (!workflow || !selectedVersion) return
    
    try {
      setIsRestoring(true)
      const updated = await workflowsApi.restoreWorkflowVersion(
        workflow.id,
        selectedVersion.version
      )
      onUpdate(updated)
      setRestoreDialogOpen(false)
      setSelectedVersion(null)
      toast.success(t('settings.restoredToVersion', { version: selectedVersion.version }))
      // 重新加载版本历史
      loadVersions()
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsRestoring(false)
    }
  }

  // 格式化时间
  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    
    // 小于 1 小时
    if (diff < 3600000) {
      const mins = Math.floor(diff / 60000)
      return mins <= 0 ? t('settings.justNow') : t('settings.minutesAgo', { n: mins })
    }
    // 小于 24 小时
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return t('settings.hoursAgo', { n: hours })
    }
    // 小于 7 天
    if (diff < 604800000) {
      const days = Math.floor(diff / 86400000)
      return t('settings.daysAgo', { n: days })
    }
    // 更久
    return date.toLocaleDateString('en', {
      month: 'short',
      day: 'numeric',
    })
  }

  // 保存设置
  const handleSave = async () => {
    if (!workflow) return
    
    try {
      setIsSaving(true)
      
      const triggerConfig: Record<string, unknown> = {}
      if (triggerType === 'cron') {
        triggerConfig.cron_expression = generateCronFromConfig()
      }
      
      const updated = await workflowsApi.updateWorkflow(workflow.id, {
        name,
        description: description || null,
        icon: icon || null,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        visibility,
      })
      
      onUpdate(updated)
      setHasChanges(false)
      toast.success(t('settings.settingsSaved'))
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsSaving(false)
    }
  }

  // 重新生成 Webhook Token
  const handleRegenerateToken = async () => {
    if (!workflow) return
    
    try {
      setIsRegenerating(true)
      const result = await workflowsApi.regenerateWebhookToken(workflow.id)
      setWebhookToken(result.webhook_token)
      toast.success(t('settings.webhookTokenRegenerated'))
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsRegenerating(false)
    }
  }

  // 复制 Webhook URL
  const handleCopyWebhookUrl = () => {
    if (!webhookToken) return
    
    const url = `${window.location.origin}/api/v1/workflows/webhook/${webhookToken}`
    navigator.clipboard.writeText(url)
    setCopied(true)
    toast.success(t('editor.copiedToClipboard'))
    setTimeout(() => setCopied(false), 2000)
  }

  // 触发类型选项
  const triggerTypeOptions: { value: TriggerType; labelKey: string; descKey: string }[] = [
    { value: 'manual', labelKey: 'settings.triggerManual', descKey: 'settings.triggerManualDesc' },
    { value: 'webhook', labelKey: 'settings.triggerWebhook', descKey: 'settings.triggerWebhookDesc' },
    { value: 'cron', labelKey: 'settings.triggerCron', descKey: 'settings.triggerCronDesc' },
  ]

  if (!workflow) return null

  return (
    <div
      className={cn(
        'absolute top-14 right-2 bottom-2 w-[380px] min-w-[380px] bg-card border border-border rounded-xl shadow-xl z-40 flex flex-col overflow-hidden',
        'transform transition-all duration-200 ease-out',
        open ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0 pointer-events-none'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          {icon ? (
            icon.startsWith('http') || icon.startsWith('/') ? (
              <div className="w-6 h-6 rounded overflow-hidden">
                <Image
                  src={icon}
                  alt="Workflow icon"
                  width={24}
                  height={24}
                  className="w-full h-full object-cover"
                  unoptimized
                />
              </div>
            ) : (
              <span className="text-lg">{icon}</span>
            )
          ) : (
            <GitBranch className="h-5 w-5 text-muted-foreground" />
          )}
          <span className="font-medium text-sm">{t('settings.title')}</span>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          <div className="p-4 space-y-4">
          {/* 只读模式提示 */}
          {readOnly && (
            <div className="bg-muted/50 rounded-lg px-3 py-2 text-xs text-muted-foreground">
              {t('settings.readOnlyNotice')}
            </div>
          )}
          {/* 基本信息 */}
          <Collapsible open={basicInfoOpen} onOpenChange={setBasicInfoOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
              <ChevronDown className={cn(
                "h-3.5 w-3.5 transition-transform",
                !basicInfoOpen && "-rotate-90"
              )} />
              <span>{t('settings.basicInfo')}</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {/* 图标 */}
              <div className="space-y-1.5">
                <Label className="text-xs">{t('settings.icon')}</Label>
                <ImageUpload
                  value={icon}
                  onChange={setIcon}
                  previewSize="lg"
                  category="icons"
                  placeholder={<GitBranch className="h-8 w-8 text-muted-foreground/50" />}
                  disabled={readOnly}
                />
              </div>

              {/* 名称 */}
              <div className="space-y-1.5">
                <Label className="text-xs">
                  {t('settings.name')} <span className="text-destructive">*</span>
                </Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('settings.namePlaceholder')}
                  className="h-9 text-sm"
                  disabled={readOnly}
                />
              </div>

              {/* 描述 */}
              <div className="space-y-1.5">
                <Label className="text-xs">{t('settings.descriptionLabel')}</Label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={t('settings.descriptionPlaceholder')}
                  className="min-h-20 text-sm resize-none"
                  disabled={readOnly}
                />
              </div>

              {/* 可见性 */}
              <div className="space-y-1.5">
                <Label className="text-xs">{t('settings.visibility')}</Label>
                <Select value={visibility} onValueChange={(v) => v && setVisibility(v as WorkflowVisibility)} disabled={readOnly}>
                  <SelectTrigger className="h-9 text-sm">
                    <span>{visibility === 'private' ? t('settings.visibilityPrivate') : t('settings.visibilityTeam')}</span>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="private">{t('settings.visibilityPrivate')}</SelectItem>
                    <SelectItem value="team">{t('settings.visibilityTeam')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* 状态信息 */}
              <div className="bg-muted/30 rounded-lg p-2.5 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t('settings.statusLabel')}</span>
                  <Badge 
                    variant="outline" 
                    className={cn(
                      'text-[10px] px-1.5 py-0',
                      workflow.status === 'published' 
                        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300'
                        : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                    )}
                  >
                    {workflow.status === 'published' ? t('settings.publishedStatus') : t('settings.draftStatus')}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t('settings.version')}</span>
                  <span className="font-mono">v{workflow.version}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t('settings.runCount')}</span>
                  <span>{workflow.run_count}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t('settings.successRate')}</span>
                  <span>
                    {workflow.run_count > 0 
                      ? `${Math.round((workflow.success_count / workflow.run_count) * 100)}%`
                      : '-'
                    }
                  </span>
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* 触发器配置 */}
          <Collapsible open={triggerOpen} onOpenChange={setTriggerOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
              <ChevronDown className={cn(
                "h-3.5 w-3.5 transition-transform",
                !triggerOpen && "-rotate-90"
              )} />
              <span>{t('settings.triggerSection')}</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {/* 触发类型 */}
              <div className="space-y-1.5">
                <Label className="text-xs">{t('settings.triggerMethod')}</Label>
                <Select value={triggerType} onValueChange={(v) => v && setTriggerType(v as TriggerType)} disabled={readOnly}>
                  <SelectTrigger className="h-9 text-sm">
                    <span>{triggerTypeOptions.find(o => o.value === triggerType) ? t(triggerTypeOptions.find(o => o.value === triggerType)!.labelKey) : t('settings.selectTriggerMethod')}</span>
                  </SelectTrigger>
                  <SelectContent>
                    {triggerTypeOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {t(opt.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">
                  {triggerTypeOptions.find(o => o.value === triggerType) && t(triggerTypeOptions.find(o => o.value === triggerType)!.descKey)}
                </p>
              </div>

              {/* Webhook 配置 */}
              {triggerType === 'webhook' && (
                <div className="space-y-2 bg-muted/30 rounded-lg p-2.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">{t('settings.webhookUrl')}</Label>
                    {!readOnly && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-[10px] px-2"
                        onClick={handleRegenerateToken}
                        disabled={isRegenerating}
                      >
                        {isRegenerating ? (
                          <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3 w-3 mr-1" />
                        )}
                        {t('settings.regenerate')}
                      </Button>
                    )}
                  </div>
                  {webhookToken ? (
                    <div className="flex items-center gap-1">
                      <Input
                        value={`${window.location.origin}/api/v1/workflows/webhook/${webhookToken}`}
                        readOnly
                        className="h-8 text-[11px] font-mono bg-background"
                      />
                      <Button
                        variant="outline"
                        size="icon"
                        className="h-8 w-8 shrink-0"
                        onClick={handleCopyWebhookUrl}
                      >
                        {copied ? (
                          <Check className="h-3 w-3 text-green-500" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </Button>
                    </div>
                  ) : (
                    <p className="text-[10px] text-muted-foreground">
                      {t('settings.webhookUrlWillGenerate')}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground">
                    {t('settings.webhookPostHint')}
                  </p>
                </div>
              )}

              {/* 定时任务配置 */}
              {triggerType === 'cron' && (
                <div className="space-y-3">
                  {/* 执行频率类型 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs">{t('settings.scheduleFrequency')}</Label>
                    <Select value={scheduleType} onValueChange={(v) => v && setScheduleType(v as typeof scheduleType)} disabled={readOnly}>
                      <SelectTrigger className="h-9 text-sm">
                        <span>
                          {scheduleType === 'interval' && t('settings.scheduleInterval')}
                          {scheduleType === 'daily' && t('settings.scheduleDaily')}
                          {scheduleType === 'weekly' && t('settings.scheduleWeekly')}
                          {scheduleType === 'monthly' && t('settings.scheduleMonthly')}
                          {scheduleType === 'custom' && t('settings.scheduleCustomCron')}
                        </span>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="interval">{t('settings.scheduleInterval')}</SelectItem>
                        <SelectItem value="daily">{t('settings.scheduleDaily')}</SelectItem>
                        <SelectItem value="weekly">{t('settings.scheduleWeekly')}</SelectItem>
                        <SelectItem value="monthly">{t('settings.scheduleMonthly')}</SelectItem>
                        <SelectItem value="custom">{t('settings.scheduleCustomCron')}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* 按间隔执行 */}
                  {scheduleType === 'interval' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs">{t('settings.executionInterval')}</Label>
                      <Select value={String(intervalMinutes)} onValueChange={(v) => v && setIntervalMinutes(parseInt(v))} disabled={readOnly}>
                        <SelectTrigger className="h-9 text-sm">
                          <span>{intervalMinutes < 60 ? t('settings.everyNMinutes', { n: intervalMinutes }) : t('settings.everyNHours', { n: intervalMinutes / 60 })}</span>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="5">{t('settings.every5Min')}</SelectItem>
                          <SelectItem value="10">{t('settings.every10Min')}</SelectItem>
                          <SelectItem value="15">{t('settings.every15Min')}</SelectItem>
                          <SelectItem value="30">{t('settings.every30Min')}</SelectItem>
                          <SelectItem value="60">{t('settings.every1Hour')}</SelectItem>
                          <SelectItem value="120">{t('settings.every2Hours')}</SelectItem>
                          <SelectItem value="180">{t('settings.every3Hours')}</SelectItem>
                          <SelectItem value="360">{t('settings.every6Hours')}</SelectItem>
                          <SelectItem value="720">{t('settings.every12Hours')}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* 每天执行 */}
                  {scheduleType === 'daily' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs">{t('settings.executionTime')}</Label>
                      <Input
                        type="time"
                        value={dailyTime}
                        onChange={(e) => setDailyTime(e.target.value)}
                        className="h-9 text-sm"
                        disabled={readOnly}
                      />
                    </div>
                  )}

                  {/* 每周执行 */}
                  {scheduleType === 'weekly' && (
                    <div className="space-y-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs">{t('settings.weekday')}</Label>
                        <Select value={String(weeklyDay)} onValueChange={(v) => v && setWeeklyDay(parseInt(v))} disabled={readOnly}>
                          <SelectTrigger className="h-9 text-sm">
                            <span>{[t('settings.sunday'), t('settings.monday'), t('settings.tuesday'), t('settings.wednesday'), t('settings.thursday'), t('settings.friday'), t('settings.saturday')][weeklyDay]}</span>
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="1">{t('settings.monday')}</SelectItem>
                            <SelectItem value="2">{t('settings.tuesday')}</SelectItem>
                            <SelectItem value="3">{t('settings.wednesday')}</SelectItem>
                            <SelectItem value="4">{t('settings.thursday')}</SelectItem>
                            <SelectItem value="5">{t('settings.friday')}</SelectItem>
                            <SelectItem value="6">{t('settings.saturday')}</SelectItem>
                            <SelectItem value="0">{t('settings.sunday')}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">{t('settings.executionTime')}</Label>
                        <Input
                          type="time"
                          value={weeklyTime}
                          onChange={(e) => setWeeklyTime(e.target.value)}
                          className="h-9 text-sm"
                          disabled={readOnly}
                        />
                      </div>
                    </div>
                  )}

                  {/* 每月执行 */}
                  {scheduleType === 'monthly' && (
                    <div className="space-y-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs">{t('settings.date')}</Label>
                        <Select value={String(monthlyDay)} onValueChange={(v) => v && setMonthlyDay(parseInt(v))} disabled={readOnly}>
                          <SelectTrigger className="h-9 text-sm">
                            <span>{t('settings.monthlyDay', { day: monthlyDay })}</span>
                          </SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                              <SelectItem key={day} value={String(day)}>
                                {t('settings.monthlyDay', { day })}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">{t('settings.executionTime')}</Label>
                        <Input
                          type="time"
                          value={monthlyTime}
                          onChange={(e) => setMonthlyTime(e.target.value)}
                          className="h-9 text-sm"
                          disabled={readOnly}
                        />
                      </div>
                    </div>
                  )}

                  {/* 自定义 Cron */}
                  {scheduleType === 'custom' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs">{t('settings.cronExpression')}</Label>
                      <Input
                        value={cronExpression}
                        onChange={(e) => setCronExpression(e.target.value)}
                        placeholder="0 0 * * *"
                        className="h-9 text-sm font-mono"
                        disabled={readOnly}
                      />
                      <p className="text-[10px] text-muted-foreground">
                        {t('settings.cronFormatHint')}
                      </p>
                    </div>
                  )}

                  {/* 显示生成的 Cron 表达式 */}
                  <div className="bg-muted/30 rounded-lg p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground">{t('settings.cronExpression')}</span>
                      <code className="text-[11px] font-mono bg-muted px-1.5 py-0.5 rounded">
                        {generateCronFromConfig()}
                      </code>
                    </div>
                  </div>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>

          {/* 版本历史 */}
          <Collapsible open={versionHistoryOpen} onOpenChange={setVersionHistoryOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
              <ChevronDown className={cn(
                "h-3.5 w-3.5 transition-transform",
                !versionHistoryOpen && "-rotate-90"
              )} />
              <History className="h-3.5 w-3.5 mr-0.5" />
              <span>{t('settings.versionHistory')}</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {loadingVersions ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : versions.length === 0 ? (
                <div className="text-center py-6">
                  <History className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                  <p className="text-xs text-muted-foreground">{t('settings.noVersions')}</p>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {t('settings.versionsAutoSaved')}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {versions.map((version) => (
                    <div
                      key={version.id}
                      className={cn(
                        "flex items-center justify-between p-2.5 rounded-lg border bg-background hover:bg-muted/30 transition-colors",
                        version.version === workflow.version && "border-primary/50 bg-primary/5"
                      )}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-medium">
                            v{version.version}
                          </span>
                          {version.version === workflow.version && (
                            <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4">
                              {t('settings.current')}
                            </Badge>
                          )}
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                          {version.description || t('noDescription')}
                        </p>
                        <p className="text-[10px] text-muted-foreground">
                          {formatTime(version.created_at)}
                        </p>
                      </div>
                      {version.version !== workflow.version && !readOnly && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs px-2 shrink-0"
                          onClick={() => {
                            setSelectedVersion(version)
                            setRestoreDialogOpen(true)
                          }}
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          {t('settings.restore')}
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
          </div>
        </ScrollArea>
      </div>

      {/* 恢复版本确认对话框 */}
      <Dialog open={restoreDialogOpen} onOpenChange={setRestoreDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('settings.restoreToVersion', { version: selectedVersion?.version ?? '' })}</DialogTitle>
            <DialogDescription>
              {t('settings.restoreConfirmation')}
            </DialogDescription>
          </DialogHeader>
          {selectedVersion && (
            <div className="bg-muted/50 rounded-lg p-3 text-sm">
              <p className="text-muted-foreground text-xs mb-1">{t('settings.versionInfo')}</p>
              <p className="font-medium">v{selectedVersion.version}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {selectedVersion.description || t('noDescription')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t('settings.createdAtLabel')} {new Date(selectedVersion.created_at).toLocaleString()}
              </p>
            </div>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRestoreDialogOpen(false)
                setSelectedVersion(null)
              }}
            >
              {t('settings.cancel')}
            </Button>
            <Button onClick={handleRestoreVersion} disabled={isRestoring}>
              {isRestoring && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              {t('settings.confirmRestore')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Footer */}
      <div className="px-4 py-3 border-t bg-card rounded-b-xl shrink-0">
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={onClose}>
            {readOnly ? t('settings.close') : t('settings.cancel')}
          </Button>
          {!readOnly && (
            <Button
              size="sm"
              className="h-8"
              onClick={handleSave}
              disabled={isSaving || !hasChanges || !name.trim()}
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : null}
              {t('settings.save')}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
