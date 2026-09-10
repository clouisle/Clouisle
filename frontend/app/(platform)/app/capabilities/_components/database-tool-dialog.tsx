'use client'

import React, { useState, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import {
  ToolCreateInput,
  ToolUpdateInput,
  ToolDetail,
  DatabaseConfig,
  DatabaseType,
  ToolCategory,
  ToolParameter,
  toolsApi,
} from '@/lib/api/tools'
import { Team } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { ImageUpload } from '@/components/ui/image-upload'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ToolCategoryInput } from './tool-category-input'
import { Eye, EyeOff, Loader2, Database, CheckCircle2, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { normalizeValidationErrors, clearValidationError } from '@/lib/validation'
import { FieldError } from '@/components/ui/field'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface DatabaseToolDialogProps {
  tool?: ToolDetail | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: ToolCreateInput | ToolUpdateInput) => Promise<void>
  teams?: Team[]
  selectedTeamId?: string
  onSelectedTeamChange?: (teamId: string | null) => void
}

const DATABASE_TYPES: Array<{ value: DatabaseType; label: string; defaultPort?: number }> = [
  { value: 'postgresql', label: 'PostgreSQL', defaultPort: 5432 },
  { value: 'mysql', label: 'MySQL / MariaDB', defaultPort: 3306 },
  { value: 'redis', label: 'Redis', defaultPort: 6379 },
  { value: 'mongodb', label: 'MongoDB', defaultPort: 27017 },
]

function getDefaultParametersForDbType(dbType: DatabaseType): ToolParameter[] {
  if (dbType === 'postgresql' || dbType === 'mysql') {
    return [
      {
        name: 'action',
        type: 'string',
        description: '执行的操作: schema (查看表结构), query (执行只读 SELECT 查询)',
        required: true,
        enum: ['schema', 'query'],
        default: 'schema',
      },
      {
        name: 'sql',
        type: 'string',
        description: '只读 SQL 查询语句 (action=query 时必填)',
        required: false,
      },
      {
        name: 'tables',
        type: 'array',
        description: '需要查看 Schema 的表名列表 (action=schema 时可选)',
        required: false,
      },
      {
        name: 'include_samples',
        type: 'boolean',
        description: '是否包含前 3 条数据样例 (action=schema 时可选)',
        required: false,
        default: false,
      },
      {
        name: 'limit',
        type: 'integer',
        description: '最大返回行数，默认 50',
        required: false,
        default: 50,
      },
    ]
  } else if (dbType === 'redis') {
    return [
      {
        name: 'action',
        type: 'string',
        description: '执行的操作: scan (扫描键列表与类型), get (获取键值与TTL), command (执行只读命令)',
        required: true,
        enum: ['scan', 'get', 'command'],
        default: 'scan',
      },
      {
        name: 'key',
        type: 'string',
        description: '目标键名 (action 为 get 或 command 时必填)',
        required: false,
      },
      {
        name: 'command',
        type: 'string',
        description: 'Redis 命令名称 (如 HGETALL, LRANGE, ZRANGE)',
        required: false,
      },
      {
        name: 'args',
        type: 'array',
        description: '命令附加参数列表',
        required: false,
      },
      {
        name: 'pattern',
        type: 'string',
        description: '键匹配模式 (action=scan 时使用，默认 *)',
        required: false,
        default: '*',
      },
    ]
  } else {
    // MongoDB
    return [
      {
        name: 'action',
        type: 'string',
        description: '操作类型: schema (查看集合/文档结构), find (查询文档), aggregate (聚合分析), count (统计文档数)',
        required: true,
        enum: ['schema', 'find', 'aggregate', 'count'],
        default: 'schema',
      },
      {
        name: 'collection',
        type: 'string',
        description: '目标集合名称',
        required: false,
      },
      {
        name: 'filter',
        type: 'object',
        description: 'JSON 格式过滤条件 (用于 find/count)',
        required: false,
      },
      {
        name: 'pipeline',
        type: 'array',
        description: '聚合管道阶段数组 (用于 aggregate)',
        required: false,
      },
      {
        name: 'projection',
        type: 'object',
        description: '指定返回或排除字段 (例如 {"_id": 0, "title": 1})',
        required: false,
      },
      {
        name: 'limit',
        type: 'integer',
        description: '返回文档上限，默认 20',
        required: false,
        default: 20,
      },
    ]
  }
}

