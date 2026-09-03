import type { ChatStreamApi } from '@/hooks/use-chat'
import {
  agentsApi,
  publicAgentsApi,
  uploadApi,
  type AgentRunAnswerInput,
  type PublicAgent,
  type ConversationListItem,
  type ChatRequest,
  type UploadResult,
} from '@/lib/api'
import type { ChatMessage } from '@/components/chat'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'

/**
 * Adapter that backs the shared chat page.
 *
 * Extends {@link ChatStreamApi} (the layer useChat consumes) with page-level
 * data access: agent info, conversation CRUD, and file upload. The default
 * implementation wraps the JWT-based publicAgentsApi/agentsApi; embed pages
 * pass an embed-backed implementation that uses API-key auth + localStorage.
 */
export interface ChatPageAdapter extends ChatStreamApi {
  getAgent(id: string): Promise<PublicAgent>
  getConversations(agentId: string, params: { page: number; pageSize: number }): Promise<{ items: ConversationListItem[]; total: number }>
  deleteConversation(id: string): Promise<void>
  updateConversation(id: string, data: { title: string }): Promise<void>
  uploadFile(file: File, category: string, onProgress: (p: { percent: number }) => void): Promise<UploadResult>
  /** Persist the current conversation before starting a new one (embed/localStorage only). */
  saveConversation?(messages: ChatMessage[], conversationId: string | null): void
}

export const defaultChatAdapter: ChatPageAdapter = {
  getAgent: (id) => publicAgentsApi.getPublicAgent(id),
  getConversations: (agentId, params) => publicAgentsApi.getConversations(agentId, params),
  getConversation: async (id) => {
    const data = await publicAgentsApi.getConversation(id)
    return { messages: convertBackendMessages(data.messages as BackendMessage[]) }
  },
  deleteConversation: (id) => publicAgentsApi.deleteConversation(id),
  updateConversation: async (id, data) => { await publicAgentsApi.updateConversation(id, data) },
  uploadFile: (file, category, onProgress) => uploadApi.uploadFileWithProgress(file, category, onProgress),

  // ChatStreamApi – versioning/edit endpoints live on agentsApi (auth-only)
  chatStream: (agentId, request: ChatRequest) => publicAgentsApi.chatStream(agentId, request),
  startRun: (agentId, request) => agentsApi.startRun(agentId, request),
  streamRun: (agentId, runId, afterSequence) => agentsApi.streamRun(agentId, runId, afterSequence),
  getRunStatus: (agentId, runId) => publicAgentsApi.getRunStatus(agentId, runId),
  getRunEvents: (agentId, runId, afterSequence) => publicAgentsApi.getRunEvents(agentId, runId, afterSequence),
  postRunInput: (agentId, runId, body) => publicAgentsApi.postRunInput(agentId, runId, body),
  postRunAnswer: (agentId, runId, body: AgentRunAnswerInput) => agentsApi.postRunAnswer(agentId, runId, body),
  stopRun: (agentId, runId) => publicAgentsApi.stopRun(agentId, runId),
  editMessageStream: (agentId, messageId, content) => agentsApi.editMessageStream(agentId, messageId, content),
  regenerateStream: (agentId, messageId, variables) => agentsApi.regenerateStream(agentId, messageId, variables),
  getMessageVersions: (agentId, messageId) => agentsApi.getMessageVersions(agentId, messageId),
  switchMessageVersion: async (agentId, messageId, versionId) => {
    await agentsApi.switchMessageVersion(agentId, messageId, versionId)
  },
}
