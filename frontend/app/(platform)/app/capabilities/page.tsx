'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Wrench, Plus, RefreshCw, Loader2, Globe, Code, Plug, ChevronDown, PackageOpen, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  toolsApi,
  teamsApi,
  type Tool,
  type ToolDetail,
  type ToolCreateInput,
  type ToolUpdateInput,
  type UserTeamInfo,
} from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { useRequireTeam } from '@/hooks/use-require-team'
import { toolConnectionsApi } from '@/lib/api/tool-connections'
import { SkillsPanel, ToolList, ToolTestPanel } from './_components'
import { ToolConnectionDialog } from '@/components/tools/tool-connection-dialog'
import { HttpToolDialog } from './_components/http-tool-dialog'
import { McpToolDialog } from './_components/mcp-tool-dialog'
import { McpToolBrowser } from '@/components/tools/mcp-tool-browser'
import { ToolShareDialog } from './_components/tool-share-dialog'
import { ImportPackageDialog } from '@/components/packages/import-package-dialog'
import { useCanPerform } from '@/components/permission-guard'
import { usePermissions } from '@/hooks/use-permissions'

type CapabilityTab = 'tools' | 'skills'

export default function CapabilitiesPage() {
  const t = useTranslations('platform')
  const tCommon = useTranslations('common')
  const packagesT = useTranslations('packages')
  const { currentTeam } = useTeam()
  const { user } = usePermissions()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { canPerform } = useCanPerform()
  const canReadTools = canPerform('tool:read')
  const canReadSkills = canPerform('skill:read')
  const isTeamAdmin = Boolean(user?.is_superuser || currentTeam?.role === 'owner' || currentTeam?.role === 'admin')
  const canCreateTool = canPerform('tool:create')
  const canEditTool = (tool: Tool) =>
    Boolean(tool.is_owned !== false && (isTeamAdmin || tool.created_by_id === user?.id))
  const canConfigureTool = () => isTeamAdmin
  const canShareTool = () => isTeamAdmin
  const canDeleteTool = () => isTeamAdmin

  // 没有团队时重定向到首页
  useRequireTeam()

  const [activeTab, setActiveTab] = useState<CapabilityTab>('tools')
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [testPanelOpen, setTestPanelOpen] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)

  // Config dialog (for builtin tools)
  const [configDialogOpen, setConfigDialogOpen] = useState(false)
  const [configuringTool, setConfiguringTool] = useState<Tool | null>(null)
  // Builtin name -> whether usable connection state currently exists. Only
  // tools with a successful lookup appear here; absence means "no evidence".
  const [configuredBuiltins, setConfiguredBuiltins] = useState<Record<string, boolean>>({})

  // HTTP tool dialog
  const [httpDialogOpen, setHttpDialogOpen] = useState(false)
  const [editingHttpTool, setEditingHttpTool] = useState<ToolDetail | null>(null)
  const [mcpDialogOpen, setMcpDialogOpen] = useState(false)
  const [editingMcpTool, setEditingMcpTool] = useState<ToolDetail | null>(null)
  const [browsingMcpTool, setBrowsingMcpTool] = useState<Tool | null>(null)

  // Delete state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deletingTool, setDeletingTool] = useState<Tool | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  // Share state
  const [shareDialogOpen, setShareDialogOpen] = useState(false)
  const [sharingTool, setSharingTool] = useState<Tool | null>(null)
  const [availableTeams, setAvailableTeams] = useState<UserTeamInfo[]>([])

  useEffect(() => {
    const tab = searchParams.get('tab')
    const requestedTab: CapabilityTab = tab === 'skills' ? 'skills' : 'tools'
    const fallbackTab: CapabilityTab = canReadTools ? 'tools' : 'skills'
    setActiveTab(requestedTab === 'skills' && canReadSkills ? 'skills' : fallbackTab)

    // Auto-open create dialog when navigated with ?action=create
    const actionParam = searchParams.get('action')
    if (actionParam === 'create') {
      setHttpDialogOpen(true)
      // Clear URL params to avoid re-opening on refresh
      const params = new URLSearchParams(searchParams.toString())
      params.delete('action')
      const queryString = params.toString()
      router.replace(window.location.pathname + (queryString ? `?${queryString}` : ''), { scroll: false })
    }
  }, [searchParams, canReadTools, canReadSkills, router])

  const handleTabChange = (value: string) => {
    const fallbackTab: CapabilityTab = canReadTools ? 'tools' : 'skills'
    const nextTab: CapabilityTab = value === 'skills' && canReadSkills ? 'skills' : fallbackTab
    setActiveTab(nextTab)
    router.replace(nextTab === 'tools' ? '/app/capabilities' : '/app/capabilities?tab=skills', { scroll: false })
  }

  // 加载用户的团队列表
  useEffect(() => {
    const loadTeams = async () => {
      try {
        const teams = await teamsApi.getMyTeams()
        setAvailableTeams(teams)
      } catch (error) {
        console.error('Failed to load teams:', error)
      }
    }
    loadTeams()
  }, [])

  // 加载工具列表
  const loadTools = useCallback(async () => {
    if (!currentTeam?.id || !canReadTools) {
      setLoading(false)
      return
    }

    setLoading(true)
    try {
      const response = await toolsApi.list(currentTeam.id)
      // 合并所有类型的工具
      const allTools = [...response.builtin, ...response.custom, ...response.mcp]
      setTools(allTools)

      const connectionAware = allTools.filter(
        (tool) =>
          tool.type === 'builtin' &&
          (tool.requires_config ||
            (tool.identity_policy && tool.identity_policy !== 'none'))
      )

      // A builtin only shows "configured" when connection state proves it.
      // One team-scoped list covers both binding forms a materialized builtin
      // can have (stable definition id or builtin key); failed lookups leave
      // no evidence so the card never claims unverified state.
      try {
        const connections = await toolConnectionsApi.list(currentTeam.id)
        const activeConnections = connections.filter(
          (connection) => connection.status === 'active'
        )
        setConfiguredBuiltins(
          Object.fromEntries(
            connectionAware.map((tool): [string, boolean] => [
              tool.name,
              activeConnections.some(
                (connection) =>
                  (tool.id !== undefined && connection.tool_id === tool.id) ||
                  connection.builtin_tool_key === tool.name
              ),
            ])
          )
        )
      } catch (error) {
        console.error('Failed to load tool connection state:', error)
        setConfiguredBuiltins({})
      }
    } catch (error) {
      console.error('Failed to load tools:', error)
    } finally {
      setLoading(false)
    }
  }, [currentTeam?.id, canReadTools])

  useEffect(() => {
    loadTools()
  }, [loadTools])

  // 选择工具进行测试
  const handleSelectTool = (tool: Tool) => {
    setSelectedTool(tool)
    setTestPanelOpen(true)
  }

  // 配置内置工具
  const handleConfigureTool = (tool: Tool) => {
    setConfiguringTool(tool)
    setConfigDialogOpen(true)
  }

  // 编辑工具
  const handleEditTool = async (tool: Tool) => {
    if (!tool.id) {
      // 内置工具 - 打开连接管理弹窗
      if (tool.requires_config || (tool.identity_policy && tool.identity_policy !== 'none')) {
        handleConfigureTool(tool)
      }
      return
    }

    // 对于代码工具，可以直接跳转，不需要再获取详情
    if (tool.type === 'custom' && tool.custom_type === 'code') {
      router.push(`/app/capabilities/code?id=${tool.id}`)
      return
    }

    try {
      const detail = await toolsApi.getById(tool.id)

      if (detail.type === 'mcp') {
        setEditingMcpTool(detail)
        setMcpDialogOpen(true)
      } else if (detail.type === 'builtin') {
        if (detail.requires_config || (detail.identity_policy && detail.identity_policy !== 'none')) {
          handleConfigureTool(detail)
        }
      } else if (detail.type === 'custom') {
        if (detail.custom_type === 'http') {
          setEditingHttpTool(detail)
          setHttpDialogOpen(true)
        } else if (detail.custom_type === 'code') {
          // 代码工具跳转到独立页面
          router.push(`/app/capabilities/code?id=${tool.id}`)
        } else {
          // 未知的自定义工具类型，尝试根据配置判断
          if (detail.http_config && Object.keys(detail.http_config).length > 0) {
            setEditingHttpTool(detail)
            setHttpDialogOpen(true)
          } else if (detail.code_config && Object.keys(detail.code_config).length > 0) {
            router.push(`/app/capabilities/code?id=${tool.id}`)
          } else {
            toast.error(t('tools.error.unknownToolType'))
          }
        }
      }
    } catch (error) {
      console.error('Failed to load tool detail:', error)
      toast.error(t('tools.error.loadToolDetailFailed'))
    }
  }

  // 创建 HTTP 工具
  const handleCreateHttpTool = () => {
    setEditingHttpTool(null)
    setHttpDialogOpen(true)
  }

  // 创建 Code 工具
  const handleCreateCodeTool = () => {
    router.push('/app/capabilities/code')
  }

  // 创建 MCP 工具
  const handleCreateMcpTool = () => {
    setEditingMcpTool(null)
    setMcpDialogOpen(true)
  }

  // 保存 HTTP 工具
  const handleSaveHttpTool = async (data: ToolCreateInput | ToolUpdateInput) => {
    if (!currentTeam?.id) return

    try {
      if (editingHttpTool?.id) {
        await toolsApi.update(editingHttpTool.id, data as ToolUpdateInput)
        toast.success(t('tools.toolUpdated'))
      } else {
        await toolsApi.create(currentTeam.id, data as ToolCreateInput)
        toast.success(t('tools.toolCreated'))
      }
      setHttpDialogOpen(false)
      setEditingHttpTool(null)
      loadTools()
    } catch (error) {
      console.error('Failed to save tool:', error)
      throw error
    }
  }

  // 保存 MCP 工具
  const handleSaveMcpTool = async (data: ToolCreateInput | ToolUpdateInput) => {
    if (!currentTeam?.id) return

    try {
      if (editingMcpTool?.id) {
        await toolsApi.update(editingMcpTool.id, data as ToolUpdateInput)
        toast.success(t('tools.toolUpdated'))
      } else {
        await toolsApi.create(currentTeam.id, data as ToolCreateInput)
        toast.success(t('tools.toolCreated'))
      }
      setMcpDialogOpen(false)
      setEditingMcpTool(null)
      loadTools()
    } catch (error) {
      console.error('Failed to save tool:', error)
      throw error
    }
  }

  // 删除工具
  const handleDeleteClick = (tool: Tool) => {
    if (!tool.id) {
      toast.error(t('tools.error.cannotDeleteBuiltin'))
      return
    }
    setDeletingTool(tool)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    if (!deletingTool?.id) return

    setDeleteLoading(true)
    try {
      await toolsApi.delete(deletingTool.id)
      toast.success(t('tools.toolDeleted'))
      setDeleteDialogOpen(false)
      setDeletingTool(null)
      loadTools()
    } catch (error) {
      console.error('Failed to delete tool:', error)
    } finally {
      setDeleteLoading(false)
    }
  }

  // 共享工具
  const handleShareTool = (tool: Tool) => {
    if (!tool.id) {
      toast.error(t('tools.error.cannotShareBuiltin'))
      return
    }
    setSharingTool(tool)
    setShareDialogOpen(true)
  }

  const handleShareSuccess = () => {
    loadTools() // 重新加载工具列表以更新共享计数
  }

  return (
    <div className="py-6 px-8 h-full overflow-y-auto">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('tools.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('tools.description')}</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4" data-testid="capabilities-tabs">
        <TabsList>
          {canReadTools && (
            <TabsTrigger value="tools">
              <Wrench className="mr-2 h-4 w-4" />
              {t('tools.tabs.tools')}
            </TabsTrigger>
          )}
          {canReadSkills && (
            <TabsTrigger value="skills" data-testid="capabilities-skills-tab">
              <PackageOpen className="mr-2 h-4 w-4" />
              {t('tools.tabs.skills')}
            </TabsTrigger>
          )}
        </TabsList>

        {canReadTools && (
          <TabsContent value="tools" className="space-y-4" data-testid="capabilities-tools-panel">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">{t('tools.tabs.tools')}</h2>
              <p className="text-sm text-muted-foreground mt-1">{t('tools.description')}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={loadTools} disabled={loading} data-testid="capabilities-refresh-button">
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                {t('tools.refresh')}
              </Button>

              {canCreateTool && (
                <Button variant="outline" onClick={() => setImportDialogOpen(true)} data-testid="capabilities-import-button">
                  <Upload className="mr-2 h-4 w-4" />
                  {packagesT('import')}
                </Button>
              )}

              {canCreateTool && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button data-testid="capabilities-create-tool-button">
                        <Plus className="mr-2 h-4 w-4" />
                        {t('tools.createTool')}
                        <ChevronDown className="ml-2 h-4 w-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" className="w-56" data-testid="capabilities-create-tool-menu">
                    <DropdownMenuItem onClick={handleCreateHttpTool}>
                      <Globe className="mr-2 h-4 w-4" />
                      <div className="flex flex-col">
                        <span>{t('tools.createMenu.http')}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('tools.createMenu.httpDesc')}
                        </span>
                      </div>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleCreateCodeTool}>
                      <Code className="mr-2 h-4 w-4" />
                      <div className="flex flex-col">
                        <span>{t('tools.createMenu.code')}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('tools.createMenu.codeDesc')}
                        </span>
                      </div>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleCreateMcpTool}>
                      <Plug className="mr-2 h-4 w-4" />
                      <div className="flex flex-col">
                        <span>{t('tools.createMenu.mcp')}</span>
                        <span className="text-xs text-muted-foreground">
                          {t('tools.createMenu.mcpDesc')}
                        </span>
                      </div>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>


          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : tools.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Wrench className="h-12 w-12 text-muted-foreground mb-4" />
                <CardTitle className="mb-2">{t('tools.noTools')}</CardTitle>
                <CardDescription className="mb-4">
                  {t('tools.createToolHint')}
                </CardDescription>
                {canCreateTool && (
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button>
                          <Plus className="mr-2 h-4 w-4" />
                          {t('tools.createFirstTool')}
                        </Button>
                      }
                    />
                    <DropdownMenuContent align="center" className="w-56">
                      <DropdownMenuItem onClick={handleCreateHttpTool}>
                        <Globe className="mr-2 h-4 w-4" />
                        {t('tools.createMenu.http')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={handleCreateCodeTool}>
                        <Code className="mr-2 h-4 w-4" />
                        {t('tools.createMenu.code')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={handleCreateMcpTool}>
                        <Plug className="mr-2 h-4 w-4" />
                        {t('tools.createMenu.mcp')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </CardContent>
            </Card>
          ) : (
            <ToolList
              tools={tools}
              onSelect={canPerform('tool:execute') ? handleSelectTool : undefined}
              onTest={canPerform('tool:execute') ? handleSelectTool : undefined}
              onEdit={handleEditTool}
              onDelete={handleDeleteClick}
              onConfigure={handleConfigureTool}
              onBrowseMcp={canPerform('tool:execute') ? setBrowsingMcpTool : undefined}
              onShare={handleShareTool}
              canConfigure={canConfigureTool}
              canEdit={canEditTool}
              canShare={canShareTool}
              canDelete={canDeleteTool}
              configuredFor={(tool) =>
                tool.type === 'builtin' ? configuredBuiltins[tool.name] : undefined
              }
            />
          )}
        </TabsContent>
        )}

        {canReadSkills && (
          <TabsContent value="skills" className="space-y-4" data-testid="capabilities-skills-panel">
            <SkillsPanel />
          </TabsContent>
        )}
      </Tabs>

      <ImportPackageDialog
        open={importDialogOpen}
        onOpenChange={setImportDialogOpen}
        teamId={currentTeam?.id || ''}
        expectedResourceType="tool"
        onImported={() => loadTools()}
      />


      {/* 工具测试面板 */}
      <ToolTestPanel
        tool={selectedTool}
        open={testPanelOpen}
        onOpenChange={setTestPanelOpen}
        teamId={currentTeam?.id}
      />

      {/* 内置工具连接管理弹窗 */}
      <ToolConnectionDialog
        tool={configuringTool}
        teamId={currentTeam?.id}
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        onChanged={loadTools}
      />

      {/* HTTP 工具弹窗 */}
      <HttpToolDialog
        tool={editingHttpTool}
        open={httpDialogOpen}
        onOpenChange={setHttpDialogOpen}
        onSave={handleSaveHttpTool}
      />

      <McpToolDialog
        tool={editingMcpTool}
        open={mcpDialogOpen}
        onOpenChange={setMcpDialogOpen}
        onSave={handleSaveMcpTool}
      />
      <McpToolBrowser
        tool={browsingMcpTool}
        teamId={currentTeam?.id}
        open={!!browsingMcpTool}
        onOpenChange={(open) => { if (!open) setBrowsingMcpTool(null) }}
      />

      {/* 工具共享对话框 */}
      <ToolShareDialog
        tool={sharingTool}
        open={shareDialogOpen}
        onOpenChange={setShareDialogOpen}
        currentTeamId={currentTeam?.id || ''}
        availableTeams={availableTeams}
        onSuccess={handleShareSuccess}
      />

      {/* 删除确认对话框 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('tools.confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('tools.deleteToolConfirm', { name: deletingTool?.display_name ?? '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteLoading}>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleteLoading}
              variant="destructive"
            >
              {deleteLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {tCommon('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
