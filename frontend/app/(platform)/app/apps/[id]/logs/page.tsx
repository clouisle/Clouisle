'use client'

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { Search, Calendar, ArrowUpDown, MessageSquare, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, X } from 'lucide-react'
import { agentsApi, type Agent, type ConversationListItem, type ConversationWithMessages } from '@/lib/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
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
import { AgentSidebar } from '../_components/agent-sidebar'
import { ConversationDrawer } from './_components/conversation-drawer'

const PAGE_SIZE = 20

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

export default function LogsPage() {
  const t = useTranslations('agents.logs')
  const locale = useLocale()
  const router = useRouter()
  const params = useParams()
  const agentId = params.id as string

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [conversations, setConversations] = React.useState<ConversationListItem[]>([])
  const [totalConversations, setTotalConversations] = React.useState(0)
  const [currentPage, setCurrentPage] = React.useState(1)
  const [isLoadingConversations, setIsLoadingConversations] = React.useState(false)

  // Search and filter state
  const [searchQuery, setSearchQuery] = React.useState('')
  const [dateFilter, setDateFilter] = React.useState('all')
  const [sortBy, setSortBy] = React.useState('created_at')

  // Drawer state
  const [drawerOpen, setDrawerOpen] = React.useState(false)
  const [selectedConversation, setSelectedConversation] = React.useState<ConversationWithMessages | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = React.useState(false)

  // Delete dialog state
  const [deleteId, setDeleteId] = React.useState<string | null>(null)

  // Fetch agent data
  const fetchAgent = React.useCallback(async () => {
    if (!agentId) return

    try {
      setIsLoading(true)
      const data = await agentsApi.getAgent(agentId)
      setAgent(data)
    } catch {
      router.push('/app/apps')
    } finally {
      setIsLoading(false)
    }
  }, [agentId, router])

  // Fetch conversations
  const fetchConversations = React.useCallback(async (page: number = 1) => {
    if (!agentId) return

    try {
      setIsLoadingConversations(true)
      const result = await agentsApi.getAgentConversations(agentId, {
        page,
        pageSize: PAGE_SIZE,
      })
      setConversations(result.items)
      setTotalConversations(result.total)
      setCurrentPage(page)
    } catch {
      // Error handled by API client
    } finally {
      setIsLoadingConversations(false)
    }
  }, [agentId])

  // Fetch conversation detail
  const handleRowClick = async (conversationId: string) => {
    setDrawerOpen(true)
    setIsLoadingDetail(true)
    try {
      const data = await agentsApi.getConversation(conversationId)
      setSelectedConversation(data)
    } catch {
      // Error handled by API client
    } finally {
      setIsLoadingDetail(false)
    }
  }

  // Delete conversation
  const handleDeleteConversation = async () => {
    if (!deleteId) return

    try {
      await agentsApi.deleteConversation(deleteId)
      // Close drawer if deleted conversation was open
      if (selectedConversation?.id === deleteId) {
        setSelectedConversation(null)
        setDrawerOpen(false)
      }
      // Refresh the list to get accurate data
      await fetchConversations(currentPage)
    } catch {
      // Error handled by API client
    } finally {
      setDeleteId(null)
    }
  }

  React.useEffect(() => {
    fetchAgent()
  }, [fetchAgent])

  React.useEffect(() => {
    if (agent) {
      fetchConversations()
    }
  }, [agent, fetchConversations])

  // Filter conversations (client-side for now)
  const filteredConversations = React.useMemo(() => {
    let result = [...conversations]
    
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      result = result.filter((c) => 
        c.title?.toLowerCase().includes(query)
      )
    }
    
    // Date filter
    if (dateFilter !== 'all') {
      const now = new Date()
      const cutoff = new Date()
      switch (dateFilter) {
        case '7d':
          cutoff.setDate(now.getDate() - 7)
          break
        case '30d':
          cutoff.setDate(now.getDate() - 30)
          break
        case '90d':
          cutoff.setDate(now.getDate() - 90)
          break
      }
      result = result.filter((c) => new Date(c.created_at) >= cutoff)
    }
    
    return result
  }, [conversations, searchQuery, dateFilter])

  const totalPages = Math.ceil(totalConversations / PAGE_SIZE)

  if (isLoading || !agent) {
    return (
      <div className="h-screen flex">
        <div className="w-52 border-r p-4">
          <Skeleton className="h-10 w-full mb-4" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
          <Skeleton className="h-8 w-full mb-2" />
        </div>
        <div className="flex-1 p-6">
          <Skeleton className="h-10 w-64 mb-6" />
          <Skeleton className="h-96 rounded-lg" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left Sidebar - Agent Info & Navigation */}
      <AgentSidebar agent={agent} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="border-b px-6 py-4 shrink-0">
          <p className="text-sm text-muted-foreground">{t('description')}</p>
        </div>

        {/* Filters Bar */}
        <div className="px-6 py-4 border-b shrink-0">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Date Filter */}
            <Select value={dateFilter} onValueChange={(v) => v && setDateFilter(v)}>
              <SelectTrigger size="default" className="w-40">
                <Calendar className="h-4 w-4 mr-2 text-muted-foreground" />
                <SelectValue>
                  {dateFilter === 'all' && t('filters.allTime')}
                  {dateFilter === '7d' && t('filters.last7Days')}
                  {dateFilter === '30d' && t('filters.last30Days')}
                  {dateFilter === '90d' && t('filters.last90Days')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('filters.allTime')}</SelectItem>
                <SelectItem value="7d">{t('filters.last7Days')}</SelectItem>
                <SelectItem value="30d">{t('filters.last30Days')}</SelectItem>
                <SelectItem value="90d">{t('filters.last90Days')}</SelectItem>
              </SelectContent>
            </Select>

            {/* Search */}
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={t('searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-9"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Sort */}
            <Select value={sortBy} onValueChange={(v) => v && setSortBy(v)}>
              <SelectTrigger size="default" className="w-36">
                <ArrowUpDown className="h-4 w-4 mr-2 text-muted-foreground" />
                <SelectValue>
                  {sortBy === 'created_at' && t('sort.createdAt')}
                  {sortBy === 'updated_at' && t('sort.updatedAt')}
                  {sortBy === 'message_count' && t('sort.messageCount')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at">{t('sort.createdAt')}</SelectItem>
                <SelectItem value="updated_at">{t('sort.updatedAt')}</SelectItem>
                <SelectItem value="message_count">{t('sort.messageCount')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          {isLoadingConversations ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="flex-1 flex items-center justify-center py-16">
              <div className="text-center text-muted-foreground">
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>{searchQuery ? t('noSearchResults') : t('noConversations')}</p>
              </div>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('table.title')}</TableHead>
                    <TableHead>{t('table.messageCount')}</TableHead>
                    <TableHead>{t('table.updatedAt')}</TableHead>
                    <TableHead>{t('table.createdAt')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredConversations.map((conv) => (
                    <TableRow
                      key={conv.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleRowClick(conv.id)}
                    >
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <MessageSquare className="h-4 w-4 text-muted-foreground" />
                          <span className="font-medium truncate">
                            {conv.title || t('untitledConversation')}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>{conv.message_count}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(conv.updated_at, locale)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(conv.created_at, locale)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-6 py-3 border-t flex items-center justify-between shrink-0">
            <p className="text-sm text-muted-foreground">
              {t('pagination.showing', {
                from: (currentPage - 1) * PAGE_SIZE + 1,
                to: Math.min(currentPage * PAGE_SIZE, totalConversations),
                total: totalConversations,
              })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={currentPage === 1}
                onClick={() => fetchConversations(1)}
              >
                <ChevronsLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={currentPage === 1}
                onClick={() => fetchConversations(currentPage - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm text-muted-foreground px-2">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={currentPage === totalPages}
                onClick={() => fetchConversations(currentPage + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                disabled={currentPage === totalPages}
                onClick={() => fetchConversations(totalPages)}
              >
                <ChevronsRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Conversation Detail Drawer */}
      <ConversationDrawer
        conversation={selectedConversation}
        isLoading={isLoadingDetail}
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDeleteConversation}>
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
