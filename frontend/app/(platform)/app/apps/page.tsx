'use client'

import * as React from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
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
import { useTeam } from '@/contexts/team-context'
import { AppCreateDialog } from './_components/app-create-dialog'

type AppType = 'all' | 'agent' | 'workflow'

export default function AppsPage() {
  const t = useTranslations('apps')
  const tCommon = useTranslations('common')
  const { currentTeam } = useTeam()
  
  const [activeTab, setActiveTab] = React.useState<AppType>('all')
  const [searchQuery, setSearchQuery] = React.useState('')
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [createDialogOpen, setCreateDialogOpen] = React.useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingAgent, setDeletingAgent] = React.useState<AgentListItem | null>(null)

  // Fetch agents
  const fetchAgents = React.useCallback(async () => {
    if (!currentTeam) return
    setIsLoading(true)
    try {
      const data = await agentsApi.getAgents({ search: searchQuery || undefined })
      setAgents(data.items)
    } catch {
      toast.error(t('loadFailed'))
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam, searchQuery, t])

  React.useEffect(() => {
    fetchAgents()
  }, [fetchAgents])

  // Filter apps by type
  const filteredApps = React.useMemo(() => {
    if (activeTab === 'all') return agents
    if (activeTab === 'agent') return agents // Agents
    // When we add workflows, filter them here
    return []
  }, [agents, activeTab])

  // Handle delete
  const handleDelete = async () => {
    if (!deletingAgent) return
    try {
      await agentsApi.deleteAgent(deletingAgent.id)
      toast.success(t('appDeleted'))
      setDeleteDialogOpen(false)
      setDeletingAgent(null)
      fetchAgents()
    } catch {
      toast.error(t('deleteFailed'))
    }
  }

  // Handle duplicate
  const handleDuplicate = async (agent: AgentListItem) => {
    try {
      await agentsApi.duplicateAgent(agent.id)
      toast.success(t('appDuplicated'))
      fetchAgents()
    } catch {
      toast.error(t('duplicateFailed'))
    }
  }

  // Handle publish/unpublish
  const handleTogglePublish = async (agent: AgentListItem) => {
    try {
      if (agent.status === 'published') {
        await agentsApi.unpublishAgent(agent.id)
        toast.success(t('appUnpublished'))
      } else {
        await agentsApi.publishAgent(agent.id)
        toast.success(t('appPublished'))
      }
      fetchAgents()
    } catch {
      toast.error(t('publishFailed'))
    }
  }

  // Get app icon based on type
  const getAppIcon = (type: 'agent' | 'workflow') => {
    if (type === 'agent') return Sparkles
    return GitBranch
  }

  return (
    <div className="py-6 px-8 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
          <p className="text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('createApp')}
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6">
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as AppType)}>
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
            <Button onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t('createFirstApp')}
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filteredApps.map((agent) => {
            const AppIcon = getAppIcon('agent')
            // Check if icon is a URL or emoji
            const isIconUrl = agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))
            return (
              <Card key={agent.id} size="sm" className="group relative hover:shadow-md transition-shadow py-0! h-36">
                <Link href={`/app/apps/${agent.id}`} className="flex flex-col justify-between px-2.5 py-3 h-full">
                  {/* Header */}
                  <div className="flex items-center gap-2">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary relative overflow-hidden">
                      {agent.icon ? (
                        isIconUrl ? (
                          <Image
                            src={agent.icon}
                            alt={agent.name}
                            fill
                            unoptimized
                            className="object-cover"
                          />
                        ) : (
                          <span className="text-base">{agent.icon}</span>
                        )
                      ) : (
                        <AppIcon className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-medium truncate">
                        {agent.name}
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <Badge
                          variant={agent.status === 'published' ? 'default' : 'secondary'}
                          className="text-[10px] px-1.5 py-0"
                        >
                          {agent.status === 'published' ? t('published') : t('draft')}
                        </Badge>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          <Sparkles className="mr-0.5 h-2.5 w-2.5" />
                          Agent
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                    {agent.description || t('noDescription')}
                  </p>

                  {/* Stats */}
                  <div className="flex items-center gap-3 text-xs text-muted-foreground border-t pt-1.5">
                    <span>{agent.conversation_count} {t('conversations')}</span>
                    <span>{agent.message_count} {t('messages')}</span>
                  </div>
                </Link>

                {/* Actions */}
                <div className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={(props) => (
                        <Button {...props} variant="ghost" size="icon" className="h-7 w-7">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      )}
                    />
                    <DropdownMenuContent align="end">
                      <Link href={`/app/apps/${agent.id}`}>
                        <DropdownMenuItem>
                          <FileEdit className="mr-2 h-4 w-4" />
                          {t('configure')}
                        </DropdownMenuItem>
                      </Link>
                      <Link href={`/app/apps/${agent.id}/chat`}>
                        <DropdownMenuItem>
                          <MessageSquare className="mr-2 h-4 w-4" />
                          {t('chat')}
                        </DropdownMenuItem>
                      </Link>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={(e) => {
                        e.preventDefault()
                        handleTogglePublish(agent)
                      }}>
                        <Send className="mr-2 h-4 w-4" />
                        {agent.status === 'published' ? t('unpublish') : t('publish')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => {
                        e.preventDefault()
                        handleDuplicate(agent)
                      }}>
                        <Copy className="mr-2 h-4 w-4" />
                        {t('duplicate')}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={(e) => {
                          e.preventDefault()
                          setDeletingAgent(agent)
                          setDeleteDialogOpen(true)
                        }}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {tCommon('delete')}
                      </DropdownMenuItem>
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
        onSuccess={() => {
          setCreateDialogOpen(false)
          fetchAgents()
        }}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('confirmDelete')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteConfirmMessage', { name: deletingAgent?.name || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {tCommon('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
