'use client'

import * as React from 'react'
import Image from 'next/image'
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
import { workflowsApi, type Workflow, type TriggerType, type WorkflowVersionListItem } from '@/lib/api/workflows'

interface WorkflowSettingsDrawerProps {
  workflow: Workflow | null
  open: boolean
  onClose: () => void
  onUpdate: (workflow: Workflow) => void
  readOnly?: boolean
}

export function WorkflowSettingsDrawer({ workflow, open, onClose, onUpdate, readOnly = false }: WorkflowSettingsDrawerProps) {
  // 基本信息
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [icon, setIcon] = React.useState('')
  
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
      setIcon(workflow.icon || '🔄')
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
      icon !== (workflow.icon || '🔄') ||
      triggerType !== workflow.trigger_type ||
      (triggerType === 'cron' && currentCron !== savedCron)
    
    setHasChanges(changed)
  }, [workflow, name, description, icon, triggerType, scheduleType, intervalMinutes, dailyTime, weeklyDay, weeklyTime, monthlyDay, monthlyTime, cronExpression, generateCronFromConfig])

  // 加载版本历史
  const loadVersions = React.useCallback(async () => {
    if (!workflow) return
    
    try {
      setLoadingVersions(true)
      const result = await workflowsApi.getWorkflowVersions(workflow.id, { pageSize: 50 })
      setVersions(result.items)
    } catch {
      toast.error('加载版本历史失败')
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
      toast.success(`已恢复到 v${selectedVersion.version}`)
      // 重新加载版本历史
      loadVersions()
    } catch {
      toast.error('恢复版本失败')
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
      return mins <= 0 ? '刚刚' : `${mins} 分钟前`
    }
    // 小于 24 小时
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return `${hours} 小时前`
    }
    // 小于 7 天
    if (diff < 604800000) {
      const days = Math.floor(diff / 86400000)
      return `${days} 天前`
    }
    // 更久
    return date.toLocaleDateString('zh-CN', {
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
      })
      
      onUpdate(updated)
      setHasChanges(false)
      toast.success('设置已保存')
    } catch {
      toast.error('保存失败')
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
      toast.success('Webhook Token 已重新生成')
    } catch {
      toast.error('重新生成失败')
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
    toast.success('已复制到剪贴板')
    setTimeout(() => setCopied(false), 2000)
  }

  // 触发类型选项
  const triggerTypeOptions: { value: TriggerType; label: string; description: string }[] = [
    { value: 'manual', label: '手动触发', description: '通过 API 或界面手动运行' },
    { value: 'webhook', label: 'Webhook', description: '通过 HTTP 请求触发' },
    { value: 'cron', label: '定时任务', description: '按照 Cron 表达式定时运行' },
  ]

  if (!workflow) return null

  return (
    <div
      className={cn(
        'absolute top-2 right-2 bottom-2 w-90 bg-card border border-border rounded-xl shadow-xl z-40',
        'transform transition-all duration-200 ease-out',
        open ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0 pointer-events-none'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          {icon ? (
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
            <GitBranch className="h-5 w-5 text-muted-foreground" />
          )}
          <span className="font-medium text-sm">工作流设置</span>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="h-[calc(100%-120px)]">
        <div className="p-4 space-y-4">
          {/* 只读模式提示 */}
          {readOnly && (
            <div className="bg-muted/50 rounded-lg px-3 py-2 text-xs text-muted-foreground">
              只读模式，无法编辑工作流设置
            </div>
          )}
          {/* 基本信息 */}
          <Collapsible open={basicInfoOpen} onOpenChange={setBasicInfoOpen}>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs font-medium w-full py-1">
              <ChevronDown className={cn(
                "h-3.5 w-3.5 transition-transform",
                !basicInfoOpen && "-rotate-90"
              )} />
              <span>基本信息</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {/* 图标 */}
              <div className="space-y-1.5">
                <Label className="text-xs">图标</Label>
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
                  名称 <span className="text-destructive">*</span>
                </Label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="输入工作流名称"
                  className="h-9 text-sm"
                  disabled={readOnly}
                />
              </div>

              {/* 描述 */}
              <div className="space-y-1.5">
                <Label className="text-xs">描述</Label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="描述工作流的用途..."
                  className="min-h-20 text-sm resize-none"
                  disabled={readOnly}
                />
              </div>

              {/* 状态信息 */}
              <div className="bg-muted/30 rounded-lg p-2.5 space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">状态</span>
                  <Badge 
                    variant="outline" 
                    className={cn(
                      'text-[10px] px-1.5 py-0',
                      workflow.status === 'published' 
                        ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300'
                        : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                    )}
                  >
                    {workflow.status === 'published' ? '已发布' : '草稿'}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">版本</span>
                  <span className="font-mono">v{workflow.version}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">运行次数</span>
                  <span>{workflow.run_count}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">成功率</span>
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
              <span>触发器</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {/* 触发类型 */}
              <div className="space-y-1.5">
                <Label className="text-xs">触发方式</Label>
                <Select value={triggerType} onValueChange={(v) => v && setTriggerType(v as TriggerType)} disabled={readOnly}>
                  <SelectTrigger className="h-9 text-sm">
                    <span>{triggerTypeOptions.find(t => t.value === triggerType)?.label || '选择触发方式'}</span>
                  </SelectTrigger>
                  <SelectContent>
                    {triggerTypeOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">
                  {triggerTypeOptions.find(t => t.value === triggerType)?.description}
                </p>
              </div>

              {/* Webhook 配置 */}
              {triggerType === 'webhook' && (
                <div className="space-y-2 bg-muted/30 rounded-lg p-2.5">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Webhook URL</Label>
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
                        重新生成
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
                      保存后将生成 Webhook URL
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground">
                    通过 POST 请求调用此 URL 触发工作流
                  </p>
                </div>
              )}

              {/* 定时任务配置 */}
              {triggerType === 'cron' && (
                <div className="space-y-3">
                  {/* 执行频率类型 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs">执行频率</Label>
                    <Select value={scheduleType} onValueChange={(v) => v && setScheduleType(v as typeof scheduleType)} disabled={readOnly}>
                      <SelectTrigger className="h-9 text-sm">
                        <span>
                          {scheduleType === 'interval' && '按间隔执行'}
                          {scheduleType === 'daily' && '每天执行'}
                          {scheduleType === 'weekly' && '每周执行'}
                          {scheduleType === 'monthly' && '每月执行'}
                          {scheduleType === 'custom' && '自定义 Cron'}
                        </span>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="interval">按间隔执行</SelectItem>
                        <SelectItem value="daily">每天执行</SelectItem>
                        <SelectItem value="weekly">每周执行</SelectItem>
                        <SelectItem value="monthly">每月执行</SelectItem>
                        <SelectItem value="custom">自定义 Cron</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* 按间隔执行 */}
                  {scheduleType === 'interval' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs">执行间隔</Label>
                      <Select value={String(intervalMinutes)} onValueChange={(v) => v && setIntervalMinutes(parseInt(v))} disabled={readOnly}>
                        <SelectTrigger className="h-9 text-sm">
                          <span>{intervalMinutes < 60 ? `每 ${intervalMinutes} 分钟` : `每 ${intervalMinutes / 60} 小时`}</span>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="5">每 5 分钟</SelectItem>
                          <SelectItem value="10">每 10 分钟</SelectItem>
                          <SelectItem value="15">每 15 分钟</SelectItem>
                          <SelectItem value="30">每 30 分钟</SelectItem>
                          <SelectItem value="60">每 1 小时</SelectItem>
                          <SelectItem value="120">每 2 小时</SelectItem>
                          <SelectItem value="180">每 3 小时</SelectItem>
                          <SelectItem value="360">每 6 小时</SelectItem>
                          <SelectItem value="720">每 12 小时</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* 每天执行 */}
                  {scheduleType === 'daily' && (
                    <div className="space-y-1.5">
                      <Label className="text-xs">执行时间</Label>
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
                        <Label className="text-xs">星期</Label>
                        <Select value={String(weeklyDay)} onValueChange={(v) => v && setWeeklyDay(parseInt(v))} disabled={readOnly}>
                          <SelectTrigger className="h-9 text-sm">
                            <span>{['周日', '周一', '周二', '周三', '周四', '周五', '周六'][weeklyDay]}</span>
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="1">周一</SelectItem>
                            <SelectItem value="2">周二</SelectItem>
                            <SelectItem value="3">周三</SelectItem>
                            <SelectItem value="4">周四</SelectItem>
                            <SelectItem value="5">周五</SelectItem>
                            <SelectItem value="6">周六</SelectItem>
                            <SelectItem value="0">周日</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">执行时间</Label>
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
                        <Label className="text-xs">日期</Label>
                        <Select value={String(monthlyDay)} onValueChange={(v) => v && setMonthlyDay(parseInt(v))} disabled={readOnly}>
                          <SelectTrigger className="h-9 text-sm">
                            <span>每月 {monthlyDay} 日</span>
                          </SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                              <SelectItem key={day} value={String(day)}>
                                每月 {day} 日
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs">执行时间</Label>
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
                      <Label className="text-xs">Cron 表达式</Label>
                      <Input
                        value={cronExpression}
                        onChange={(e) => setCronExpression(e.target.value)}
                        placeholder="0 0 * * *"
                        className="h-9 text-sm font-mono"
                        disabled={readOnly}
                      />
                      <p className="text-[10px] text-muted-foreground">
                        格式：分 时 日 月 周
                      </p>
                    </div>
                  )}

                  {/* 显示生成的 Cron 表达式 */}
                  <div className="bg-muted/30 rounded-lg p-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-muted-foreground">Cron 表达式</span>
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
              <span>版本历史</span>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 space-y-3">
              {loadingVersions ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : versions.length === 0 ? (
                <div className="text-center py-6">
                  <History className="h-8 w-8 mx-auto text-muted-foreground/50 mb-2" />
                  <p className="text-xs text-muted-foreground">暂无版本记录</p>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    发布工作流时会自动保存版本
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
                              当前
                            </Badge>
                          )}
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-0.5 truncate">
                          {version.description || '无描述'}
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
                          恢复
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

      {/* 恢复版本确认对话框 */}
      <Dialog open={restoreDialogOpen} onOpenChange={setRestoreDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>恢复到 v{selectedVersion?.version}</DialogTitle>
            <DialogDescription>
              确定要恢复到此版本吗？当前版本将自动保存，之后可以随时恢复。
            </DialogDescription>
          </DialogHeader>
          {selectedVersion && (
            <div className="bg-muted/50 rounded-lg p-3 text-sm">
              <p className="text-muted-foreground text-xs mb-1">版本信息</p>
              <p className="font-medium">v{selectedVersion.version}</p>
              <p className="text-xs text-muted-foreground mt-1">
                {selectedVersion.description || '无描述'}
              </p>
              <p className="text-xs text-muted-foreground">
                创建于 {new Date(selectedVersion.created_at).toLocaleString('zh-CN')}
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
              取消
            </Button>
            <Button onClick={handleRestoreVersion} disabled={isRestoring}>
              {isRestoring && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              确认恢复
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Footer */}
      <div className="absolute bottom-0 left-0 right-0 px-4 py-3 border-t bg-card rounded-b-xl">
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" className="h-8" onClick={onClose}>
            {readOnly ? '关闭' : '取消'}
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
              保存
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
