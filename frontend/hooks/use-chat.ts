'use client'

import { useState, useCallback, useRef } from 'react'
import type { BackendMessage } from '@/lib/utils/message-converter'
import {
  agentsApi,
  parseSSEStream,
  type ChatRequest,
  type ChatImageContent,
  type ChatFileContent,
  type ChatFileUrl,
  type SSEEventType,
  type SSEMessageStart,
  type SSEContentDelta,
  type SSERagContext,
  type SSEMessageEnd,
  type SSEError,
  type SSEToolCall,
  type SSEToolResult,
} from '@/lib/api'
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

export type ChatStatus = 'idle' | 'loading' | 'streaming' | 'error'

export interface ChatError {
  code?: number
  message: string
  msgKey?: string  // i18n key for the error message
  quotaType?: string
}

export interface UseChatOptions {
  /** Agent ID */
  agentId: string
  /** Initial conversation ID (for continuing a conversation) */
  conversationId?: string
  /** Variables to pass to the agent */
  variables?: Record<string, unknown>
  /** Callback when conversation ID changes (new conversation created) */
  onConversationChange?: (conversationId: string) => void
  /** Callback when error occurs */
  onError?: (error: ChatError) => void
  /** Callback when message streaming starts */
  onStreamStart?: () => void
  /** Callback when message streaming ends */
  onStreamEnd?: () => void
}

// Re-export for convenience
export type { ChatImageContent, ChatFileContent, ChatFileUrl }

export interface UseChatReturn {
  /** Current messages */
  messages: ChatMessage[]
  /** Current status */
  status: ChatStatus
  /** Current error (if any) */
  error: ChatError | null
  /** Current conversation ID */
  conversationId: string | null
  /** Whether currently loading or streaming */
  isLoading: boolean
  /** Whether currently streaming */
  isStreaming: boolean
  /** Send a message with optional images (vision) and/or file URLs (file upload) */
  sendMessage: (message: string, images?: ChatImageContent[], fileUrls?: ChatFileUrl[]) => Promise<void>
  /** Regenerate (retry) a message by ID */
  regenerate: (messageId: string) => Promise<void>
  /** Switch to a different version of a message */
  switchVersion: (messageId: string, versionIndex: number) => Promise<void>
  /** Stop current streaming */
  stop: () => void
  /** Reset chat (clear messages and conversation) */
  reset: () => void
  /** Set messages (for loading history) */
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  /** Set conversation ID (for loading history) */
  setConversationId: React.Dispatch<React.SetStateAction<string | null>>
}

/**
 * Hook for managing chat state with an agent
 */
