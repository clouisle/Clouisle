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
  UserInputRequestPart,
} from '@/components/chat'
import { isSourcePart } from '@/components/chat'
import {
  isMediaImageToolResult,
  isMediaVideoToolResult,
  parseToolResultOutput,
} from '@/lib/utils/tool-result'

/**
 * Backend Message format (from API response)
 */
export interface BackendMessageStep {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls?: Array<{
    id: string
    name: string
    display_name?: string
    arguments: Record<string, unknown>
  }> | null
  tool_call_id?: string | null
  tool_name?: string | null
  reasoning_content?: string | null
  created_at: string
  round_index?: number
  round_role?: 'user_input' | 'assistant_final' | 'assistant_step' | 'tool_result' | null
  iteration_index?: number | null
}

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
  is_manually_stopped?: boolean | null
  round_status?: 'completed' | 'max_iterations_reached' | 'manually_stopped' | 'error' | null
  steps?: BackendMessageStep[] | null
  created_at: string
  // Version info
  parent_id?: string | null
  is_active?: boolean
  version_number?: number
  version_count?: number
}

/**
 * Parse user input request from XML format in message content
 * Returns the parsed request and the content with XML removed
 */
function parseUserInputRequest(content: string): {
  userInputRequest: UserInputRequestPart | null
  cleanContent: string
} {
  // Match <user_input_request>...</user_input_request>
  const regex = /<user_input_request>([\s\S]*?)<\/user_input_request>/
  const match = content.match(regex)

  if (!match) {
    return { userInputRequest: null, cleanContent: content }
  }

  const xmlContent = match[1]

  // Extract question
  const questionMatch = xmlContent.match(/<question>([\s\S]*?)<\/question>/)
  const question = questionMatch ? questionMatch[1].trim() : ''

  // Extract options
  const optionsMatch = xmlContent.match(/<options>([\s\S]*?)<\/options>/)
  const options: string[] = []

  if (optionsMatch) {
    const optionsContent = optionsMatch[1]
    const optionMatches = optionsContent.matchAll(/<option>([\s\S]*?)<\/option>/g)
    for (const optionMatch of optionMatches) {
      const option = optionMatch[1].trim()
      if (option) {
        options.push(option)
      }
    }
  }

  // Only create request if we have valid question and options
  if (!question || options.length < 2) {
    return { userInputRequest: null, cleanContent: content }
  }

  const userInputRequest: UserInputRequestPart = {
    type: 'user-input-request',
    question,
    options,
    state: 'answered', // Historical messages are already answered
  }

  // Remove XML from content
  const cleanContent = content.replace(regex, '').trim()

  return { userInputRequest, cleanContent }
}

function appendStoppedPart(parts: MessagePart[]): MessagePart[] {
  return parts.some((part) => part.type === 'stopped') ? parts : [...parts, { type: 'stopped' }]
}

function appendIterationCapReachedPart(parts: MessagePart[]): MessagePart[] {
  return parts.some((part) => part.type === 'iteration-cap-reached')
    ? parts
    : [...parts, { type: 'iteration-cap-reached' }]
}

