'use client'

import { useState, useCallback, useRef, useEffect } from 'react'
import { embedApi, type EmbedChatRequest } from '@/lib/api/embed'
import { parseSSEStream, type SSECompression, type SSEMessageEnd } from '@/lib/api/agents'
import type {
  ChatMessage,
  MessagePart,
  TextPart,
  ReasoningPart,
  SourceDocumentPart,
  TaskPart,
  ToolCallPart,
  ToolResultPart,
  UserInputRequestPart,
} from '@/components/chat'
import { parseToolResultOutput } from '@/lib/utils/tool-result'

export type EmbedChatStatus = 'idle' | 'loading' | 'streaming' | 'error'

export interface UseEmbedChatOptions {
  agentId: string
  apiKey: string
  variables?: Record<string, unknown>
  initialMessages?: ChatMessage[]
  onConversationChange?: (conversationId: string) => void
  onError?: (error: { code?: number; message: string }) => void
}

export interface UseEmbedChatReturn {
  messages: ChatMessage[]
  status: EmbedChatStatus
  conversationId: string | null
  isLoading: boolean
  isStreaming: boolean
  sendMessage: (message: string, images?: Array<{ type: string; url: string }>, fileUrls?: Array<{ filename: string; url: string; size: number; mime_type: string }>) => Promise<void>
  stop: () => void
  reset: () => void
}

// Content segment types for building message parts
type ContentSegment =
  | { type: 'text'; text: string }
  | { type: 'tool-group'; calls: ToolCallPart[]; results: ToolResultPart[] }
  | { type: 'reasoning'; index: number }
  | { type: 'user-input-request'; userInputRequest: UserInputRequestPart }
  | { type: 'truncated' }

interface TaskState {
  rag: 'pending' | 'running' | 'completed' | 'error'
  generating: 'pending' | 'running' | 'completed' | 'error'
  toolCalling: 'pending' | 'running' | 'completed' | 'error'
  compression: 'pending' | 'running' | 'completed' | 'error'
  ragSourceCount?: number
  toolCallCount?: number
  compressionInfo?: Record<string, unknown>
}

function parseUserInputRequestSegments(segments: ContentSegment[]): ContentSegment[] {
  const allText = segments
    .filter((segment): segment is Extract<ContentSegment, { type: 'text' }> => segment.type === 'text')
    .map(segment => segment.text)
    .join('')

  if (!allText.includes('<user_input_request>') || !allText.includes('</user_input_request>')) {
    return segments
  }

  const xmlMatch = allText.match(/<user_input_request>([\s\S]*?)<\/user_input_request>/)
  if (!xmlMatch) {
    return segments
  }

  const xmlContent = xmlMatch[1]
  const questionMatch = xmlContent.match(/<question>([\s\S]*?)<\/question>/)
  const optionsMatch = xmlContent.match(/<options>([\s\S]*?)<\/options>/)

  if (!questionMatch || !optionsMatch) {
    return segments
  }

  const question = questionMatch[1].trim()
  const options = Array.from(optionsMatch[1].matchAll(/<option>([\s\S]*?)<\/option>/g))
    .map(match => match[1].trim())
    .filter(Boolean)

  if (!question || options.length < 2) {
    return segments
  }

  const textBeforeXML = allText.substring(0, allText.indexOf('<user_input_request>'))
  const textAfterXML = allText.substring(
    allText.indexOf('</user_input_request>') + '</user_input_request>'.length
  )
  const cleanedText = `${textBeforeXML}${textAfterXML}`.trim()

  const nextSegments: ContentSegment[] = segments.filter(
    segment => segment.type !== 'text' && segment.type !== 'user-input-request'
  )

  if (cleanedText) {
    nextSegments.push({ type: 'text', text: cleanedText })
  }

  nextSegments.push({
    type: 'user-input-request',
    userInputRequest: {
      type: 'user-input-request',
      question,
      options,
      state: 'pending',
    },
  })

  return nextSegments
}

