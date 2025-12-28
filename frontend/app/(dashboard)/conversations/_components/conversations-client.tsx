'use client'

import * as React from 'react'
import { useTranslations, useLocale } from 'next-intl'
import {
  Search,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  X,
  Trash2,
  Bot,
  MoreHorizontal,
  Users,
  User as UserIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  conversationsApi,
  teamsApi,
  agentsApi,
  usersApi,
  type AdminConversationListItem,
  type AdminConversationWithMessages,
  type Team,
  type AgentListItem,
  type ConversationStats,
} from '@/lib/api'
import type { User } from '@/lib/api/auth'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { ConversationDrawer } from './conversation-drawer'

// Helper to format datetime
function formatDateTime(dateString: string, locale: string): string {
  const date = new Date(dateString)
  if (locale === 'zh') {
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } else {
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
}

export function ConversationsClient() {
  const t = useTranslations('conversations')
  const commonT = useTranslations('common')
  const locale = useLocale()

  // Data state
  const [conversations, setConversations] = React.useState<AdminConversationListItem[]>([])
  const [totalConversations, setTotalConversations] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(20)
  const [isLoading, setIsLoading] = React.useState(true)
  const [stats, setStats] = React.useState<ConversationStats | null>(null)

  // Filter state
  const [teams, setTeams] = React.useState<Team[]>([])
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [users, setUsers] = React.useState<User[]>([])
  const [teamFilter, setTeamFilter] = React.useState<Set<string>>(new Set())
  const [agentFilter, setAgentFilter] = React.useState<Set<string>>(new Set())
  const [userFilter, setUserFilter] = React.useState<Set<string>>(new Set())
  const [titleFilter, setTitleFilter] = React.useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = React.useState('')
  const [debouncedSearch, setDebouncedSearch] = React.useState('')

  // Selection state
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set())

  // Drawer state
  const [drawerOpen, setDrawerOpen] = React.useState(false)
  const [selectedConversation, setSelectedConversation] = React.useState<AdminConversationWithMessages | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false)

  // Delete dialog state
  const [deleteId, setDeleteId] = React.useState<string | null>(null)
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false)

  // Debounce search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Fetch teams
  React.useEffect(() => {
    const fetchTeams = async () => {
      try {
        const result = await teamsApi.getTeams(1, 100)
        setTeams(result.items)
      } catch {
        // Ignore
      }
    }
    fetchTeams()
  }, [])

  // Fetch agents
  React.useEffect(() => {
    const fetchAgents = async () => {
      try {
        const result = await agentsApi.getAgents({
          page: 1,
          pageSize: 100,
        })
        setAgents(result.items)
      } catch {
        // Ignore
      }
    }
    fetchAgents()
  }, [])

  // Fetch users
  React.useEffect(() => {
    const fetchUsers = async () => {
      try {
        const result = await usersApi.getUsers({
          page: 1,
          pageSize: 100,
        })
        setUsers(result.items)
      } catch {
        // Ignore
      }
    }
    fetchUsers()
  }, [])

  // Fetch conversations
  const fetchConversations = React.useCallback(async () => {
    try {
      setIsLoading(true)
      const selectedTeamId = teamFilter.size === 1 ? Array.from(teamFilter)[0] : undefined
      const selectedAgentId = agentFilter.size === 1 ? Array.from(agentFilter)[0] : undefined
      const selectedUserId = userFilter.size === 1 ? Array.from(userFilter)[0] : undefined
      const untitledOnly = titleFilter.has('untitled')
      
      const result = await conversationsApi.listAll({
        page,
        pageSize,
        ...(selectedTeamId ? { team_id: selectedTeamId } : {}),
        ...(selectedAgentId ? { agent_id: selectedAgentId } : {}),
        ...(selectedUserId ? { user_id: selectedUserId } : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        ...(untitledOnly ? { untitled_only: true } : {}),
      })
      setConversations(result.items)
      setTotalConversations(result.total)
      setSelectedIds(new Set())
    } catch {
      toast.error(t('fetchError'))
    } finally {
      setIsLoading(false)
    }
  }, [teamFilter, agentFilter, userFilter, titleFilter, debouncedSearch, page, pageSize, t])

  // Fetch stats
  const fetchStats = React.useCallback(async () => {
    try {
      const selectedTeamId = teamFilter.size === 1 ? Array.from(teamFilter)[0] : undefined
      const data = await conversationsApi.getStats(selectedTeamId)
      setStats(data)
    } catch {
      // Ignore stats errors
    }
  }, [teamFilter])

  // Initial load and filter changes
  React.useEffect(() => {
    fetchConversations()
  }, [fetchConversations])

  React.useEffect(() => {
    fetchStats()
  }, [fetchStats])

  // Handle row click
  const handleRowClick = async (conversationId: string) => {
    setDrawerOpen(true)
    setIsLoadingDetail(true)
    try {
      const data = await conversationsApi.getDetail(conversationId)
      setSelectedConversation(data)
    } catch {
      toast.error(t('fetchDetailError'))
    } finally {
      setIsLoadingDetail(false)
    }
  }

  // Handle single delete
  const handleDelete = async () => {
    if (!deleteId) return
    try {
      await conversationsApi.delete(deleteId)
      setConversations((prev) => prev.filter((c) => c.id !== deleteId))
      setTotalConversations((prev) => prev - 1)
      if (selectedConversation?.id === deleteId) {
        setSelectedConversation(null)
        setDrawerOpen(false)
      }
      toast.success(t('deleteSuccess'))
      fetchStats()
    } catch {
      toast.error(t('deleteError'))
    } finally {
      setDeleteId(null)
    }
  }

  // Handle bulk delete
  const handleBulkDelete = async () => {
    try {
      await conversationsApi.batchDelete(Array.from(selectedIds))
      setConversations((prev) => prev.filter((c) => !selectedIds.has(c.id)))
      setTotalConversations((prev) => prev - selectedIds.size)
      toast.success(t('batchDeleteSuccess', { count: selectedIds.size }))
      setSelectedIds(new Set())
      fetchStats()
    } catch {
      toast.error(t('deleteError'))
    } finally {
      setBulkDeleteDialogOpen(false)
    }
  }

  // Selection handlers
  const toggleSelectAll = () => {
    if (selectedIds.size === conversations.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(conversations.map((c) => c.id)))
    }
  }

  const toggleSelectOne = (id: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedIds(newSelected)
  }

  // Filter options
  const teamOptions = React.useMemo(() => {
    return teams.map((team) => ({
      value: team.id,
      label: team.name,
      icon: <Users className="h-4 w-4" />,
    }))
  }, [teams])

  const agentOptions = React.useMemo(() => {
    return agents.map((agent) => ({
      value: agent.id,
      label: agent.name,
      icon: agent.icon ? <img src={agent.icon} alt="" className="h-4 w-4 rounded object-cover" /> : <Bot className="h-4 w-4" />,
    }))
  }, [agents])

  const userOptions = React.useMemo(() => {
    return users.map((user) => ({
      value: user.id,
      label: user.username,
      icon: <UserIcon className="h-4 w-4" />,
    }))
  }, [users])

  const titleOptions = React.useMemo(() => {
    return [
      {
        value: 'untitled',
        label: t('filters.untitledOnly'),
        icon: <MessageSquare className="h-4 w-4" />,
      },
    ]
  }, [t])

  // Check if filtered
  const isFiltered = searchQuery || teamFilter.size > 0 || agentFilter.size > 0 || userFilter.size > 0 || titleFilter.size > 0

  // Reset filters
  const resetFilters = () => {
    setSearchQuery('')
    setTeamFilter(new Set())
    setAgentFilter(new Set())
    setUserFilter(new Set())
    setTitleFilter(new Set())
  }

  // Pagination
  const totalPages = Math.ceil(totalConversations / pageSize)

  return (
    <div className="flex flex-col gap-6">
      {/* Stats Summary */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">{t('stats.totalConversations')}</p>
            <p className="text-2xl font-bold">{stats.total_conversations}</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">{t('stats.totalMessages')}</p>
            <p className="text-2xl font-bold">{stats.total_messages}</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">{t('stats.avgMessagesPerConversation')}</p>
            <p className="text-2xl font-bold">
              {stats.total_conversations > 0 
                ? (stats.total_messages / stats.total_conversations).toFixed(1)
                : '0'}
            </p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">{t('stats.topAgent')}</p>
            <p className="text-lg font-semibold truncate">
              {stats.conversations_by_agent?.[0]?.agent_name || '-'}
            </p>
          </div>
        </div>
      )}

      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('title')}</h1>
          <p className="text-muted-foreground">{t('description')}</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-1 items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t('filters.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-50 h-9"
            />
          </div>

          <DataTableFacetedFilter
            title={t('filters.team')}
            options={teamOptions}
            selectedValues={teamFilter}
            onSelectionChange={(values) => {
              setTeamFilter(values)
              setAgentFilter(new Set())
            }}
            searchable
          />

          <DataTableFacetedFilter
            title={t('filters.agent')}
            options={agentOptions}
            selectedValues={agentFilter}
            onSelectionChange={setAgentFilter}
            searchable
          />

          <DataTableFacetedFilter
            title={t('filters.user')}
            options={userOptions}
            selectedValues={userFilter}
            onSelectionChange={setUserFilter}
            searchable
          />

          <DataTableFacetedFilter
            title={t('filters.title')}
            options={titleOptions}
            selectedValues={titleFilter}
            onSelectionChange={setTitleFilter}
          />

          {isFiltered && (
            <Button variant="ghost" onClick={resetFilters} className="h-9 px-2 lg:px-3">
              {commonT('reset')}
              <X className="ml-2 h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-10">
                <Checkbox
                  checked={selectedIds.size === conversations.length && conversations.length > 0}
                  onCheckedChange={toggleSelectAll}
                />
              </TableHead>
              <TableHead>{t('table.title')}</TableHead>
              <TableHead>{t('table.agent')}</TableHead>
              <TableHead>{t('table.user')}</TableHead>
              <TableHead className="text-center">{t('table.messages')}</TableHead>
              <TableHead>{t('table.updatedAt')}</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center">
                  {commonT('loading')}
                </TableCell>
              </TableRow>
            ) : conversations.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  <MessageSquare className="mx-auto h-8 w-8 mb-2 opacity-30" />
                  {debouncedSearch ? t('noSearchResults') : t('noConversations')}
                </TableCell>
              </TableRow>
            ) : (
              conversations.map((conv) => (
                <TableRow
                  key={conv.id}
                  className="cursor-pointer"
                  data-state={selectedIds.has(conv.id) ? 'selected' : undefined}
                  onClick={() => handleRowClick(conv.id)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(conv.id)}
                      onCheckedChange={() => toggleSelectOne(conv.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <span className="font-medium truncate block max-w-72">
                      {conv.title || t('untitled')}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      {conv.agent_icon && (
                        <img 
                          src={conv.agent_icon} 
                          alt="" 
                          className="h-5 w-5 rounded object-cover"
                        />
                      )}
                      <span className="truncate max-w-36">{conv.agent_name || '-'}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {conv.user_name || '-'}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="secondary">{conv.message_count}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDateTime(conv.updated_at, locale)}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger className="ring-offset-background focus-visible:ring-ring data-[state=open]:bg-accent inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">Open menu</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => setDeleteId(conv.id)}
                          className="text-destructive focus:text-destructive"
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          {commonT('delete')}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1) }}>
            <SelectTrigger size="sm" className="w-18">
              <SelectValue />
            </SelectTrigger>
            <SelectContent side="top" alignItemWithTrigger={false}>
              <SelectItem value="10">10</SelectItem>
              <SelectItem value="20">20</SelectItem>
              <SelectItem value="50">50</SelectItem>
              <SelectItem value="100">100</SelectItem>
            </SelectContent>
          </Select>
          <span>{t('rowsPerPage')}</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {t('pageInfo', { page, total: totalPages || 1 })}
          </span>

          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage(1)}
              disabled={page === 1}
            >
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8"
              onClick={() => setPage(totalPages)}
              disabled={page >= totalPages}
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Conversation Detail Drawer */}
      <ConversationDrawer
        conversation={selectedConversation}
        isLoading={isLoadingDetail}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onDelete={(id) => setDeleteId(id)}
      />

      {/* Floating Bulk Action Toolbar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-1 rounded-lg border bg-background px-2 py-1.5 shadow-lg">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setSelectedIds(new Set())}
            >
              <X className="h-4 w-4" />
            </Button>

            <Badge variant="secondary" className="px-2 py-1">
              {selectedIds.size} {t('selected')}
            </Badge>

            <Tooltip>
              <TooltipTrigger
                onClick={() => setBulkDeleteDialogOpen(true)}
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                }
              />
              <TooltipContent>{commonT('delete')}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      )}

      {/* Single Delete Dialog */}
      <AlertDialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Bulk Delete Dialog */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('batchDeleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('batchDeleteDescription', { count: selectedIds.size })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleBulkDelete}>
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
