import { api } from './client'

export type ImConversationType = 'direct' | 'system'
export type ImMessageType = 'text' | 'markdown' | 'card' | 'system_notice' | 'file'

export interface ImPeer {
  id: string
  username: string
  full_name: string
  avatar_url?: string | null
}

export interface ImConversation {
  id: string
  type: ImConversationType
  team_id: string
  is_pinned: boolean
  is_muted: boolean
  last_read_seq: number
  latest_seq: number
  unread_count: number
  last_message_content?: string | null
  last_message_at?: string | null
  peer?: ImPeer | null
  created_at: string
  updated_at: string
}

export interface ImMessage {
  id: string
  conversation_id: string
  sender_id?: string | null
  client_msg_id?: string | null
  seq: number
  msg_type: ImMessageType
  content: string
  payload?: Record<string, unknown> | null
  status: string
  created_at: string
  attachment?: ImAttachment | null
}

export interface ImAttachment {
  asset_id: string
  filename: string
  size: number
  content_type: string
  url: string
}

export interface ImMessageListResponse {
  messages: ImMessage[]
  has_more: boolean
}

export interface ImTeamChatCandidate {
  id: string
  username: string
  full_name: string
  avatar_url?: string | null
  role: string
}
export interface ImSearchResult {
  message_id: string
  conversation_id: string
  seq: number
  content: string
  msg_type: ImMessageType
  conversation_type: ImConversationType
  created_at: string
  peer?: ImPeer | null
}

export interface ImEventCallbacks {
  onNewMessage?: (message: ImMessage) => void
  onConversationRead?: (data: { conversation_id: string; last_read_seq: number }) => void
  onError?: (err: unknown) => void
}


export const imApi = {
  listConversations: async (teamId: string): Promise<ImConversation[]> => {
    return api.get('/im/conversations', { params: { team_id: teamId } })
  },

  createDirectConversation: async (teamId: string, targetUserId: string): Promise<ImConversation> => {
    return api.post('/im/conversations/direct', { team_id: teamId, target_user_id: targetUserId })
  },

  getMessages: async (
    conversationId: string,
    params?: { before_seq?: number; after_seq?: number; around_seq?: number; limit?: number }
  ): Promise<ImMessageListResponse> => {
    return api.get(`/im/conversations/${conversationId}/messages`, { params })
  },

  sendMessage: async (
    conversationId: string,
    payload: {
      content: string
      client_msg_id?: string
      msg_type?: ImMessageType
      payload?: Record<string, unknown>
      asset_id?: string
    }
  ): Promise<ImMessage> => {
    return api.post(`/im/conversations/${conversationId}/messages`, payload)
  },

  uploadAttachment: async (conversationId: string, file: File): Promise<ImAttachment> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/im/conversations/${conversationId}/attachments`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  markRead: async (conversationId: string, upToSeq?: number): Promise<{ cleared: number }> => {
    return api.post(`/im/conversations/${conversationId}/read`, { up_to_seq: upToSeq })
  },

  getUnreadCount: async (options?: { silent?: boolean; skipAuthRedirect?: boolean }): Promise<{ total: number }> => {
    return api.get('/im/unread-count', {
      silent: options?.silent,
      skipAuthRedirect: options?.skipAuthRedirect,
    })
  },

  listTeamCandidates: async (teamId: string): Promise<ImTeamChatCandidate[]> => {
    return api.get('/im/team-members', { params: { team_id: teamId } })
  },

  searchMessages: async (teamId: string, query: string, limit?: number): Promise<ImSearchResult[]> => {
    return api.get('/im/search', { params: { team_id: teamId, q: query, limit } })
  },

  subscribeEvents: (callbacks: ImEventCallbacks): (() => void) => {
    const controller = new AbortController()
    let closed = false

    const connect = async () => {
      const url = `${api.getBaseUrl()}/im/events`
      try {
        const response = await fetch(url, {
          headers: { ...api.getAuthHeaders(), Accept: 'text/event-stream' },
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          throw new Error(`im_events_connect_failed:${response.status}`)
        }
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let eventType = ''
        let eventData = ''

        while (!closed) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          for (const line of lines) {
            if (line.startsWith(':')) {
              continue
            }
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              eventData = line.slice(5).trim()
            } else if (line === '' && eventData) {
              try {
                const payload = JSON.parse(eventData)
                if (eventType === 'new_message') {
                  callbacks.onNewMessage?.(payload as ImMessage)
                } else if (eventType === 'conversation_read') {
                  callbacks.onConversationRead?.(payload)
                }
              } catch {
                // ignore json parse error
              }
              eventType = ''
              eventData = ''
            }
          }
        }
      } catch (err) {
        if (!closed && !controller.signal.aborted) {
          callbacks.onError?.(err)
          setTimeout(() => {
            if (!closed) connect()
          }, 3000)
        }
      }
    }

    connect()

    return () => {
      closed = true
      controller.abort()
    }
  },
}
