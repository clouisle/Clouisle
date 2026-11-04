'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { Bell, Loader2, Send, ShieldAlert, Sparkles } from 'lucide-react'
import { imApi, type ImConversation, type ImMessage } from '@/lib/api'
import { Streamdown } from 'streamdown'
import { PauseRequestActions } from '@/components/chat/pause-request-actions'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

function isDifferentDay(d1: Date, d2: Date | null): boolean {
  if (!d2) return true
  return (
    d1.getFullYear() !== d2.getFullYear() ||
    d1.getMonth() !== d2.getMonth() ||
    d1.getDate() !== d2.getDate()
  )
}

function formatDateDivider(date: Date, locale: string = 'zh'): string {
  const now = new Date()
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()

  const isZh = locale.startsWith('zh')
  if (isToday) return isZh ? '今天' : 'Today'
  if (isYesterday) return isZh ? '昨天' : 'Yesterday'

  const isSameYear = date.getFullYear() === now.getFullYear()
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()

  if (isZh) {
    return isSameYear ? `${month}月${day}日` : `${year}年${month}月${day}日`
  }
  return isSameYear ? `${month}/${day}` : `${year}/${month}/${day}`
}

interface ChatWindowProps {
  conversation: ImConversation | null
  currentUserId: string
  incomingMessage?: ImMessage | null
  targetSeq?: number | null
  targetMessageId?: string | null
  onMessageSent?: () => void
}

