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
    // Assistant message: reasoning + text + tool calls + RAG context

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
          input: tc.arguments || {},
          state: 'done',
        } as ToolCallPart)
      }
    }

    // Add RAG context as source documents
    if (message.rag_context && Array.isArray(message.rag_context)) {
      for (const ctx of message.rag_context) {
        parts.push({
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

  for (const message of messages) {
    if (message.role === 'tool' || message.role === 'system') {
      continue
    }

    const chatMessage = convertBackendMessage(message)
    if (!chatMessage) continue

    // If assistant message has tool calls, add corresponding tool results
    if (message.role === 'assistant' && message.tool_calls && Array.isArray(message.tool_calls)) {
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

    result.push(chatMessage)
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
