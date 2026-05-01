'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { Wrench, Plus, RefreshCw, Loader2, Globe, Code, Plug, ChevronDown, PackageOpen } from 'lucide-react'
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
  Tool,
  ToolDetail,
  ToolCreateInput,
  ToolUpdateInput,
  type UserTeamInfo,
} from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { useRequireTeam } from '@/hooks/use-require-team'
import { SkillsPanel, ToolList, ToolTestPanel } from './_components'
import { ToolConfigDialog } from './_components/tool-config-dialog'
import { HttpToolDialog } from './_components/http-tool-dialog'
import { McpToolDialog } from './_components/mcp-tool-dialog'
import { ToolShareDialog } from './_components/tool-share-dialog'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

type ToolsTab = 'tools' | 'skills'

export default function ToolsPage() {
  const t = useTranslations('platform')
  const tCommon = useTranslations('common')
  const locale = useLocale()
  const { currentTeam } = useTeam()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { canPerform } = useCanPerform()

  // 没有团队时重定向到首页
  useRequireTeam()

  const [activeTab, setActiveTab] = useState<ToolsTab>('tools')
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [testPanelOpen, setTestPanelOpen] = useState(false)

  // Config dialog (for builtin tools)
  const [configDialogOpen, setConfigDialogOpen] = useState(false)
  const [configuringTool, setConfiguringTool] = useState<Tool | null>(null)

  // HTTP tool dialog
  const [httpDialogOpen, setHttpDialogOpen] = useState(false)
  const [editingHttpTool, setEditingHttpTool] = useState<ToolDetail | null>(null)

  // MCP tool dialog
  const [mcpDialogOpen, setMcpDialogOpen] = useState(false)
  const [editingMcpTool, setEditingMcpTool] = useState<ToolDetail | null>(null)

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
    setActiveTab(tab === 'skills' ? 'skills' : 'tools')
  }, [searchParams])

  const handleTabChange = (value: string) => {
    const nextTab: ToolsTab = value === 'skills' ? 'skills' : 'tools'
    setActiveTab(nextTab)
    router.replace(nextTab === 'tools' ? '/app/tools' : '/app/tools?tab=skills', { scroll: false })
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
    if (!currentTeam?.id) return

    setLoading(true)
    try {
      const response = await toolsApi.list(currentTeam.id)
      // 合并所有类型的工具
      const allTools = [...response.builtin, ...response.custom, ...response.mcp]
      setTools(allTools)
    } catch (error) {
      console.error('Failed to load tools:', error)
    } finally {
      setLoading(false)
    }
  }, [currentTeam?.id, locale])

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
      // 内置工具 - 打开配置弹窗
      if (tool.requires_config) {
        handleConfigureTool(tool)
      }
      return
    }

    // 对于代码工具，可以直接跳转，不需要再获取详情
    if (tool.type === 'custom' && tool.custom_type === 'code') {
      router.push(`/app/tools/code?id=${tool.id}`)
      return
    }

    try {
      const detail = await toolsApi.getById(tool.id)

      if (detail.type === 'mcp') {
        setEditingMcpTool(detail)
        setMcpDialogOpen(true)
      } else if (detail.type === 'custom') {
        if (detail.custom_type === 'http') {
          setEditingHttpTool(detail)
          setHttpDialogOpen(true)
        } else if (detail.custom_type === 'code') {
          // 代码工具跳转到独立页面
          router.push(`/app/tools/code?id=${tool.id}`)
        } else {
          // 未知的自定义工具类型，尝试根据配置判断
          if (detail.http_config && Object.keys(detail.http_config).length > 0) {
            setEditingHttpTool(detail)
            setHttpDialogOpen(true)
          } else if (detail.code_config && Object.keys(detail.code_config).length > 0) {
            router.push(`/app/tools/code?id=${tool.id}`)
          } else {
            toast.error(t('tools.error.unknownToolType'))
          }
        }
      }
    } catch (error) {
      console.error('Failed to load tool detail:', error)
    }
  }

  // 创建 HTTP 工具
  const handleCreateHttpTool = () => {
    setEditingHttpTool(null)
    setHttpDialogOpen(true)
  }

  // 创建 Code 工具
  const handleCreateCodeTool = () => {
    router.push('/app/tools/code')
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

  // 保存内置工具配置
  const handleSaveConfig = async (config: Record<string, string>) => {
    if (!currentTeam?.id || !configuringTool) return

    try {
      // 先尝试获取现有配置
      let configExists = false
      try {
        await toolsApi.getConfig(configuringTool.name, currentTeam.id)
        configExists = true
      } catch (error: unknown) {
        // 404 表示配置不存在，需要创建
        const apiError = error as { response?: { status?: number } }
        if (apiError?.response?.status !== 404) {
          throw error
        }
      }

      // 根据配置是否存在选择创建或更新
      if (configExists) {
        await toolsApi.updateConfig(configuringTool.name, config, currentTeam.id)
      } else {
        await toolsApi.createConfig(configuringTool.name, config, currentTeam.id)
      }

      toast.success(t('tools.configSaved'))
      setConfigDialogOpen(false)
    } catch (error) {
      console.error('Failed to save config:', error)
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
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">{t('tools.title')}</h1>
        <p className="text-muted-foreground mt-1">{t('tools.description')}</p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4">
        <TabsList>
          <TabsTrigger value="tools">
            <Wrench className="mr-2 h-4 w-4" />
            {t('tools.tabs.tools')}
          </TabsTrigger>
          <TabsTrigger value="skills">
            <PackageOpen className="mr-2 h-4 w-4" />
            {t('tools.tabs.skills')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="tools" className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">{t('tools.tabs.tools')}</h2>
              <p className="text-sm text-muted-foreground mt-1">{t('tools.description')}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadTools} disabled={loading}>
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                {t('tools.refresh')}
              </Button>

              <PermissionGuard permission="tool:create">
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button>
                        <Plus className="mr-2 h-4 w-4" />
                        {t('tools.createTool')}
                        <ChevronDown className="ml-2 h-4 w-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end" className="w-56">
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
              </PermissionGuard>
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
                <PermissionGuard permission="tool:create">
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
                </PermissionGuard>
              </CardContent>
            </Card>
          ) : (
            <ToolList
              tools={tools}
              onSelect={handleSelectTool}
              onTest={handleSelectTool}
              onEdit={canPerform('tool:update') ? handleEditTool : undefined}
              onDelete={canPerform('tool:delete') ? handleDeleteClick : undefined}
              onConfigure={canPerform('tool:update') ? handleConfigureTool : undefined}
              onShare={canPerform('tool:update') ? handleShareTool : undefined}
            />
          )}
        </TabsContent>

        <TabsContent value="skills" className="space-y-4">
          <SkillsPanel />
        </TabsContent>
      </Tabs>

      {/* 工具测试面板 */}
      <ToolTestPanel
        tool={selectedTool}
        open={testPanelOpen}
        onOpenChange={setTestPanelOpen}
      />

      {/* 内置工具配置弹窗 */}
      <ToolConfigDialog
        tool={configuringTool}
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        onSave={handleSaveConfig}
      />

      {/* HTTP 工具弹窗 */}
      <HttpToolDialog
        tool={editingHttpTool}
        open={httpDialogOpen}
        onOpenChange={setHttpDialogOpen}
        onSave={handleSaveHttpTool}
      />

      {/* MCP 工具弹窗 */}
      <McpToolDialog
        tool={editingMcpTool}
        open={mcpDialogOpen}
        onOpenChange={setMcpDialogOpen}
        onSave={handleSaveMcpTool}
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
