/**
 * Embed API client - uses API Key authentication instead of JWT.
 * Used by embed pages loaded in iframes on external websites.
 */

import { API_BASE_URL } from '@/lib/constants'
import { getErrorMessage } from './client'
import type {
  AgentRunAnswerInput,
  AgentRunEventOut,
  AgentRunStartOut,
  AgentRunStatusOut,
  ConversationListItem,
  PageData,
} from './agents'
import type { NodeExecution, WorkflowRun, WorkflowRunListItem } from './workflows'

export interface EmbedWorkflowInputParameter {
  name: string
  type: string
  required: boolean
  label?: string
  description?: string
  default?: unknown
  options?: string[]
}

export interface EmbedWorkflowInfo {
  id: string
  name: string
  description: string | null
  icon: string | null
  variables: Array<Record<string, unknown>>
  /** Start-node parameters projected by the API for the embed run form. */
  input_parameters?: EmbedWorkflowInputParameter[]
  embed_config: Record<string, unknown>
}

export interface EmbedWorkflowRunResponse {
  run_id: string
  stream_url: string
}

export interface EmbedAgentInfo {
  id: string
  name: string
  description: string | null
  icon: string | null
  avatar_url: string | null
  opening_message: string | null
  suggested_questions: string[]
  variables: Array<Record<string, unknown>>
  input_modalities: string[]
  enable_attachments: boolean
  attachment_config: Record<string, unknown> | null
  hide_tool_calls: boolean
  hide_message_actions: boolean
  hide_reasoning: boolean
  enable_citations: boolean
  hide_artifact_list: boolean
  embed_config: Record<string, unknown>
}

export interface EmbedChatRequest {
  message: string
  images?: Array<{ type: string; url: string }>
  file_urls?: Array<{ filename: string; url: string; size: number; mime_type: string }>
  conversation_id?: string | null
  variables?: Record<string, unknown>
}

type EmbedRunInput = {
  delivery: 'steer' | 'follow_up' | 'auto'
  content?: string
  request_id?: string
}

async function requestEmbedRun<T>(path: string, apiKey: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...makeHeaders(apiKey),
      ...(init?.headers ?? {}),
    },
  })
  const data = await response.json().catch(() => ({})) as { data?: T; msg?: unknown }
  if (!response.ok) {
    throw new Error(resolveEmbedApiErrorMessage(response.status, data.msg))
  }
  return data.data as T
}

export interface EmbedConversationSummary {
  id: string
  title?: string | null
}

export interface EmbedConversationDetail {
  id: string
  title?: string | null
  /** Visible messages of the conversation, newest last. */
  messages: EmbedMessage[]
  /** Durable run this credential is still waiting on, if any. */
  active_run_id?: string | null
}

export interface EmbedMessage {
  id: string
  conversation_id: string
  role: string
  content: string
  images?: Array<Record<string, unknown>> | null
  file_urls?: Array<Record<string, unknown>> | null
  tool_calls?: Array<Record<string, unknown>> | null
  tool_call_id?: string | null
  tool_name?: string | null
  reasoning_content?: string | null
  model_used?: string | null
  token_usage?: Record<string, number> | null
  duration_ms?: number | null
  rag_context?: Array<Record<string, unknown>> | null
  created_at: string
  parent_id?: string | null
  is_active: boolean
  version_number: number
  version_count: number
}