export function DatabaseToolDialog({
  tool,
  open,
  onOpenChange,
  onSave,
  teams = [],
  selectedTeamId,
  onSelectedTeamChange,
}: DatabaseToolDialogProps) {
  const t = useTranslations('platform.tools')
  const tCommon = useTranslations('common')
  const isEditing = !!tool

  // 基础信息
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('')
  const [category, setCategory] = useState<ToolCategory>('data')
  const [isEnabled, setIsEnabled] = useState(true)

  // 数据库配置
  const [dbType, setDbType] = useState<DatabaseType>('postgresql')
  const [connectionMode, setConnectionMode] = useState<'params' | 'url'>('params')
  const [host, setHost] = useState('127.0.0.1')
  const [port, setPort] = useState<string>('5432')
  const [database, setDatabase] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [url, setUrl] = useState('')
  const [authSource, setAuthSource] = useState('admin')
  const [timeout, setTimeoutSec] = useState('15')
  const [maxLimit, setMaxLimit] = useState('100')

  const [showPassword, setShowPassword] = useState(false)
  const [testingConnection, setTestingConnection] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // 初始化数据
  useEffect(() => {
    if (tool && open) {
      setName(tool.name || '')
      setDisplayName(tool.display_name || '')
      setDescription(tool.description || '')
      setIcon(tool.icon || '')
      setCategory((tool.category as ToolCategory) || 'data')
      setIsEnabled(tool.is_enabled ?? true)

      const cfg = (tool.database_config || {}) as Partial<DatabaseConfig>
      const curType = (cfg.db_type as DatabaseType) || 'postgresql'
      setDbType(curType)
      setConnectionMode(cfg.url ? 'url' : 'params')
      setHost(cfg.host || '127.0.0.1')
      setPort(cfg.port ? String(cfg.port) : String(DATABASE_TYPES.find((d) => d.value === curType)?.defaultPort || ''))
      setDatabase(cfg.database || '')
      setUsername(cfg.username || '')
      setPassword(cfg.password || '')
      setUrl(cfg.url || '')
      setAuthSource(cfg.auth_source || 'admin')
      setTimeoutSec(cfg.timeout ? String(cfg.timeout) : '15')
      setMaxLimit(cfg.max_limit ? String(cfg.max_limit) : '100')
    } else if (open) {
      setName('')
      setDisplayName('')
      setDescription('')
      setIcon('')
      setCategory('data')
      setIsEnabled(true)
      setDbType('postgresql')
      setConnectionMode('params')
      setHost('127.0.0.1')
      setPort('5432')
      setDatabase('')
      setUsername('')
      setPassword('')
      setUrl('')
      setAuthSource('admin')
      setTimeoutSec('15')
      setMaxLimit('100')
    }
    setFieldErrors({})
    setTestResult(null)
  }, [tool, open])

  // 切换数据库类型时更新默认端口
  const handleDbTypeChange = (type: DatabaseType) => {
    setDbType(type)
    const target = DATABASE_TYPES.find((d) => d.value === type)
    if (target?.defaultPort) {
      setPort(String(target.defaultPort))
    }
    setTestResult(null)
  }

  const buildDatabaseConfig = (): DatabaseConfig => {
    if (connectionMode === 'url') {
      return {
        db_type: dbType,
        url: url.trim() || undefined,
        timeout: parseInt(timeout, 10) || 15,
        max_limit: parseInt(maxLimit, 10) || 100,
      }
    }
    return {
      db_type: dbType,
      host: host.trim() || undefined,
      port: port ? parseInt(port, 10) : undefined,
      database: database.trim() || undefined,
      username: username.trim() || undefined,
      password: password || undefined,
      auth_source: authSource.trim() || undefined,
      timeout: parseInt(timeout, 10) || 15,
      max_limit: parseInt(maxLimit, 10) || 100,
    }
  }

  // 测试连接
  const handleTestConnection = async () => {
    setTestingConnection(true)
    setTestResult(null)
    try {
      const config = buildDatabaseConfig()
      const res = await toolsApi.testDatabaseConnection(config)
      if (res.success) {
        setTestResult({
          success: true,
          message: res.message || tCommon('success'),
        })
        toast.success(t('databaseDialog.connectionSuccess'))
      } else {
        setTestResult({
          success: false,
          message: res.message || t('databaseDialog.connectionFailed'),
        })
        toast.error(t('databaseDialog.connectionFailed'))
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : t('databaseDialog.connectionFailed')
      setTestResult({
        success: false,
        message: msg,
      })
      toast.error(msg)
    } finally {
      setTestingConnection(false)
    }
  }

  // 保存工具
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const errors: Record<string, string> = {}
    if (!name.trim()) errors.name = t('error.nameRequired')
    if (!displayName.trim()) errors.displayName = t('form.displayNameRequired')
    if (connectionMode === 'url') {
      if (!url.trim()) errors.url = t('databaseDialog.urlRequired')
    } else {
      if (!host.trim()) errors.host = t('databaseDialog.hostRequired')
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors)
      return
    }

    setIsSubmitting(true)
    try {
      const dbConfig = buildDatabaseConfig()
      const params = getDefaultParametersForDbType(dbType)

      const payload: ToolCreateInput | ToolUpdateInput = {
        name: name.trim(),
        display_name: displayName.trim(),
        description: description.trim(),
        icon: icon.trim() || undefined,
        category,
        type: 'custom',
        custom_type: 'database',
        is_enabled: isEnabled,
        database_config: dbConfig,
        parameters: params,
      }

      await onSave(payload)
      onOpenChange(false)
    } catch (error) {
      const normalized = normalizeValidationErrors(error)
      setFieldErrors(normalized)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            {isEditing ? t('databaseDialog.editTitle') : t('databaseDialog.createTitle')}
          </DialogTitle>
          <DialogDescription>{t('databaseDialog.description')}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          {/* 团队选择 (仅新建时) */}
          {!isEditing && onSelectedTeamChange && teams.length > 0 && (
            <div className="space-y-1.5">
              <Label htmlFor="team">{tCommon('team')}</Label>
              <Select value={selectedTeamId} onValueChange={onSelectedTeamChange}>
                <SelectTrigger id="team">
                  <SelectValue>{teams.find((team) => team.id === selectedTeamId)?.name || t('selectTeam')}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {teams.map((team) => (
                    <SelectItem key={team.id} value={team.id}>
                      {team.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 基础信息 */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="name">{t('form.name')} *</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'name'))
                }}
                placeholder="crm_db"
                disabled={isEditing}
                aria-invalid={!!fieldErrors.name}
              />
              <FieldError>{fieldErrors.name}</FieldError>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="displayName">{t('form.displayName')} *</Label>
              <Input
                id="displayName"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'displayName'))
                }}
                placeholder="客户中心主数据库"
                aria-invalid={!!fieldErrors.displayName}
              />
              <FieldError>{fieldErrors.displayName}</FieldError>
            </div>
          </div>

          {/* 图标上传与描述 */}
          <div className="flex items-start gap-4">
            <div className="space-y-1.5">
              <Label>{t('form.icon')}</Label>
              <ImageUpload
                value={icon.startsWith('http') ? icon : ''}
                onChange={setIcon}
                previewSize="sm"
                category="icons"
                placeholder={
                  icon ? (
                    <span className="text-2xl">
                      {icon.startsWith('http') ? '' : icon}
                    </span>
                  ) : (
                    <Database className="h-6 w-6 text-muted-foreground" />
                  )
                }
              />
            </div>
            <div className="flex-1 space-y-1.5">
              <Label htmlFor="description">{t('form.description')}</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('databaseDialog.descriptionPlaceholder')}
                rows={2}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="category">{t('form.category')}</Label>
              <ToolCategoryInput
                id="category"
                value={category}
                onChange={(val) => setCategory(val as ToolCategory)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="dbType">{t('databaseDialog.dbType')} *</Label>
              <Select value={dbType} onValueChange={(v) => handleDbTypeChange(v as DatabaseType)}>
                <SelectTrigger id="dbType">
                  <SelectValue>{DATABASE_TYPES.find((d) => d.value === dbType)?.label || dbType}</SelectValue>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {DATABASE_TYPES.map((d) => (
                    <SelectItem key={d.value} value={d.value}>
                      {d.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* 数据库连接参数 */}
          <div className="border rounded-lg p-4 bg-muted/20 space-y-3">
            <div className="flex items-center justify-between pb-1 border-b">
              <span className="text-sm font-semibold">{t('databaseDialog.connectionSettings')}</span>
              <Tabs
                value={connectionMode}
                onValueChange={(v) => {
                  setConnectionMode(v as 'params' | 'url')
                  setFieldErrors((prev) => {
                    const next = { ...prev }
                    delete next.host
                    delete next.url
                    return next
                  })
                }}
              >
                <TabsList className="h-7 p-0.5">
                  <TabsTrigger value="params" className="text-xs px-2.5 h-6">
                    {t('databaseDialog.paramsMode')}
                  </TabsTrigger>
                  <TabsTrigger value="url" className="text-xs px-2.5 h-6">
                    {t('databaseDialog.urlMode')}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {connectionMode === 'url' ? (
              <div className="space-y-1.5">
                <Label htmlFor="connectionUrl">{t('databaseDialog.url')} *</Label>
                <Input
                  id="connectionUrl"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value)
                    setFieldErrors((prev) => clearValidationError(prev, 'url'))
                  }}
                  placeholder={
                    dbType === 'postgresql'
                      ? 'postgresql://user:password@127.0.0.1:5432/dbname'
                      : dbType === 'mysql'
                        ? 'mysql://user:password@127.0.0.1:3306/dbname'
                        : dbType === 'redis'
                          ? 'redis://:password@127.0.0.1:6379/0'
                          : 'mongodb://user:password@127.0.0.1:27017/dbname'
                  }
                  aria-invalid={!!fieldErrors.url}
                />
                <FieldError>{fieldErrors.url}</FieldError>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2 space-y-1.5">
                    <Label htmlFor="host">{t('databaseDialog.host')} *</Label>
                    <Input
                      id="host"
                      value={host}
                      onChange={(e) => {
                        setHost(e.target.value)
                        setFieldErrors((prev) => clearValidationError(prev, 'host'))
                      }}
                      placeholder="127.0.0.1"
                      aria-invalid={!!fieldErrors.host}
                    />
                    <FieldError>{fieldErrors.host}</FieldError>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="port">{t('databaseDialog.port')}</Label>
                    <Input
                      id="port"
                      value={port}
                      onChange={(e) => setPort(e.target.value)}
                      placeholder="5432"
                    />
                  </div>
                </div>

                {dbType !== 'redis' && (
                  <div className="space-y-1.5">
                    <Label htmlFor="database">{t('databaseDialog.databaseName')}</Label>
                    <Input
                      id="database"
                      value={database}
                      onChange={(e) => setDatabase(e.target.value)}
                      placeholder="production_db"
                    />
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="username">{t('databaseDialog.username')}</Label>
                    <Input
                      id="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="readonly_user"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="password">{t('databaseDialog.password')}</Label>
                    <div className="relative">
                      <Input
                        id="password"
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="pr-10"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-full px-3 hover:bg-transparent"
                        onClick={() => setShowPassword(!showPassword)}
                      >
                        {showPassword ? (
                          <EyeOff className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <Eye className="h-4 w-4 text-muted-foreground" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* 查询控制参数 */}
            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-dashed">
              <div className="space-y-1.5">
                <Label htmlFor="timeout">{t('databaseDialog.timeout')}</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="timeout"
                    type="number"
                    value={timeout}
                    onChange={(e) => setTimeoutSec(e.target.value)}
                    min={1}
                    max={120}
                    placeholder="15"
                  />
                  <span className="text-xs text-muted-foreground whitespace-nowrap">s</span>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="maxLimit">{t('databaseDialog.maxLimit')}</Label>
                <Input
                  id="maxLimit"
                  type="number"
                  value={maxLimit}
                  onChange={(e) => setMaxLimit(e.target.value)}
                  min={1}
                  max={1000}
                  placeholder="100"
                />
              </div>
            </div>

            {/* 测试连通性按钮与结果 */}
            <div className="pt-2 flex items-center justify-between">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testingConnection}
                className="gap-1.5"
              >
                {testingConnection && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {t('databaseDialog.testConnection')}
              </Button>

              {testResult && (
                <div className="flex items-center gap-1.5 text-xs">
                  {testResult.success ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                        {testResult.message}
                      </span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 text-destructive" />
                      <span className="text-destructive font-medium truncate max-w-[280px]">
                        {testResult.message}
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {tCommon('cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditing ? tCommon('save') : tCommon('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
