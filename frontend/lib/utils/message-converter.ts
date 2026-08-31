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
  inferToolResultIsError,
  parseToolResultOutput,
  shouldDisplayMediaResultInBody,
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
  duration_ms?: number | null
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
    cache_read?: number
    cache_creation?: number
    total_input?: number
  } | null
  duration_ms?: number | null
  first_token_ms?: number | null
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

/**
 * Per-step reasoning duration. The backend never persisted duration_ms on
 * round step messages (it is always NULL), so fall back to wall-clock deltas:
 * - non-last assistant steps: delta to the NEXT assistant step's created_at
 *   (the immediate next entry is wrong — an assistant step is followed
 *   milliseconds later by its own tool_result);
 * - last assistant step: delta to the round end. The final message is either
 *   created at round end (non-streaming flow) or pre-created at round start
 *   with duration_ms covering the whole round (streaming flow).
 */
function stepReasoningDurationMs(
  step: BackendMessageStep,
  sortedSteps: BackendMessageStep[],
  stepIndex: number,
  message: BackendMessage
): number | undefined {
  if (step.duration_ms != null) return step.duration_ms
  const start = new Date(step.created_at).getTime()
  if (!Number.isFinite(start)) return undefined

  for (let j = stepIndex + 1; j < sortedSteps.length; j++) {
    if (sortedSteps[j].role !== 'assistant') continue
    const end = new Date(sortedSteps[j].created_at).getTime()
    if (!Number.isFinite(end) || end <= start) return undefined
    return end - start
  }

  // Last assistant step: anchor at the round end.
  const finalCreated = new Date(message.created_at).getTime()
  if (!Number.isFinite(finalCreated)) return undefined
  const roundEnd = finalCreated > start
    ? finalCreated
    : message.duration_ms != null
      ? finalCreated + message.duration_ms
      : finalCreated
  if (roundEnd <= start) return undefined
  return roundEnd - start
}

function buildAssistantStepParts(step: BackendMessageStep, durationMs?: number): MessagePart[] {
  const parts: MessagePart[] = []

  if (step.reasoning_content) {
    parts.push({
      type: 'reasoning',
      text: step.reasoning_content,
      state: 'done',
      duration: durationMs,
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
    message.is_manually_stopped ||
    message.round_status === 'error'
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
      const sortedSteps = message.steps
        .map((step, index) => ({ step, index }))
        .sort((a, b) => {
          const roundDelta = (a.step.round_index ?? Number.MAX_SAFE_INTEGER)
            - (b.step.round_index ?? Number.MAX_SAFE_INTEGER)
          if (roundDelta !== 0) return roundDelta

          const aCreatedAt = Date.parse(a.step.created_at)
          const bCreatedAt = Date.parse(b.step.created_at)
          if (Number.isFinite(aCreatedAt) && Number.isFinite(bCreatedAt) && aCreatedAt !== bCreatedAt) {
            return aCreatedAt - bCreatedAt
          }
          if (Number.isFinite(aCreatedAt) !== Number.isFinite(bCreatedAt)) {
            return Number.isFinite(aCreatedAt) ? -1 : 1
          }
          return a.index - b.index
        })
        .map(({ step }) => step)

      const toolResultEntries = sortedSteps.flatMap((step, index) => (
        step.role === 'tool' && step.tool_call_id
          ? [{ step, index, consumed: false }]
          : []
      ))
      const takeToolResult = (toolCallId: string, assistantStepIndex: number) => {
        const entry = toolResultEntries.find((candidate) => (
          !candidate.consumed
          && candidate.step.tool_call_id === toolCallId
          && candidate.index > assistantStepIndex
        )) ?? toolResultEntries.find((candidate) => (
          !candidate.consumed && candidate.step.tool_call_id === toolCallId
        ))
        if (!entry) return undefined
        entry.consumed = true
        return entry.step
      }

      for (let i = 0; i < sortedSteps.length; i++) {
        const step = sortedSteps[i]
        if (step.role !== 'assistant') continue
        const stepParts = buildAssistantStepParts(
          step,
          stepReasoningDurationMs(step, sortedSteps, i, message)
        )
        for (const part of stepParts) {
          parts.push(part)
          if (part.type === 'tool-call') {
            const toolResultMsg = takeToolResult(part.toolCallId, i)
            if (toolResultMsg) {
              const parsedOutput = parseToolResultOutput(toolResultMsg.content)
              const isError = inferToolResultIsError(parsedOutput)
              if (part.state !== 'error' && isError) {
                part.state = 'error'
              }
              if (shouldDisplayMediaResultInBody(parsedOutput)) {
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
                  isError,
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

  // Reconstruct the streaming metadata (usage/timing) from persisted fields so
  // historical messages show the same token-stats popover as fresh ones.
  let metadata: Record<string, unknown> | undefined
  if (message.role === 'assistant') {
    metadata = {
      isManuallyStopped: Boolean(message.is_manually_stopped),
      isError: message.round_status === 'error',
      preservedPartialProgress: message.round_status === 'error' && Boolean(
        message.reasoning_content ||
        (message.steps && message.steps.length > 0)
      ),
      errorMessage: message.round_status === 'error' ? (message.content || undefined) : undefined,
    }
    const usage = message.token_usage
      ? {
          prompt_tokens: message.token_usage.prompt ?? 0,
          completion_tokens: message.token_usage.completion ?? 0,
          total_tokens: (message.token_usage.prompt ?? 0) + (message.token_usage.completion ?? 0),
          cache_read_tokens: message.token_usage.cache_read ?? 0,
          cache_creation_tokens: message.token_usage.cache_creation ?? 0,
          total_input_tokens: message.token_usage.total_input ?? message.token_usage.prompt ?? 0,
        }
      : undefined
    if (usage) {
      const durationMs = message.duration_ms
      metadata.usage = usage
      // The renderer types timing.duration_ms as a number; omit the key when
      // the backend did not persist a duration instead of emitting null.
      const timing: Record<string, unknown> = {
        first_token_ms: message.first_token_ms ?? null,
        // tokens_per_second is not persisted; recompute it the same way the
        // streaming message_end event does (round(completion / duration)).
        tokens_per_second: usage.completion_tokens > 0 && durationMs && durationMs > 0
          ? Math.round((usage.completion_tokens / (durationMs / 1000)) * 10) / 10
          : null,
      }
      if (durationMs != null) {
        timing.duration_ms = durationMs
      }
      metadata.timing = timing
    }
  }

  return {
    id: message.id,
    role: message.role as 'user' | 'assistant',
    parts: finalParts,
    createdAt: new Date(message.created_at),
    metadata,
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

  // Keep every legacy result so repeated call IDs are consumed by occurrence.
  const toolResults = new Map<string, BackendMessage[]>()
  for (const msg of messages) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      const results = toolResults.get(msg.tool_call_id) ?? []
      results.push(msg)
      toolResults.set(msg.tool_call_id, results)
    }
  }
  const takeLegacyToolResult = (toolCallId: string): BackendMessage | undefined => {
    const results = toolResults.get(toolCallId)
    const result = results?.shift()
    if (results && results.length === 0) toolResults.delete(toolCallId)
    return result
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
            const toolResultMsg = takeLegacyToolResult(toolCallPart.toolCallId)
            if (toolResultMsg) {
              const parsedOutput = parseToolResultOutput(toolResultMsg.content)
              const isError = inferToolResultIsError(parsedOutput)
              if (toolCallPart.state !== 'error' && isError) {
                toolCallPart.state = 'error'
              }
              if (shouldDisplayMediaResultInBody(parsedOutput)) {
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
                  isError,
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