export function ChatWindow({
  conversation,
  currentUserId,
  incomingMessage,
  targetSeq,
  targetMessageId,
  onMessageSent,
}: ChatWindowProps) {
  const locale = useLocale()
  const t = useTranslations('notifications.im')
  const [messages, setMessages] = React.useState<ImMessage[]>([])
  const [loading, setLoading] = React.useState(false)
  const [loadingMore, setLoadingMore] = React.useState(false)
  const [hasMore, setHasMore] = React.useState(false)
  const [inputText, setInputText] = React.useState('')
  const [sending, setSending] = React.useState(false)
  const messagesEndRef = React.useRef<HTMLDivElement>(null)
  const isComposingRef = React.useRef(false)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  const scrollContainerRef = React.useRef<HTMLDivElement>(null)
  const pendingScrollAnchorRef = React.useRef<{ scrollHeight: number; scrollTop: number } | null>(null)
  const shouldScrollToBottomRef = React.useRef(false)

  // 换行自适应增高，设置最大高度限制 (160px，约 6 行文本)
  const adjustTextareaHeight = React.useCallback(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const maxHeight = 160
    const minHeight = 44
    const newHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight)
    textarea.style.height = `${newHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [])

  React.useEffect(() => {
    adjustTextareaHeight()
  }, [inputText, adjustTextareaHeight])

  const convId = conversation?.id
  const isSystem = conversation?.type === 'system'

  // 加载会话最新消息
  const loadInitialMessages = React.useCallback(async (id: string, seqTarget?: number | null) => {
    setLoading(true)
    try {
      const params = seqTarget ? { around_seq: seqTarget, limit: 40 } : { limit: 40 }
      const resp = await imApi.getMessages(id, params)
      setMessages(resp.messages)
      setHasMore(resp.has_more)
      if (!seqTarget) {
        shouldScrollToBottomRef.current = true
      }
      // 进入会话自动标记已读
      await imApi.markRead(id)
    } catch (err) {
      console.error('Failed to load messages:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    if (!convId) {
      setMessages([])
      return
    }
    loadInitialMessages(convId, targetSeq)
  }, [convId, targetSeq, loadInitialMessages])

  // 搜索目标消息居中视口滚动
  React.useEffect(() => {
    if (!targetMessageId || loading) return
    const timer = setTimeout(() => {
      const el = document.getElementById(`im-msg-${targetMessageId}`)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 100)
    return () => clearTimeout(timer)
  }, [targetMessageId, messages, loading])

  // 实时 SSE 增量新消息推入
  React.useEffect(() => {
    if (incomingMessage && incomingMessage.conversation_id === convId) {
      setMessages((prev) => {
        const exists = prev.some(
          (m) =>
            m.id === incomingMessage.id ||
            (m.client_msg_id &&
              incomingMessage.client_msg_id &&
              m.client_msg_id === incomingMessage.client_msg_id)
        )
        if (exists) return prev

        const container = scrollContainerRef.current
        if (container) {
          const isNearBottom =
            container.scrollHeight - container.scrollTop - container.clientHeight <= 150
          if (isNearBottom) {
            shouldScrollToBottomRef.current = true
          }
        } else {
          shouldScrollToBottomRef.current = true
        }

        return [...prev, incomingMessage]
      })
    }
  }, [incomingMessage, convId])

  // 精准视口位置锚定与滚底调度
  React.useEffect(() => {
    if (loading) return

    const anchor = pendingScrollAnchorRef.current
    const container = scrollContainerRef.current

    if (anchor && container) {
      // 加载更早历史消息：计算内容高度增量并调整 scrollTop，精准锚定视角，绝不滚到底部
      const delta = container.scrollHeight - anchor.scrollHeight
      container.scrollTop = anchor.scrollTop + delta
      pendingScrollAnchorRef.current = null
      return
    }

    if (shouldScrollToBottomRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'auto' })
      shouldScrollToBottomRef.current = false
    }
  }, [messages, loading])

  // 加载更早历史消息
  const handleLoadMore = async () => {
    if (!convId || loadingMore || messages.length === 0) return
    const container = scrollContainerRef.current
    if (container) {
      pendingScrollAnchorRef.current = {
        scrollHeight: container.scrollHeight,
        scrollTop: container.scrollTop,
      }
    }
    const earliestSeq = messages[0].seq
    setLoadingMore(true)
    try {
      const resp = await imApi.getMessages(convId, {
        before_seq: earliestSeq,
        limit: 30,
      })
      shouldScrollToBottomRef.current = false
      setMessages((prev) => [...resp.messages, ...prev])
      setHasMore(resp.has_more)
    } catch (err) {
      console.error('Failed to load more messages:', err)
      pendingScrollAnchorRef.current = null
    } finally {
      setLoadingMore(false)
    }
  }

  // 发送消息
  const handleSend = async () => {
    const text = inputText.trim()
    if (!convId || !text || sending || isSystem) return

    setSending(true)
    const clientMsgId = `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    try {
      const newMsg = await imApi.sendMessage(convId, {
        content: text,
        client_msg_id: clientMsgId,
      })
      shouldScrollToBottomRef.current = true
      setMessages((prev) => [...prev, newMsg])
      setInputText('')
      if (textareaRef.current) {
        textareaRef.current.style.height = '44px'
        textareaRef.current.style.overflowY = 'hidden'
      }
      onMessageSent?.()
    } catch (err) {
      console.error('Failed to send message:', err)
    } finally {
      setSending(false)
    }
  }

  const handleCompositionStart = () => {
    isComposingRef.current = true
  }

  const handleCompositionEnd = () => {
    isComposingRef.current = false
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 忽略中文输入法未完成时的 Enter 上屏事件
    if (isComposingRef.current || e.nativeEvent.isComposing || e.keyCode === 229) {
      return
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!conversation) {
    return (
      <div className="flex flex-1 flex-col h-full bg-background min-w-0">
        <div className="h-14 shrink-0 border-b" />
        <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-muted-foreground">
          <Sparkles className="size-10 mb-3 stroke-1 text-muted-foreground/60" />
          <p className="text-base font-medium">{t('selectConversationTitle')}</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-xs">
            {t('selectConversationDesc')}
          </p>
        </div>
      </div>
    )
  }

  const headerTitle = isSystem
    ? t('systemNotifications')
    : conversation.peer?.full_name || conversation.peer?.username || t('unknownUser')

  return (
    <div className="flex flex-1 flex-col h-full bg-background min-w-0">
      {/* 聊天窗口顶栏 */}
      <div className="flex h-14 shrink-0 items-center justify-between px-4 border-b">
        <div className="flex items-center gap-3 overflow-hidden">
          {isSystem ? (
            <div className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-primary shrink-0">
              <Bell className="size-4.5" />
            </div>
          ) : (
            <Avatar className="size-9 shrink-0">
              {conversation.peer?.avatar_url && (
                <AvatarImage src={conversation.peer.avatar_url} />
              )}
              <AvatarFallback className="text-xs">
                {headerTitle.slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
          )}
          <div className="flex flex-col overflow-hidden">
            <span className="font-semibold text-sm truncate">{headerTitle}</span>
            <span className="text-muted-foreground text-xs truncate">
              {isSystem ? t('systemNoticeBadge') : `@${conversation.peer?.username}`}
            </span>
          </div>
        </div>
      </div>

      {/* 消息流区域 */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {hasMore && (
          <div className="flex justify-center pb-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="text-xs h-7 text-muted-foreground"
            >
              {loadingMore && <Loader2 className="mr-1.5 size-3 animate-spin" />}
              {t('loadEarlierMessages')}
            </Button>
          </div>
        )}

        {!hasMore && messages.length > 0 && !loading && (
          <div className="relative flex items-center justify-center my-3 select-none">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border/40" />
            </div>
            <span className="relative bg-background px-3 text-[11px] font-medium text-muted-foreground/70">
              {t('earliestMessageNotice')}
            </span>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20 text-muted-foreground">
            <Loader2 className="size-6 animate-spin" />
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground text-xs">
            {t('noMessagesInConversation')}
          </div>
        ) : (
          messages.map((msg, idx) => {
            const currentDate = new Date(msg.created_at)
            const prevDate = idx > 0 ? new Date(messages[idx - 1].created_at) : null
            const showDateDivider = isDifferentDay(currentDate, prevDate)
            const isMe = msg.sender_id === currentUserId
            const isCard = msg.msg_type === 'card'
            const pauseData =
              msg.payload && typeof msg.payload === 'object'
                ? (msg.payload.data as Record<string, unknown> | undefined) ||
                  (msg.payload as Record<string, unknown>)
                : null

            const pauseReqId =
              pauseData?.pause_request_id ||
              pauseData?.pauseRequestId ||
              (msg.payload?.pause_request_id as string)
            const workflowId =
              pauseData?.workflow_id ||
              pauseData?.workflowId ||
              (msg.payload?.workflow_id as string)
            const runId =
              pauseData?.run_id ||
              pauseData?.runId ||
              (msg.payload?.run_id as string)

            const isTarget = Boolean(
              (targetMessageId && msg.id === targetMessageId) ||
              (targetSeq && msg.seq === targetSeq)
            )

            return (
              <React.Fragment key={msg.id}>
                {showDateDivider && (
                  <div className="relative flex items-center justify-center my-4 select-none">
                    <div className="absolute inset-0 flex items-center">
                      <span className="w-full border-t border-border/50" />
                    </div>
                    <span className="relative bg-background px-3 text-[11px] font-medium text-muted-foreground/80 rounded-full border border-border/40 py-0.5 shadow-2xs">
                      {formatDateDivider(currentDate, locale)}
                    </span>
                  </div>
                )}
                <div
                  id={`im-msg-${msg.id}`}
                  className={cn('flex flex-col', isMe ? 'items-end' : 'items-start')}
                >
                {/* 消息主体 */}
                {isCard && pauseReqId && workflowId && runId ? (
                  <div className="w-full max-w-2xl rounded-xl border bg-card p-4 shadow-xs space-y-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-primary">
                      <ShieldAlert className="size-4" />
                      {t('approvalCardTitle')}
                    </div>
                    <div className="text-xs prose prose-xs max-w-none dark:prose-invert [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <Streamdown>{msg.content}</Streamdown>
                    </div>
                    <div className="pt-2 border-t">
                      <PauseRequestActions
                        workflowId={String(workflowId)}
                        runId={String(runId)}
                        pauseRequestId={String(pauseReqId)}
                        variant="compact"
                        onResolved={() => {
                          loadInitialMessages(conversation.id)
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <div
                    className={cn(
                      'max-w-[75%] rounded-2xl px-4 py-2.5 text-sm break-words leading-relaxed prose prose-sm max-w-none dark:prose-invert [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 transition-all duration-300',
                      isTarget && 'ring-2 ring-primary ring-offset-2 shadow-lg animate-pulse',
                      isMe
                        ? 'bg-primary text-primary-foreground rounded-br-xs prose-headings:text-primary-foreground prose-p:text-primary-foreground prose-strong:text-primary-foreground prose-a:text-primary-foreground prose-code:text-primary-foreground prose-ul:text-primary-foreground prose-ol:text-primary-foreground'
                        : isSystem
                        ? 'bg-muted/70 border text-foreground rounded-bl-xs'
                        : 'bg-muted text-foreground rounded-bl-xs'
                    )}
                  >
                    <Streamdown>{msg.content}</Streamdown>
                  </div>
                )}

                {/* 时间戳 */}
                <span className="text-[10px] text-muted-foreground/70 mt-1 px-1">
                  {new Date(msg.created_at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                  })}
                </span>
              </div>
              </React.Fragment>
            )
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入框 */}
      {isSystem ? (
        <div className="p-3 border-t bg-muted/20 text-center text-xs text-muted-foreground">
          {t('systemNoticeReadOnly')}
        </div>
      ) : (
        <div className="p-3 border-t flex items-end gap-2 bg-background">
          <Textarea
            ref={textareaRef}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={handleCompositionStart}
            onCompositionEnd={handleCompositionEnd}
            placeholder={t('inputPlaceholder')}
            className="min-h-[44px] max-h-40 resize-none text-sm leading-normal py-2.5 transition-[height] duration-75"
            rows={1}
            disabled={sending}
          />
          <Button
            size="icon"
            className="size-10 shrink-0 cursor-pointer"
            onClick={handleSend}
            disabled={!inputText.trim() || sending}
          >
            {sending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
