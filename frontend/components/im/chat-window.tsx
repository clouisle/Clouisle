'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import {
  Bell,
  Image as ImageIcon,
  Loader2,
  Paperclip,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react'
import { imApi, type ImAttachment, type ImConversation, type ImMessage, type ImMessageType } from '@/lib/api'
import { Streamdown } from 'streamdown'
import { toast } from 'sonner'
import { PauseRequestActions } from '@/components/chat/pause-request-actions'
import { FileTypeIcon } from '@/components/file-type-icon'
import {
  downloadAuthenticatedAsset,
  useAuthenticatedAssetUrl,
} from '@/components/chat/authenticated-asset'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

function isSameMessage(a: ImMessage, b: ImMessage): boolean {
  if (a.id === b.id) return true
  return Boolean(
    a.client_msg_id && b.client_msg_id && a.client_msg_id === b.client_msg_id
  )
}

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


function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function AttachmentBubble({ attachment }: { attachment: ImAttachment }) {
  const t = useTranslations('notifications.im')
  const { src, loading, error } = useAuthenticatedAssetUrl(attachment.url)
  const isImage = attachment.content_type.startsWith('image/')

  if (isImage) {
    return (
      <div className="max-w-[75%] overflow-hidden rounded-2xl border bg-muted/30">
        {loading ? (
          <div className="flex size-40 items-center justify-center text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />
          </div>
        ) : error || !src ? (
          <div className="flex size-40 items-center justify-center px-4 text-center text-xs text-muted-foreground">
            {attachment.filename}
          </div>
        ) : (
          <img src={src} alt={attachment.filename} className="max-h-72 max-w-full object-contain" />
        )}
      </div>
    )
  }

  return (
    <button
      type="button"
      className="flex w-full max-w-[320px] cursor-pointer items-start gap-3 rounded-xl bg-[#EEEEF0] p-3 text-left transition-colors hover:bg-[#E4E4E8] dark:bg-muted/50 dark:hover:bg-muted"
      title={t('download')}
      onClick={() => void downloadAuthenticatedAsset(attachment.url, attachment.filename)}
    >
      <div className="min-w-0 flex-1">
        <div className="line-clamp-2 break-all text-sm font-medium leading-snug">
          {attachment.filename}
        </div>
        <div className="mt-2 text-xs text-muted-foreground">
          {formatFileSize(attachment.size)}
        </div>
      </div>
      <FileTypeIcon
        filename={attachment.filename}
        mimeType={attachment.content_type}
        className="size-10 shrink-0"
      />
    </button>
  )
}


interface MessageRowProps {
  message: ImMessage
  isMe: boolean
  isSystem: boolean
  showDateDivider: boolean
  showUnreadDivider: boolean
  isTarget: boolean
  locale: string
  onPauseResolved: () => void
}

/**
 * Memoized so typing in the composer only re-renders the composer instead of
 * every markdown bubble. Props must stay primitive or referentially stable.
 */