export function useChat(options: UseChatOptions): UseChatReturn {
  const {
    agentId,
    conversationId: initialConversationId,
    variables = {},
    onConversationChange,
    onError,
    onStreamStart,
    onStreamEnd,
  } = options

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<ChatStatus>('idle')
  const [error, setError] = useState<ChatError | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(
    initialConversationId ?? null
  )

  // Abort controller for cancelling requests
  const abortRef = useRef<(() => void) | null>(null)

  // Streaming state ref for stop function to access
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
    taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending' },
  })

  const isLoading = status === 'loading' || status === 'streaming'
  const isStreaming = status === 'streaming'

  /**
   * Send a message to the agent
   */
  const sendMessage = useCallback(
    async (message: string, images?: ChatImageContent[], fileUrls?: ChatFileUrl[]) => {
      if (!message.trim() || isLoading) return

      // Clear previous error
      setError(null)

      // Create user message parts
      const userParts: MessagePart[] = [{ type: 'text', text: message.trim() }]
      
      // Add image parts if provided
      if (images && images.length > 0) {
        for (const img of images) {
          userParts.push({ type: 'image', url: img.url } as MessagePart)
        }
      }
      
      // Add file info for user message display (file content injected via {{fileContent}})
      if (fileUrls && fileUrls.length > 0) {
        for (const f of fileUrls) {
          userParts.push({ type: 'file', filename: f.filename, size: f.size } as MessagePart)
        }
      }

      // Create user message
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        parts: userParts,
        createdAt: new Date(),
      }

      // Add user message to state
      setMessages((prev) => [...prev, userMessage])
      setStatus('loading')

      // Create placeholder assistant message for streaming
      let assistantMessageId = `assistant-${Date.now()}`
      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        parts: [],
        createdAt: new Date(),
        metadata: { isLoading: true }, // Mark as loading
      }

      // Add assistant message placeholder immediately (for loading state)
      setMessages((prev) => [...prev, assistantMessage])

      try {
        // Prepare request
        // Backend loads history from database (only active messages) so no history_override needed
        const chatRequest: ChatRequest = {
          message: message.trim(),
          images: images,
          file_urls: fileUrls,
          conversation_id: conversationId,
          variables,
        }

        // Start streaming
        const { stream, abort } = agentsApi.chatStream(agentId, chatRequest)
        abortRef.current = abort

        const response = await stream

        if (!response.ok) {
          // Handle HTTP errors
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.msg || `HTTP ${response.status}`)
        }

        // Update status to streaming
        setStatus('streaming')
        onStreamStart?.()

        // Content segments - tracks text and tool calls in order
        let segments: ContentSegment[] = []
        // Reasoning blocks - each tool call iteration creates a new block
        const reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }> = []
        let currentReasoningIndex = -1
        // RAG sources
        let ragSources: SourceDocumentPart[] = []
        // Task state for showing progress
        const taskState: TaskState = { rag: 'pending', generating: 'pending', toolCalling: 'pending' }

        // Helper to get or create current text segment
        const getCurrentTextSegment = (): ContentSegment => {
          const lastSegment = segments[segments.length - 1]
          if (lastSegment && lastSegment.type === 'text') {
            return lastSegment
          }
          // Create new text segment
          const newSegment: ContentSegment = { type: 'text', text: '' }
          segments.push(newSegment)
          return newSegment
        }

        // Helper to add a tool group segment
        const addToolGroupSegment = (toolCall: ToolCallPart): ContentSegment => {
          // Check if last segment is a tool-group, if so add to it
          const lastSegment = segments[segments.length - 1]
          if (lastSegment && lastSegment.type === 'tool-group') {
            lastSegment.toolCalls = lastSegment.toolCalls || []
            lastSegment.toolCalls.push(toolCall)
            return lastSegment
          }
          // Create new tool group segment
          const newSegment: ContentSegment = { 
            type: 'tool-group', 
            toolCalls: [toolCall],
            toolResults: []
          }
          segments.push(newSegment)
          return newSegment
        }

        // Helper to find tool group containing a tool call
        const findToolGroup = (toolCallId: string): ContentSegment | undefined => {
          return segments.find(s => 
            s.type === 'tool-group' && 
            s.toolCalls?.some(tc => tc.toolCallId === toolCallId)
          )
        }

        // Store in ref for stop function to access
        streamingStateRef.current = {
          assistantMessageId,
          segments,
          reasoningBlocks,
          currentReasoningIndex,
          ragSources,
          taskState,
        }

        // Parse SSE stream
        for await (const event of parseSSEStream(response)) {
          switch (event.event as SSEEventType) {
            case 'message_start': {
              const data = event.data as SSEMessageStart
              if (data.conversation_id && data.conversation_id !== conversationId) {
                setConversationId(data.conversation_id)
                onConversationChange?.(data.conversation_id)
              }
              // Update assistant message ID to the real database ID
              if (data.message_id) {
                const oldId = assistantMessageId
                assistantMessageId = data.message_id
                streamingStateRef.current.assistantMessageId = data.message_id
                // Update the message in state with the real ID
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === oldId ? { ...msg, id: data.message_id } : msg
                  )
                )
              }
              break
            }

            case 'rag_start': {
              // Mark RAG as running
              taskState.rag = 'running'
              streamingStateRef.current.taskState = taskState

              // Update message with RAG progress
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'reasoning_start': {
              // Start a new reasoning block and add it as a segment
              const newBlock = {
                text: '',
                startTime: Date.now(),
                state: 'streaming' as const,
              }
              reasoningBlocks.push(newBlock)
              currentReasoningIndex = reasoningBlocks.length - 1

              // Add reasoning segment to maintain order
              const reasoningSegment: ContentSegment = {
                type: 'reasoning',
                reasoningText: '',
                reasoningState: 'streaming',
                reasoningStartTime: Date.now(),
              }
              segments.push(reasoningSegment)

              streamingStateRef.current.segments = segments
              streamingStateRef.current.reasoningBlocks = reasoningBlocks
              streamingStateRef.current.currentReasoningIndex = currentReasoningIndex
              break
            }

            case 'reasoning_delta': {
              const data = event.data as { delta: string }
              // Add to current reasoning block
              if (currentReasoningIndex >= 0 && reasoningBlocks[currentReasoningIndex]) {
                reasoningBlocks[currentReasoningIndex].text += data.delta
                streamingStateRef.current.reasoningBlocks = reasoningBlocks

                // Update the corresponding reasoning segment (find last reasoning segment)
                let lastReasoningSegmentIndex = -1
                for (let i = segments.length - 1; i >= 0; i--) {
                  if (segments[i].type === 'reasoning') {
                    lastReasoningSegmentIndex = i
                    break
                  }
                }
                if (lastReasoningSegmentIndex >= 0) {
                  segments[lastReasoningSegmentIndex].reasoningText = reasoningBlocks[currentReasoningIndex].text
                  streamingStateRef.current.segments = segments
                }
              }

              // Update assistant message with current reasoning blocks
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'reasoning_end': {
              // Mark current reasoning block as done
              if (currentReasoningIndex >= 0 && reasoningBlocks[currentReasoningIndex]) {
                const block = reasoningBlocks[currentReasoningIndex]
                block.duration = Date.now() - block.startTime
                block.state = 'done'
                streamingStateRef.current.reasoningBlocks = reasoningBlocks

                // Update the corresponding reasoning segment (find last reasoning segment)
                let lastReasoningSegmentIndex = -1
                for (let i = segments.length - 1; i >= 0; i--) {
                  if (segments[i].type === 'reasoning') {
                    lastReasoningSegmentIndex = i
                    break
                  }
                }
                if (lastReasoningSegmentIndex >= 0) {
                  segments[lastReasoningSegmentIndex].reasoningState = 'done'
                  segments[lastReasoningSegmentIndex].reasoningDuration = block.duration
                  streamingStateRef.current.segments = segments
                }
              }

              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'content_delta': {
              const data = event.data as SSEContentDelta
              // Add to current text segment
              const textSegment = getCurrentTextSegment()
              textSegment.text = (textSegment.text || '') + data.delta

              // Collect all text from all text segments to check for complete XML
              const allText = segments
                .filter(s => s.type === 'text')
                .map(s => s.text || '')
                .join('')

              const hasStartTag = allText.includes('<user_input_request>')
              const hasEndTag = allText.includes('</user_input_request>')

              console.log('[XML Debug] hasStartTag:', hasStartTag, 'hasEndTag:', hasEndTag, 'allTextLength:', allText.length)

              if (hasStartTag && hasEndTag) {
                // Complete XML detected - parse it
                console.log('[XML Debug] Complete XML detected, parsing...')
                const xmlMatch = allText.match(/<user_input_request>([\s\S]*?)<\/user_input_request>/)
                if (xmlMatch) {
                  console.log('[XML Debug] XML matched:', xmlMatch[0].substring(0, 100))
                  const xmlContent = xmlMatch[1]
                  const questionMatch = xmlContent.match(/<question>([\s\S]*?)<\/question>/)
                  const optionsMatch = xmlContent.match(/<options>([\s\S]*?)<\/options>/)

                  console.log('[XML Debug] questionMatch:', !!questionMatch, 'optionsMatch:', !!optionsMatch)

                  if (questionMatch && optionsMatch) {
                    const question = questionMatch[1].trim()
                    const options: string[] = []
                    const optionMatches = optionsMatch[1].matchAll(/<option>([\s\S]*?)<\/option>/g)
                    for (const match of optionMatches) {
                      options.push(match[1].trim())
                    }

                    console.log('[XML Debug] Parsed - question:', question, 'options count:', options.length)

                    if (question && options.length >= 2) {
                      // Remove XML from all text segments
                      const textBeforeXML = allText.substring(0, allText.indexOf('<user_input_request>'))
                      const textAfterXML = allText.substring(allText.indexOf('</user_input_request>') + '</user_input_request>'.length)
                      const cleanedText = (textBeforeXML + textAfterXML).trim()

                      console.log('[XML Debug] Text before XML:', textBeforeXML.length, 'after XML:', textAfterXML.length)

                      // Replace all text segments with a single cleaned one
                      segments = segments.filter(s => s.type !== 'text' && s.type !== 'user-input-request')
                      if (cleanedText) {
                        segments.push({
                          type: 'text',
                          text: cleanedText
                        })
                      }

                      // Add user input request segment
                      const userInputSegment: ContentSegment = {
                        type: 'user-input-request',
                        userInputRequest: {
                          type: 'user-input-request',
                          question,
                          options,
                          state: 'pending',
                        }
                      }
                      segments.push(userInputSegment)

                      console.log('[XML Debug] Segments after processing:', segments.length)
                    }
                  }
                }
              }

              streamingStateRef.current.segments = segments

              // Mark generating as running when first content arrives
              if (taskState.generating === 'pending') {
                // Complete RAG if it was running
                if (taskState.rag === 'running') {
                  taskState.rag = 'completed'
                }
                taskState.generating = 'running'
                streamingStateRef.current.taskState = taskState
              }

              // Update assistant message with current text
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'rag_context': {
              const data = event.data as SSERagContext
              ragSources = data.contexts.map((ctx) => ({
                type: 'source-document' as const,
                sourceId: ctx.document_id,
                documentId: ctx.document_id,
                documentName: ctx.document_name,
                content: ctx.content,
                metadata: {
                  kb_id: ctx.kb_id,
                  kb_name: ctx.kb_name,
                  score: ctx.score,
                },
              }))
              streamingStateRef.current.ragSources = ragSources

              // Update RAG task state to completed
              taskState.rag = 'completed'
              taskState.ragSourceCount = ragSources.length
              streamingStateRef.current.taskState = taskState

              // Update message with RAG progress
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'tool_call': {
              const data = event.data as SSEToolCall
              const toolCallPart: ToolCallPart = {
                type: 'tool-call',
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                toolDisplayName: data.tool_display_name,
                input: data.arguments,
                state: 'running',
              }
              // Add to tool group segment (creates new one or adds to existing)
              addToolGroupSegment(toolCallPart)
              streamingStateRef.current.segments = segments

              // Mark tool calling as running
              taskState.toolCalling = 'running'
              // Count total tool calls across all segments
              const totalToolCalls = segments
                .filter(s => s.type === 'tool-group')
                .reduce((sum, s) => sum + (s.toolCalls?.length || 0), 0)
              taskState.toolCallCount = totalToolCalls
              streamingStateRef.current.taskState = taskState

              // Update message with tool call progress
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'tool_result': {
              const data = event.data as SSEToolResult
              const parsedOutput = parseToolResultOutput(data.result)
              const toolResultPart: ToolResultPart = {
                type: 'tool-result',
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                toolDisplayName: data.tool_display_name,
                output: parsedOutput,
                isError: data.is_error,
              }
              
              // Find the tool group containing this tool call
              const toolGroup = findToolGroup(data.tool_call_id)
              if (toolGroup) {
                toolGroup.toolResults = toolGroup.toolResults || []
                toolGroup.toolResults.push(toolResultPart)

                // Update corresponding tool call state to done (create new object for React to detect change)
                if (toolGroup.toolCalls) {
                  toolGroup.toolCalls = toolGroup.toolCalls.map(tc =>
                    tc.toolCallId === data.tool_call_id
                      ? { ...tc, state: data.is_error ? 'error' as const : 'done' as const }
                      : tc
                  )
                }
              }
              streamingStateRef.current.segments = segments

              // Check if all tool calls have completed
              const allToolCalls = segments
                .filter(s => s.type === 'tool-group')
                .flatMap(s => s.toolCalls || [])
              const allToolsCompleted = allToolCalls.every(tc => tc.state === 'done' || tc.state === 'error')
              if (allToolsCompleted && taskState.toolCalling === 'running') {
                taskState.toolCalling = 'completed'
                streamingStateRef.current.taskState = taskState
              }

              // Update message with tool result
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'output_truncated': {
              const truncatedSegment: ContentSegment = { type: 'truncated' }
              segments.push(truncatedSegment)
              streamingStateRef.current.segments = segments
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'message_end': {
              // Get version info from event data
              const endData = event.data as SSEMessageEnd & { version_number?: number; version_count?: number }
              // Finalize message - pass taskState to keep RAG steps visible
              // Mark tool calling as completed if it was running
              if (taskState.toolCalling === 'running') {
                taskState.toolCalling = 'completed'
              }
              // Safety: ensure all tool calls are marked as done on message end
              for (const segment of segments) {
                if (segment.type === 'tool-group' && segment.toolCalls) {
                  segment.toolCalls = segment.toolCalls.map(tc =>
                    tc.state === 'running' ? { ...tc, state: 'done' as const } : tc
                  )
                }
              }
              // Mark all reasoning blocks as done
              reasoningBlocks.forEach(block => {
                if (block.state === 'streaming') {
                  block.duration = Date.now() - block.startTime
                  block.state = 'done'
                }
              })
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, false, taskState),
                        versionNumber: endData.version_number ?? 1,
                        versionCount: endData.version_count ?? 1,
                        metadata: { ...msg.metadata, isLoading: false, usage: endData.usage, timing: endData.timing },
                      }
                    : msg
                )
              )
              break
            }

            case 'error': {
              const data = event.data as SSEError
              const chatError: ChatError = {
                code: data.code,
                message: data.msg,
                quotaType: data.quota_type,
              }
              // Don't set error state, handle gracefully with error message
              onError?.(chatError)

              // Generate friendly error message as AI response
              const errorText = getErrorMessage(chatError)
              
              // Create a text segment with the error message
              const errorSegment: ContentSegment = { type: 'text', text: errorText }
              segments = [errorSegment]
              streamingStateRef.current.segments = segments

              // Update message with error text as AI response
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, [], [], false, undefined),
                        metadata: { ...msg.metadata, isError: true },
                      }
                    : msg
                )
              )
              break
            }
          }
        }

        setStatus('idle')
        onStreamEnd?.()
      } catch (err) {
        // Handle abort
        if (err instanceof Error && err.name === 'AbortError') {
          setStatus('idle')
          return
        }

        const chatError: ChatError = {
          message: err instanceof Error ? err.message : 'Unknown error',
        }
        onError?.(chatError)

        // Generate friendly error message as AI response
        const errorText = getErrorMessage(chatError)
        const errorSegment: ContentSegment = { type: 'text', text: errorText }
        
        // Update message with error text as AI response
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  parts: buildMessageParts([errorSegment], [], [], false, undefined),
                  metadata: { ...msg.metadata, isError: true },
                }
              : msg
          )
        )
        
        setStatus('idle')
      } finally {
        abortRef.current = null
        // Reset streaming state
        streamingStateRef.current = {
          assistantMessageId: null,
          segments: [],
          reasoningBlocks: [],
          currentReasoningIndex: -1,
          ragSources: [],
          taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending' },
        }
      }
    },
    [
      agentId,
      conversationId,
      variables,
      isLoading,
      onConversationChange,
      onError,
      onStreamStart,
      onStreamEnd,
    ]
  )

  /**
   * Stop current streaming
   */
  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current()
      abortRef.current = null
    }

    // Finalize the current message state when stopped
    const state = streamingStateRef.current
    if (state.assistantMessageId) {
      // Mark all reasoning blocks as done
      state.reasoningBlocks.forEach((block, index) => {
        if (block.state === 'streaming') {
          block.duration = Date.now() - block.startTime
          block.state = 'done'

          // Update corresponding reasoning segment
          const reasoningSegments = state.segments.filter(s => s.type === 'reasoning')
          if (reasoningSegments[index]) {
            reasoningSegments[index].reasoningState = 'done'
            reasoningSegments[index].reasoningDuration = block.duration
          }
        }
      })

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === state.assistantMessageId
            ? {
                ...msg,
                metadata: { ...msg.metadata, isLoading: false },
                parts: buildMessageParts(
                  state.segments,
                  state.reasoningBlocks,
                  state.ragSources,
                  false, // Not streaming anymore
                  state.taskState
                ),
              }
            : msg
        )
      )
      // Reset streaming state
      streamingStateRef.current = {
        assistantMessageId: null,
        segments: [],
        reasoningBlocks: [],
        currentReasoningIndex: -1,
        ragSources: [],
        taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending' },
      }
    }

    setStatus('idle')
  }, [])

  /**
   * Reset chat state
   */
  const reset = useCallback(() => {
    stop()
    setMessages([])
    setConversationId(null)
    setError(null)
    setStatus('idle')
  }, [stop])

  /**
   * Switch to a different version of a message using backend API
   * This loads versions from backend and switches to the specified version
   */
  const switchVersion = useCallback(
    async (messageId: string, versionIndex: number) => {
      if (isLoading) return

      // Find the message index
      const messageIndex = messages.findIndex((m) => m.id === messageId)
      if (messageIndex === -1) {
        console.error('switchVersion: message not found', messageId)
        return
      }

      try {
        // Fetch all versions from backend
        console.log('switchVersion: fetching versions for message', messageId)
        const versions = await agentsApi.getMessageVersions(agentId, messageId)
        console.log('switchVersion: got versions', versions)

        if (versionIndex < 0 || versionIndex >= versions.length) {
          console.error('switchVersion: invalid versionIndex', versionIndex, 'versions.length', versions.length)
          return
        }

        const targetVersion = versions[versionIndex]
        console.log('switchVersion: switching to version', targetVersion)

        // Call backend to switch version (this updates is_active in database)
        // Backend will also deactivate messages that came after this message
        const result = await agentsApi.switchMessageVersion(agentId, messageId, targetVersion.id)
        console.log('switchVersion: switch result', result)

        // Reload the entire conversation to get the correct message history
        // This ensures tool messages and subsequent messages are correctly loaded
        if (conversationId) {
          console.log('switchVersion: reloading conversation', conversationId)
          const conversationData = await agentsApi.getConversation(conversationId)
          console.log('switchVersion: conversation data', conversationData)
          console.log('switchVersion: messages count', conversationData.messages?.length)

          const { convertBackendMessages } = await import('@/lib/utils/message-converter')
          const convertedMessages = convertBackendMessages(conversationData.messages as BackendMessage[])
          console.log('switchVersion: converted messages count', convertedMessages.length)
          console.log('switchVersion: converted messages', convertedMessages)

          // Update all messages
          setMessages(convertedMessages)
        } else {
          console.warn('switchVersion: no conversationId, cannot reload conversation')
        }
      } catch (err) {
        console.error('Failed to switch version:', err)
      }
    },
    [agentId, messages, isLoading, conversationId]
  )

  /**
   * Check if a message ID is a valid UUID (from backend) vs temporary ID (from frontend)
   */
  const isValidUUID = (id: string): boolean => {
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    return uuidRegex.test(id)
  }

  /**
   * Regenerate (retry) an assistant message using backend version management
   */
  const regenerate = useCallback(
    async (messageId: string) => {
      if (isLoading) return

      // Find the message
      const messageIndex = messages.findIndex((m) => m.id === messageId)
      if (messageIndex === -1) return

      const targetMessage = messages[messageIndex]
      if (targetMessage.role !== 'assistant') return

      // Check if this is a temporary ID (not saved to backend yet)
      // In this case, we need to resend the user message instead of regenerating
      if (!isValidUUID(messageId)) {
        // Find the user message before this assistant message
        const userMessageIndex = messageIndex - 1
        if (userMessageIndex >= 0 && messages[userMessageIndex]?.role === 'user') {
          const userMessage = messages[userMessageIndex]
          // Get text content from user message
          const textPart = userMessage.parts.find(p => p.type === 'text')
          const text = textPart && 'text' in textPart ? textPart.text : ''
          
          // Remove the failed assistant message and user message
          setMessages((prev) => prev.slice(0, userMessageIndex))
          
          // Resend the message
          if (text) {
            // Extract images if any
            const imageParts = userMessage.parts.filter(p => p.type === 'image')
            const images: ChatImageContent[] = imageParts.map(p => ({
              type: 'image_url' as const,
              url: 'url' in p ? p.url : '',
            })).filter(img => img.url)
            
            await sendMessage(text, images.length > 0 ? images : undefined)
          }
        }
        return
      }

      // Clear previous error
      setError(null)
      setStatus('loading')

      // Update message to loading state
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                parts: [],
                metadata: { ...msg.metadata, isLoading: true },
              }
            : msg
        )
      )

      try {
        // Use backend regenerate API which handles versioning
        const { stream, abort } = agentsApi.regenerateStream(agentId, messageId, variables)
        abortRef.current = abort

        const response = await stream

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.msg || `HTTP ${response.status}`)
        }

        setStatus('streaming')
        onStreamStart?.()

        // Content segments
        let segments: ContentSegment[] = []
        const reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }> = []
        let currentReasoningIndex = -1
        let ragSources: SourceDocumentPart[] = []
        const taskState: TaskState = { rag: 'pending', generating: 'pending', toolCalling: 'pending' }
        let newMessageId = messageId  // May be updated by message_start

        // Helper functions
        const getCurrentTextSegment = (): ContentSegment => {
          const lastSegment = segments[segments.length - 1]
          if (lastSegment && lastSegment.type === 'text') {
            return lastSegment
          }
          const newSegment: ContentSegment = { type: 'text', text: '' }
          segments.push(newSegment)
          return newSegment
        }

        const addToolGroupSegment = (toolCall: ToolCallPart): ContentSegment => {
          const lastSegment = segments[segments.length - 1]
          if (lastSegment && lastSegment.type === 'tool-group') {
            lastSegment.toolCalls = lastSegment.toolCalls || []
            lastSegment.toolCalls.push(toolCall)
            return lastSegment
          }
          const newSegment: ContentSegment = { 
            type: 'tool-group', 
            toolCalls: [toolCall],
            toolResults: []
          }
          segments.push(newSegment)
          return newSegment
        }

        const findToolGroup = (toolCallId: string): ContentSegment | undefined => {
          return segments.find(s => 
            s.type === 'tool-group' && 
            s.toolCalls?.some(tc => tc.toolCallId === toolCallId)
          )
        }

        streamingStateRef.current = {
          assistantMessageId: messageId,
          segments,
          reasoningBlocks,
          currentReasoningIndex,
          ragSources,
          taskState,
        }

        // Track version info from message_start
        let newVersionNumber = 1
        let newVersionCount = 1

        // Parse SSE stream
        for await (const event of parseSSEStream(response)) {
          switch (event.event as SSEEventType) {
            case 'message_start': {
              const data = event.data as SSEMessageStart & { version_number?: number; version_count?: number }
              // Backend creates a new message version with a new ID
              if (data.message_id) {
                newMessageId = data.message_id
                streamingStateRef.current.assistantMessageId = newMessageId
              }
              // Track version info for later use
              if (data.version_number) newVersionNumber = data.version_number
              if (data.version_count) newVersionCount = data.version_count
              break
            }

            case 'rag_start': {
              taskState.rag = 'running'
              streamingStateRef.current.taskState = taskState
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'reasoning_start': {
              // Start a new reasoning block and add it as a segment
              const newBlock = {
                text: '',
                startTime: Date.now(),
                state: 'streaming' as const,
              }
              reasoningBlocks.push(newBlock)
              currentReasoningIndex = reasoningBlocks.length - 1

              // Add reasoning segment to maintain order
              const reasoningSegment: ContentSegment = {
                type: 'reasoning',
                reasoningText: '',
                reasoningState: 'streaming',
                reasoningStartTime: Date.now(),
              }
              segments.push(reasoningSegment)

              // Update streamingStateRef for stop() to work correctly
              streamingStateRef.current.segments = segments
              streamingStateRef.current.reasoningBlocks = reasoningBlocks
              streamingStateRef.current.currentReasoningIndex = currentReasoningIndex
              break
            }

            case 'reasoning_delta': {
              const data = event.data as { delta: string }
              // Add to current reasoning block
              if (currentReasoningIndex >= 0 && reasoningBlocks[currentReasoningIndex]) {
                reasoningBlocks[currentReasoningIndex].text += data.delta

                // Update the corresponding reasoning segment (find last reasoning segment)
                let lastReasoningSegmentIndex = -1
                for (let i = segments.length - 1; i >= 0; i--) {
                  if (segments[i].type === 'reasoning') {
                    lastReasoningSegmentIndex = i
                    break
                  }
                }
                if (lastReasoningSegmentIndex >= 0) {
                  segments[lastReasoningSegmentIndex].reasoningText = reasoningBlocks[currentReasoningIndex].text
                }

                // Update streamingStateRef for stop() to work correctly
                streamingStateRef.current.segments = segments
                streamingStateRef.current.reasoningBlocks = reasoningBlocks
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'reasoning_end': {
              // Mark current reasoning block as done
              if (currentReasoningIndex >= 0 && reasoningBlocks[currentReasoningIndex]) {
                const block = reasoningBlocks[currentReasoningIndex]
                block.duration = Date.now() - block.startTime
                block.state = 'done'

                // Update the corresponding reasoning segment (find last reasoning segment)
                let lastReasoningSegmentIndex = -1
                for (let i = segments.length - 1; i >= 0; i--) {
                  if (segments[i].type === 'reasoning') {
                    lastReasoningSegmentIndex = i
                    break
                  }
                }
                if (lastReasoningSegmentIndex >= 0) {
                  segments[lastReasoningSegmentIndex].reasoningState = 'done'
                  segments[lastReasoningSegmentIndex].reasoningDuration = block.duration
                }

                // Update streamingStateRef for stop() to work correctly
                streamingStateRef.current.segments = segments
                streamingStateRef.current.reasoningBlocks = reasoningBlocks
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'content_delta': {
              const data = event.data as SSEContentDelta
              const textSegment = getCurrentTextSegment()
              textSegment.text = (textSegment.text || '') + data.delta

              // Collect all text from all text segments to check for complete XML
              const allText = segments
                .filter(s => s.type === 'text')
                .map(s => s.text || '')
                .join('')

              const hasStartTag = allText.includes('<user_input_request>')
              const hasEndTag = allText.includes('</user_input_request>')

              if (hasStartTag && hasEndTag) {
                // Complete XML detected - parse it
                const xmlMatch = allText.match(/<user_input_request>([\s\S]*?)<\/user_input_request>/)
                if (xmlMatch) {
                  const xmlContent = xmlMatch[1]
                  const questionMatch = xmlContent.match(/<question>([\s\S]*?)<\/question>/)
                  const optionsMatch = xmlContent.match(/<options>([\s\S]*?)<\/options>/)

                  if (questionMatch && optionsMatch) {
                    const question = questionMatch[1].trim()
                    const options: string[] = []
                    const optionMatches = optionsMatch[1].matchAll(/<option>([\s\S]*?)<\/option>/g)
                    for (const match of optionMatches) {
                      options.push(match[1].trim())
                    }

                    if (question && options.length >= 2) {
                      // Remove XML from all text segments
                      const textBeforeXML = allText.substring(0, allText.indexOf('<user_input_request>'))
                      const textAfterXML = allText.substring(allText.indexOf('</user_input_request>') + '</user_input_request>'.length)
                      const cleanedText = (textBeforeXML + textAfterXML).trim()

                      // Replace all text segments with a single cleaned one
                      segments = segments.filter(s => s.type !== 'text' && s.type !== 'user-input-request')
                      if (cleanedText) {
                        segments.push({
                          type: 'text',
                          text: cleanedText
                        })
                      }

                      // Add user input request segment
                      const userInputSegment: ContentSegment = {
                        type: 'user-input-request',
                        userInputRequest: {
                          type: 'user-input-request',
                          question,
                          options,
                          state: 'pending',
                        }
                      }
                      segments.push(userInputSegment)
                    }
                  }
                }
              }

              streamingStateRef.current.segments = segments

              if (taskState.generating === 'pending') {
                if (taskState.rag === 'running') {
                  taskState.rag = 'completed'
                }
                taskState.generating = 'running'
                streamingStateRef.current.taskState = taskState
              }

              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'rag_context': {
              const data = event.data as SSERagContext
              ragSources = data.contexts.map((ctx) => ({
                type: 'source-document' as const,
                sourceId: ctx.document_id,
                documentId: ctx.document_id,
                documentName: ctx.document_name,
                content: ctx.content,
                metadata: {
                  kb_id: ctx.kb_id,
                  kb_name: ctx.kb_name,
                  score: ctx.score,
                },
              }))
              streamingStateRef.current.ragSources = ragSources
              taskState.rag = 'completed'
              taskState.ragSourceCount = ragSources.length
              streamingStateRef.current.taskState = taskState
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'tool_call': {
              const data = event.data as SSEToolCall
              const toolCallPart: ToolCallPart = {
                type: 'tool-call',
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                toolDisplayName: data.tool_display_name,
                input: data.arguments,
                state: 'running',
              }
              addToolGroupSegment(toolCallPart)
              streamingStateRef.current.segments = segments
              taskState.toolCalling = 'running'
              const totalToolCalls = segments
                .filter(s => s.type === 'tool-group')
                .reduce((sum, s) => sum + (s.toolCalls?.length || 0), 0)
              taskState.toolCallCount = totalToolCalls
              streamingStateRef.current.taskState = taskState
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'tool_result': {
              const data = event.data as SSEToolResult
              const parsedOutput = parseToolResultOutput(data.result)
              const toolResultPart: ToolResultPart = {
                type: 'tool-result',
                toolCallId: data.tool_call_id,
                toolName: data.tool_name,
                toolDisplayName: data.tool_display_name,
                output: parsedOutput,
                isError: data.is_error,
              }
              const toolGroup = findToolGroup(data.tool_call_id)
              if (toolGroup) {
                toolGroup.toolResults = toolGroup.toolResults || []
                toolGroup.toolResults.push(toolResultPart)
                // Update corresponding tool call state (create new object for React to detect change)
                if (toolGroup.toolCalls) {
                  toolGroup.toolCalls = toolGroup.toolCalls.map(tc =>
                    tc.toolCallId === data.tool_call_id
                      ? { ...tc, state: data.is_error ? 'error' as const : 'done' as const }
                      : tc
                  )
                }
              }
              streamingStateRef.current.segments = segments
              const allToolCalls = segments
                .filter(s => s.type === 'tool-group')
                .flatMap(s => s.toolCalls || [])
              const allToolsCompleted = allToolCalls.every(tc => tc.state === 'done' || tc.state === 'error')
              if (allToolsCompleted && taskState.toolCalling === 'running') {
                taskState.toolCalling = 'completed'
                streamingStateRef.current.taskState = taskState
              }
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'output_truncated': {
              const truncatedSegment: ContentSegment = { type: 'truncated' }
              segments.push(truncatedSegment)
              streamingStateRef.current.segments = segments
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === messageId
                    ? {
                        ...msg,
                        parts: buildMessageParts(segments, reasoningBlocks, ragSources, true, taskState),
                      }
                    : msg
                )
              )
              break
            }

            case 'message_end': {
              if (taskState.toolCalling === 'running') {
                taskState.toolCalling = 'completed'
              }
              // Safety: ensure all tool calls are marked as done on message end
              for (const segment of segments) {
                if (segment.type === 'tool-group' && segment.toolCalls) {
                  segment.toolCalls = segment.toolCalls.map(tc =>
                    tc.state === 'running' ? { ...tc, state: 'done' as const } : tc
                  )
                }
              }
              // Mark all reasoning blocks as done
              reasoningBlocks.forEach(block => {
                if (block.state === 'streaming') {
                  block.duration = Date.now() - block.startTime
                  block.state = 'done'
                }
              })
              const newParts = buildMessageParts(segments, reasoningBlocks, ragSources, false, taskState)

              // Get version info from event data if available (for regenerate)
              // Priority: message_end > message_start > existing values
              const endData = event.data as SSEMessageEnd & { version_number?: number; version_count?: number }
              const finalVersionNumber = endData.version_number ?? newVersionNumber
              const finalVersionCount = endData.version_count ?? newVersionCount

              // Update message with new content and new ID from backend
              // Backend handles version management, frontend just updates display
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== messageId) return msg
                  return {
                    ...msg,
                    id: newMessageId,  // Use new ID from backend
                    parts: newParts,
                    versionNumber: finalVersionNumber,
                    versionCount: finalVersionCount,
                    metadata: { ...msg.metadata, isLoading: false, usage: endData.usage, timing: endData.timing },
                  }
                })
              )
              break
            }

            case 'error': {
              const data = event.data as SSEError
              const chatError: ChatError = {
                code: data.code,
                message: data.msg,
                quotaType: data.quota_type,
              }
              onError?.(chatError)

              const errorText = getErrorMessage(chatError)
              const errorSegment: ContentSegment = { type: 'text', text: errorText }
              const errorParts = buildMessageParts([errorSegment], [], [], false, undefined)

              // Show error as message content
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== messageId) return msg
                  return {
                    ...msg,
                    parts: errorParts,
                    metadata: { ...msg.metadata, isLoading: false, isError: true },
                  }
                })
              )
              break
            }
          }
        }

        setStatus('idle')
        onStreamEnd?.()
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
          setStatus('idle')
          return
        }

        const chatError: ChatError = {
          message: err instanceof Error ? err.message : 'Unknown error',
        }
        onError?.(chatError)

        const errorText = getErrorMessage(chatError)
        const errorSegment: ContentSegment = { type: 'text', text: errorText }
        const errorParts = buildMessageParts([errorSegment], [], [], false, undefined)

        // Show error as message content
        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id !== messageId) return msg
            return {
              ...msg,
              parts: errorParts,
              metadata: { ...msg.metadata, isLoading: false, isError: true },
            }
          })
        )

        setStatus('idle')
      } finally {
        abortRef.current = null
        streamingStateRef.current = {
          assistantMessageId: null,
          segments: [],
          reasoningBlocks: [],
          currentReasoningIndex: -1,
          ragSources: [],
          taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending' },
        }
      }
    },
    [
      agentId,
      variables,
      messages,
      isLoading,
      onError,
      onStreamStart,
      onStreamEnd,
      sendMessage,
    ]
  )

  return {
    messages,
    status,
    error,
    conversationId,
    isLoading,
    isStreaming,
    sendMessage,
    regenerate,
    switchVersion,
    stop,
    reset,
    setMessages,
    setConversationId,
  }
}

