/**
 * Utility functions to convert backend Message format to frontend ChatMessage format
 * Supports: text, images, files, reasoning, tool calls, RAG context
 */

import type {
  ChatMessage,
  MessagePart,
  TextPart,
  ImagePart,
  FilePart,
  ReasoningPart,
  ToolCallPart,
  ToolResultPart,
  SourceDocumentPart,
} from '@/components/chat'
import { isSourcePart, isTextPart } from '@/components/chat'

/**
 * Backend Message format (from API response)
 */
export interface BackendMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  // Attachments (for user messages)
  images?: Array<{
    type: string
    url: string
  }> | null
  file_urls?: Array<{
    filename: string
    url: string
    size: number
    mime_type: string
  }> | null
  // Tool calls (for assistant messages)
  tool_calls?: Array<{
    id: string
    name: string
    display_name?: string
    arguments: Record<string, unknown>
  }> | null
  tool_call_id?: string | null
  tool_name?: string | null
  // Reasoning (for assistant messages with CoT)
  reasoning_content?: string | null
  // RAG context
  rag_context?: Array<{
    document_id: string
    document_name: string
    content: string
    kb_id?: string
    kb_name?: string
    score?: number
  }> | null
  // Metadata
  model_used?: string | null
  token_usage?: {
    prompt: number
    completion: number
  } | null
  duration_ms?: number | null
  created_at: string
  // Version info
  parent_id?: string | null
  is_active?: boolean
  version_number?: number
  version_count?: number
}

/**
 * Convert a backend Message to a frontend ChatMessage
 * Handles all message parts: text, images, files, reasoning, tool calls, RAG context
 */
export function convertBackendMessage(message: BackendMessage): ChatMessage | null {
  // Skip tool role messages (they are represented via tool_result parts in assistant messages)
  if (message.role === 'tool' || message.role === 'system') {
    return null
  }

  const parts: MessagePart[] = []

  if (message.role === 'user') {
    // User message: text + images + files
    if (message.content) {
      parts.push({
        type: 'text',
        text: message.content,
        state: 'done',
      } as TextPart)
    }

    // Add images
    if (message.images && Array.isArray(message.images)) {
      for (const img of message.images) {
        parts.push({
          type: 'image',
          url: img.url,
        } as ImagePart)
      }
    }

    // Add files
    if (message.file_urls && Array.isArray(message.file_urls)) {
      for (const file of message.file_urls) {
        parts.push({
          type: 'file',
          filename: file.filename,
          url: file.url,
          size: file.size,
          mimeType: file.mime_type,
        } as FilePart)
      }
    }
  } else if (message.role === 'assistant') {
    // Assistant message: reasoning + text + tool calls
    // Note: RAG context is stored with user messages and attached in convertBackendMessages()

    // Add reasoning content first (if exists)
    if (message.reasoning_content) {
      parts.push({
        type: 'reasoning',
        text: message.reasoning_content,
        state: 'done',
        duration: message.duration_ms ?? undefined,
      } as ReasoningPart)
    }

    // Add text content
    if (message.content) {
      parts.push({
        type: 'text',
        text: message.content,
        state: 'done',
      } as TextPart)
    }

    // Add tool calls
    if (message.tool_calls && Array.isArray(message.tool_calls)) {
      for (const tc of message.tool_calls) {
        parts.push({
          type: 'tool-call',
          toolCallId: tc.id,
          toolName: tc.name,
          toolDisplayName: tc.display_name,
          input: tc.arguments || {},
          state: 'done',
        } as ToolCallPart)
      }
    }
  }

  return {
    id: message.id,
    role: message.role as 'user' | 'assistant',
    parts,
    createdAt: new Date(message.created_at),
    versionNumber: message.version_number,
    versionCount: message.version_count,
  }
}

/**
 * Convert an array of backend messages to frontend ChatMessages
 * Filters out tool and system messages, handles tool results by attaching to previous assistant message
 * RAG context is stored with user messages but displayed with the following assistant response
 */
