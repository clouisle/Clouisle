'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Bell, MessageSquarePlus, MessageSquareText, Search } from 'lucide-react'
import { imApi, type ImConversation, type ImSearchResult } from '@/lib/api'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { cn, stripMarkdown } from '@/lib/utils'

interface ConversationListProps {
  teamId?: string
  conversations: ImConversation[]
  selectedId: string | null
  onSelect: (conv: ImConversation) => void
  onSelectSearchResult?: (result: ImSearchResult) => void
  onNewChat: () => void
  search: string
  onSearchChange: (val: string) => void
}

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ''
  const now = new Date()
  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  if (isSameDay) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function highlightMatch(text: string, query: string) {
  if (!query) return text
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'))
  return parts.map((part, i) =>
    part.toLowerCase() === query.toLowerCase() ? (
      <span key={i} className="text-primary font-semibold bg-primary/15 rounded-xs px-0.5">
        {part}
      </span>
    ) : (
      part
    )
  )
}

export function ConversationList({
  teamId,
  conversations,
  selectedId,
  onSelect,
  onSelectSearchResult,
  onNewChat,
  search,
  onSearchChange,
}: ConversationListProps) {
  const t = useTranslations('notifications.im')
  const [matchedMessages, setMatchedMessages] = React.useState<ImSearchResult[]>([])
  const [searchingMessages, setSearchingMessages] = React.useState(false)

  React.useEffect(() => {
    const q = search.trim()
    if (!q || !teamId) {
      setMatchedMessages([])
      setSearchingMessages(false)
      return
    }

    let active = true
    setSearchingMessages(true)
    // 立刻清空上一轮结果，避免新搜索请求期间旧结果仍可点击，失败时也不会残留
    setMatchedMessages([])
    const timer = setTimeout(() => {
      imApi
        .searchMessages(teamId, q)
        .then((res) => {
          if (active) setMatchedMessages(res)
        })
        .catch((err) => {
          console.error('Failed to search messages:', err)
        })
        .finally(() => {
          if (active) setSearchingMessages(false)
        })
    }, 250)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [search, teamId])

  const filtered = conversations.filter((conv) => {
    const q = search.trim().toLowerCase()
    if (!q) return true
    if (conv.type === 'system') {
      return t('systemNotifications').toLowerCase().includes(q)
    }
    if (conv.peer) {
      return (
        conv.peer.username.toLowerCase().includes(q) ||
        conv.peer.full_name.toLowerCase().includes(q)
      )
    }
    return false
  })

  return (
    <div className="flex h-full w-72 md:w-80 flex-col border-r bg-muted/20">
      {/* 头部搜索与新对话 */}
      <div className="flex h-14 shrink-0 items-center gap-2 px-3 border-b">
        <div className="relative flex-1">
          <Search className="text-muted-foreground pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={t('searchConversationsPlaceholder')}
            className="h-8 pl-8 text-xs bg-background"
          />
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="size-8 shrink-0 cursor-pointer"
          onClick={onNewChat}
          title={t('newChat')}
        >
          <MessageSquarePlus className="size-4" />
        </Button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {search.trim() ? (
          <>
            {/* 匹配的会话 */}
            {filtered.length > 0 && (
              <div className="space-y-1">
                <div className="px-2.5 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('sectionConversations')}
                </div>
                {filtered.map((conv) => {
                  const isSelected = conv.id === selectedId
                  const isSystem = conv.type === 'system'
                  const title = isSystem
                    ? t('systemNotifications')
                    : conv.peer?.full_name || conv.peer?.username || t('unknownUser')
                  const subtitle = stripMarkdown(conv.last_message_content) || t('noMessagesYet')
                  const timeLabel = formatRelativeTime(conv.last_message_at || conv.created_at)

                  return (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => onSelect(conv)}
                      className={cn(
                        'flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition-colors cursor-pointer',
                        isSelected
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'hover:bg-muted/60 text-foreground'
                      )}
                    >
                      {isSystem ? (
                        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                          <Bell className="size-4.5" />
                        </div>
                      ) : (
                        <Avatar className="size-9 shrink-0">
                          {conv.peer?.avatar_url && <AvatarImage src={conv.peer.avatar_url} />}
                          <AvatarFallback className="text-xs">
                            {title.slice(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          <span className="truncate text-sm font-semibold">{title}</span>
                          {timeLabel && (
                            <span className="shrink-0 text-[11px] text-muted-foreground font-normal">
                              {timeLabel}
                            </span>
                          )}
                        </div>
                        <p className="flex items-center justify-between gap-1 mt-0.5">
                          <span className="truncate text-xs text-muted-foreground font-normal min-w-0">
                            {highlightMatch(subtitle, search.trim())}
                          </span>
                          {conv.unread_count > 0 && (
                            <Badge
                              variant="destructive"
                              className="size-4.5 rounded-full p-0 flex items-center justify-center text-[10px] shrink-0 font-medium"
                            >
                              {conv.unread_count > 99 ? '99+' : conv.unread_count}
                            </Badge>
                          )}
                        </p>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {/* 匹配的聊天记录 */}
            {matchedMessages.length > 0 && (
              <div className="space-y-1 pt-1">
                <div className="px-2.5 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                  <span>{t('sectionMessages')}</span>
                  <span className="text-[10px] font-normal lowercase">
                    {matchedMessages.length} {t('messagesMatched')}
                  </span>
                </div>
                {matchedMessages.map((item) => {
                  const isSystem = item.conversation_type === 'system'
                  const title = isSystem
                    ? t('systemNotifications')
                    : item.peer?.full_name || item.peer?.username || t('unknownUser')
                  const timeLabel = formatRelativeTime(item.created_at)

                  return (
                    <button
                      key={item.message_id}
                      type="button"
                      onClick={() => onSelectSearchResult?.(item)}
                      className="flex w-full items-start gap-2.5 rounded-lg p-2 text-left hover:bg-muted/60 text-foreground transition-colors cursor-pointer border border-transparent hover:border-border"
                    >
                      <MessageSquareText className="size-4 text-muted-foreground shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-1">
                          <span className="truncate text-xs font-medium text-foreground/90">
                            {title}
                          </span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {timeLabel}
                          </span>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground font-normal mt-0.5 leading-relaxed break-words">
                          {highlightMatch(stripMarkdown(item.content), search.trim())}
                        </p>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {filtered.length === 0 && matchedMessages.length === 0 && !searchingMessages && (
              <div className="text-muted-foreground py-10 text-center text-xs">
                {t('noSearchResults')}
              </div>
            )}
          </>
        ) : (
          conversations.map((conv) => {
            const isSelected = conv.id === selectedId
            const isSystem = conv.type === 'system'
            const title = isSystem
              ? t('systemNotifications')
              : conv.peer?.full_name || conv.peer?.username || t('unknownUser')
            const subtitle = stripMarkdown(conv.last_message_content) || t('noMessagesYet')
            const timeLabel = formatRelativeTime(conv.last_message_at || conv.created_at)

            return (
              <button
                key={conv.id}
                type="button"
                onClick={() => onSelect(conv)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition-colors cursor-pointer',
                  isSelected
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'hover:bg-muted/60 text-foreground'
                )}
              >
                {/* 头像 */}
                {isSystem ? (
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                    <Bell className="size-5" />
                  </div>
                ) : (
                  <Avatar className="size-10 shrink-0">
                    {conv.peer?.avatar_url && <AvatarImage src={conv.peer.avatar_url} />}
                    <AvatarFallback className="text-xs">
                      {title.slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                )}

                {/* 文本内容与未读 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate text-sm font-semibold">{title}</span>
                    {timeLabel && (
                      <span className="shrink-0 text-[11px] text-muted-foreground font-normal">
                        {timeLabel}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-1 mt-0.5">
                    <p className="truncate text-xs text-muted-foreground font-normal">
                      {subtitle}
                    </p>
                    {conv.unread_count > 0 && (
                      <Badge
                        variant="destructive"
                        className="size-4.5 rounded-full p-0 flex items-center justify-center text-[10px] shrink-0 font-medium"
                      >
                        {conv.unread_count > 99 ? '99+' : conv.unread_count}
                      </Badge>
                    )}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