function buildMessageParts(
  segments: ContentSegment[],
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>,
  ragSources: SourceDocumentPart[],
  isStreaming: boolean,
  taskState: TaskState,
): MessagePart[] {
  const parts: MessagePart[] = []

  // Add task parts for RAG and generating steps (not tool calling - we show individual tool calls instead)
  // Keep showing them even after streaming ends so they're visible when collapsed
  // RAG task - show if it ran (not pending)
  if (taskState.rag !== 'pending') {
    const ragTask: TaskPart = {
      type: 'task',
      taskType: 'rag',
      // Mark as completed when streaming ends
      state: isStreaming ? taskState.rag : 'completed',
      info: taskState.ragSourceCount,
    }
    parts.push(ragTask)
  }

  // Compression task - show if it ran (not pending)
  if (taskState.compression !== 'pending') {
    const compressionTask: TaskPart = {
      type: 'task',
      taskType: 'compression',
      state: isStreaming ? taskState.compression : 'completed',
      info: taskState.compressionInfo,
    }
    parts.push(compressionTask)
  }

  // Generating task - show if it ran (not pending)
  if (taskState.generating !== 'pending') {
    const generatingTask: TaskPart = {
      type: 'task',
      taskType: 'generating',
      // Mark as completed when streaming ends
      state: isStreaming ? taskState.generating : 'completed',
    }
    parts.push(generatingTask)
  }

  // Source documents
  for (const src of ragSources) {
    parts.push(src)
  }

  // Content segments
  for (const seg of segments) {
    if (seg.type === 'text') {
      parts.push({ type: 'text', text: seg.text } as TextPart)
    } else if (seg.type === 'reasoning') {
      const block = reasoningBlocks[seg.index]
      if (block) {
        parts.push({
          type: 'reasoning',
          text: block.text,
          duration: block.duration,
          state: block.state,
        } as ReasoningPart)
      }
    } else if (seg.type === 'tool-group') {
      for (const call of seg.calls) parts.push(call)
      for (const result of seg.results) parts.push(result)
    } else if (seg.type === 'user-input-request') {
      parts.push(seg.userInputRequest)
    } else if (seg.type === 'truncated') {
      parts.push({ type: 'truncated' })
    }
  }

  return parts
}