function makeHeaders(apiKey: string): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`,
  }
}

function getEmbedLocale(): string {
  if (typeof document === 'undefined') return 'en'
  const locale = document.cookie
    .split('; ')
    .find(row => row.startsWith('locale='))
    ?.split('=')[1]
  return locale || 'en'
}

function isLikelyMessageKey(message: string): boolean {
  return /^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(message.trim())
}

function isLikelyTechnicalMessage(message: string): boolean {
  const lowered = message.toLowerCase()
  return (
    message.includes('\n')
    || lowered.startsWith('http ')
    || lowered.includes('traceback')
    || lowered.includes('exception')
    || lowered.includes('stack')
    || lowered.includes('failed to fetch')
  )
}

function getEmbedStatusErrorMessage(status: number): string {
  if (status === 404) return getErrorMessage('resourceNotFound')
  if (status >= 500 && status < 600) return getErrorMessage('serverErrorDescription')
  return getErrorMessage('requestFailed')
}

function shouldUseEmbedBackendMessage(message: string): boolean {
  const trimmed = message.trim()
  if (!trimmed || trimmed.length > 200) return false
  if (isLikelyMessageKey(trimmed) || isLikelyTechnicalMessage(trimmed)) return false

  const locale = getEmbedLocale().toLowerCase()
  if (locale.startsWith('zh')) {
    return /[\u4e00-\u9fff]/.test(trimmed)
  }

  return true
}

function resolveEmbedApiErrorMessage(status: number, message: unknown): string {
  if (typeof message === 'string' && shouldUseEmbedBackendMessage(message)) {
    return message.trim()
  }

  return getEmbedStatusErrorMessage(status)
}

export function resolveEmbedMessage(message: unknown, fallback: string): string {
  if (typeof message === 'string' && shouldUseEmbedBackendMessage(message)) {
    return message.trim()
  }

  return fallback
}

export const embedApi = {
  getAgentInfo: async (agentId: string, apiKey: string): Promise<EmbedAgentInfo> => {
    const response = await fetch(`${API_BASE_URL}/embed/agents/${agentId}/info`, {
      headers: makeHeaders(apiKey),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(resolveEmbedApiErrorMessage(response.status, error.msg))
    }

    const data = await response.json()
    return data.data
  },

  chatStream: (
    agentId: string,
    data: EmbedChatRequest,
    apiKey: string
  ): { stream: Promise<Response>; abort: () => void } => {
    const controller = new AbortController()

    const stream = fetch(`${API_BASE_URL}/embed/agents/${agentId}/chat/stream`, {
      method: 'POST',
      headers: makeHeaders(apiKey),
      body: JSON.stringify(data),
      signal: controller.signal,
    })

    return {
      stream,
      abort: () => controller.abort(),
    }
  },

  startRun: (
    agentId: string,
    data: EmbedChatRequest,
    apiKey: string
  ): Promise<AgentRunStartOut> => requestEmbedRun<AgentRunStartOut>(
    `/embed/agents/${agentId}/chat/runs`,
    apiKey,
    { method: 'POST', body: JSON.stringify(data) },
  ),

  streamRun: (
    agentId: string,
    runId: string,
    apiKey: string,
    afterSequence = 0,
  ): { stream: Promise<Response>; abort: () => void } => {
    const controller = new AbortController()
    const stream = fetch(
      `${API_BASE_URL}/embed/agents/${agentId}/chat/runs/${runId}/stream?after_sequence=${afterSequence}`,
      {
        headers: { Accept: 'text/event-stream', Authorization: `Bearer ${apiKey}` },
        signal: controller.signal,
      },
    )
    return { stream, abort: () => controller.abort() }
  },

  getRunStatus: (agentId: string, runId: string, apiKey: string): Promise<AgentRunStatusOut> =>
    requestEmbedRun<AgentRunStatusOut>(`/embed/agents/${agentId}/chat/runs/${runId}`, apiKey),

  getRunEvents: (
    agentId: string,
    runId: string,
    apiKey: string,
    afterSequence = 0,
  ): Promise<AgentRunEventOut[]> => requestEmbedRun<AgentRunEventOut[]>(
    `/embed/agents/${agentId}/chat/runs/${runId}/events?after_sequence=${afterSequence}`,
    apiKey,
  ),

  postRunInput: (
    agentId: string,
    runId: string,
    body: EmbedRunInput,
    apiKey: string,
  ): Promise<AgentRunStatusOut> => requestEmbedRun<AgentRunStatusOut>(
    `/embed/agents/${agentId}/chat/runs/${runId}/inputs`,
    apiKey,
    { method: 'POST', body: JSON.stringify(body) },
  ),

  postRunAnswer: (
    agentId: string,
    runId: string,
    body: AgentRunAnswerInput,
    apiKey: string,
  ): Promise<AgentRunStatusOut> => requestEmbedRun<AgentRunStatusOut>(
    `/embed/agents/${agentId}/chat/runs/${runId}/answers`,
    apiKey,
    { method: 'POST', body: JSON.stringify(body) },
  ),

  stopRun: (agentId: string, runId: string, apiKey: string): Promise<AgentRunStatusOut> =>
    requestEmbedRun<AgentRunStatusOut>(
      `/embed/agents/${agentId}/chat/runs/${runId}/stop`,
      apiKey,
      { method: 'POST' },
    ),

  getMessages: async (
    agentId: string,
    conversationId: string,
    apiKey: string
  ): Promise<EmbedMessage[]> => {
    const response = await fetch(
      `${API_BASE_URL}/embed/agents/${agentId}/conversations/${conversationId}/messages`,
      { headers: makeHeaders(apiKey) }
    )

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(resolveEmbedApiErrorMessage(response.status, error.msg))
    }

    const data = await response.json()
    return data.data
  },

  // ============ Key-scoped history ============
  //
  // Embed history is read and mutated through the API-key scoped routes: they
  // filter rows by the exact key that created them, so a page holding another
  // key (or a logged-in session) can never read or change this history. Only
  // the credential travels in the request; a browser session token is never
  // added, which keeps the embed surface bound to its own key.

  getConversations: (
    agentId: string,
    apiKey: string,
    params: { page?: number; pageSize?: number } = {},
  ): Promise<PageData<ConversationListItem>> => {
    const { page = 1, pageSize = 20 } = params
    return requestEmbedRun<PageData<ConversationListItem>>(
      `/agents/${agentId}/conversations?page=${page}&page_size=${pageSize}`,
      apiKey,
      { cache: 'no-store' },
    )
  },

  getConversation: (conversationId: string, apiKey: string): Promise<EmbedConversationDetail> =>
    requestEmbedRun<EmbedConversationDetail>(
      `/agents/conversations/${conversationId}`,
      apiKey,
      { cache: 'no-store' },
    ),

  renameConversation: (
    agentId: string,
    conversationId: string,
    title: string,
    apiKey: string,
  ): Promise<EmbedConversationSummary> => requestEmbedRun<EmbedConversationSummary>(
    `/embed/agents/${agentId}/conversations/${conversationId}`,
    apiKey,
    { method: 'PATCH', body: JSON.stringify({ title }) },
  ),

  deleteConversation: (
    agentId: string,
    conversationId: string,
    apiKey: string,
  ): Promise<void> => requestEmbedRun<{ id: string }>(
    `/embed/agents/${agentId}/conversations/${conversationId}`,
    apiKey,
    { method: 'DELETE' },
  ).then(() => undefined),

  getWorkflowRuns: (
    workflowId: string,
    apiKey: string,
    params: { page?: number; pageSize?: number } = {},
  ): Promise<PageData<WorkflowRunListItem>> => {
    const { page = 1, pageSize = 20 } = params
    return requestEmbedRun<PageData<WorkflowRunListItem>>(
      `/workflows/${workflowId}/runs/mine?page=${page}&page_size=${pageSize}`,
      apiKey,
      { cache: 'no-store' },
    )
  },

  getWorkflowRun: (
    workflowId: string,
    runId: string,
    apiKey: string,
  ): Promise<WorkflowRun> => requestEmbedRun<WorkflowRun>(
    `/workflows/${workflowId}/runs/mine/${runId}`,
    apiKey,
    { cache: 'no-store' },
  ),

  getWorkflowRunNodes: (
    workflowId: string,
    runId: string,
    apiKey: string,
  ): Promise<NodeExecution[]> => requestEmbedRun<NodeExecution[]>(
    `/workflows/${workflowId}/runs/mine/${runId}/nodes`,
    apiKey,
    { cache: 'no-store' },
  ),

  uploadFile: async (
    agentId: string,
    file: File,
    apiKey: string,
    onProgress?: (percent: number) => void
  ): Promise<{ url: string; filename: string; original_name: string; size: number; content_type: string }> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE_URL}/embed/agents/${agentId}/upload/file?category=documents`)
      xhr.setRequestHeader('Authorization', `Bearer ${apiKey}`)

      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded * 100) / e.total))
          }
        }
      }

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const data = JSON.parse(xhr.responseText)
          resolve(data.data)
        } else {
          const response = JSON.parse(xhr.responseText)
          reject(new Error(resolveEmbedApiErrorMessage(xhr.status, response.msg)))
        }
      }
      xhr.onerror = () => reject(new Error(getErrorMessage('requestFailed')))

      const formData = new FormData()
      formData.append('file', file)
      xhr.send(formData)
    })
  },

  // ============ Workflow Embed API ============

  getWorkflowInfo: async (workflowId: string, apiKey: string): Promise<EmbedWorkflowInfo> => {
    const response = await fetch(`${API_BASE_URL}/embed/workflows/${workflowId}/info`, {
      headers: makeHeaders(apiKey),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(resolveEmbedApiErrorMessage(response.status, error.msg))
    }

    const data = await response.json()
    return data.data
  },

  runWorkflow: async (
    workflowId: string,
    inputs: Record<string, unknown>,
    apiKey: string
  ): Promise<EmbedWorkflowRunResponse> => {
    const response = await fetch(`${API_BASE_URL}/embed/workflows/${workflowId}/run`, {
      method: 'POST',
      headers: makeHeaders(apiKey),
      body: JSON.stringify({ inputs }),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(resolveEmbedApiErrorMessage(response.status, error.msg))
    }

    const data = await response.json()
    return data.data
  },

  streamWorkflowRun: (
    runId: string,
    apiKey: string,
    options: {
      fromSequence?: number
      onEvent?: (event: { type: string; data: Record<string, unknown>; sequence: number; timestamp: string }) => void
      onError?: (error: Error) => void
      onComplete?: () => void
    } = {}
  ): (() => void) => {
    const { fromSequence = 0, onEvent, onError, onComplete } = options
    const controller = new AbortController()

    const connect = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/embed/workflows/runs/${runId}/stream?from_sequence=${fromSequence}`,
          {
            headers: { Authorization: `Bearer ${apiKey}`, Accept: 'text/event-stream' },
            signal: controller.signal,
          }
        )

        if (!response.ok) throw new Error(getEmbedStatusErrorMessage(response.status))

        const reader = response.body?.getReader()
        if (!reader) throw new Error(getErrorMessage('requestFailed'))

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) { onComplete?.(); break }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let eventType = ''
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              eventData = line.slice(5).trim()
            } else if (line === '' && eventData) {
              try {
                const parsedData = JSON.parse(eventData)
                const eventDataWithNodeId = { ...parsedData.data, node_id: parsedData.node_id }
                onEvent?.({
                  type: eventType || parsedData.event || 'message',
                  data: eventDataWithNodeId,
                  sequence: parsedData.sequence || 0,
                  timestamp: parsedData.timestamp || new Date().toISOString(),
                })
              } catch { /* ignore parse errors */ }
              eventType = ''
              eventData = ''
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name !== 'AbortError') onError?.(error)
      }
    }

    connect()
    return () => controller.abort()
  },
}