const MessageRow = React.memo(function MessageRow({
  message: msg,
  isMe,
  isSystem,
  showDateDivider,
  showUnreadDivider,
  isTarget,
  locale,
  onPauseResolved,
}: MessageRowProps) {
  const t = useTranslations('notifications.im')
  const currentDate = new Date(msg.created_at)
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
    pauseData?.run_id || pauseData?.runId || (msg.payload?.run_id as string)

  return (
    <React.Fragment>
      {showDateDivider && (
        <div
          data-testid="im-date-divider"
          className="relative my-4 flex select-none items-center justify-center"
        >
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-border/50" />
          </div>
          <span className="relative rounded-full border border-border/40 bg-background px-3 py-0.5 text-[11px] font-medium text-muted-foreground/80 shadow-2xs">
            {formatDateDivider(currentDate, locale)}
          </span>
        </div>
      )}
      {showUnreadDivider && (
        <div
          id="im-unread-divider"
          className="relative my-4 flex select-none items-center justify-center"
        >
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t border-primary/40 dark:border-primary/50" />
          </div>
          <span className="relative rounded-full border border-primary/30 bg-background px-3 py-0.5 text-[11px] font-medium text-primary shadow-2xs">
            {t('unreadMessagesDivider')}
          </span>
        </div>
      )}
      <div
        id={`im-msg-${msg.id}`}
        className={cn(
          'flex flex-col [content-visibility:auto] [contain-intrinsic-size:auto_96px]',
          isMe ? 'items-end' : 'items-start'
        )}
      >
        {msg.msg_type === 'card' && pauseReqId && workflowId && runId ? (
          <div className="w-full max-w-2xl space-y-3 rounded-xl border bg-card p-4 shadow-xs">
            <div className="flex items-center gap-2 text-xs font-semibold text-primary">
              <ShieldAlert className="size-4" />
              {t('approvalCardTitle')}
            </div>
            <div className="prose prose-xs max-w-none text-xs dark:prose-invert [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <Streamdown>{msg.content}</Streamdown>
            </div>
            <div className="border-t pt-2">
              <PauseRequestActions
                workflowId={String(workflowId)}
                runId={String(runId)}
                pauseRequestId={String(pauseReqId)}
                variant="compact"
                onResolved={onPauseResolved}
              />
            </div>
          </div>
        ) : msg.attachment ? (
          <AttachmentBubble attachment={msg.attachment} />
        ) : (
          <div
            className={cn(
              'prose prose-sm max-w-none break-words rounded-2xl px-4 py-2.5 text-sm leading-relaxed transition-all duration-300 dark:prose-invert [&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
              isTarget && 'ring-2 ring-primary ring-offset-2 shadow-lg animate-pulse',
              isMe
                ? 'rounded-br-xs bg-primary text-primary-foreground prose-headings:text-primary-foreground prose-p:text-primary-foreground prose-strong:text-primary-foreground prose-a:text-primary-foreground prose-code:text-primary-foreground prose-ul:text-primary-foreground prose-ol:text-primary-foreground'
                : isSystem
                  ? 'rounded-bl-xs border bg-muted/70 text-foreground'
                  : 'rounded-bl-xs bg-muted text-foreground'
            )}
          >
            <Streamdown>{msg.content}</Streamdown>
          </div>
        )}

        <span className="mt-1 px-1 text-[10px] text-muted-foreground/70">
          {currentDate.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          })}
        </span>
      </div>
    </React.Fragment>
  )
})

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
  const shouldScrollToUnreadRef = React.useRef(false)
  const currentConvIdRef = React.useRef<string | null>(null)
  // 初始历史请求令牌：切换会话或发起新请求后，旧的响应一律丢弃
  const loadTokenRef = React.useRef(0)
  // 当前消息流是否定位在 around_seq 历史切片上（中间历史可能未加载）
  const aroundSeqViewRef = React.useRef(false)
  const messagesRef = React.useRef<ImMessage[]>([])
  const [unreadWatermark, setUnreadWatermark] = React.useState<number | null>(null)
  const [pendingAttachments, setPendingAttachments] = React.useState<ImAttachment[]>([])
  const [uploading, setUploading] = React.useState(false)
  const draftBatchIdRef = React.useRef<string | null>(null)
  const fileInputRef = React.useRef<HTMLInputElement>(null)
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

  React.useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // 加载会话最新消息（支持未读消息位置探测与加载）
  const loadInitialMessages = React.useCallback(
    async (
      id: string,
      seqTarget?: number | null,
      watermark?: number | null,
      unreadCount?: number
    ) => {
      const token = ++loadTokenRef.current
      const isAround = Boolean(seqTarget)
      aroundSeqViewRef.current = isAround
      setLoading(true)
      try {
        let params: { around_seq?: number; limit?: number } = { limit: 40 }
        if (seqTarget) {
          params = { around_seq: seqTarget, limit: 40 }
        } else if (unreadCount && unreadCount > 30) {
          params = { limit: Math.min(100, unreadCount + 10) }
        }

        const resp = await imApi.getMessages(id, params)
        // 会话已切换或已有更新的请求：丢弃过期响应
        if (token !== loadTokenRef.current || currentConvIdRef.current !== id) return

        if (isAround) {
          setMessages(resp.messages)
        } else {
          // SSE 可能在历史请求期间到达：保留响应中不存在且比已加载消息更新的实时消息
          setMessages((prev) => {
            const newestSeq = resp.messages.reduce((max, m) => Math.max(max, m.seq), 0)
            const live = prev.filter(
              (m) =>
                m.conversation_id === id &&
                m.seq > newestSeq &&
                !resp.messages.some((loaded) => isSameMessage(loaded, m))
            )
            if (live.length === 0) return resp.messages
            return [...resp.messages, ...live].sort((a, b) => a.seq - b.seq)
          })
        }
        setHasMore(resp.has_more)

        if (watermark !== null && watermark !== undefined) {
          shouldScrollToUnreadRef.current = true
          shouldScrollToBottomRef.current = false
        } else if (!isAround) {
          shouldScrollToUnreadRef.current = false
          shouldScrollToBottomRef.current = true
        }

        // 进入会话自动标记已读：
        // - 定位到历史消息（around_seq）时不标记，否则会把整段最新消息误标为已读
        // - 未读数超出本次已加载窗口时不标记，避免清掉未加载消息的未读状态
        const unreadWithinWindow =
          unreadCount === undefined || unreadCount <= resp.messages.length
        if (!isAround && unreadWithinWindow) {
          await imApi.markRead(id)
        }
      } catch (err) {
        console.error('Failed to load messages:', err)
      } finally {
        if (token === loadTokenRef.current) setLoading(false)
      }
    },
    []
  )

  const handlePauseResolved = React.useCallback(() => {
    if (convId) {
      void loadInitialMessages(convId, null, null, conversation?.unread_count)
    }
  }, [convId, conversation?.unread_count, loadInitialMessages])

  React.useEffect(() => {
    if (!convId || !conversation) {
      loadTokenRef.current += 1
      aroundSeqViewRef.current = false
      setLoading(false)
      setMessages([])
      setUnreadWatermark(null)
      setPendingAttachments([])
      draftBatchIdRef.current = null
      currentConvIdRef.current = null
      return
    }

    currentConvIdRef.current = convId
    setPendingAttachments([])
    draftBatchIdRef.current = null

    if (targetSeq) {
      setUnreadWatermark(null)
      loadInitialMessages(convId, targetSeq)
      return
    }

    const hasUnread =
      conversation.unread_count > 0 &&
      conversation.latest_seq > conversation.last_read_seq
    const watermark = hasUnread ? conversation.last_read_seq : null
    setUnreadWatermark(watermark)

    loadInitialMessages(convId, null, watermark, conversation.unread_count)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convId, targetSeq, loadInitialMessages])

  // 切换至可回复会话时自动聚焦输入框
  React.useEffect(() => {
    if (!isSystem && convId) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    }
  }, [convId, isSystem])
  // 搜索目标消息居中视口滚动
  React.useEffect(() => {
    if (!targetMessageId || loading || typeof document === 'undefined') return
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
    if (!incomingMessage || incomingMessage.conversation_id !== convId) return

    const prev = messagesRef.current
    if (prev.some((m) => isSameMessage(m, incomingMessage))) return

    // around_seq 切片只包含目标附近的消息：若新消息与当前切片之间存在断层，
    // 说明中间历史从未加载，直接追加会漏消息，改为重新加载最新历史。
    // 切换会话后尚未加载完成时，state 里仍是上一个会话的消息，不做断层判断。
    const hasCurrentConvMessages = prev.length > 0 && prev[0].conversation_id === convId
    const newestSeq = prev.reduce((max, m) => Math.max(max, m.seq), 0)
    if (
      aroundSeqViewRef.current &&
      hasCurrentConvMessages &&
      incomingMessage.seq > newestSeq + 1
    ) {
      void loadInitialMessages(convId, null, null, conversation?.unread_count)
      return
    }

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

    setMessages((current) => {
      if (current.some((m) => isSameMessage(m, incomingMessage))) return current
      const next = [...current, incomingMessage]
      return next.sort((a, b) => a.seq - b.seq)
    })
  }, [incomingMessage, convId, conversation?.unread_count, loadInitialMessages])

  // 精准视口位置锚定与滚底调度（优先处理未读分割线定位）
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

    if (shouldScrollToUnreadRef.current) {
      const divider =
        typeof document !== 'undefined'
          ? document.getElementById('im-unread-divider')
          : null
      if (divider && container) {
        const containerRect = container.getBoundingClientRect()
        const dividerRect = divider.getBoundingClientRect()
        if (containerRect.height > 0) {
          const relativeTop = dividerRect.top - containerRect.top + container.scrollTop
          container.scrollTop = Math.max(0, relativeTop - 16)
        } else {
          divider.scrollIntoView?.({ behavior: 'auto', block: 'start' })
        }
        shouldScrollToUnreadRef.current = false
        return
      }
      if (shouldScrollToBottomRef.current && messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView?.({ behavior: 'auto' })
        shouldScrollToBottomRef.current = false
      }
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
    const snapshotConvId = convId
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
      const resp = await imApi.getMessages(snapshotConvId, {
        before_seq: earliestSeq,
        limit: 30,
      })
      // 会话已切换：丢弃过期响应，且不覆盖新会话的 hasMore / 滚动锚点
      if (currentConvIdRef.current !== snapshotConvId) {
        pendingScrollAnchorRef.current = null
        return
      }
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

  const handleFilesSelected = React.useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0 || !convId) return
      const snapshotConvId = convId
      setUploading(true)
      try {
        const uploaded = await Promise.all(
          Array.from(files).map((file) =>
            imApi.uploadAttachment(snapshotConvId, file)
          )
        )
        if (currentConvIdRef.current !== snapshotConvId) return
        setPendingAttachments((prev) => [...prev, ...uploaded])
      } catch (err) {
        console.error('Failed to upload attachment:', err)
        toast.error(t('uploadFailed'))
      } finally {
        setUploading(false)
      }
    },
    [convId, t]
  )

  // 发送：文本与每个附件拆成独立消息，串行 await 保证顺序与 seq 一致
  const handleSend = async () => {
    const text = inputText.trim()
    if (!convId || sending || isSystem || uploading) return
    // 与后端 max_length 对齐（按 Unicode 码点计数），超限时不发送并保留草稿
    if (text && [...text].length > 10000) {
      toast.error(t('composerMessageTooLong'))
      return
    }

    // 发送始终绑定发起时的会话；会话切换后不再把结果写进新会话
    const sendConvId = convId

    const items: Array<{
      content: string
      msg_type: ImMessageType
      asset_id?: string
      dedupeKey: string
    }> = []
    if (text) items.push({ content: text, msg_type: 'text', dedupeKey: 'text' })
    for (const attachment of pendingAttachments) {
      items.push({
        content: '',
        msg_type: 'file',
        asset_id: attachment.asset_id,
        dedupeKey: attachment.asset_id.slice(0, 8),
      })
    }
    if (items.length === 0) return

    // 同一草稿重试复用 batch id，保证 client_msg_id 稳定、已成功的消息幂等去重
    const batchId =
      draftBatchIdRef.current ??
      `batch-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    draftBatchIdRef.current = batchId
    setSending(true)
    try {
      for (let i = 0; i < items.length; i += 1) {
        const newMsg = await imApi.sendMessage(sendConvId, {
          content: items[i].content,
          msg_type: items[i].msg_type,
          asset_id: items[i].asset_id,
          client_msg_id: `${batchId}-${items[i].dedupeKey}`,
        })
        if (currentConvIdRef.current !== sendConvId) continue
        shouldScrollToBottomRef.current = true
        shouldScrollToUnreadRef.current = false
        setMessages((prev) =>
          prev.some((m) => m.id === newMsg.id) ? prev : [...prev, newMsg]
        )
      }
      // 清掉本次已发送的草稿内容：若用户在发送期间切换了会话并输入了新内容，
      // 只移除仍然属于这次发送的文本/附件，不覆盖新会话的草稿。
      const sentAssetIds = new Set(
        items.map((item) => item.asset_id).filter((id): id is string => Boolean(id))
      )
      setInputText((prev) => (prev.trim() === text ? '' : prev))
      setPendingAttachments((prev) =>
        prev.filter((attachment) => !sentAssetIds.has(attachment.asset_id))
      )
      if (currentConvIdRef.current === sendConvId) {
        draftBatchIdRef.current = null
        if (textareaRef.current) {
          textareaRef.current.style.height = '44px'
          textareaRef.current.style.overflowY = 'hidden'
          textareaRef.current.focus()
        }
      }
      onMessageSent?.()
    } catch (err) {
      // 保留草稿：已成功的消息靠 client_msg_id 幂等，整批重试不会产生重复
      console.error('Failed to send message:', err)
    } finally {
      setSending(false)
      textareaRef.current?.focus()
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
      textareaRef.current?.focus()
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
          (() => {
            const firstUnreadIndex =
              unreadWatermark !== null
                ? messages.findIndex((m) => m.seq > unreadWatermark)
                : -1

            return messages.map((msg, idx) => {
              const currentDate = new Date(msg.created_at)
              const prevDate = idx > 0 ? new Date(messages[idx - 1].created_at) : null
              return (
                <MessageRow
                  key={msg.id}
                  message={msg}
                  isMe={msg.sender_id === currentUserId}
                  isSystem={isSystem}
                  showDateDivider={isDifferentDay(currentDate, prevDate)}
                  showUnreadDivider={idx === firstUnreadIndex}
                  isTarget={Boolean(
                    (targetMessageId && msg.id === targetMessageId) ||
                      (targetSeq && msg.seq === targetSeq)
                  )}
                  locale={locale}
                  onPauseResolved={handlePauseResolved}
                />
              )
            })
          })()
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入框 */}
      {isSystem ? (
        <div className="p-3 border-t bg-muted/20 text-center text-xs text-muted-foreground">
          {t('systemNoticeReadOnly')}
        </div>
      ) : (
        <div className="p-3">
          <div className="rounded-2xl border bg-muted/40 px-2 py-1.5 transition-colors focus-within:border-ring/60">
            {pendingAttachments.length > 0 && (
              <div className="mb-1 flex flex-wrap gap-2 px-1 pt-1">
                {pendingAttachments.map((attachment) => (
                  <span
                    key={attachment.asset_id}
                    className="inline-flex items-center gap-1 rounded-full border bg-background px-2.5 py-1 text-[11px]"
                  >
                    {attachment.content_type.startsWith('image/') ? (
                      <ImageIcon className="size-3" />
                    ) : (
                      <Paperclip className="size-3" />
                    )}
                  <span className="max-w-32 truncate">{attachment.filename}</span>
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    title={t('removeAttachment')}
                    onClick={() =>
                      setPendingAttachments((prev) =>
                        prev.filter((p) => p.asset_id !== attachment.asset_id)
                      )
                    }
                  >
                    <X className="size-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                void handleFilesSelected(e.target.files)
                e.target.value = ''
              }}
            />
            <Textarea
              ref={textareaRef}
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              onCompositionStart={handleCompositionStart}
              onCompositionEnd={handleCompositionEnd}
              placeholder={t('inputPlaceholder')}
              className="min-h-[48px] max-h-40 resize-none border-0 bg-transparent px-2 py-2.5 text-sm leading-normal shadow-none transition-[height] duration-75 focus-visible:border-0 focus-visible:ring-0 dark:bg-transparent"
              rows={1}
              disabled={isSystem}
            />
            <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
              <Button
                variant="ghost"
                size="icon"
                className="size-9 cursor-pointer rounded-full text-muted-foreground hover:text-foreground"
                title={t('attachFile')}
                disabled={uploading || sending}
                onClick={() => fileInputRef.current?.click()}
              >
                {uploading ? (
                  <Loader2 className="size-5 animate-spin" />
                ) : (
                  <Paperclip className="size-5" />
                )}
              </Button>
              <Button
                className="h-9 cursor-pointer rounded-full px-4 text-sm disabled:bg-muted disabled:text-muted-foreground disabled:opacity-100"
                onClick={handleSend}
                onMouseDown={(e) => e.preventDefault()}
                disabled={(!inputText.trim() && pendingAttachments.length === 0) || sending || uploading}
              >
                {sending ? <Loader2 className="size-4 animate-spin" /> : t('send')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
