'use client'

import * as React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { useRouter, useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import {
  AppWindow,
  Plus,
  Sparkles,
  GitBranch,
  MoreHorizontal,
  Trash2,
  Copy,
  Send,
  FileEdit,
  MessageSquare,
  Loader2,
  Upload,
  Download,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardTitle,
} from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
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
import { agentsApi, type AgentListItem } from '@/lib/api/agents'
import { workflowsApi, type WorkflowListItem } from '@/lib/api/workflows'
import { useTeam } from '@/contexts/team-context'
import { useRequireTeam } from '@/hooks/use-require-team'
import { usePermissions } from '@/hooks/use-permissions'
import { AppCreateDialog } from './_components/app-create-dialog'
import { useCanPerform } from '@/components/permission-guard'
import { ImportPackageDialog } from '@/components/packages/import-package-dialog'
import { downloadBlob, packagesApi, type ClouisleResourceType } from '@/lib/api/packages'

type AppType = 'all' | 'agent' | 'workflow'

// Unified app item type for display
interface AppItem {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  status: 'draft' | 'published'
  type: 'agent' | 'workflow'
  // Agent-specific
  conversation_count?: number
  message_count?: number
  // Workflow-specific
  run_count?: number
  success_count?: number
  fail_count?: number
  created_at: string
  updated_at: string
  created_by_id?: string | null
  created_by_name?: string | null
}

export default function AppsPage() {
  const t = useTranslations('apps')
  const packageT = useTranslations('packages')
  const tCommon = useTranslations('common')
  const { currentTeam } = useTeam()
  const { user } = usePermissions()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { canPerform } = useCanPerform()

  // 没有团队时重定向到首页
  useRequireTeam()

  const [activeTab, setActiveTab] = React.useState<AppType>('all')
  const [searchQuery, setSearchQuery] = React.useState('')
  const [apps, setApps] = React.useState<AppItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [createDialogOpen, setCreateDialogOpen] = React.useState(false)
  const [initialCreateType, setInitialCreateType] = React.useState<'agent' | 'workflow'>('agent')
  const [importDialogOpen, setImportDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingApp, setDeletingApp] = React.useState<AppItem | null>(null)

  // Initialize activeTab from URL parameter after mount
  React.useEffect(() => {
    const tabParam = searchParams.get('tab')
    if (tabParam === 'agent' || tabParam === 'workflow') {
      setActiveTab(tabParam)
    }

    // Auto-open create dialog when navigated with ?action=create
    const actionParam = searchParams.get('action')
    if (actionParam === 'create') {
      const typeParam = searchParams.get('type')
      if (typeParam === 'agent' || typeParam === 'workflow') {
        setInitialCreateType(typeParam)
      }
      setCreateDialogOpen(true)
      // Clear URL params to avoid re-opening on refresh
      const params = new URLSearchParams(searchParams.toString())
      params.delete('action')
      params.delete('type')
      const queryString = params.toString()
      router.replace(window.location.pathname + (queryString ? `?${queryString}` : ''), { scroll: false })
    }
  }, [searchParams, router])

  // Fetch all apps (agents + workflows)
  const fetchApps = React.useCallback(async () => {
    if (!currentTeam) return
    setIsLoading(true)
    try {
      // Fetch agents and workflows in parallel
      const [agentsData, workflowsData] = await Promise.all([
        agentsApi.getAgents({ 
          search: searchQuery || undefined,
          teamId: currentTeam.id,
        }),
        workflowsApi.getWorkflows({ 
          keyword: searchQuery || undefined,
          teamId: currentTeam.id,
        }),
      ])
      
      // Transform agents to unified format
      const agentItems: AppItem[] = agentsData.items.map((agent: AgentListItem) => ({
        id: agent.id,
        name: agent.name,
        description: agent.description,
        icon: agent.icon,
        status: agent.status,
        type: 'agent' as const,
        conversation_count: agent.conversation_count,
        message_count: agent.message_count,
        created_at: agent.created_at,
        updated_at: agent.updated_at,
        created_by_id: agent.created_by?.id ?? null,
        created_by_name: agent.created_by?.username ?? null,
      }))
      
      // Transform workflows to unified format
      const workflowItems: AppItem[] = workflowsData.items.map((workflow: WorkflowListItem) => ({
        id: workflow.id,
        name: workflow.name,
        description: workflow.description,
        icon: workflow.icon,
        status: workflow.status,
        type: 'workflow' as const,
        run_count: workflow.run_count,
        success_count: workflow.success_count,
        fail_count: workflow.fail_count,
        created_at: workflow.created_at,
        updated_at: workflow.updated_at,
        created_by_id: workflow.created_by_id ?? null,
        created_by_name: workflow.created_by_name ?? null,
      }))
      
      // Combine and sort by updated_at
      const allApps = [...agentItems, ...workflowItems].sort(
        (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
      )
      
      setApps(allApps)
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam, searchQuery])

  React.useEffect(() => {
    fetchApps()
  }, [fetchApps])

  // Filter apps by type
  const filteredApps = React.useMemo(() => {
    if (activeTab === 'all') return apps
    return apps.filter(app => app.type === activeTab)
  }, [apps, activeTab])

  // Handle delete
  const handleDelete = async () => {
    if (!deletingApp) return
    try {
      if (deletingApp.type === 'agent') {
        await agentsApi.deleteAgent(deletingApp.id)
      } else {
        await workflowsApi.deleteWorkflow(deletingApp.id)
      }
      toast.success(t('appDeleted'))
      setDeleteDialogOpen(false)
      setDeletingApp(null)
      fetchApps()
    } catch {
      // toast handled by API interceptor
    }
  }

  // Handle duplicate
  const handleDuplicate = async (app: AppItem) => {
    try {
      if (app.type === 'agent') {
        await agentsApi.duplicateAgent(app.id)
      } else {
        await workflowsApi.duplicateWorkflow(app.id)
      }
      toast.success(t('appDuplicated'))
      fetchApps()
    } catch {
      // toast handled by API interceptor
    }
  }

  const handleExport = async (app: AppItem) => {
    try {
      const { blob, filename } = await packagesApi.export(app.type, app.id)
      downloadBlob(blob, filename)
    } catch {
      // toast handled by API interceptor
    }
  }

  // Handle publish/unpublish
  const handleTogglePublish = async (app: AppItem) => {
    try {
      if (app.type === 'agent') {
        if (app.status === 'published') {
          await agentsApi.unpublishAgent(app.id)
        } else {
          await agentsApi.publishAgent(app.id)
        }
      } else {
        if (app.status === 'published') {
          await workflowsApi.unpublishWorkflow(app.id)
        } else {
          await workflowsApi.publishWorkflow(app.id)
        }
      }
      toast.success(app.status === 'published' ? t('appUnpublished') : t('appPublished'))
      fetchApps()
    } catch {
      // toast handled by API interceptor
    }
  }

  // Get app icon based on type
  const getAppIcon = (type: 'agent' | 'workflow') => {
    if (type === 'agent') return Sparkles
    return GitBranch
  }

  // Get app link
  const getAppLink = (app: AppItem) => {
    if (app.type === 'agent') return `/app/apps/${app.id}`
    return `/app/apps/workflow/${app.id}`
  }

  // Handle tab change and update URL
  const handleTabChange = (value: string) => {
    const newTab = value as AppType
    setActiveTab(newTab)
    router.push(`?tab=${newTab}`, { scroll: false })
  }

  const expectedImportType: ClouisleResourceType | undefined = activeTab === 'agent' || activeTab === 'workflow' ? activeTab : undefined
  const isTeamAdmin = Boolean(user?.is_superuser || currentTeam?.role === 'owner' || currentTeam?.role === 'admin')
  const canCreateAgent = isTeamAdmin || canPerform('agent:create')
  const canCreateWorkflow = isTeamAdmin || canPerform('workflow:create')
  const canCreateApp = canCreateAgent || canCreateWorkflow
  const isAppOwner = (app: AppItem) => Boolean(user?.id && app.created_by_id === user.id)
  const canEditApp = (app: AppItem) => isTeamAdmin || isAppOwner(app)
  const canDuplicateApp = (app: AppItem) => app.type === 'agent' ? canCreateAgent : canCreateWorkflow
  const canExportApp = (app: AppItem) => isTeamAdmin || isAppOwner(app)
  const canPublishApp = () => isTeamAdmin
  const canDeleteApp = () => isTeamAdmin

  return (
    <div className="py-6 px-8 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          {currentTeam && canCreateApp && (
            <Button variant="outline" onClick={() => setImportDialogOpen(true)}>
              <Upload className="mr-2 h-4 w-4" />
              {packageT('import')}
            </Button>
          )}
          {canCreateApp && (
            <Button data-testid="apps-create-button" onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createApp')}
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6" suppressHydrationWarning>
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList>
            <TabsTrigger value="all">{t('tabs.all')}</TabsTrigger>
            <TabsTrigger value="agent">
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              {t('tabs.agent')}
            </TabsTrigger>
            <TabsTrigger value="workflow">
              <GitBranch className="mr-1 h-3.5 w-3.5" />
              {t('tabs.workflow')}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <Input
          placeholder={t('searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : filteredApps.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AppWindow className="h-12 w-12 text-muted-foreground mb-4" />
            <CardTitle className="mb-2">{t('noApps')}</CardTitle>
            <CardDescription className="mb-4">{t('noAppsHint')}</CardDescription>
            {canCreateApp && (
              <Button onClick={() => setCreateDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                {t('createFirstApp')}
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div data-testid="apps-grid" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filteredApps.map((app) => {
            const AppIcon = getAppIcon(app.type)
            // Check if icon is a URL or emoji
            const isIconUrl = app.icon && (app.icon.startsWith('http') || app.icon.startsWith('/'))
            return (
              <Card key={app.id} size="sm" className="group relative hover:shadow-md transition-shadow py-0! h-36" data-testid={`app-card-${app.id}`}>
                <Link href={getAppLink(app)} className="flex flex-col justify-between px-2.5 py-3 h-full">
                  {/* Header */}
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary relative overflow-hidden">
                      {app.icon ? (
                        isIconUrl ? (
                          <Image
                            src={app.icon}
                            alt={app.name}
                            fill
                            unoptimized
                            className="object-cover"
                          />
                        ) : (
                          <span className="flex h-full w-full items-center justify-center leading-none text-base">{app.icon}</span>
                        )
                      ) : (
                        <AppIcon className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-medium truncate">
                        {app.name}
                      </h3>
                      {app.created_by_name && (
                        <p className="text-xs text-muted-foreground truncate">
                          {tCommon('createdBy')}：{app.created_by_name}
                        </p>
                      )}
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Badge
                          variant={app.status === 'published' ? 'default' : 'secondary'}
                          className="text-[10px] px-1.5 py-0"
                        >
                          {app.status === 'published' ? t('published') : t('draft')}
                        </Badge>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {app.type === 'agent' ? (
                            <>
                              <Sparkles className="mr-0.5 h-2.5 w-2.5" />
                              Agent
                            </>
                          ) : (
                            <>
                              <GitBranch className="mr-0.5 h-2.5 w-2.5" />
                              Workflow
                            </>
                          )}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                    {app.description || t('noDescription')}
                  </p>

                  {/* Stats */}
                  <div className="flex items-center gap-3 text-xs text-muted-foreground border-t pt-1.5">
                    {app.type === 'agent' ? (
                      <>
                        <span>{app.conversation_count || 0} {t('conversations')}</span>
                        <span>{app.message_count || 0} {t('messages')}</span>
                      </>
                    ) : (
                      <>
                        <span>{app.run_count || 0} {t('runs')}</span>
                        <span className="text-green-600">{app.success_count || 0} {t('success')}</span>
                        {(app.fail_count || 0) > 0 && (
                          <span className="text-red-600">{app.fail_count} {t('failed')}</span>
                        )}
                      </>
                    )}
                  </div>
                </Link>

                {/* Actions */}
                <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={(props) => (
                        <Button {...props} variant="ghost" size="icon" className="h-7 w-7" data-testid={`app-actions-button-${app.id}`}>
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      )}
                    />
                    <DropdownMenuContent align="end">
                      {canEditApp(app) && (
                        <Link href={getAppLink(app)}>
                          <DropdownMenuItem>
                            <FileEdit className="mr-2 h-4 w-4" />
                            {t('configure')}
                          </DropdownMenuItem>
                        </Link>
                      )}
                      {app.type === 'agent' && (
                        <Link href={`/chat/${app.id}`} target="_blank">
                          <DropdownMenuItem data-testid={`app-chat-button-${app.id}`}>
                            <MessageSquare className="mr-2 h-4 w-4" />
                            {t('chat')}
                          </DropdownMenuItem>
                        </Link>
                      )}
                      {app.type === 'workflow' && (
                        <Link href={`/run/${app.id}?type=workflow`} target="_blank">
                          <DropdownMenuItem>
                            <MessageSquare className="mr-2 h-4 w-4" />
                            {t('run')}
                          </DropdownMenuItem>
                        </Link>
                      )}
                      {canPublishApp() && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={(e) => {
                            e.preventDefault()
                            handleTogglePublish(app)
                          }}>
                            <Send className="mr-2 h-4 w-4" />
                            {app.status === 'published' ? t('unpublish') : t('publish')}
                          </DropdownMenuItem>
                        </>
                      )}
                      {canDuplicateApp(app) && (
                        <DropdownMenuItem onClick={(e) => {
                          e.preventDefault()
                          handleDuplicate(app)
                        }}>
                          <Copy className="mr-2 h-4 w-4" />
                          {t('duplicate')}
                        </DropdownMenuItem>
                      )}
                      {canExportApp(app) && (
                        <DropdownMenuItem onClick={(e) => {
                          e.preventDefault()
                          handleExport(app)
                        }}>
                          <Download className="mr-2 h-4 w-4" />
                          {packageT('export')}
                        </DropdownMenuItem>
                      )}
                      {canDeleteApp() && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={(e) => {
                              e.preventDefault()
                              setDeletingApp(app)
                              setDeleteDialogOpen(true)
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {tCommon('delete')}
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create Dialog */}
      <AppCreateDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        initialType={initialCreateType}
        onSuccess={() => {
          setCreateDialogOpen(false)
          fetchApps()
        }}
      />

      {currentTeam && (
        <ImportPackageDialog
          open={importDialogOpen}
          onOpenChange={setImportDialogOpen}
          teamId={currentTeam.id}
          expectedResourceType={expectedImportType}
          onImported={fetchApps}
        />
      )}

      {/* Delete Confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteConfirmMessage', { name: deletingApp?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDelete}>
              {tCommon('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