export function convertBackendMessages(messages: BackendMessage[]): ChatMessage[] {
  const result: ChatMessage[] = []
  
  // Create a map for tool results by tool_call_id
  const toolResults = new Map<string, BackendMessage>()
  for (const msg of messages) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      toolResults.set(msg.tool_call_id, msg)
    }
  }

  // Track RAG context from user messages to attach to the following assistant message
  let pendingRagContext: BackendMessage['rag_context'] = null
  // Track assistant tool-call messages to merge into the next assistant reply
  let pendingToolParts: MessagePart[] = []

  const aggregateRagContext = (
    contexts: BackendMessage['rag_context']
  ): BackendMessage['rag_context'] => {
    if (!contexts || contexts.length === 0) return contexts

    const map = new Map<string, { ctx: NonNullable<BackendMessage['rag_context']>[number]; contents: string[]; score?: number }>()
    const order: string[] = []

    for (const ctx of contexts) {
      const key = `${ctx.kb_id || ''}:${ctx.document_id || ctx.document_name || ''}`
      if (!map.has(key)) {
        map.set(key, {
          ctx: { ...ctx },
          contents: [],
          score: typeof ctx.score === 'number' ? ctx.score : undefined,
        })
        order.push(key)
      }
      const entry = map.get(key)!
      if (typeof ctx.content === 'string' && ctx.content.trim()) {
        entry.contents.push(ctx.content)
      }
      if (typeof ctx.score === 'number') {
        entry.score = entry.score == null ? ctx.score : Math.max(entry.score, ctx.score)
      }
    }

    return order.map((key) => {
      const entry = map.get(key)!
      return {
        ...entry.ctx,
        score: entry.score,
        content: entry.contents.join('\n\n'),
      }
    })
  }

  for (const message of messages) {
    if (message.role === 'tool' || message.role === 'system') {
      continue
    }

    // Capture RAG context from user messages
    if (message.role === 'user' && message.rag_context && Array.isArray(message.rag_context)) {
      pendingRagContext = aggregateRagContext(message.rag_context)
    }

    const chatMessage = convertBackendMessage(message)
    if (!chatMessage) continue

    const isToolCallAssistant =
      message.role === 'assistant' &&
      Array.isArray(message.tool_calls) &&
      message.tool_calls.length > 0

    // If assistant message, add pending RAG context from previous user message
    if (message.role === 'assistant') {
      // If assistant message has tool calls, add corresponding tool results
      if (message.tool_calls && Array.isArray(message.tool_calls)) {
        // Find tool call parts and add results after each
        const partsWithResults: MessagePart[] = []
        
        for (const part of chatMessage.parts) {
          partsWithResults.push(part)
          
          // If this is a tool-call part, add its result
          if (part.type === 'tool-call') {
            const toolCallPart = part as ToolCallPart
            const toolResultMsg = toolResults.get(toolCallPart.toolCallId)
            if (toolResultMsg) {
              partsWithResults.push({
                type: 'tool-result',
                toolCallId: toolCallPart.toolCallId,
                toolName: toolResultMsg.tool_name || toolCallPart.toolName,
                output: toolResultMsg.content,
                isError: false,
              } as ToolResultPart)
            }
          }
        }
        
        chatMessage.parts = partsWithResults
      }

      // Add RAG context as source documents (from pending user message)
      if (!isToolCallAssistant && pendingRagContext && pendingRagContext.length > 0) {
        for (const ctx of pendingRagContext) {
          chatMessage.parts.push({
            type: 'source-document',
            sourceId: ctx.document_id,
            documentId: ctx.document_id,
            documentName: ctx.document_name,
            content: ctx.content,
            metadata: {
              kb_id: ctx.kb_id,
              kb_name: ctx.kb_name,
              score: ctx.score,
            },
          } as SourceDocumentPart)
        }
        // Clear pending RAG context after attaching
        pendingRagContext = null
      }
    }

    // Defer tool-call assistant messages so they can be merged
    // into the following assistant response (matching call position).
    if (isToolCallAssistant) {
      pendingToolParts = pendingToolParts.concat(chatMessage.parts)
      continue
    }

    if (pendingToolParts.length > 0 && message.role === 'assistant') {
      const sources = chatMessage.parts.filter(isSourcePart)
      const nonSourceParts: MessagePart[] = chatMessage.parts.filter((p) => !isSourcePart(p))
      const insertIndex = nonSourceParts.findIndex(isTextPart)
      if (insertIndex === -1) {
        nonSourceParts.push(...pendingToolParts)
      } else {
        nonSourceParts.splice(insertIndex, 0, ...pendingToolParts)
      }
      chatMessage.parts = [...nonSourceParts, ...sources]
      pendingToolParts = []
    }

    result.push(chatMessage)
  }

  if (pendingToolParts.length > 0) {
    result.push({
      id: `assistant-tool-${Date.now()}`,
      role: 'assistant',
      parts: pendingToolParts,
      createdAt: new Date(),
    })
  }

  return result
}

/**
 * Type guard to check if an object is a BackendMessage
 */
export function isBackendMessage(obj: unknown): obj is BackendMessage {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'role' in obj &&
    'content' in obj
  )
}
