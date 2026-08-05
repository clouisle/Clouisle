import { embedApi, type EmbedAgentInfo } from '@/lib/api/embed'
import type { ChatPageAdapter } from '@/lib/chat/chat-adapter'
import type {
  PublicAgent,
  ConversationListItem,
  VariableDefinition,
  VariableType,
  AttachmentConfig,
} from '@/lib/api'
import type { ChatMessage } from '@/components/chat'

interface EmbedHistoryEntry {
  id: string
  title: string
  createdAt: number
  messages: ChatMessage[]
}

const MAX_ENTRIES = 20

function normalizeVariables(vars: Array<Record<string, unknown>>): VariableDefinition[] {
  const normalized: VariableDefinition[] = []
  for (const v of vars) {
    const name = v.name as string | undefined
    const type = v.type as string | undefined
    if (!name || !type) continue
    normalized.push({
      name,
      type: type as VariableType,
      label: (v.label as string | null | undefined) ?? null,
      required: Boolean(v.required),
      hidden: Boolean(v.hidden),
      default: (v.default as string | null | undefined) ?? null,
      description: (v.description as string | null | undefined) ?? null,
      options: (v.options as string[] | null | undefined) ?? null,
      min: (v.min as number | null | undefined) ?? null,
      max: (v.max as number | null | undefined) ?? null,
      maxLength: (v.maxLength as number | null | undefined) ?? null,
    })
  }
  return normalized
}

function mapAgentInfo(info: EmbedAgentInfo): PublicAgent {
  return {
    id: info.id,
    name: info.name,
    description: info.description,
    icon: info.icon,
    avatar_url: info.avatar_url,
    opening_message: info.opening_message,
    suggested_questions: info.suggested_questions,
    variables: normalizeVariables(info.variables),
    enable_attachments: info.enable_attachments,
    attachment_config: (info.attachment_config as AttachmentConfig | null) ?? null,
    hide_tool_calls: info.hide_tool_calls,
    hide_message_actions: info.hide_message_actions,
    hide_reasoning: info.hide_reasoning,
    embed_config: info.embed_config,
  }
}

function deriveTitle(messages: ChatMessage[]): string {
  for (const m of messages) {
    if (m.role !== 'user') continue
    for (const p of m.parts) {
      if (p.type === 'text') return p.text
    }
  }
  return 'Untitled'
}

/**
 * Create a ChatPageAdapter backed by the API-key embedApi + browser localStorage
 * for conversation history. Used by the embed agent page.
 */
export function createEmbedChatAdapter(agentId: string, apiKey: string): ChatPageAdapter {
  const storageKey = `clouisle:embed:history:agent:${agentId}`

  function readEntries(): EmbedHistoryEntry[] {
    try {
      const raw = localStorage.getItem(storageKey)
      return raw ? (JSON.parse(raw) as EmbedHistoryEntry[]) : []
    } catch {
      return []
    }
  }

  function writeEntries(entries: EmbedHistoryEntry[]) {
    try {
      localStorage.setItem(storageKey, JSON.stringify(entries.slice(0, MAX_ENTRIES)))
    } catch {
      // localStorage may be full or disabled
    }
  }

  return {
    getAgent: async (id) => mapAgentInfo(await embedApi.getAgentInfo(id, apiKey)),

    getConversations: async (_agentId, { page, pageSize }) => {
      const entries = readEntries()
      const items: ConversationListItem[] = entries.map((e) => ({
        id: e.id,
        agent_id: _agentId,
        title: e.title,
        message_count: e.messages.length,
        created_at: new Date(e.createdAt).toISOString(),
        updated_at: new Date(e.createdAt).toISOString(),
      }))
      const start = (page - 1) * pageSize
      return { items: items.slice(start, start + pageSize), total: items.length }
    },

    getConversation: async (id) => {
      const entry = readEntries().find((e) => e.id === id)
      if (!entry) throw new Error('Conversation not found')
      return { messages: entry.messages }
    },

    deleteConversation: async (id) => {
      writeEntries(readEntries().filter((e) => e.id !== id))
    },

    updateConversation: async (id, data) => {
      writeEntries(readEntries().map((e) => (e.id === id ? { ...e, title: data.title } : e)))
    },

    uploadFile: (file, _category, onProgress) =>
      embedApi.uploadFile(agentId, file, apiKey, (percent) => onProgress({ percent })),

    chatStream: (id, request) => embedApi.chatStream(id, request, apiKey),

    // Versioning/edit endpoints are not available in embed mode; the UI hides them.
    editMessageStream: () => { throw new Error('Not supported in embed mode') },
    regenerateStream: () => { throw new Error('Not supported in embed mode') },
    getMessageVersions: async () => [],
    switchMessageVersion: async () => {},

    saveConversation: (messages, conversationId) => {
      if (messages.length === 0) return
      const id = conversationId || `conv-${Date.now()}`
      const title = deriveTitle(messages)
      const entries = readEntries()
      const existing = entries.findIndex((e) => e.id === id)
      if (existing >= 0) {
        entries[existing] = { ...entries[existing], title, messages }
      } else {
        entries.unshift({ id, title, createdAt: Date.now(), messages })
      }
      writeEntries(entries)
    },
  }
}
