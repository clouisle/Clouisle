'use client'

import { useState, useEffect, useCallback } from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Plus, Trash2, Info, Terminal, Globe, RefreshCw, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ToolCreateInput,
  ToolUpdateInput,
  ToolDetail,
  McpConfig,
  McpTransportType,
  McpToolInfo,
  toolsApi
} from '@/lib/api/tools'
import type { UserTeamInfo } from '@/lib/api'
import { ImageUpload } from '@/components/ui/image-upload'

interface McpToolDialogProps {
  tool?: ToolDetail | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (data: ToolCreateInput | ToolUpdateInput) => Promise<void>
  teams?: UserTeamInfo[]
  selectedTeamId?: string
  onSelectedTeamChange?: (teamId: string | null) => void
}

interface EnvVar {
  key: string
  value: string
}

interface Header {
  key: string
  value: string
}

const TOOL_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/

export function McpToolDialog({
  tool,
  open,
  onOpenChange,
  onSave,
  teams = [],
  selectedTeamId,
  onSelectedTeamChange,
}: McpToolDialogProps) {
  const t = useTranslations('platform.tools')
  const tCommon = useTranslations('common')

  const isEditing = !!tool

  // 基本信息
  const [name, setName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [icon, setIcon] = useState('')
  const [isEnabled, setIsEnabled] = useState(true)
  const [nameError, setNameError] = useState('')

  // 传输类型
  const [transportType, setTransportType] = useState<McpTransportType>('stdio')

  // stdio 配置
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState<string[]>([''])
  const [envVars, setEnvVars] = useState<EnvVar[]>([{ key: '', value: '' }])

  // SSE/HTTP 配置
  const [url, setUrl] = useState('')
  const [headers, setHeaders] = useState<Header[]>([{ key: '', value: '' }])

  // MCP 工具列表
  const [mcpTools, setMcpTools] = useState<McpToolInfo[]>([])
  const [isLoadingTools, setIsLoadingTools] = useState(false)
  const [toolsLoaded, setToolsLoaded] = useState(false)

  // UI 状态
  const [isLoading, setIsLoading] = useState(false)

  // 重置工具列表状态
  const resetToolsState = useCallback(() => {
    setMcpTools([])
    setToolsLoaded(false)
  }, [])

  // 初始化表单
  useEffect(() => {
    if (open) {
      if (tool) {
        setName(tool.name)
        setDisplayName(tool.display_name)
        setIcon(tool.icon || '')
        setIsEnabled(tool.is_enabled)
        setNameError('')

        if (tool.mcp_config) {
          const transport = tool.mcp_config.transport || 'stdio'
          setTransportType(transport)
          
          if (transport === 'stdio') {
            setCommand(tool.mcp_config.command || '')
            setArgs(tool.mcp_config.args?.length ? tool.mcp_config.args : [''])
            setEnvVars(
              tool.mcp_config.env
                ? Object.entries(tool.mcp_config.env).map(([key, value]) => ({ key, value: String(value) }))
                : [{ key: '', value: '' }]
            )
            setUrl('')
            setHeaders([{ key: '', value: '' }])
          } else {
            setUrl(tool.mcp_config.url || '')
            setHeaders(
              tool.mcp_config.headers
                ? Object.entries(tool.mcp_config.headers).map(([key, value]) => ({ key, value: String(value) }))
                : [{ key: '', value: '' }]
            )
            setCommand('')
            setArgs([''])
            setEnvVars([{ key: '', value: '' }])
          }
        }
        // 编辑时不自动加载工具列表
        setToolsLoaded(true)
      } else {
        // 重置为默认值
        setName('')
        setDisplayName('')
        setIcon('')
        setIsEnabled(true)
        setNameError('')
        setTransportType('stdio')
        setCommand('')
        setArgs([''])
        setEnvVars([{ key: '', value: '' }])
        setUrl('')
        setHeaders([{ key: '', value: '' }])
        resetToolsState()
      }
    }
  }, [tool, open, resetToolsState])

  // 当传输配置改变时，重置工具列表
  useEffect(() => {
    if (!isEditing) {
      resetToolsState()
    }
  }, [transportType, command, url, isEditing, resetToolsState])

  // 构建当前 MCP 配置
  const buildMcpConfig = useCallback((): McpConfig => {
    if (transportType === 'stdio') {
      return {
        transport: 'stdio',
        command,
        args: args.filter((a) => a.trim()),
        env: envVars
          .filter((e) => e.key.trim())
          .reduce((acc, e) => ({ ...acc, [e.key]: e.value }), {} as Record<string, string>),
      }
    } else {
      return {
        transport: transportType,
        url,
        headers: headers
          .filter((h) => h.key.trim())
          .reduce((acc, h) => ({ ...acc, [h.key]: h.value }), {} as Record<string, string>),
      }
    }
  }, [transportType, command, args, envVars, url, headers])

  // 获取 MCP 工具列表
  const handleFetchTools = async () => {
    const config = buildMcpConfig()
    
    // 验证配置
    if (transportType === 'stdio' && !command) {
      toast.error(t('mcpDialog.commandRequired'))
      return
    }
    if ((transportType === 'sse' || transportType === 'http') && !url) {
      toast.error(t('mcpDialog.urlRequired'))
      return
    }

    setIsLoadingTools(true)
    try {
      const response = await toolsApi.listMcpTools(config)
      setMcpTools(response.tools)
      setToolsLoaded(true)
      
      if (response.tools.length === 0) {
        toast.info(t('mcpDialog.noToolsFound'))
      } else {
        toast.success(t('mcpDialog.toolsLoaded', { count: response.tools.length }))
      }
    } catch (error) {
      console.error('Failed to fetch MCP tools:', error)
      setMcpTools([])
      setToolsLoaded(false)
    } finally {
      setIsLoadingTools(false)
    }
  }

  const handleSave = async () => {
    if (!TOOL_NAME_PATTERN.test(name.trim())) {
      setNameError(t('error.invalidName'))
      return
    }

    setNameError('')

    setIsLoading(true)
    try {
      const mcpConfig = buildMcpConfig()

      // 生成工具描述
      let toolsDescription = ''
      if (mcpTools.length > 0) {
        toolsDescription = mcpTools.map(t => `- ${t.name}: ${t.description || 'No description'}`).join('\n')
      }

      const data: ToolCreateInput | ToolUpdateInput = {
        name,
        display_name: displayName,
        description: toolsDescription || `MCP Server: ${displayName || name}`,
        icon,
        is_enabled: isEnabled,
        type: 'mcp',
        mcp_config: mcpConfig,
      }

      await onSave(data)
    } finally {
      setIsLoading(false)
    }
  }

  // 判断是否可以连接
  const canConnect = transportType === 'stdio' ? !!command : !!url
  
  // 判断是否可以保存
  const canSave = name && canConnect

  const addArg = () => {
    setArgs([...args, ''])
  }

  const removeArg = (index: number) => {
    if (args.length > 1) {
      setArgs(args.filter((_, i) => i !== index))
    }
  }

  const updateArg = (index: number, value: string) => {
    const newArgs = [...args]
    newArgs[index] = value
    setArgs(newArgs)
  }

  const addEnvVar = () => {
    setEnvVars([...envVars, { key: '', value: '' }])
  }

  const removeEnvVar = (index: number) => {
    if (envVars.length > 1) {
      setEnvVars(envVars.filter((_, i) => i !== index))
    }
  }

  const updateEnvVar = (index: number, field: 'key' | 'value', value: string) => {
    const newEnvVars = [...envVars]
    newEnvVars[index][field] = value
    setEnvVars(newEnvVars)
  }

  // Header 操作
  const addHeader = () => {
    setHeaders([...headers, { key: '', value: '' }])
  }

  const removeHeader = (index: number) => {
    if (headers.length > 1) {
      setHeaders(headers.filter((_, i) => i !== index))
    }
  }

  const updateHeader = (index: number, field: 'key' | 'value', value: string) => {
    const newHeaders = [...headers]
    newHeaders[index][field] = value
    setHeaders(newHeaders)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? t('mcpDialog.editTitle') : t('mcpDialog.createTitle')}
          </DialogTitle>
          <DialogDescription>
            {t('mcpDialog.description')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* 基本信息 */}
          <div className="grid grid-cols-2 gap-4">
            {!isEditing && onSelectedTeamChange && teams.length > 0 && (
              <div className="space-y-2 col-span-2">
                <Label htmlFor="team">{tCommon('team')}</Label>
                <Select value={selectedTeamId} onValueChange={onSelectedTeamChange}>
                  <SelectTrigger id="team">
                    <SelectValue>
                      {teams.find((team) => team.id === selectedTeamId)?.name || t('selectTeam')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent side="bottom" alignItemWithTrigger={false}>
                    {teams.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="name">{t('form.name')}</Label>
              <Input
                id="name"
                placeholder="my_mcp_server"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  if (nameError) setNameError('')
                }}
                disabled={isEditing}
                aria-invalid={!!nameError}
              />
              {nameError && <p className="text-sm text-destructive">{nameError}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="displayName">{t('form.displayName')}</Label>
              <Input
                id="displayName"
                placeholder="My MCP Server"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="space-y-2">
              <Label>{t('form.icon')}</Label>
              <ImageUpload
                value={icon.startsWith('http') ? icon : ''}
                onChange={setIcon}
                previewSize="sm"
                category="icons"
                placeholder={
                  <span className="text-2xl">
                    {icon.startsWith('http') ? '' : icon}
                  </span>
                }
              />
            </div>
            <div className="flex-1 flex items-center justify-end gap-2">
              <Label htmlFor="enabled">{t('form.enabled')}</Label>
              <Switch
                id="enabled"
                checked={isEnabled}
                onCheckedChange={setIsEnabled}
              />
            </div>
          </div>

          {/* MCP 配置 */}
          <div className="space-y-4 border rounded-lg p-4">
            <h4 className="font-medium flex items-center gap-2">
              {t('mcpDialog.mcpConfig')}
              <span title={t('mcpDialog.mcpConfigHint')}>
                <Info className="h-4 w-4 text-muted-foreground cursor-help" />
              </span>
            </h4>

            {/* 传输类型选择 */}
            <Tabs value={transportType} onValueChange={(v) => setTransportType(v as McpTransportType)}>
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="stdio" className="flex items-center gap-2">
                  <Terminal className="h-4 w-4" />
                  {t('mcpDialog.stdioMode')}
                </TabsTrigger>
                <TabsTrigger value="sse" className="flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  {t('mcpDialog.sseMode')}
                </TabsTrigger>
                <TabsTrigger value="http" className="flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  {t('mcpDialog.httpMode')}
                </TabsTrigger>
              </TabsList>

              {/* stdio 配置 */}
              <TabsContent value="stdio" className="space-y-4 mt-4">
                {/* Command */}
                <div className="space-y-2">
                  <Label htmlFor="command">{t('mcpDialog.command')}</Label>
                  <Input
                    id="command"
                    placeholder="npx"
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    className="font-mono"
                  />
                </div>

                {/* Arguments */}
                <div className="space-y-2">
                  <Label>{t('mcpDialog.arguments')}</Label>
                  <div className="space-y-2">
                    {args.map((arg, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          placeholder={`arg ${index + 1}`}
                          value={arg}
                          onChange={(e) => updateArg(index, e.target.value)}
                          className="flex-1 font-mono"
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeArg(index)}
                          disabled={args.length === 1}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addArg}>
                      <Plus className="h-4 w-4 mr-1" />
                      {t('mcpDialog.addArg')}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t('mcpDialog.argsExample')}
                  </p>
                </div>

                {/* Environment Variables */}
                <div className="space-y-2">
                  <Label>{t('mcpDialog.envVars')}</Label>
                  <div className="space-y-2">
                    {envVars.map((envVar, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          placeholder="KEY"
                          value={envVar.key}
                          onChange={(e) => updateEnvVar(index, 'key', e.target.value)}
                          className="flex-1 font-mono"
                        />
                        <Input
                          placeholder="value"
                          value={envVar.value}
                          onChange={(e) => updateEnvVar(index, 'value', e.target.value)}
                          className="flex-1 font-mono"
                          type="password"
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeEnvVar(index)}
                          disabled={envVars.length === 1}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addEnvVar}>
                      <Plus className="h-4 w-4 mr-1" />
                      {t('mcpDialog.addEnvVar')}
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* SSE 配置 */}
              <TabsContent value="sse" className="space-y-4 mt-4">
                {/* URL */}
                <div className="space-y-2">
                  <Label htmlFor="url">{t('mcpDialog.url')}</Label>
                  <Input
                    id="url"
                    placeholder="http://localhost:3000/sse"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('mcpDialog.sseUrlHint')}
                  </p>
                </div>

                {/* Headers */}
                <div className="space-y-2">
                  <Label>{t('mcpDialog.headers')}</Label>
                  <div className="space-y-2">
                    {headers.map((header, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          placeholder="Header-Name"
                          value={header.key}
                          onChange={(e) => updateHeader(index, 'key', e.target.value)}
                          className="flex-1 font-mono"
                        />
                        <Input
                          placeholder="value"
                          value={header.value}
                          onChange={(e) => updateHeader(index, 'value', e.target.value)}
                          className="flex-1 font-mono"
                          type="password"
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeHeader(index)}
                          disabled={headers.length === 1}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addHeader}>
                      <Plus className="h-4 w-4 mr-1" />
                      {t('mcpDialog.addHeader')}
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* HTTP 配置 */}
              <TabsContent value="http" className="space-y-4 mt-4">
                {/* URL */}
                <div className="space-y-2">
                  <Label htmlFor="http-url">{t('mcpDialog.url')}</Label>
                  <Input
                    id="http-url"
                    placeholder="http://localhost:3000/mcp"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('mcpDialog.httpUrlHint')}
                  </p>
                </div>

                {/* Headers */}
                <div className="space-y-2">
                  <Label>{t('mcpDialog.headers')}</Label>
                  <div className="space-y-2">
                    {headers.map((header, index) => (
                      <div key={index} className="flex gap-2">
                        <Input
                          placeholder="Header-Name"
                          value={header.key}
                          onChange={(e) => updateHeader(index, 'key', e.target.value)}
                          className="flex-1 font-mono"
                        />
                        <Input
                          placeholder="value"
                          value={header.value}
                          onChange={(e) => updateHeader(index, 'value', e.target.value)}
                          className="flex-1 font-mono"
                          type="password"
                        />
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => removeHeader(index)}
                          disabled={headers.length === 1}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={addHeader}>
                      <Plus className="h-4 w-4 mr-1" />
                      {t('mcpDialog.addHeader')}
                    </Button>
                  </div>
                </div>
              </TabsContent>
            </Tabs>

            {/* 获取工具列表按钮 */}
            <div className="pt-2">
              <Button 
                variant="outline" 
                onClick={handleFetchTools}
                disabled={!canConnect || isLoadingTools}
                className="w-full"
              >
                {isLoadingTools ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                {t('mcpDialog.fetchTools')}
              </Button>
            </div>
          </div>

          {/* 工具列表 */}
          {toolsLoaded && (
            <div className="space-y-3 border rounded-lg p-4">
              <div className="flex items-center justify-between">
                <h4 className="font-medium flex items-center gap-2">
                  {t('mcpDialog.availableTools')}
                  <Badge variant="secondary">{mcpTools.length}</Badge>
                </h4>
                {mcpTools.length > 0 && (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                )}
              </div>

              {mcpTools.length > 0 ? (
                <ScrollArea className="h-[200px] -m-1">
                  <div className="space-y-2 p-1">
                    {mcpTools.map((mcpTool, index) => (
                      <Card key={index} className="p-3">
                        <div className="flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-sm truncate">{mcpTool.name}</div>
                            <div className="text-xs text-muted-foreground line-clamp-2">
                              {mcpTool.description || t('mcpDialog.noDescription')}
                            </div>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                </ScrollArea>
              ) : (
                <div className="text-center text-muted-foreground py-4">
                  {t('mcpDialog.noToolsAvailable')}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {tCommon('cancel')}
          </Button>
          <Button onClick={handleSave} disabled={isLoading || !canSave}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEditing ? tCommon('save') : tCommon('create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