export function useEmbedChat(options: UseEmbedChatOptions): UseEmbedChatReturn {
  const { agentId, apiKey, variables = {}, initialMessages = [], onConversationChange, onError } = options

  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [status, setStatus] = useState<EmbedChatStatus>('idle')
  const [conversationId, setConversationId] = useState<string | null>(null)

  // Sync initial messages when they change (e.g. agent loaded async)
  const initialMessagesApplied = useRef(false)
  useEffect(() => {
    if (initialMessages.length > 0 && !initialMessagesApplied.current) {
      initialMessagesApplied.current = true
      setMessages(initialMessages)
    }
  }, [initialMessages])

  const abortRef = useRef<(() => void) | null>(null)
  const streamingStateRef = useRef<{
    assistantMessageId: string | null
    segments: ContentSegment[]
    reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>
    currentReasoningIndex: number
    ragSources: SourceDocumentPart[]
    taskState: TaskState
  }>({
    assistantMessageId: null,
    segments: [],
    reasoningBlocks: [],
    currentReasoningIndex: -1,
    ragSources: [],
    taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending', compression: 'pending' },
  })

  const isLoading = status === 'loading' || status === 'streaming'
  const isStreaming = status === 'streaming'

  const sendMessage = useCallback(
    async (message: string, images?: Array<{ type: string; url: string }>, fileUrls?: Array<{ filename: string; url: string; size: number; mime_type: string }>) => {
      if (!message.trim() || isLoading) return

      const userParts: MessagePart[] = [{ type: 'text', text: message.trim() }]
      if (images && images.length > 0) {
        for (const img of images) {
          userParts.push({ type: 'image', url: img.url } as MessagePart)
        }
      }
      if (fileUrls && fileUrls.length > 0) {
        for (const f of fileUrls) {
          userParts.push({ type: 'file', filename: f.filename, size: f.size } as MessagePart)
        }
      }
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        parts: userParts,
      }

      setMessages(prev => [...prev, userMessage])
      setStatus('loading')

      // Reset streaming state
      const state = streamingStateRef.current
      state.assistantMessageId = null
      state.segments = []
      state.reasoningBlocks = []
      state.currentReasoningIndex = -1
      state.ragSources = []
      state.taskState = { rag: 'pending', generating: 'pending', toolCalling: 'pending', compression: 'pending' }

      try {
        const chatRequest: EmbedChatRequest = {
          message: message.trim(),
          images,
          file_urls: fileUrls,
          conversation_id: conversationId,
          variables,
        }

        const { stream, abort } = embedApi.chatStream(agentId, chatRequest, apiKey)
        abortRef.current = abort

        const response = await stream
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ msg: 'Request failed' }))
          throw new Error(errorData.msg || `HTTP ${response.status}`)
        }

        setStatus('streaming')

        for await (const event of parseSSEStream(response)) {
          const eventType = event.event as string
          const data = event.data as Record<string, unknown>

          switch (eventType) {
            case 'message_start': {
              const msgData = data as { conversation_id?: string; message_id?: string }
              state.assistantMessageId = msgData.message_id || `assistant-${Date.now()}`
              if (msgData.conversation_id && msgData.conversation_id !== conversationId) {
                setConversationId(msgData.conversation_id)
                onConversationChange?.(msgData.conversation_id)
              }
              state.taskState.generating = 'running'
              // Create initial assistant message
              const assistantMsg: ChatMessage = {
                id: state.assistantMessageId,
                role: 'assistant',
                parts: buildMessageParts(state.segments, state.reasoningBlocks, state.ragSources, true, state.taskState),
              }
              setMessages(prev => [...prev, assistantMsg])
              break
            }

            case 'content_delta': {
              const delta = (data as { delta?: string }).delta || ''
              // Find or create text segment
              const lastSeg = state.segments[state.segments.length - 1]
              if (lastSeg && lastSeg.type === 'text') {
                lastSeg.text += delta
              } else {
                state.segments.push({ type: 'text', text: delta })
              }
              state.segments = parseUserInputRequestSegments(state.segments)
              // Update assistant message
              if (state.assistantMessageId) {
                const parts = buildMessageParts(state.segments, state.reasoningBlocks, state.ragSources, true, state.taskState)
                setMessages(prev =>
                  prev.map(m => m.id === state.assistantMessageId ? { ...m, parts } : m)
                )
              }
              break
            }

            case 'reasoning_start': {
              const newBlock = { text: '', startTime: Date.now(), state: 'streaming' as const }
              state.reasoningBlocks.push(newBlock)
              state.currentReasoningIndex = state.reasoningBlocks.length - 1
              state.segments.push({ type: 'reasoning', index: state.currentReasoningIndex })
              break
            }

            case 'reasoning_delta': {
              const reasoningDelta = (data as { delta?: string }).delta || ''
              if (state.currentReasoningIndex >= 0) {
                state.reasoningBlocks[state.currentReasoningIndex].text += reasoningDelta
                if (state.assistantMessageId) {
                  const parts = buildMessageParts(state.segments, state.reasoningBlocks, state.ragSources, true, state.taskState)
                  setMessages(prev =>
                    prev.map(m => m.id === state.assistantMessageId ? { ...m, parts } : m)
                  )
                }
              }
              break
            }

            case 'reasoning_end': {
              if (state.currentReasoningIndex >= 0) {
                const block = state.reasoningBlocks[state.currentReasoningIndex]
                block.state = 'done'
                block.duration = Date.now() - block.startTime
                state.currentReasoningIndex = -1
              }
              break
            }

            case 'rag_start': {
              state.taskState.rag = 'running'
              break
            }

            case 'rag_context': {
              state.taskState.rag = 'completed'
              const contexts = (data as { contexts?: Array<Record<string, unknown>> }).contexts || []
              state.ragSources = contexts.map((ctx, i) => ({
                type: 'source-document' as const,
                documentName: (ctx.document_name as string) || `Source ${i + 1}`,
                content: (ctx.content as string) || '',
                metadata: ctx,
              }))
              state.taskState.ragSourceCount = contexts.length
              break
            }

            case 'compression': {
              const compressionData = data as unknown as SSECompression
              state.taskState.compression = 'running'
              state.taskState.compressionInfo = compressionData as unknown as Record<string, unknown>
              break
            }

            case 'tool_call': {
              state.taskState.toolCalling = 'running'
              const toolData = data as { tool_name?: string; tool_call_id?: string; arguments?: Record<string, unknown> }
              // Find or create tool-group segment
              let toolGroup = state.segments[state.segments.length - 1]
              if (!toolGroup || toolGroup.type !== 'tool-group') {
                toolGroup = { type: 'tool-group', calls: [], results: [] }
                state.segments.push(toolGroup)
              }
              if (toolGroup.type === 'tool-group') {
                toolGroup.calls.push({
                  type: 'tool-call',
                  toolName: toolData.tool_name || 'unknown',
                  toolCallId: toolData.tool_call_id || '',
                  input: toolData.arguments || {},
                  state: 'running',
                } as ToolCallPart)
              }
              break
            }

            case 'tool_result': {
              const resultData = data as { tool_call_id?: string; tool_name?: string; result?: unknown }
              const parsedOutput = parseToolResultOutput(resultData.result)
              // Find the tool-group and update
              for (const seg of state.segments) {
                if (seg.type === 'tool-group') {
                  // Mark matching call as done
                  for (const call of seg.calls) {
                    if (call.toolCallId === resultData.tool_call_id) {
                      call.state = 'done'
                    }
                  }
                  seg.results.push({
                    type: 'tool-result',
                    toolName: resultData.tool_name || 'unknown',
                    toolCallId: resultData.tool_call_id || '',
                    output: parsedOutput,
                  } as ToolResultPart)
                }
              }
              break
            }

            case 'output_truncated': {
              state.segments.push({ type: 'truncated' })
              if (state.assistantMessageId) {
                const parts = buildMessageParts(state.segments, state.reasoningBlocks, state.ragSources, true, state.taskState)
                setMessages(prev =>
                  prev.map(m => m.id === state.assistantMessageId ? { ...m, parts } : m)
                )
              }
              break
            }

            case 'message_end': {
              const endData = data as unknown as SSEMessageEnd
              state.taskState.generating = 'completed'
              state.taskState.toolCalling = state.taskState.toolCalling === 'running' ? 'completed' : state.taskState.toolCalling
              state.taskState.compression = state.taskState.compression === 'running' ? 'completed' : state.taskState.compression
              if (state.assistantMessageId) {
                const parts = buildMessageParts(state.segments, state.reasoningBlocks, state.ragSources, false, state.taskState)
                setMessages(prev =>
                  prev.map(m => m.id === state.assistantMessageId
                    ? { ...m, parts, metadata: { ...m.metadata, usage: endData.usage, timing: endData.timing } }
                    : m
                  )
                )
              }
              break
            }

            case 'error': {
              state.taskState.compression = state.taskState.compression === 'running' ? 'error' : state.taskState.compression
              const errorData = data as { code?: number; msg?: string }
              const errorObj = { code: errorData.code, message: errorData.msg || 'Unknown error' }
              onError?.(errorObj)
              break
            }
          }
        }

        setStatus('idle')
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setStatus('idle')
          return
        }
        const errorMessage = err instanceof Error ? err.message : 'Unknown error'
        onError?.({ message: errorMessage })
        setStatus('error')
      } finally {
        abortRef.current = null
      }
    },
    [agentId, apiKey, conversationId, variables, isLoading, onConversationChange, onError]
  )

  const stop = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    setStatus('idle')
  }, [])

  const reset = useCallback(() => {
    stop()
    setMessages(initialMessages)
    setConversationId(null)
  }, [stop, initialMessages])

  return {
    messages,
    status,
    conversationId,
    isLoading,
    isStreaming,
    sendMessage,
    stop,
    reset,
  }
}