function buildAssistantStepParts(step: BackendMessageStep): MessagePart[] {
  const parts: MessagePart[] = []

  if (step.reasoning_content) {
    parts.push({
      type: 'reasoning',
      text: step.reasoning_content,
      state: 'done',
    } as ReasoningPart)
  }

  if (step.content) {
    parts.push({
      type: 'text',
      text: step.content,
      state: 'done',
    } as TextPart)
  }

  if (step.tool_calls && Array.isArray(step.tool_calls)) {
    for (const tc of step.tool_calls) {
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

  return parts
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

  const hasRenderableAssistantContent = Boolean(
    message.content ||
    message.reasoning_content ||
    (message.tool_calls && message.tool_calls.length > 0) ||
    (message.steps && message.steps.length > 0) ||
    message.is_manually_stopped
  )

  if (message.role === 'assistant' && !hasRenderableAssistantContent) {
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
    // Assistant message: step traces first, then final reasoning/text
    // Note: RAG context is stored with user messages and attached in convertBackendMessages()

    if (message.steps && Array.isArray(message.steps) && message.steps.length > 0) {
      const sortedSteps = [...message.steps].sort(
        (a, b) => (a.round_index ?? 0) - (b.round_index ?? 0)
      )
      const toolResultMap = new Map<string, BackendMessageStep>()
      for (const step of sortedSteps) {
        if (step.role === 'tool' && step.tool_call_id) {
          toolResultMap.set(step.tool_call_id, step)
        }
      }

      for (const step of sortedSteps) {
        if (step.role !== 'assistant') continue
        const stepParts = buildAssistantStepParts(step)
        for (const part of stepParts) {
          parts.push(part)
          if (part.type === 'tool-call') {
            const toolResultMsg = toolResultMap.get(part.toolCallId)
            if (toolResultMsg) {
              const parsedOutput = parseToolResultOutput(toolResultMsg.content)
              if (isMediaImageToolResult(parsedOutput) || isMediaVideoToolResult(parsedOutput)) {
                parts.push({
                  type: 'media-result',
                  output: parsedOutput,
                })
              } else {
                parts.push({
                  type: 'tool-result',
                  toolCallId: part.toolCallId,
                  toolName: toolResultMsg.tool_name || part.toolName,
                  output: parsedOutput,
                  isError: false,
                } as ToolResultPart)
              }
            }
          }
        }
      }
    }

    if (message.reasoning_content) {
      parts.push({
        type: 'reasoning',
        text: message.reasoning_content,
        state: 'done',
        duration: message.duration_ms ?? undefined,
      } as ReasoningPart)
    }

    let contentToAdd = message.content
    let userInputRequestPart: UserInputRequestPart | null = null

    if (message.content) {
      const { userInputRequest, cleanContent } = parseUserInputRequest(message.content)
      userInputRequestPart = userInputRequest
      contentToAdd = cleanContent
    }

    if (contentToAdd) {
      parts.push({
        type: 'text',
        text: contentToAdd,
        state: 'done',
      } as TextPart)
    }

    if (userInputRequestPart) {
      parts.push(userInputRequestPart)
    }

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

  let finalParts = parts
  if (message.role === 'assistant' && message.round_status === 'max_iterations_reached') {
    finalParts = appendIterationCapReachedPart(finalParts)
  }
  if (message.role === 'assistant' && message.is_manually_stopped) {
    finalParts = appendStoppedPart(finalParts)
  }

  return {
    id: message.id,
    role: message.role as 'user' | 'assistant',
    parts: finalParts,
    createdAt: new Date(message.created_at),
    metadata: message.role === 'assistant'
      ? {
          isManuallyStopped: Boolean(message.is_manually_stopped),
          isError: message.round_status === 'error',
          preservedPartialProgress: message.round_status === 'error' && Boolean(
            message.reasoning_content ||
            (message.steps && message.steps.length > 0)
          ),
          errorMessage: message.round_status === 'error' ? (message.content || undefined) : undefined,
        }
      : undefined,
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

    // If assistant message, add pending RAG context from previous user message
    if (message.role === 'assistant') {
      // Legacy flat tool-call message compatibility path
      if (
        (!message.steps || message.steps.length === 0) &&
        message.tool_calls &&
        Array.isArray(message.tool_calls)
      ) {
        const partsWithResults: MessagePart[] = []

        for (const part of chatMessage.parts) {
          partsWithResults.push(part)

          if (part.type === 'tool-call') {
            const toolCallPart = part as ToolCallPart
            const toolResultMsg = toolResults.get(toolCallPart.toolCallId)
            if (toolResultMsg) {
              const parsedOutput = parseToolResultOutput(toolResultMsg.content)
              if (isMediaImageToolResult(parsedOutput) || isMediaVideoToolResult(parsedOutput)) {
                partsWithResults.push({
                  type: 'media-result',
                  output: parsedOutput,
                })
              } else {
                partsWithResults.push({
                  type: 'tool-result',
                  toolCallId: toolCallPart.toolCallId,
                  toolName: toolResultMsg.tool_name || toolCallPart.toolName,
                  output: parsedOutput,
                  isError: false,
                } as ToolResultPart)
              }
            }
          }
        }

        chatMessage.parts = partsWithResults
      }

      if (pendingRagContext && pendingRagContext.length > 0) {
        const sources = pendingRagContext.map((ctx) => ({
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
        } as SourceDocumentPart))
        const nonSourceParts = chatMessage.parts.filter((part) => !isSourcePart(part))
        const existingSources = chatMessage.parts.filter(isSourcePart)
        chatMessage.parts = [...nonSourceParts, ...existingSources, ...sources]
        pendingRagContext = null
      }
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
