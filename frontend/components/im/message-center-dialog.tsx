'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { imApi, type ImConversation, type ImMessage, type ImSearchResult } from '@/lib/api'
import { useTeam } from '@/contexts/team-context'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConversationList } from './conversation-list'
import { ChatWindow } from './chat-window'
import { NewChatDialog } from './new-chat-dialog'

export interface MessageCenterDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentUserId: string
  onUnreadUpdated?: () => void
}

export function MessageCenterDialog({
  open,
  onOpenChange,
  currentUserId,
  onUnreadUpdated,
}: MessageCenterDialogProps) {
  const t = useTranslations('notifications')
  const { currentTeam } = useTeam()
  const teamId = currentTeam?.id

  const [conversations, setConversations] = React.useState<ImConversation[]>([])
  const [selectedConv, setSelectedConv] = React.useState<ImConversation | null>(null)
  const [search, setSearch] = React.useState('')
  const [newChatOpen, setNewChatOpen] = React.useState(false)
  const [targetJump, setTargetJump] = React.useState<{ seq: number; messageId: string } | null>(null)
  const [liveMessage, setLiveMessage] = React.useState<ImMessage | null>(null)

  // 会话列表请求令牌：只接受最新一次请求、且仍属当前团队的结果
  const listRequestRef = React.useRef(0)
  const teamIdRef = React.useRef(teamId)

  React.useEffect(() => {
    teamIdRef.current = teamId
  }, [teamId])

  // 切换团队时清空上一团队的选择与会话，避免串队
  React.useEffect(() => {
    setConversations([])
    setSelectedConv(null)
    setTargetJump(null)
    setLiveMessage(null)
  }, [teamId])

  // 刷新会话列表
  const refreshConversations = React.useCallback(async (targetSelectId?: string) => {
    if (!teamId) return
    const requestId = listRequestRef.current + 1
    listRequestRef.current = requestId
    const requestTeamId = teamId
    try {
      const items = await imApi.listConversations(teamId)
      if (requestId !== listRequestRef.current || requestTeamId !== teamIdRef.current) {
        // 迟到的旧请求/旧团队响应，丢弃
        return undefined
      }
      setConversations(items)
      if (targetSelectId) {
        const found = items.find((c) => c.id === targetSelectId)
        if (found) setSelectedConv(found)
      } else if (!selectedConv && items.length > 0) {
        // 默认选中置顶的系统通知会话或第一个会话
        const sys = items.find((c) => c.type === 'system')
        setSelectedConv(sys || items[0])
      }
      return items
    } catch (err) {
      console.error('Failed to load conversations:', err)
      return undefined
    }
  }, [teamId, selectedConv])

  React.useEffect(() => {
    if (!open || !teamId) return
    refreshConversations()
  }, [open, teamId, refreshConversations])

  // SSE 实时下推监听
  React.useEffect(() => {
    if (!open) return

    const unsubscribe = imApi.subscribeEvents({
      onNewMessage: (msg) => {
        const isCurrent = selectedConv?.id === msg.conversation_id
        if (isCurrent) {
          setLiveMessage(msg)
          imApi.markRead(msg.conversation_id, msg.seq).catch(() => {})
        }

        setConversations((prev) => {
          const idx = prev.findIndex((c) => c.id === msg.conversation_id)
          if (idx === -1) {
            refreshConversations()
            return prev
          }
          const current = prev[idx]
          // 迟到的旧事件不能回退会话预览与最新序号
          if (msg.seq <= current.latest_seq) return prev
          const next = [...prev]
          next[idx] = {
            ...current,
            last_message_content: msg.content,
            last_message_at: msg.created_at,
            latest_seq: msg.seq,
            // 仅在非当前会话且事件确实更新时递增，避免重复投递重复计数
            unread_count: isCurrent ? current.unread_count : (current.unread_count || 0) + 1,
          }
          return next.sort((a, b) => {
            const pA = a.is_pinned ? 1 : 0
            const pB = b.is_pinned ? 1 : 0
            if (pA !== pB) return pB - pA
            const tA = a.last_message_at || a.created_at
            const tB = b.last_message_at || b.created_at
            return tB.localeCompare(tA)
          })
        })

        onUnreadUpdated?.()
      },
      onConversationRead: (data) => {
        setConversations((prev) =>
          prev.map((c) => {
            if (c.id !== data.conversation_id) return c
            // 按已读游标重算：部分已读时，更新的消息仍保持未读
            const lastRead = Math.max(c.last_read_seq || 0, data.last_read_seq || 0)
            return {
              ...c,
              last_read_seq: lastRead,
              unread_count: Math.max((c.latest_seq || 0) - lastRead, 0),
            }
          })
        )
        onUnreadUpdated?.()
      },
    })

    return () => {
      unsubscribe()
    }
  }, [open, selectedConv?.id, refreshConversations, onUnreadUpdated])

  // 选中会话
  const handleSelectConversation = (conv: ImConversation) => {
    setTargetJump(null)
    setSelectedConv(conv)
    if (conv.unread_count > 0) {
      // 乐观清除该会话未读数
      setConversations((prev) =>
        prev.map((c) => (c.id === conv.id ? { ...c, unread_count: 0 } : c))
      )
      onUnreadUpdated?.()
    }
  }

  // 点击历史消息搜索结果直接定位会话与消息切片
  const handleSelectSearchResult = (result: ImSearchResult) => {
    setTargetJump(null)
    const existing = conversations.find((c) => c.id === result.conversation_id)
    if (existing) {
      handleSelectConversation(existing)
      setTargetJump({ seq: result.seq, messageId: result.message_id })
      return
    }
    // 列表里没有该会话（例如刚被创建/不在当前分页内）：先刷新列表再定位
    void refreshConversations(result.conversation_id).then((items) => {
      if (items?.some((c) => c.id === result.conversation_id)) {
        setTargetJump({ seq: result.seq, messageId: result.message_id })
      }
    })
  }

  // 发起新聊天
  const handleCreateChat = async (targetUserId: string) => {
    if (!teamId) return
    try {
      const conv = await imApi.createDirectConversation(teamId, targetUserId)
      await refreshConversations(conv.id)
    } catch (err) {
      console.error('Failed to create direct conversation:', err)
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-[92vw] !max-w-5xl lg:!max-w-6xl h-[780px] max-h-[90vh] p-0 overflow-hidden flex flex-col gap-0 border shadow-2xl">
          <DialogHeader className="sr-only">
            <DialogTitle>{t('title')}</DialogTitle>
          </DialogHeader>

          {/* 模态框主体：双栏架构 */}
          <div className="flex flex-1 min-h-0 overflow-hidden">
            {/* 左栏：会话列表 */}
            <ConversationList
              teamId={teamId}
              conversations={conversations}
              selectedId={selectedConv?.id || null}
              onSelect={handleSelectConversation}
              onSelectSearchResult={handleSelectSearchResult}
              onNewChat={() => setNewChatOpen(true)}
              search={search}
              onSearchChange={setSearch}
            />

            {/* 右栏：聊天窗口 */}
            <ChatWindow
              conversation={selectedConv}
              currentUserId={currentUserId}
              incomingMessage={liveMessage}
              targetSeq={targetJump?.seq}
              targetMessageId={targetJump?.messageId}
              onMessageSent={() => {
                refreshConversations()
              }}
            />
          </div>
        </DialogContent>
      </Dialog>

      {/* 选择团队成员发起对话的小弹窗 */}
      {teamId && (
        <NewChatDialog
          open={newChatOpen}
          onOpenChange={setNewChatOpen}
          teamId={teamId}
          onSelectUser={handleCreateChat}
        />
      )}
    </>
  )
}
