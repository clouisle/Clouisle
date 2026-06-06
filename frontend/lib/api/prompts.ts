import { api, ApiError, type ApiResponse } from './client'
import type {
  AgentKnowledgeBaseConfig,
  FileUploadConfig,
  ImageGenerationConfig,
  MemoryConfig,
  RAGMode,
  ToolConfig,
  VariableDefinition,
  VideoGenerationConfig,
} from './agents'

// ============ Types ============

export interface PromptGenerateToolContext extends ToolConfig {
  display_name?: string | null
  description?: string | null
}

export interface PromptGenerateKnowledgeBaseContext {
  name: string
  description?: string | null
  config?: AgentKnowledgeBaseConfig | null
}

export interface PromptGenerateCapabilitiesContext {
  enable_vision?: boolean
  enable_file_upload?: boolean
  file_upload_config?: FileUploadConfig | null
  enable_user_input_request?: boolean
  enable_memory?: boolean
  memory_config?: MemoryConfig | null
  enable_image_generation?: boolean
  image_generation_config?: ImageGenerationConfig | null
  enable_video_generation?: boolean
  video_generation_config?: VideoGenerationConfig | null
}

export interface PromptGenerateContext {
  agent_name?: string | null
  agent_description?: string | null
  tools?: PromptGenerateToolContext[] | null
  knowledge_bases?: PromptGenerateKnowledgeBaseContext[] | null
  variables?: VariableDefinition[] | null
  rag_mode?: RAGMode | null
  capabilities?: PromptGenerateCapabilitiesContext | null
}

export interface PromptStyle {
  tone: 'professional' | 'friendly' | 'concise' | 'detailed'
  focus: 'task-oriented' | 'conversational' | 'balanced'
  include_cot: boolean
  include_constraints: boolean
}

export interface PromptGenerateRequest {
  description: string
  context?: PromptGenerateContext | null
  style?: PromptStyle | null
  language?: 'zh' | 'en'
}

export interface PromptOptimizeRequest {
  current_prompt: string
  feedback: string
}

// SSE Event Types
export type PromptSSEEventType = 'start' | 'content_delta' | 'complete' | 'error'

export interface PromptSSEStart {
  model: string
}

export interface PromptSSEContentDelta {
  delta: string
}

export interface PromptSSEComplete {
  total_length: number
}

export interface PromptSSEError {
  code: number
  msg: string
}

export type PromptSSEEvent =
  | { type: 'start'; data: PromptSSEStart }
  | { type: 'content_delta'; data: PromptSSEContentDelta }
  | { type: 'complete'; data: PromptSSEComplete }
  | { type: 'error'; data: PromptSSEError }

// ============ SSE Parser ============

export async function* parsePromptSSEStream(
  response: Response
): AsyncGenerator<PromptSSEEvent> {
  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('Response body is not readable')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Process complete events
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // Keep incomplete line in buffer

      let currentEventType: PromptSSEEventType | null = null

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim() as PromptSSEEventType
        } else if (line.startsWith('data: ') && currentEventType) {
          const data = line.slice(6)
          try {
            const parsed = JSON.parse(data)
            yield { type: currentEventType, data: parsed } as PromptSSEEvent
          } catch {
            // Ignore malformed JSON
          }
          currentEventType = null
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// ============ API ============

export const promptsApi = {
  /**
   * Generate prompt (SSE streaming)
   */
  generate: async (request: PromptGenerateRequest): Promise<Response> => {
    const response = await fetch(`${api.getBaseUrl()}/prompts/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...api.getAuthHeaders(),
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      const responseData = await response.json() as ApiResponse
      if (responseData && typeof responseData === 'object' && responseData.code !== undefined) {
        throw new ApiError(responseData.code, responseData.msg, responseData.data)
      }
      throw new Error(`Failed to generate prompt: ${response.status}`)
    }

    return response
  },

  /**
   * Optimize prompt (SSE streaming)
   */
  optimize: async (request: PromptOptimizeRequest): Promise<Response> => {
    const params = new URLSearchParams({
      current_prompt: request.current_prompt,
      feedback: request.feedback,
    })

    const response = await fetch(`${api.getBaseUrl()}/prompts/optimize?${params}`, {
      method: 'POST',
      headers: {
        ...api.getAuthHeaders(),
      },
    })

    if (!response.ok) {
      throw new Error(`Failed to optimize prompt: ${response.status}`)
    }

    return response
  },
}
