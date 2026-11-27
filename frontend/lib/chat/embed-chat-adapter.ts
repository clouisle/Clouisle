import { embedApi, type EmbedAgentInfo } from '@/lib/api/embed'
import type { ChatPageAdapter } from '@/lib/chat/chat-adapter'
import { purgeLegacyEmbedHistory } from '@/lib/embed/legacy-history-cache'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import type {
  PublicAgent,
  VariableDefinition,
  VariableType,
  AttachmentConfig,
  AgentRunAnswerInput,
} from '@/lib/api'

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
    input_modalities: info.input_modalities,
    enable_attachments: info.enable_attachments,
    attachment_config: (info.attachment_config as AttachmentConfig | null) ?? null,
    hide_tool_calls: info.hide_tool_calls,
    hide_message_actions: info.hide_message_actions,
    hide_reasoning: info.hide_reasoning,
    enable_citations: info.enable_citations,
    hide_artifact_list: info.hide_artifact_list,
    embed_config: info.embed_config,
  }
}

/**
 * Create a ChatPageAdapter for the embed agent page.
 *
 * Conversation history belongs to the server: the list, the messages and the
 * rename/delete mutations all travel to the API-key scoped routes, which filter
 * by the exact key that created each conversation. A page loaded with another
 * key - or with a logged-in session - therefore cannot list, open or continue
 * this key's conversations.
 *
 * Nothing is written to browser storage. `localStorage` is readable by every
 * script on the origin, so caching messages there would defeat the isolation
 * however the key is named, and the caches left by earlier releases are purged
 * when the adapter is created.
 */
export function createEmbedChatAdapter(agentId: string, apiKey: string): ChatPageAdapter {
  purgeLegacyEmbedHistory()

  return {
    getAgent: async (id) => mapAgentInfo(await embedApi.getAgentInfo(id, apiKey)),

    getConversations: (_agentId, { page, pageSize }) =>
      embedApi.getConversations(agentId, apiKey, { page, pageSize }),

    getConversation: async (id) => {
      const conversation = await embedApi.getConversation(id, apiKey)
      return {
        messages: convertBackendMessages(conversation.messages as unknown as BackendMessage[]),
        activeRunId: conversation.active_run_id ?? null,
      }
    },

    deleteConversation: (id) => embedApi.deleteConversation(agentId, id, apiKey),

    updateConversation: async (id, data) => {
      await embedApi.renameConversation(agentId, id, data.title, apiKey)
    },

    uploadFile: (file, _category, onProgress) =>
      embedApi.uploadFile(agentId, file, apiKey, (percent) => onProgress({ percent })),

    chatStream: (id, request) => embedApi.chatStream(id, request, apiKey),
    startRun: (id, request) => embedApi.startRun(id, request, apiKey),
    streamRun: (id, runId, afterSequence) => embedApi.streamRun(id, runId, apiKey, afterSequence),
    getRunStatus: (id, runId) => embedApi.getRunStatus(id, runId, apiKey),
    getRunEvents: (id, runId, afterSequence) => embedApi.getRunEvents(id, runId, apiKey, afterSequence),
    postRunInput: (id, runId, body) => embedApi.postRunInput(id, runId, body, apiKey),
    postRunAnswer: (id, runId, body: AgentRunAnswerInput) => embedApi.postRunAnswer(id, runId, body, apiKey),
    stopRun: (id, runId) => embedApi.stopRun(id, runId, apiKey),

    // Versioning/edit endpoints are not available in embed mode; the UI hides them.
    editMessageStream: () => { throw new Error('Not supported in embed mode') },
    regenerateStream: () => { throw new Error('Not supported in embed mode') },
    getMessageVersions: async () => [],
    switchMessageVersion: async () => {},
  }
}
