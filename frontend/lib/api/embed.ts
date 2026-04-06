/**
 * Embed API client - uses API Key authentication instead of JWT.
 * Used by embed pages loaded in iframes on external websites.
 */

import { API_BASE_URL } from '@/lib/constants'

export interface EmbedWorkflowInfo {
  id: string
  name: string
  description: string | null
  icon: string | null
  variables: Array<Record<string, unknown>>
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
  enable_vision: boolean
  enable_file_upload: boolean
  file_upload_config: Record<string, unknown> | null
  embed_config: Record<string, unknown>
}

export interface EmbedChatRequest {
  message: string
  images?: Array<{ type: string; url: string }>
  file_urls?: Array<{ filename: string; url: string; size: number; mime_type: string }>
  conversation_id?: string | null
  variables?: Record<string, unknown>
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

export const embedApi = {
  getAgentInfo: async (agentId: string, apiKey: string): Promise<EmbedAgentInfo> => {
    const response = await fetch(`${API_BASE_URL}/embed/agents/${agentId}/info`, {
      headers: makeHeaders(apiKey),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ msg: 'Unknown error' }))
      throw new Error(error.msg || `HTTP ${response.status}`)
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
      const error = await response.json().catch(() => ({ msg: 'Unknown error' }))
      throw new Error(error.msg || `HTTP ${response.status}`)
    }

    const data = await response.json()
    return data.data
  },

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
          const error = JSON.parse(xhr.responseText).msg || `HTTP ${xhr.status}`
          reject(new Error(error))
        }
      }
      xhr.onerror = () => reject(new Error('Upload failed'))

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
      const error = await response.json().catch(() => ({ msg: 'Unknown error' }))
      throw new Error(error.msg || `HTTP ${response.status}`)
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
      const error = await response.json().catch(() => ({ msg: 'Unknown error' }))
      throw new Error(error.msg || `HTTP ${response.status}`)
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

        if (!response.ok) throw new Error(`SSE connection failed: ${response.status}`)

        const reader = response.body?.getReader()
        if (!reader) throw new Error('No response body')

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
