'use client'

import * as React from 'react'
import { useRouter, useParams } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { Search, Calendar, ArrowUpDown, MessageSquare, Loader2, X } from 'lucide-react'
import { agentsApi, type Agent, type ConversationListItem, type ConversationWithMessages } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
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
import { useDebounce } from '@/hooks/use-debounce'
import { useInfiniteScroll } from '@/hooks/use-infinite-scroll'
import { AgentSidebar } from '../_components/agent-sidebar'
import { ConversationDrawer } from './_components/conversation-drawer'

const PAGE_SIZE = 20

function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

function getCreatedAfter(dateFilter: string): string | undefined {
  if (dateFilter === 'all') return undefined

  const cutoff = new Date()
  switch (dateFilter) {
    case '7d':
      cutoff.setDate(cutoff.getDate() - 7)
      break
    case '30d':
      cutoff.setDate(cutoff.getDate() - 30)
      break
    case '90d':
      cutoff.setDate(cutoff.getDate() - 90)
      break
    default:
      return undefined
  }
  return cutoff.toISOString()
}

export default function LogsPage() {
  const t = useTranslations('agents.logs')
  const tCommon = useTranslations('common')
  const locale = useLocale()
  const router = useRouter()
  const params = useParams()
  const agentId = params.id as string

  const [agent, setAgent] = React.useState<Agent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [conversations, setConversations] = React.useState<ConversationListItem[]>([])
  const [totalConversations, setTotalConversations] = React.useState(0)
  const [page, setPage] = React.useState(1)
  const [isLoadingConversations, setIsLoadingConversations] = React.useState(false)
  const [isLoadingMore, setIsLoadingMore] = React.useState(false)
  const [loadFailure, setLoadFailure] = React.useState<{ page: number; append: boolean } | null>(null)
  const requestIdRef = React.useRef(0)
  const inFlightRef = React.useRef(false)
  const loadedIdsRef = React.useRef<Set<string> | null>(null)

  // Search and filter state
  const [searchQuery, setSearchQuery] = React.useState('')
  const debouncedSearchQuery = useDebounce(searchQuery, 300)
  const [dateFilter, setDateFilter] = React.useState('all')
  const [sortBy, setSortBy] = React.useState<'created_at' | 'updated_at' | 'message_count'>('created_at')

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

  // Fetch conversations. Reset requests replace the list; load-more requests append.
  // Resets always supersede an in-flight request; appends and retries are single-flight.
  const fetchConversations = React.useCallback(async (targetPage: number, append: boolean = false) => {
    if (!agentId) return
    if (append && inFlightRef.current) return

    inFlightRef.current = true
    const requestId = ++requestIdRef.current
    if (append) {
      setIsLoadingMore(true)
    } else {
      setIsLoadingConversations(true)
      setLoadFailure(null)
      setConversations([])
      setTotalConversations(0)
      setPage(1)
      loadedIdsRef.current = new Set()
    }

    try {
      const search = debouncedSearchQuery.trim()
      const result = await agentsApi.getAgentConversations(agentId, {
        page: targetPage,
        pageSize: PAGE_SIZE,
        search: search || undefined,
        createdAfter: getCreatedAfter(dateFilter),
        sortBy,
      })
      if (requestId !== requestIdRef.current) return

      if (append) {
        const seen = (loadedIdsRef.current ??= new Set<string>())
        const fresh: ConversationListItem[] = []
        for (const conversation of result.items) {
          if (seen.has(conversation.id)) continue
          seen.add(conversation.id)
          fresh.push(conversation)
        }
        setConversations((previous) => [...previous, ...fresh])
        // An empty page with a stale total means the list has ended.
        setTotalConversations(fresh.length === 0 ? seen.size : result.total)
        setPage(targetPage)
      } else {
        const unique = dedupeById(result.items)
        loadedIdsRef.current = new Set(unique.map((conversation) => conversation.id))
        setConversations(unique)
        setTotalConversations(result.total)
        setPage(targetPage)
      }
      setLoadFailure(null)
    } catch {
      if (requestId !== requestIdRef.current) return
      setLoadFailure({ page: targetPage, append })
    } finally {
      if (requestId === requestIdRef.current) {
        inFlightRef.current = false
        setIsLoadingConversations(false)
        setIsLoadingMore(false)
      }
    }
  }, [agentId, debouncedSearchQuery, dateFilter, sortBy])

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
      await fetchConversations(1)
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
      void fetchConversations(1)
    }
    return () => {
      requestIdRef.current += 1
      inFlightRef.current = false
    }
  }, [agent, fetchConversations])

  const hasMore = !loadFailure && conversations.length < totalConversations

  const loadMore = React.useCallback(() => {
    if (isLoadingConversations || isLoadingMore || loadFailure) return
    if (conversations.length >= totalConversations) return
    return fetchConversations(page + 1, true)
  }, [conversations.length, fetchConversations, isLoadingConversations, isLoadingMore, loadFailure, page, totalConversations])

  const retryLoad = React.useCallback(() => {
    if (!loadFailure || inFlightRef.current) return
    const { page: failedPage, append } = loadFailure
    setLoadFailure(null)
    return fetchConversations(failedPage, append)
  }, [fetchConversations, loadFailure])

  const sentinelRef = useInfiniteScroll({
    hasMore,
    loading: isLoadingConversations || isLoadingMore,
    onLoadMore: loadMore,
  })

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
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
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
        <div className="flex-1 min-h-0 overflow-auto">
          {isLoadingConversations && conversations.length === 0 ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : loadFailure && conversations.length === 0 ? (
            <div className="flex-1 flex items-center justify-center py-16">
              <div className="text-center text-muted-foreground">
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>{tCommon('loadFailed')}</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={retryLoad}>
                  {tCommon('retry')}
                </Button>
              </div>
            </div>
          ) : conversations.length === 0 ? (
            <div className="flex-1 flex items-center justify-center py-16">
              <div className="text-center text-muted-foreground">
                <MessageSquare className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>{searchQuery ? t('noSearchResults') : t('noConversations')}</p>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('table.title')}</TableHead>
                  <TableHead>{t('table.conversationId')}</TableHead>
                  <TableHead>{t('table.messageCount')}</TableHead>
                  <TableHead>{t('table.updatedAt')}</TableHead>
                  <TableHead>{t('table.createdAt')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {conversations.map((conv) => (
                  <TableRow
                    key={conv.id}
                    className="group cursor-pointer hover:bg-muted/50"
                    onClick={() => handleRowClick(conv.id)}
                  >
                    <TableCell className="max-w-[300px]">
                      <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="font-medium truncate">
                          {conv.title || t('untitledConversation')}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Tooltip>
                        <TooltipTrigger
                          type="button"
                          className="font-mono text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRowClick(conv.id)
                          }}
                          render={<button />}
                        >
                          {conv.id.slice(0, 8)}…
                        </TooltipTrigger>
                        <TooltipContent>{`${t('table.conversationId')}: ${conv.id}`}</TooltipContent>
                      </Tooltip>
                    </TableCell>
                    <TableCell>{conv.message_count}</TableCell>
                    <TableCell className="text-muted-foreground" suppressHydrationWarning>
                      {formatDateTime(conv.updated_at, locale)}
                    </TableCell>
                    <TableCell className="text-muted-foreground" suppressHydrationWarning>
                      {formatDateTime(conv.created_at, locale)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {isLoadingMore && (
            <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{tCommon('loadingMore')}</span>
            </div>
          )}

          {loadFailure && conversations.length > 0 && !isLoadingMore && (
            <div className="flex items-center justify-center gap-3 py-4 text-sm text-muted-foreground">
              <span>{tCommon('loadFailed')}</span>
              <Button variant="outline" size="sm" onClick={retryLoad}>
                {tCommon('retry')}
              </Button>
            </div>
          )}

          <div ref={sentinelRef} aria-hidden className="h-px w-full" />
        </div>

        {/* Loaded range */}
        {totalConversations > 0 && (
          <div className="px-6 py-3 border-t shrink-0">
            <p className="text-sm text-muted-foreground">
              {t('pagination.showing', {
                from: conversations.length > 0 ? 1 : 0,
                to: conversations.length,
                total: totalConversations,
              })}
            </p>
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
