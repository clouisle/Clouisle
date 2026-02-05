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
  MoreHorizontal,
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
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'
import { ConversationDrawer } from './conversation-drawer'
import { useCanPerform } from '@/components/permission-guard'

// Helper to format datetime
function formatDateTime(dateString: string, _locale: string): string {
  const d = new Date(dateString)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  return `${year}/${month}/${day} ${hour}:${minute}`
}

export function ConversationsTable() {
  const t = useTranslations('activities')
  const commonT = useTranslations('common')
  const locale = useLocale()
  const { canPerform } = useCanPerform()

  // State
  const [conversations, setConversations] = React.useState<AdminConversationListItem[]>([])
  const [total, setTotal] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [pageSize, setPageSize] = React.useState(20)
  const [loading, setLoading] = React.useState(true)
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set())
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [deletingIds, setDeletingIds] = React.useState<string[]>([])
  const [drawerOpen, setDrawerOpen] = React.useState(false)
  const [selectedConversation, setSelectedConversation] = React.useState<AdminConversationWithMessages | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false)

  // Filters
  const [search, setSearch] = React.useState('')
  const [teamFilter, setTeamFilter] = React.useState<string[]>([])
  const [agentFilter, setAgentFilter] = React.useState<string[]>([])
  const [userFilter, setUserFilter] = React.useState<string[]>([])
  const [untitledOnly, setUntitledOnly] = React.useState(false)

  // Filter options
  const [teams, setTeams] = React.useState<Team[]>([])
  const [agents, setAgents] = React.useState<AgentListItem[]>([])
  const [users, setUsers] = React.useState<User[]>([])

  // Load filter options
  React.useEffect(() => {
    const loadOptions = async () => {
      try {
        const [teamsData, agentsData, usersData] = await Promise.all([
          teamsApi.getTeams(1, 100),
          agentsApi.getAgents({ page: 1, pageSize: 100 }),
          usersApi.getUsers({ page: 1, pageSize: 100 }),
        ])
        setTeams(teamsData.items)
        setAgents(agentsData.items)
        setUsers(usersData.items)
      } catch (error) {
        console.error('Failed to load filter options:', error)
      }
    }

    loadOptions()
  }, [])

  // Load conversations
  const loadConversations = React.useCallback(async () => {
    try {
      setLoading(true)
      const data = await conversationsApi.listAll({
        page,
        pageSize,
        search: search || undefined,
        team_id: teamFilter.length > 0 ? teamFilter[0] : undefined,
        agent_id: agentFilter.length > 0 ? agentFilter[0] : undefined,
        user_id: userFilter.length > 0 ? userFilter[0] : undefined,
        untitled_only: untitledOnly || undefined,
      })
      setConversations(data.items)
      setTotal(data.total)
    } catch (error) {
      console.error('Failed to load conversations:', error)
      toast.error(t('loadError'))
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, search, teamFilter, agentFilter, userFilter, untitledOnly, t])

  React.useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // Selection handlers
  const toggleSelectAll = () => {
    if (selectedIds.size === conversations.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(conversations.map((c) => c.id)))
    }
  }

  const toggleSelect = (id: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedIds(newSelected)
  }

  // Delete handlers
  const handleDeleteClick = (ids: string[]) => {
    setDeletingIds(ids)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = async () => {
    try {
      await conversationsApi.batchDelete(deletingIds)
      toast.success(t('deleteSuccess'))
      setSelectedIds(new Set())
      // Close drawer if deleted conversation was open
      if (selectedConversation && deletingIds.includes(selectedConversation.id)) {
        setSelectedConversation(null)
        setDrawerOpen(false)
      }
      loadConversations()
    } catch (error) {
      console.error('Failed to delete conversations:', error)
      toast.error(t('deleteError'))
    } finally {
      setDeleteDialogOpen(false)
      setDeletingIds([])
    }
  }

  // View conversation
  const handleViewConversation = async (id: string) => {
    setDrawerOpen(true)
    setIsLoadingDetail(true)
    try {
      const data = await conversationsApi.getDetail(id)
      setSelectedConversation(data)
    } catch (error) {
      console.error('Failed to load conversation detail:', error)
      toast.error(t('loadError'))
    } finally {
      setIsLoadingDetail(false)
    }
  }

  // Reset filters
  const resetFilters = () => {
    setSearch('')
    setTeamFilter([])
    setAgentFilter([])
    setUserFilter([])
    setUntitledOnly(false)
    setPage(1)
  }

  const hasFilters = search || teamFilter.length > 0 || agentFilter.length > 0 || userFilter.length > 0 || untitledOnly

  const totalPages = Math.ceil(total / pageSize)

  return (
    <>
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 items-center gap-2">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('searchPlaceholder')}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                className="pl-8"
              />
            </div>

            {teams.length > 0 && (
              <DataTableFacetedFilter
                title={commonT('team')}
                options={teams.map((team) => ({ label: team.name, value: team.id }))}
                selectedValues={new Set(teamFilter)}
                onSelectionChange={(values) => {
                  setTeamFilter(Array.from(values))
                  setPage(1)
                }}
              />
            )}

            {agents.length > 0 && (
              <DataTableFacetedFilter
                title={t('agent')}
                options={agents.map((agent) => ({ label: agent.name, value: agent.id }))}
                selectedValues={new Set(agentFilter)}
                onSelectionChange={(values) => {
                  setAgentFilter(Array.from(values))
                  setPage(1)
                }}
              />
            )}

            {users.length > 0 && (
              <DataTableFacetedFilter
                title={t('user')}
                options={users.map((user) => ({ label: user.username, value: user.id }))}
                selectedValues={new Set(userFilter)}
                onSelectionChange={(values) => {
                  setUserFilter(Array.from(values))
                  setPage(1)
                }}
              />
            )}

            {hasFilters && (
              <Button variant="ghost" onClick={resetFilters} className="h-8 px-2 lg:px-3">
                {commonT('reset')}
                <X className="ml-2 h-4 w-4" />
              </Button>
            )}
          </div>

          {selectedIds.size > 0 && canPerform('conversation:delete') && (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleDeleteClick(Array.from(selectedIds))}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {t('deleteSelected', { count: selectedIds.size })}
            </Button>
          )}
        </div>

        {/* Table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">
                  <Checkbox
                    checked={conversations.length > 0 && selectedIds.size === conversations.length}
                    onCheckedChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead>{t('title')}</TableHead>
                <TableHead>{t('agent')}</TableHead>
                <TableHead>{t('user')}</TableHead>
                <TableHead>{t('messageCount')}</TableHead>
                <TableHead>{t('updatedAt')}</TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8">
                    {commonT('loading')}
                  </TableCell>
                </TableRow>
              ) : conversations.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                    {t('noConversations')}
                  </TableCell>
                </TableRow>
              ) : (
                conversations.map((conversation) => (
                  <TableRow
                    key={conversation.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleViewConversation(conversation.id)}
                  >
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selectedIds.has(conversation.id)}
                        onCheckedChange={() => toggleSelect(conversation.id)}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">
                          {conversation.title || t('untitled')}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{conversation.agent_name}</Badge>
                    </TableCell>
                    <TableCell>{conversation.user_name}</TableCell>
                    <TableCell>{conversation.message_count}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(conversation.updated_at, locale)}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          }
                        />
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleViewConversation(conversation.id)}>
                            {t('viewDetails')}
                          </DropdownMenuItem>
                          {canPerform('conversation:delete') && (
                            <DropdownMenuItem
                              onClick={() => handleDeleteClick([conversation.id])}
                              className="text-destructive"
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              {commonT('delete')}
                            </DropdownMenuItem>
                          )}
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
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteConfirmDescription', { count: deletingIds.length })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConfirm} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              {commonT('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Conversation Drawer */}
      <ConversationDrawer
        conversation={selectedConversation}
        isLoading={isLoadingDetail}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onDelete={(id) => {
          handleDeleteClick([id])
        }}
      />
    </>
  )
}