/**
 * Task state for tracking RAG, generating, and tool calling steps
 */
interface TaskState {
  rag: 'pending' | 'running' | 'completed' | 'error'
  generating: 'pending' | 'running' | 'completed' | 'error'
  toolCalling: 'pending' | 'running' | 'completed' | 'error'
  ragSourceCount?: number
  toolCallCount?: number
}

/**
 * A segment represents either text content, a tool call group, or a reasoning block
 * This allows all content to appear in the order they were triggered
 */
interface ContentSegment {
  type: 'text' | 'tool-group' | 'reasoning' | 'user-input-request' | 'truncated'
  // For text type
  text?: string
  // For tool-group type
  toolCalls?: ToolCallPart[]
  toolResults?: ToolResultPart[]
  // For reasoning type
  reasoningText?: string
  reasoningState?: 'streaming' | 'done'
  reasoningStartTime?: number
  reasoningDuration?: number
  // For user-input-request type
  userInputRequest?: UserInputRequestPart
}

/**
 * Build message parts from text segments, reasoning blocks, sources, and task state
 * Text and tool calls are interleaved based on when they appear in the stream
 */
function buildMessageParts(
  segments: ContentSegment[],
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>,
  sources: SourceDocumentPart[],
  isStreaming: boolean,
  taskState?: TaskState
): MessagePart[] {
  const parts: MessagePart[] = []

  // Add task parts for RAG and generating steps (not tool calling - we show individual tool calls instead)
  // Keep showing them even after streaming ends so they're visible when collapsed
  if (taskState) {
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

    // Note: We no longer add aggregated tool calling task here
    // Individual tool calls are shown in the segments below

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
  }

  // Add content segments in order (text, reasoning, and tool calls interleaved)
  for (const segment of segments) {
    if (segment.type === 'text' && segment.text && segment.text.length > 0) {
      const textPart: TextPart = {
        type: 'text',
        text: segment.text,
        state: isStreaming ? 'streaming' : 'done',
      }
      parts.push(textPart)
    } else if (segment.type === 'reasoning' && segment.reasoningText) {
      const reasoningPart: ReasoningPart = {
        type: 'reasoning',
        text: segment.reasoningText,
        state: segment.reasoningState || 'streaming',
        duration: segment.reasoningDuration,
      }
      parts.push(reasoningPart)
    } else if (segment.type === 'tool-group' && segment.toolCalls && segment.toolCalls.length > 0) {
      // Add tool calls and their results
      for (const toolCall of segment.toolCalls) {
        parts.push(toolCall)
        // Find matching result
        const result = segment.toolResults?.find(r => r.toolCallId === toolCall.toolCallId)
        if (result) {
          parts.push(result)
        }
      }
    } else if (segment.type === 'user-input-request' && segment.userInputRequest) {
      // Add user input request
      parts.push(segment.userInputRequest)
    } else if (segment.type === 'truncated') {
      // Add truncated warning
      parts.push({ type: 'truncated' })
    }
  }

  // Add sources at the end
  if (sources.length > 0 && !isStreaming) {
    parts.push(...sources)
  }

  return parts
}

/**
 * Get user-friendly error message based on error type
 * Returns an object with message and optional i18n key
 */
function getErrorMessage(error: ChatError): string {
  const { code, message, quotaType } = error

  // Network errors
  if (message?.includes('fetch') || message?.includes('network') || message?.includes('Failed to fetch')) {
    return '抱歉，网络连接出现问题，请检查您的网络后重试。'
  }

  // Timeout errors
  if (message?.includes('timeout') || message?.includes('Timeout')) {
    return '抱歉，请求超时了，可能是网络较慢或服务器繁忙，请稍后重试。'
  }

  // Quota exceeded (business code 6103 or HTTP 429)
  if (code === 6103 || code === 429 || quotaType) {
    const type = quotaType === 'input' ? '输入' : quotaType === 'output' ? '输出' : '使用'
    return `抱歉，${type}配额已用尽，请联系管理员或稍后重试。`
  }

  // Model vision not supported (business code 6105)
  if (code === 6105) {
    return '当前模型不支持视觉功能，请更换支持视觉的模型'
  }

  // Model not found (business code 6100 or specific error messages)
  if (code === 6100 || message?.includes('No model found') || message?.includes('no_default_model') || message?.includes('no_chat_model')) {
    return '抱歉，尚未配置默认模型，请联系管理员在后台设置默认的聊天模型。'
  }

  // Model not authorized (business code 6104)
  if (code === 6104) {
    return '抱歉，当前团队未授权使用该模型，请联系管理员。'
  }

  // Authentication errors (business code 2000-2999 or HTTP 401/403)
  if ((code && code >= 2000 && code < 3000) || code === 401 || code === 403) {
    return '抱歉，您的登录已过期或没有访问权限，请重新登录。'
  }

  // Not found (business code 4000-4999 or HTTP 404)
  if ((code && code >= 4000 && code < 5000) || code === 404) {
    return '抱歉，找不到相关资源，可能已被删除或移动。'
  }

  // HTTP Server errors (500-599 range only)
  if (code && code >= 500 && code < 600) {
    return '抱歉，服务器出现了一些问题，我们正在处理中，请稍后重试。'
  }

  // Model not configured
  if (message?.includes('model') && message?.includes('configured')) {
    return '抱歉，当前 Agent 尚未配置模型，请先在设置中配置一个可用的模型。'
  }

  // If there's a specific message from the server, use it
  if (message && message.length > 0 && message.length < 200) {
    return message
  }

  // Default error message
  return '抱歉，出现了一些问题，请稍后重试。如果问题持续存在，请联系管理员。'
}

/**
 * Get i18n key for error code
 */
export function getErrorMsgKey(error: ChatError): string | undefined {
  const { code, message } = error

  // If server returned an i18n key
  if (error.msgKey) return error.msgKey
  if (message === 'model_vision_not_supported') return 'modelVisionNotSupported'

  // Map code to i18n key
  if (code === 6105) return 'modelVisionNotSupported'
  if (code === 6100) return 'modelNotFound'
  if (code === 6104) return 'modelNotAuthorized'
  if (code === 6103) return 'quotaExceeded'

  return undefined
}
