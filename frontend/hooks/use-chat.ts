'use client'

import { useState, useCallback, useRef, useMemo, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import {
  agentsApi,
  publicAgentsApi,
  parseSSEStream,
  type ChatRequest,
  type ChatImageContent,
  type ChatFileContent,
  type ChatFileUrl,
  type MessageVersion,
  type SSEEventType,
  type SSEMessageStart,
  type SSEContentDelta,
  type SSERagContext,
  type SSEMessageEnd,
  type SSEIterationCapReached,
  type SSEToolCall,
  type SSEToolResult,
  type SSEMediaResult,
} from '@/lib/api'
import type { AgentRunEventOut, AgentRunStartOut, AgentRunStatus, AgentRunStatusOut } from '@/lib/api/agents'
import type {
  ChatMessage,
  MessagePart,
  TextPart,
  ReasoningPart,
  SourceDocumentPart,
  TaskPart,
  ToolCallPart,
  ToolResultPart,
  McpToolCallPart,
  McpToolResultPart,
  UserInputRequestPart,
  MediaResultPart,
} from '@/components/chat'
import { getErrorMessage as getApiErrorMessage } from '@/lib/api/client'
import { parseToolResultOutput, shouldDisplayMediaResultInBody } from '@/lib/utils/tool-result'

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
  /** Injectable chat streaming API (defaults to agentsApi) */
  api?: ChatStreamApi
  /** Initial messages (e.g. embed greeting) */
  initialMessages?: ChatMessage[]
}

// Re-export for convenience
export type { ChatImageContent, ChatFileContent, ChatFileUrl }

/**
 * Injectable chat streaming API used by useChat.
 * The default wraps agentsApi; embed pages pass an embed-backed implementation.
 */
export interface ChatStreamApi {
  chatStream(agentId: string, request: ChatRequest): { stream: Promise<Response>; abort: () => void }
  getConversation(conversationId: string): Promise<{ messages: ChatMessage[] }>
  editMessageStream(agentId: string, messageId: string, content: string): { stream: Promise<Response>; abort: () => void }
  regenerateStream(agentId: string, messageId: string, variables: Record<string, unknown>): { stream: Promise<Response>; abort: () => void }
  getMessageVersions(agentId: string, messageId: string): Promise<MessageVersion[]>
  switchMessageVersion(agentId: string, messageId: string, versionId: string): Promise<void>
  startRun?(agentId: string, request: ChatRequest): Promise<AgentRunStartOut>
  streamRun?(agentId: string, runId: string, afterSequence?: number): { stream: Promise<Response>; abort: () => void }
  getRunStatus?(agentId: string, runId: string): Promise<AgentRunStatusOut>
  getRunEvents?(agentId: string, runId: string, afterSequence?: number): Promise<AgentRunEventOut[]>
  postRunInput?(
    agentId: string,
    runId: string,
    body: { delivery: 'steer' | 'follow_up' | 'auto'; content?: string; request_id?: string }
  ): Promise<AgentRunStatusOut>
  stopRun?(agentId: string, runId: string): Promise<AgentRunStatusOut>
}


const defaultChatApi: ChatStreamApi = {
  chatStream: (agentId, request) => agentsApi.chatStream(agentId, request),
  startRun: agentsApi.startRun
    ? (agentId, request) => agentsApi.startRun!(agentId, request)
    : undefined,
  streamRun: agentsApi.streamRun
    ? (agentId, runId, afterSequence) => agentsApi.streamRun!(agentId, runId, afterSequence)
    : undefined,
  getConversation: async (conversationId) => {
    const data = await agentsApi.getConversation(conversationId)
    return { messages: convertBackendMessages(data.messages as BackendMessage[]) }
  },
  editMessageStream: (agentId, messageId, content) => agentsApi.editMessageStream(agentId, messageId, content),
  regenerateStream: (agentId, messageId, variables) => agentsApi.regenerateStream(agentId, messageId, variables),
  getMessageVersions: (agentId, messageId) => agentsApi.getMessageVersions(agentId, messageId),
  switchMessageVersion: async (agentId, messageId, versionId) => {
    await agentsApi.switchMessageVersion(agentId, messageId, versionId)
  },
  getRunStatus: (agentId, runId) => publicAgentsApi.getRunStatus(agentId, runId),
  getRunEvents: (agentId, runId, afterSequence) => publicAgentsApi.getRunEvents(agentId, runId, afterSequence),
  postRunInput: (agentId, runId, body) => publicAgentsApi.postRunInput(agentId, runId, body),
  stopRun: (agentId, runId) => publicAgentsApi.stopRun(agentId, runId),
}

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
  /** Durable run identity when the active stream is backed by AgentRun. */
  runId: string | null
  /** Latest server-authoritative run status. */
  runStatus: AgentRunStatus | null
  /** Send a message with optional images (vision) and/or file URLs (file upload) */
  sendMessage: (message: string, images?: ChatImageContent[], fileUrls?: ChatFileUrl[]) => Promise<void>
  /** Regenerate (retry) a message by ID */
  regenerate: (messageId: string) => Promise<void>
  /** Edit a user message and regenerate the downstream response */
  editMessage: (messageId: string, content: string) => Promise<void>
  /** Switch to a different version of a message */
  switchVersion: (messageId: string, versionIndex: number) => Promise<void>
  /** Stop current streaming run after the server emits its terminal event. */
  stop: () => Promise<void>
  /** Replay buffered events for the current conversation's active run. */
  reconnect: () => void
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
    api: overrideApi,
    initialMessages = [],
  } = options

  const api = useMemo(() => overrideApi ?? defaultChatApi, [overrideApi])
  const runApi = useMemo(() => {
    const useDefaultRunControls = api === defaultChatApi
    return {
      startRun: api.startRun,
      streamRun: api.streamRun,
      getRunStatus: api.getRunStatus ?? (useDefaultRunControls ? publicAgentsApi.getRunStatus : undefined),
      getRunEvents: api.getRunEvents ?? (useDefaultRunControls ? publicAgentsApi.getRunEvents : undefined),
      postRunInput: api.postRunInput ?? (useDefaultRunControls ? publicAgentsApi.postRunInput : undefined),
      stopRun: api.stopRun ?? (useDefaultRunControls ? publicAgentsApi.stopRun : undefined),
    }
  }, [api])

  const tError = useTranslations('errors')
  const tAuth = useTranslations('auth')
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [status, setStatus] = useState<ChatStatus>('idle')
  const [error, setError] = useState<ChatError | null>(null)
  const [conversationId, setConversationIdState] = useState<string | null>(initialConversationId ?? null)
  const [runId, setRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<AgentRunStatus | null>(null)

  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const statusRef = useRef<ChatStatus>(status)
  const conversationIdRef = useRef<string | null>(conversationId)
  const runIdRef = useRef<string | null>(null)
  const runStatusRef = useRef<AgentRunStatus | null>(null)
  const lastSequenceRef = useRef(0)
  const appliedSequenceKeysRef = useRef(new Set<string>())
  const subscriptionAbortRef = useRef<(() => void) | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const connectionEpochRef = useRef(0)
  const previousConversationRef = useRef<string | null>(conversationId)
  const activeRunConversationRef = useRef<string | null>(conversationId)
  const activeSessionRef = useRef<AssistantStreamSession | null>(null)
  const sessionsByRunRef = useRef(new Map<string, AssistantStreamSession>())
  const pendingRunInputsRef = useRef<PendingRunInput[]>([])
  const flushPendingInputsRef = useRef<(runId: string) => void>(() => undefined)
  const terminalRunsRef = useRef(new Set<string>())
  const terminalWaitersRef = useRef(new Map<string, Set<() => void>>())
  const runStartWaiterRef = useRef<RunStartWaiter | null>(null)

  const streamingStateRef = useRef<StreamingState>(emptyStreamingState())
  const scheduledStreamingFlushRef = useRef<
    | { id: number; type: 'frame' }
    | { id: ReturnType<typeof setTimeout>; type: 'timeout' }
    | null
  >(null)

  const isLoading = status === 'loading' || status === 'streaming'
  const isStreaming = status === 'streaming'

  const setCurrentStatus = useCallback((next: ChatStatus) => {
    statusRef.current = next
    setStatus(next)
  }, [])

  const setCurrentRunStatus = useCallback((next: AgentRunStatus | null) => {
    runStatusRef.current = next
    setRunStatus(next)
  }, [])

  const waitForRunEnd = useCallback((targetRunId: string) => {
    if (terminalRunsRef.current.has(targetRunId)) return Promise.resolve()
    return new Promise<void>((resolve) => {
      const waiters = terminalWaitersRef.current.get(targetRunId) ?? new Set<() => void>()
      waiters.add(resolve)
      terminalWaitersRef.current.set(targetRunId, waiters)
    })
  }, [])

  const resolveRunEnd = useCallback((targetRunId: string) => {
    terminalRunsRef.current.add(targetRunId)
    const waiters = terminalWaitersRef.current.get(targetRunId)
    terminalWaitersRef.current.delete(targetRunId)
    waiters?.forEach((resolve) => resolve())
  }, [])
  const resolveRunStart = useCallback((session: AssistantStreamSession, nextRunId: string) => {
    const waiter = runStartWaiterRef.current
    if (!waiter || waiter.session !== session) return
    waiter.resolve(nextRunId)
    runStartWaiterRef.current = null
  }, [])

  const setConversationId = useCallback((next: React.SetStateAction<string | null>) => {
    setConversationIdState((current) => {
      const resolved = typeof next === 'function'
        ? (next as (value: string | null) => string | null)(current)
        : next
      conversationIdRef.current = resolved
      return resolved
    })
  }, [])

  const cancelScheduledStreamingFlush = useCallback(() => {
    const scheduled = scheduledStreamingFlushRef.current
    if (!scheduled) return
    if (scheduled.type === 'frame') {
      window.cancelAnimationFrame(scheduled.id)
    } else {
      globalThis.clearTimeout(scheduled.id)
    }
    scheduledStreamingFlushRef.current = null
  }, [])

  const resetStreamingState = useCallback(() => {
    streamingStateRef.current = emptyStreamingState()
  }, [])

  const storeRunSnapshot = useCallback((conversation = activeRunConversationRef.current) => {
    const activeRunId = runIdRef.current
    if (!agentId || !conversation || !activeRunId) return
    saveRunSnapshot(agentId, conversation, {
      runId: activeRunId,
      lastSequence: lastSequenceRef.current,
    })
  }, [agentId])

  const clearStoredRunSnapshot = useCallback((conversation = activeRunConversationRef.current) => {
    if (!agentId || !conversation) return
    removeRunSnapshot(agentId, conversation)
  }, [agentId])

  const trackRun = useCallback((nextRunId: string, conversation?: string | null) => {
    if (runIdRef.current !== nextRunId) {
      runIdRef.current = nextRunId
      lastSequenceRef.current = 0
      appliedSequenceKeysRef.current.clear()
      setRunId(nextRunId)
    }
    if (conversation) {
      activeRunConversationRef.current = conversation
    }
    for (const pending of pendingRunInputsRef.current) {
      if (!pending.runId) pending.runId = nextRunId
    }
    queueMicrotask(() => {
      if (runIdRef.current === nextRunId) flushPendingInputsRef.current(nextRunId)
    })
  }, [])

  const syncStreamingState = useCallback((session: AssistantStreamSession) => {
    streamingStateRef.current = {
      assistantMessageId: session.displayMessageId,
      visibleMessageId: session.displayMessageId,
      backendMessageId: session.backendMessageId,
      segments: session.state.segments,
      reasoningBlocks: session.state.reasoningBlocks,
      currentReasoningIndex: session.state.currentReasoningIndex,
      ragSources: session.state.ragSources,
      taskState: session.state.taskState,
    }
  }, [])

  const renderSession = useCallback((session: AssistantStreamSession, streaming: boolean, endData?: SSEMessageEnd) => {
    const messageId = session.displayMessageId
    if (!messageId) return
    const parts = buildMessageParts(
      session.state.segments,
      session.state.ragSources,
      streaming
    )
    setMessages((previous) => previous.map((message) => (
      message.id === messageId
        ? {
            ...message,
            parts,
            metadata: {
              ...message.metadata,
              ...(streaming
                ? { isLoading: true }
                : {
                    isLoading: false,
                    isManuallyStopped: false,
                    isError: false,
                    errorMessage: undefined,
                    preservedPartialProgress: undefined,
                    ...(endData ? { usage: endData.usage, timing: endData.timing } : {}),
                  }),
            },
          }
        : message
    )))
  }, [])

  const scheduleSessionRender = useCallback((session: AssistantStreamSession) => {
    if (scheduledStreamingFlushRef.current) return
    const flush = () => {
      scheduledStreamingFlushRef.current = null
      renderSession(session, true)
    }
    if (typeof window !== 'undefined' && 'requestAnimationFrame' in window) {
      const id = window.requestAnimationFrame(flush)
      scheduledStreamingFlushRef.current = { id, type: 'frame' }
      return
    }
    const id = globalThis.setTimeout(flush, 16)
    scheduledStreamingFlushRef.current = { id, type: 'timeout' }
  }, [renderSession])

  const ensureSession = useCallback((messageId: string | null, runIdForSession?: string) => {
    if (runIdForSession) {
      const existing = sessionsByRunRef.current.get(runIdForSession)
      if (existing) {
        activeSessionRef.current = existing
        return existing
      }
    }

    if (!messageId) return null
    const existingMessage = messagesRef.current.find((message) => message.id === messageId)
    const session: AssistantStreamSession = {
      mode: 'reconnect',
      displayMessageId: messageId,
      backendMessageId: messageId,
      state: existingMessage ? createAssistantStreamStateFromParts(existingMessage.parts) : createAssistantStreamState(),
      versionNumber: existingMessage?.versionNumber ?? 1,
      versionCount: existingMessage?.versionCount ?? 1,
      receivedTerminalEvent: false,
      receivedMessageEnd: false,
      endNotified: false,
      runId: runIdForSession,
    }
    setMessages((previous) => previous.some((message) => message.id === messageId)
      ? previous
      : [...previous, {
          id: messageId,
          role: 'assistant',
          parts: [],
          createdAt: new Date(),
          metadata: { isLoading: true, isManuallyStopped: false },
        }])
    activeSessionRef.current = session
    if (runIdForSession) sessionsByRunRef.current.set(runIdForSession, session)
    syncStreamingState(session)
    return session
  }, [syncStreamingState])

  const reloadConversationMessages = useCallback(async (targetConversationId = conversationIdRef.current) => {
    if (!targetConversationId) return
    const { messages: convertedMessages } = await api.getConversation(targetConversationId)
    const currentById = new Map(messagesRef.current.map((message) => [message.id, message]))
    setMessages(convertedMessages.map((message) => {
      const previous = currentById.get(message.id)
      if (!previous?.metadata) return message
      const transientKeys = ['errorCode', 'errorMessage', 'preservedPartialProgress', 'isManuallyStopped', 'runInputState', 'runInputKind', 'runInputSequence']
      const transientMetadata = Object.fromEntries(
        transientKeys
          .filter((key) => {
            const value = previous.metadata?.[key]
            return value !== undefined && value !== false && value !== null
          })
          .map((key) => [key, previous.metadata?.[key]])
      )
      if (previous.metadata.isError === true) transientMetadata.isError = true
      return Object.keys(transientMetadata).length > 0
        ? { ...message, metadata: { ...message.metadata, ...transientMetadata } }
        : message
    }))
  }, [api])

  const notifyStreamEnd = useCallback((session: AssistantStreamSession) => {
    if (session.endNotified) return
    session.endNotified = true
    onStreamEnd?.()
  }, [onStreamEnd])

  const finishAssistantMessage = useCallback((session: AssistantStreamSession, data: SSEMessageEnd = {} as SSEMessageEnd) => {
    cancelScheduledStreamingFlush()
    finalizeStreamingState(session.state)
    const endData = data as SSEMessageEnd & { version_number?: number; version_count?: number }
    const previousMessageId = session.displayMessageId
    const nextMessageId = session.keepDisplayIdOnStart && session.backendMessageId
      ? session.backendMessageId
      : session.displayMessageId
    if (!previousMessageId || !nextMessageId) return

    session.versionNumber = endData.version_number ?? session.versionNumber
    session.versionCount = endData.version_count ?? session.versionCount
    const parts = buildMessageParts(
      session.state.segments,
      session.state.ragSources,
      false
    )
    setMessages((previous) => previous.map((message) => (
      message.id === previousMessageId
        ? {
            ...message,
            id: nextMessageId,
            parts,
            versionNumber: session.versionNumber,
            versionCount: session.versionCount,
            metadata: {
              ...message.metadata,
              isLoading: false,
              isManuallyStopped: false,
              isError: false,
              errorMessage: undefined,
              preservedPartialProgress: undefined,
              usage: endData.usage,
              timing: endData.timing,
            },
          }
        : message
    )))
    session.displayMessageId = nextMessageId
    session.receivedMessageEnd = true
    session.receivedTerminalEvent = true
    syncStreamingState(session)
  }, [cancelScheduledStreamingFlush, syncStreamingState])

  const markAssistantStopped = useCallback((session: AssistantStreamSession) => {
    cancelScheduledStreamingFlush()
    finalizeStreamingState(session.state)
    const messageId = session.displayMessageId || session.backendMessageId
    if (!messageId) return
    const stoppedParts = appendStoppedPart(buildMessageParts(
      session.state.segments,
      session.state.ragSources,
      false
    ))
    setMessages((previous) => previous.map((message) => (
      message.id === messageId
        ? {
            ...message,
            parts: stoppedParts,
            metadata: { ...message.metadata, isLoading: false, isManuallyStopped: true },
          }
        : message
    )))
    session.receivedTerminalEvent = true
    syncStreamingState(session)
  }, [cancelScheduledStreamingFlush, syncStreamingState])

  const markAssistantError = useCallback((session: AssistantStreamSession, chatError: ChatError) => {
    cancelScheduledStreamingFlush()
    if (session.state.taskState.compression === 'running') {
      session.state.taskState.compression = 'error'
      updateLatestTimelineTask(session.state.segments, 'compression', 'error')
    }
    const errorText = getErrorMessage(chatError, tError, tAuth)
    const { parts, preservedProgress } = buildErroredMessageParts({
      ...session.state,
      errorText,
    })
    const messageId = session.displayMessageId || session.backendMessageId
    if (messageId) {
      setMessages((previous) => previous.map((message) => (
        message.id === messageId
          ? {
              ...message,
              parts,
              metadata: {
                ...message.metadata,
                isLoading: false,
                isError: true,
                errorMessage: errorText,
                errorCode: chatError.code,
                preservedPartialProgress: preservedProgress,
              },
            }
          : message
      )))
    }
    session.receivedTerminalEvent = true
    syncStreamingState(session)
  }, [cancelScheduledStreamingFlush, syncStreamingState, tAuth, tError])

  const reconcileOptimisticUserMessage = useCallback((
    session: AssistantStreamSession,
    persistedUserMessageId: string,
  ) => {
    const optimisticUserMessageId = session.optimisticUserMessageId
    if (!optimisticUserMessageId) return

    session.optimisticUserMessageId = persistedUserMessageId
    setMessages((previous) => previous.map((message) => {
      if (message.id !== optimisticUserMessageId) return message
      const metadata = { ...message.metadata }
      delete metadata.pendingPersistence
      return {
        ...message,
        id: persistedUserMessageId,
        metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
      }
    }))
  }, [])

  const markRunInputAccepted = useCallback((data: Record<string, unknown>, event: NormalizedStreamEvent) => {
    const kind = data.kind === 'follow_up' ? 'follow_up' : 'steer'
    const content = typeof data.content === 'string' ? data.content : ''
    const inputSequence = typeof data.sequence === 'number' ? data.sequence : undefined
    const pendingIndex = pendingRunInputsRef.current.findIndex((input) => (
      input.kind === kind && input.content === content
    ))
    const pending = pendingIndex >= 0 ? pendingRunInputsRef.current.splice(pendingIndex, 1)[0] : undefined
    const runIdentity = event.envelope?.run_id ?? runIdRef.current ?? 'unknown'
    const messageId = pending?.messageId ?? `run-input-${runIdentity}-${inputSequence ?? event.envelope?.sequence ?? Date.now()}`
    setMessages((previous) => {
      let committed = false
      const next = previous.map((message) => {
        const matchesInput = message.id === messageId || (
          inputSequence !== undefined && message.metadata?.runInputSequence === inputSequence
        )
        if (!matchesInput) return message
        committed = true
        return {
          ...message,
          metadata: {
            ...message.metadata,
            runInputState: 'committed',
            runInputKind: kind,
            runInputSequence: inputSequence,
          },
        }
      })
      if (committed || pending) return next
      return [...next, {
        id: messageId,
        role: 'user',
        parts: [{ type: 'text', text: content }],
        createdAt: new Date(),
        metadata: {
          runInputState: 'committed',
          runInputKind: kind,
          runInputSequence: inputSequence,
        },
      }]
    })
  }, [])

  const applyIncomingEvent = useCallback((rawEvent: { event: string; data: unknown }, providedSession?: AssistantStreamSession) => {
    const event = normalizeStreamEvent(rawEvent)
    let session = providedSession ?? activeSessionRef.current
    const envelope = event.envelope

    if (envelope) {
      const currentRunId = runIdRef.current
      if (currentRunId && currentRunId !== envelope.run_id) {
        lastSequenceRef.current = 0
        appliedSequenceKeysRef.current.clear()
      }
      trackRun(envelope.run_id)
      const sequenceKey = `${envelope.run_id}:${envelope.sequence}`
      if (appliedSequenceKeysRef.current.has(sequenceKey)) return
      if (lastSequenceRef.current !== 0 && envelope.sequence <= lastSequenceRef.current) return
      appliedSequenceKeysRef.current.add(sequenceKey)
      lastSequenceRef.current = Math.max(lastSequenceRef.current, envelope.sequence)
      if (session) {
        session.runId = envelope.run_id
        sessionsByRunRef.current.set(envelope.run_id, session)
        activeSessionRef.current = session
        resolveRunStart(session, envelope.run_id)
      }
    } else if (event.event === 'run_start') {
      const eventRunId = typeof event.data === 'object' && event.data && typeof (event.data as Record<string, unknown>).run_id === 'string'
        ? (event.data as Record<string, unknown>).run_id as string
        : null
      if (eventRunId) {
        trackRun(eventRunId)
        if (session) {
          session.runId = eventRunId
          sessionsByRunRef.current.set(eventRunId, session)
          resolveRunStart(session, eventRunId)
        }
      }
    }

    if (session?.runId) resolveRunStart(session, session.runId)

    const data = (event.data && typeof event.data === 'object' ? event.data : {}) as Record<string, unknown>
    if (event.event === 'run_start' || event.event === 'run_status') {
      const nextStatus = data.status as AgentRunStatus | undefined
      if (nextStatus) {
        setCurrentRunStatus(nextStatus)
        if (isActiveRunStatus(nextStatus)) setCurrentStatus('streaming')
      }
      storeRunSnapshot()
      return
    }

    if (event.event === 'input_accepted') {
      markRunInputAccepted(data, event)
      storeRunSnapshot()
      return
    }

    const eventMessageId = envelope?.message_id ?? getEventMessageId(event)
    if (!session && eventMessageId) {
      session = ensureSession(eventMessageId, envelope?.run_id)
    }

    if (event.event === 'message_start') {
      const startData = {
        ...data,
        ...(eventMessageId ? { message_id: eventMessageId } : {}),
      } as SSEMessageStart & {
        edited_message_id?: string
        edited_version_number?: number
        edited_version_count?: number
      }
      if (!session) return
      const nextConversationId = startData.conversation_id
      if (nextConversationId) {
        activeRunConversationRef.current = nextConversationId
        if (conversationIdRef.current !== nextConversationId) {
          setConversationId(nextConversationId)
          onConversationChange?.(nextConversationId)
        }
      }
      if (startData.user_message_id) {
        reconcileOptimisticUserMessage(session, startData.user_message_id)
      }
      if (session.sourceMessageId && startData.edited_message_id) {
        setMessages((previous) => previous.map((message) => (
          message.id === session.sourceMessageId
            ? {
                ...message,
                id: startData.edited_message_id ?? message.id,
                versionNumber: startData.edited_version_number ?? message.versionNumber,
                versionCount: startData.edited_version_count ?? message.versionCount,
              }
            : message
        )))
        session.sourceMessageId = startData.edited_message_id
      }
      if (startData.message_id) {
        const nextMessageId = startData.message_id
        session.backendMessageId = nextMessageId
        if (!session.keepDisplayIdOnStart) {
          const previousMessageId = session.displayMessageId
          session.displayMessageId = nextMessageId
          setMessages((previous) => {
            if (!previousMessageId) {
              return previous.some((message) => message.id === nextMessageId)
                ? previous
                : [...previous, {
                    id: nextMessageId,
                    role: 'assistant',
                    parts: [],
                    createdAt: new Date(),
                    metadata: { isLoading: true, isManuallyStopped: false },
                  }]
            }
            return previous.map((message) => (
              message.id === previousMessageId ? { ...message, id: nextMessageId } : message
            ))
          })
        }
      }
      syncStreamingState(session)
      storeRunSnapshot()
      return
    }

    if (event.event === 'message_end') {
      if (session) finishAssistantMessage(session, data as unknown as SSEMessageEnd)
      storeRunSnapshot()
      return
    }

    if (event.event === 'error') {
      if (session) {
        const chatError: ChatError = {
          code: typeof data.code === 'number' ? data.code : undefined,
          message: typeof data.msg === 'string' ? data.msg : '',
          quotaType: typeof data.quota_type === 'string' ? data.quota_type : undefined,
        }
        onError?.(chatError)
        markAssistantError(session, chatError)
      }
      storeRunSnapshot()
      return
    }

    if (event.event === 'run_end') {
      const terminalStatus = data.status as AgentRunStatus | undefined
      const terminalSession = session ?? (eventMessageId ? ensureSession(eventMessageId, envelope?.run_id) : null)
      if (terminalSession) {
        if (terminalStatus === 'stopped') {
          markAssistantStopped(terminalSession)
        } else if (terminalStatus === 'failed') {
          if (!terminalSession.receivedTerminalEvent) {
            markAssistantError(terminalSession, {
              message: typeof data.msg === 'string' ? data.msg : 'Run failed',
            })
          }
        } else if (!terminalSession.receivedMessageEnd) {
          finishAssistantMessage(terminalSession)
        }
        if (terminalSession.reloadAfterTerminal) {
          void reloadConversationMessages().catch(() => undefined)
        }
        notifyStreamEnd(terminalSession)
      }
      if (terminalStatus) setCurrentRunStatus(terminalStatus)
      const terminalRunId = envelope?.run_id ?? runIdRef.current
      if (terminalRunId) {
        resolveRunEnd(terminalRunId)
        clearStoredRunSnapshot()
        sessionsByRunRef.current.delete(terminalRunId)
      }
      setCurrentStatus('idle')
      if (!envelope || envelope.run_id === runIdRef.current) {
        runIdRef.current = null
        setRunId(null)
      }
      resetStreamingState()
      return
    }

    if (!session) return
    const changed = applyAssistantStreamEvent(session.state, { event: event.event, data: event.data })
    syncStreamingState(session)
    if (changed) {
      if (event.event === 'content_delta' || event.event === 'reasoning_delta') {
        scheduleSessionRender(session)
      } else {
        renderSession(session, true)
      }
    }
    storeRunSnapshot()
  }, [
    ensureSession,
    finishAssistantMessage,
    markAssistantError,
    markAssistantStopped,
    markRunInputAccepted,
    notifyStreamEnd,
    onConversationChange,
    onError,
    reconcileOptimisticUserMessage,
    reloadConversationMessages,
    renderSession,
    resetStreamingState,
    scheduleSessionRender,
    setConversationId,
    setCurrentRunStatus,
    setCurrentStatus,
    storeRunSnapshot,
    syncStreamingState,
    trackRun,
    resolveRunEnd,
    resolveRunStart,
    clearStoredRunSnapshot,
  ])

  const startSubscription = useCallback((targetRunId: string) => {
    subscriptionAbortRef.current?.()
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let streamAbort: (() => void) | null = null
    const scheduleRetry = () => {
      if (cancelled || runIdRef.current !== targetRunId || !isActiveRunStatus(runStatusRef.current)) return
      timer = globalThis.setTimeout(() => {
        timer = null
        startSubscription(targetRunId)
      }, 1000)
    }
    subscriptionAbortRef.current = () => {
      cancelled = true
      if (timer) globalThis.clearTimeout(timer)
      timer = null
      streamAbort?.()
      streamAbort = null
    }

    if (runApi.streamRun) {
      try {
        const source = runApi.streamRun(agentId, targetRunId, lastSequenceRef.current)
        streamAbort = source.abort
        const consumeSubscription = async () => {
          try {
            const response = await source.stream
            if (!response.ok) throw new Error(`Run stream failed (${response.status})`)
            for await (const event of parseSSEStream(response)) {
              if (cancelled || runIdRef.current !== targetRunId) return
              applyIncomingEvent(event)
            }
            scheduleRetry()
          } catch {
            scheduleRetry()
          }
        }
        void consumeSubscription()
        return
      } catch {
        // Fall through to replay polling when a custom stream adapter cannot subscribe.
      }
    }

    const poll = async () => {
      if (cancelled || runIdRef.current !== targetRunId || !runApi.getRunEvents) return
      try {
        const events = await runApi.getRunEvents(agentId, targetRunId, lastSequenceRef.current)
        if (cancelled || runIdRef.current !== targetRunId) return
        for (const event of events) {
          applyIncomingEvent({ event: event.type, data: event })
        }
      } catch {
        // Keep the durable run alive. The next focus or polling turn retries the replay endpoint.
      }
      if (cancelled || runIdRef.current !== targetRunId || !isActiveRunStatus(runStatusRef.current)) return
      timer = globalThis.setTimeout(() => { void poll() }, 1000)
    }

    void poll()
  }, [agentId, applyIncomingEvent, runApi])

  const reconnectToRun = useCallback(async (targetConversationId = conversationIdRef.current) => {
    if (!agentId || !targetConversationId || !runApi.getRunStatus) return
    const currentRunId = activeRunConversationRef.current === targetConversationId
      ? runIdRef.current
      : null
    const stored = currentRunId
      ? { runId: currentRunId, lastSequence: lastSequenceRef.current }
      : loadRunSnapshot(agentId, targetConversationId)
    if (!stored) return

    trackRun(stored.runId, targetConversationId)
    lastSequenceRef.current = stored.lastSequence
    try {
      const current = await runApi.getRunStatus(agentId, stored.runId)
      setCurrentRunStatus(current.status)
      if (!isActiveRunStatus(current.status)) {
        clearStoredRunSnapshot(targetConversationId)
        if (runIdRef.current === stored.runId) {
          runIdRef.current = null
          setRunId(null)
        }
        setCurrentStatus('idle')
        return
      }
      setCurrentStatus('streaming')
      startSubscription(stored.runId)
    } catch {
      // A transient status failure must not stop a server-owned run.
    }
  }, [agentId, clearStoredRunSnapshot, runApi, setCurrentRunStatus, setCurrentStatus, startSubscription, trackRun])

  const reconnect = useCallback(() => {
    void reconnectToRun()
  }, [reconnectToRun])

  const disconnectLocalSubscription = useCallback(() => {
    connectionEpochRef.current += 1
    subscriptionAbortRef.current?.()
    subscriptionAbortRef.current = null
    abortRef.current?.()
    abortRef.current = null
    cancelScheduledStreamingFlush()
  }, [cancelScheduledStreamingFlush])

  useEffect(() => {
    const previousConversationId = previousConversationRef.current
    if (previousConversationId !== conversationId) {
      if (activeRunConversationRef.current && activeRunConversationRef.current !== conversationId) {
        disconnectLocalSubscription()
        activeSessionRef.current = null
        resetStreamingState()
        if (runStartWaiterRef.current) {
          runStartWaiterRef.current.reject(new Error('Conversation changed before the run started'))
          runStartWaiterRef.current = null
        }
        runIdRef.current = null
        lastSequenceRef.current = 0
        appliedSequenceKeysRef.current.clear()
        setRunId(null)
        setCurrentRunStatus(null)
        setCurrentStatus('idle')
      }
      previousConversationRef.current = conversationId
    }
    if (conversationId) void reconnectToRun(conversationId)
  }, [conversationId, disconnectLocalSubscription, reconnectToRun, resetStreamingState, setCurrentRunStatus, setCurrentStatus])

  useEffect(() => {
    if (typeof window === 'undefined' || !window.addEventListener) return
    const handleFocus = () => reconnect()
    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [reconnect])

  useEffect(() => () => {
    disconnectLocalSubscription()
    if (runStartWaiterRef.current) {
      runStartWaiterRef.current.reject(new Error('Chat unmounted before the run started'))
      runStartWaiterRef.current = null
    }
  }, [disconnectLocalSubscription])
  const dispatchRunInput = useCallback(async (pending: PendingRunInput, targetRunId: string) => {
    if (pending.submitted || pending.runId && pending.runId !== targetRunId || !runApi.postRunInput) return
    pending.submitted = true
    try {
      const result = await runApi.postRunInput(agentId, targetRunId, {
        delivery: pending.kind,
        content: pending.content,
        request_id: pending.requestId,
      })
      if (runIdRef.current === targetRunId && result?.status) {
        setCurrentRunStatus(result.status)
      }
    } catch (reason) {
      pendingRunInputsRef.current = pendingRunInputsRef.current.filter((input) => input !== pending)
      const chatError: ChatError = { message: reason instanceof Error ? reason.message : '' }
      setError(chatError)
      onError?.(chatError)
      setMessages((previous) => previous.map((message) => (
        message.id === pending.messageId
          ? { ...message, metadata: { ...message.metadata, runInputState: 'failed' } }
          : message
      )))
    }
  }, [agentId, onError, runApi, setCurrentRunStatus])

  const flushPendingRunInputs = useCallback(async (targetRunId: string) => {
    const pending = pendingRunInputsRef.current.filter((input) => !input.submitted && (
      !input.runId || input.runId === targetRunId
    ))
    await Promise.all(pending.map((input) => dispatchRunInput(input, targetRunId)))
  }, [dispatchRunInput])

  flushPendingInputsRef.current = (targetRunId) => {
    void flushPendingRunInputs(targetRunId)
  }

  const submitRunInput = useCallback(async (content: string) => {
    if (!runApi.postRunInput) return
    const delivery = runStatusRef.current === 'completing' ? 'follow_up' : 'steer'
    const requestId = createRunInputRequestId()
    const pending: PendingRunInput = {
      messageId: `run-input-${requestId}`,
      requestId,
      content,
      kind: delivery,
      submitted: false,
      runId: runIdRef.current ?? undefined,
    }
    pendingRunInputsRef.current.push(pending)
    setMessages((previous) => [...previous, {
      id: pending.messageId,
      role: 'user',
      parts: [{ type: 'text', text: content }],
      createdAt: new Date(),
      metadata: { runInputState: 'queued', runInputKind: delivery },
    }])
    const activeRunId = runIdRef.current
    if (activeRunId) await flushPendingRunInputs(activeRunId)
  }, [flushPendingRunInputs, runApi, setMessages])

  const consumeStream = useCallback(async (
    session: AssistantStreamSession,
    start: () => { stream: Promise<Response>; abort: () => void } | Promise<{ stream: Promise<Response>; abort: () => void }>,
    options: { reloadAfterTerminal?: boolean; reloadOnError?: boolean } = {}
  ) => {
    const epoch = ++connectionEpochRef.current
    try {
      const { stream, abort } = await start()
      abortRef.current = abort
      if (connectionEpochRef.current !== epoch) {
        abort()
        return
      }
      const response = await stream
      if (!response.ok) {
        throw new Error(getHttpErrorMessage(response.status, tError, tAuth))
      }
      if (connectionEpochRef.current !== epoch) return
      setCurrentStatus('streaming')
      onStreamStart?.()
      for await (const event of parseSSEStream(response)) {
        if (connectionEpochRef.current !== epoch) return
        applyIncomingEvent(event, session)
      }
      if (connectionEpochRef.current !== epoch) return
      if (session.runId && isActiveRunStatus(runStatusRef.current)) {
        startSubscription(session.runId)
        return
      }
      if (!session.receivedTerminalEvent) finishAssistantMessage(session)
      if (options.reloadAfterTerminal) await reloadConversationMessages().catch(() => undefined)
      setCurrentStatus('idle')
      notifyStreamEnd(session)
      resetStreamingState()
    } catch (reason) {
      if (connectionEpochRef.current !== epoch || (reason instanceof Error && reason.name === 'AbortError')) return
      if (session.runId && runIdRef.current === session.runId && !terminalRunsRef.current.has(session.runId)) {
        setCurrentStatus('streaming')
        startSubscription(session.runId)
        return
      }
      const chatError: ChatError = { message: reason instanceof Error ? reason.message : '' }
      onError?.(chatError)
      markAssistantError(session, chatError)
      if (options.reloadOnError) await reloadConversationMessages().catch(() => undefined)
      setCurrentStatus('idle')
      notifyStreamEnd(session)
      resetStreamingState()
    } finally {
      if (connectionEpochRef.current === epoch) abortRef.current = null
    }
  }, [
    applyIncomingEvent,
    finishAssistantMessage,
    markAssistantError,
    notifyStreamEnd,
    onError,
    onStreamStart,
    reloadConversationMessages,
    resetStreamingState,
    setCurrentStatus,
    startSubscription,
    tAuth,
    tError,
  ])

  const sendMessage = useCallback(async (message: string, images?: ChatImageContent[], fileUrls?: ChatFileUrl[]) => {
    const content = message.trim()
    if (!content && !images?.length && !fileUrls?.length) return
    if (statusRef.current === 'loading' || statusRef.current === 'streaming') {
      if (images?.length || fileUrls?.length) return
      await submitRunInput(content)
      return
    }

    setError(null)
    runIdRef.current = null
    lastSequenceRef.current = 0
    appliedSequenceKeysRef.current.clear()
    setRunId(null)
    setCurrentRunStatus(null)

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      parts: buildUserMessageParts(content, images, fileUrls),
      createdAt: new Date(),
      metadata: { pendingPersistence: true },
    }
    const assistantMessageId = `assistant-${Date.now()}`
    const assistantMessage: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      parts: [],
      createdAt: new Date(),
      metadata: { isLoading: true, isManuallyStopped: false },
    }
    const session: AssistantStreamSession = {
      mode: 'send',
      displayMessageId: assistantMessageId,
      backendMessageId: null,
      optimisticUserMessageId: userMessage.id,
      state: createAssistantStreamState(),
      versionNumber: 1,
      versionCount: 1,
      receivedTerminalEvent: false,
      receivedMessageEnd: false,
      endNotified: false,
    }
    activeSessionRef.current = session
    syncStreamingState(session)
    setMessages((previous) => [...previous, userMessage, assistantMessage])
    setCurrentStatus('loading')

    const request: ChatRequest = {
      message: content,
      images,
      file_urls: fileUrls,
      conversation_id: conversationIdRef.current,
      variables,
    }
    if (api.startRun && api.streamRun) {
      const startWaiter = createRunStartWaiter(session)
      runStartWaiterRef.current = startWaiter
      try {
        await consumeStream(session, async () => {
          const started = await api.startRun!(agentId, request)
          session.runId = started.run_id
          reconcileOptimisticUserMessage(session, started.user_message_id)
          trackRun(started.run_id, started.conversation_id)
          setCurrentRunStatus(started.status)
          if (started.conversation_id && conversationIdRef.current !== started.conversation_id) {
            setConversationId(started.conversation_id)
            onConversationChange?.(started.conversation_id)
          }
          if (runStartWaiterRef.current?.session === session) {
            runStartWaiterRef.current.resolve(started.run_id)
            runStartWaiterRef.current = null
          }
          return api.streamRun!(agentId, started.run_id, lastSequenceRef.current)
        })
      } finally {
        if (runStartWaiterRef.current?.session === session) {
          runStartWaiterRef.current.reject(new Error('Agent run did not start'))
          runStartWaiterRef.current = null
        }
      }
    } else {
      await consumeStream(session, () => api.chatStream(agentId, request))
    }
  }, [agentId, api, consumeStream, onConversationChange, reconcileOptimisticUserMessage, setConversationId, setCurrentRunStatus, setCurrentStatus, submitRunInput, syncStreamingState, trackRun, variables])

  const stop = useCallback(async () => {
    let activeRunId = runIdRef.current ?? activeSessionRef.current?.runId ?? null
    const session = activeSessionRef.current
    if (
      !activeRunId
      && session
      && (statusRef.current === 'loading' || statusRef.current === 'streaming')
      && runApi.stopRun
      && runStartWaiterRef.current?.session === session
    ) {
      try {
        activeRunId = await runStartWaiterRef.current.promise
      } catch {
        activeRunId = null
      }
    } else if (!activeRunId && session && (statusRef.current === 'loading' || statusRef.current === 'streaming')) {
      for (let attempt = 0; attempt < 8 && !activeRunId; attempt += 1) {
        await Promise.resolve()
        activeRunId = runIdRef.current ?? session.runId ?? null
      }
      if (!activeRunId) {
        await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0))
        activeRunId = runIdRef.current ?? session.runId ?? null
      }
    }

    if (activeRunId && runApi.stopRun && (
      isActiveRunStatus(runStatusRef.current) || statusRef.current === 'loading' || statusRef.current === 'streaming'
    )) {
      setCurrentRunStatus('stopping')
      const terminal = waitForRunEnd(activeRunId)
      try {
        const result = await runApi.stopRun(agentId, activeRunId)
        if (runIdRef.current === activeRunId && result?.status) {
          setCurrentRunStatus(result.status)
        }
        startSubscription(activeRunId)
        await terminal
      } catch (reason) {
        const chatError: ChatError = { message: reason instanceof Error ? reason.message : '' }
        setError(chatError)
        onError?.(chatError)
      }
      return
    }

    connectionEpochRef.current += 1
    abortRef.current?.()
    abortRef.current = null
    if (runStartWaiterRef.current) {
      runStartWaiterRef.current.reject(new Error('Run stopped before it started'))
      runStartWaiterRef.current = null
    }
    if (session) {
      markAssistantStopped(session)
      notifyStreamEnd(session)
    }
    setCurrentStatus('idle')
    resetStreamingState()
  }, [agentId, markAssistantStopped, notifyStreamEnd, onError, resetStreamingState, runApi, setCurrentRunStatus, setCurrentStatus, startSubscription, waitForRunEnd])

  const reset = useCallback(() => {
    disconnectLocalSubscription()
    if (runStartWaiterRef.current) {
      runStartWaiterRef.current.reject(new Error('Chat reset before the run started'))
      runStartWaiterRef.current = null
    }
    activeSessionRef.current = null
    runIdRef.current = null
    lastSequenceRef.current = 0
    appliedSequenceKeysRef.current.clear()
    pendingRunInputsRef.current = []
    setRunId(null)
    setCurrentRunStatus(null)
    resetStreamingState()
    setMessages(initialMessages)
    setConversationId(null)
    setError(null)
    setCurrentStatus('idle')
  }, [disconnectLocalSubscription, initialMessages, resetStreamingState, setConversationId, setCurrentRunStatus, setCurrentStatus])

  const switchVersion = useCallback(async (messageId: string, versionIndex: number) => {
    if (statusRef.current !== 'idle') return
    const message = messagesRef.current.find((item) => item.id === messageId)
    if (!message) return
    try {
      const versions = await api.getMessageVersions(agentId, messageId)
      if (versionIndex < 0 || versionIndex >= versions.length) return
      await api.switchMessageVersion(agentId, messageId, versions[versionIndex].id)
      await reloadConversationMessages()
    } catch (reason) {
      console.error('Failed to switch version:', reason)
    }
  }, [agentId, api, reloadConversationMessages])

  const editMessage = useCallback(async (messageId: string, content: string) => {
    if (statusRef.current !== 'idle' || !isValidUUID(messageId)) return
    const targetIndex = messagesRef.current.findIndex((message) => message.id === messageId)
    if (targetIndex < 0 || messagesRef.current[targetIndex].role !== 'user') return

    const placeholderId = `editing-${Date.now()}`
    setError(null)
    setCurrentStatus('loading')
    setMessages((previous) => {
      const currentTargetIndex = previous.findIndex((message) => message.id === messageId)
      if (currentTargetIndex < 0) return previous
      const beforeAndEditedUser = previous.slice(0, currentTargetIndex + 1).map((message) => {
        if (message.id !== messageId) return message
        const hasTextPart = message.parts.some((part) => part.type === 'text')
        const parts = hasTextPart
          ? message.parts.map((part) => part.type === 'text' ? { ...part, text: content } : part)
          : [{ type: 'text' as const, text: content }, ...message.parts]
        return { ...message, parts }
      })
      return [...beforeAndEditedUser, {
        id: placeholderId,
        role: 'assistant',
        parts: [],
        createdAt: new Date(),
        metadata: { isLoading: true },
      }]
    })
    const session: AssistantStreamSession = {
      mode: 'edit',
      displayMessageId: placeholderId,
      backendMessageId: null,
      sourceMessageId: messageId,
      state: createAssistantStreamState(),
      versionNumber: 1,
      versionCount: 1,
      receivedTerminalEvent: false,
      receivedMessageEnd: false,
      endNotified: false,
      reloadAfterTerminal: true,
    }
    activeSessionRef.current = session
    syncStreamingState(session)
    await consumeStream(
      session,
      () => api.editMessageStream(agentId, messageId, content),
      { reloadAfterTerminal: true, reloadOnError: true }
    )
  }, [agentId, api, consumeStream, setCurrentStatus, syncStreamingState])

  const regenerate = useCallback(async (messageId: string) => {
    if (statusRef.current !== 'idle') return
    const messageIndex = messagesRef.current.findIndex((message) => message.id === messageId)
    if (messageIndex < 0 || messagesRef.current[messageIndex].role !== 'assistant') return

    if (!isValidUUID(messageId)) {
      const userMessage = messagesRef.current[messageIndex - 1]
      const textPart = userMessage?.role === 'user' ? userMessage.parts.find((part) => part.type === 'text') : undefined
      const text = textPart && 'text' in textPart ? textPart.text : ''
      if (!text) return
      const images = userMessage.parts.filter((part) => part.type === 'image').map((part) => ({
        type: 'image_url' as const,
        url: 'url' in part ? part.url : '',
      })).filter((image) => image.url)
      setMessages((previous) => previous.slice(0, Math.max(0, messageIndex - 1)))
      await sendMessage(text, images.length > 0 ? images : undefined)
      return
    }

    setError(null)
    setCurrentStatus('loading')
    setMessages((previous) => previous.slice(0, messageIndex + 1).map((message) => {
      if (message.id !== messageId) return message
      const metadata = { ...message.metadata }
      delete metadata.isError
      delete metadata.errorMessage
      delete metadata.preservedPartialProgress
      return {
        ...message,
        parts: [],
        metadata: { ...metadata, isLoading: true, isManuallyStopped: false },
      }
    }))
    const session: AssistantStreamSession = {
      mode: 'regenerate',
      displayMessageId: messageId,
      backendMessageId: null,
      state: createAssistantStreamState(),
      versionNumber: 1,
      versionCount: 1,
      receivedTerminalEvent: false,
      receivedMessageEnd: false,
      endNotified: false,
      keepDisplayIdOnStart: true,
    }
    activeSessionRef.current = session
    await consumeStream(session, () => api.regenerateStream(agentId, messageId, variables))
  }, [agentId, api, consumeStream, sendMessage, setCurrentStatus, variables])

  return {
    messages,
    status,
    error,
    conversationId,
    isLoading,
    isStreaming,
    runId,
    runStatus,
    sendMessage,
    regenerate,
    editMessage,
    switchVersion,
    stop,
    reconnect,
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
  compression: 'pending' | 'running' | 'completed' | 'error'
  ragSourceCount?: number
  toolCallCount?: number
}

/** A single tool invocation and its optional result at one timeline position. */
type StreamToolCallPart = ToolCallPart | McpToolCallPart
type StreamToolResultPart = ToolResultPart | McpToolResultPart

/**
 * A segment represents a stream event in the order it was received.
 * Keeping task events here prevents progress steps from being rendered as a
 * fixed prelude to the rest of the thinking timeline.
 */
interface ContentSegment {
  type: 'text' | 'tool' | 'reasoning' | 'task' | 'user-input-request' | 'media-result' | 'truncated' | 'iteration-cap-reached'
  // For text type
  text?: string
  // For tool type
  toolCall?: StreamToolCallPart
  toolResult?: StreamToolResultPart
  // For reasoning type
  reasoningIndex?: number
  reasoningText?: string
  reasoningState?: 'streaming' | 'done'
  reasoningStartTime?: number
  reasoningDuration?: number
  // For task type
  task?: TaskPart
  // For user-input-request type
  userInputRequest?: UserInputRequestPart
  // For media-result type
  mediaResult?: MediaResultPart
}

interface StreamingState {
  assistantMessageId: string | null
  visibleMessageId: string | null
  backendMessageId: string | null
  segments: ContentSegment[]
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>
  currentReasoningIndex: number
  ragSources: SourceDocumentPart[]
  taskState: TaskState
}

interface AssistantStreamSession {
  mode: 'send' | 'edit' | 'regenerate' | 'reconnect'
  displayMessageId: string | null
  backendMessageId: string | null
  optimisticUserMessageId?: string
  sourceMessageId?: string
  state: AssistantStreamState
  versionNumber: number
  versionCount: number
  receivedTerminalEvent: boolean
  receivedMessageEnd: boolean
  endNotified: boolean
  keepDisplayIdOnStart?: boolean
  reloadAfterTerminal?: boolean
  runId?: string
}

interface PendingRunInput {
  messageId: string
  requestId: string
  content: string
  kind: 'steer' | 'follow_up'
  submitted: boolean
  runId?: string
}
interface RunStartWaiter {
  session: AssistantStreamSession
  promise: Promise<string>
  resolve: (runId: string) => void
  reject: (reason?: unknown) => void
}
interface NormalizedStreamEvent {
  event: string
  data: unknown
  envelope?: AgentRunEventOut
}

interface StoredRunSnapshot {
  runId: string
  lastSequence: number
}

const RUN_STORAGE_PREFIX = 'clouisle:agent-run:'

function createRunStartWaiter(session: AssistantStreamSession): RunStartWaiter {
  let resolve!: (runId: string) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<string>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  promise.catch(() => undefined)
  return { session, promise, resolve, reject }
}
function emptyStreamingState(): StreamingState {
  return {
    assistantMessageId: null,
    visibleMessageId: null,
    backendMessageId: null,
    segments: [],
    reasoningBlocks: [],
    currentReasoningIndex: -1,
    ragSources: [],
    taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending', compression: 'pending' },
  }
}

function normalizeStreamEvent(event: { event: string; data: unknown }): NormalizedStreamEvent {
  if (isAgentRunEvent(event.data)) {
    return {
      event: event.data.type,
      data: event.data.payload,
      envelope: event.data,
    }
  }
  return event
}

function isAgentRunEvent(value: unknown): value is AgentRunEventOut {
  if (!value || typeof value !== 'object') return false
  const event = value as Record<string, unknown>
  return typeof event.run_id === 'string'
    && typeof event.sequence === 'number'
    && typeof event.type === 'string'
    && Boolean(event.payload && typeof event.payload === 'object')
}

function getEventMessageId(event: NormalizedStreamEvent): string | null {
  if (!event.data || typeof event.data !== 'object') return null
  const messageId = (event.data as Record<string, unknown>).message_id
  return typeof messageId === 'string' ? messageId : null
}

function isActiveRunStatus(status: AgentRunStatus | null): boolean {
  return status === 'queued' || status === 'running' || status === 'stopping' || status === 'completing'
}

function runStorageKey(agentId: string, conversationId: string): string {
  return `${RUN_STORAGE_PREFIX}${encodeURIComponent(agentId)}:${encodeURIComponent(conversationId)}`
}

function loadRunSnapshot(agentId: string, conversationId: string): StoredRunSnapshot | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(runStorageKey(agentId, conversationId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredRunSnapshot>
    if (typeof parsed.runId !== 'string' || typeof parsed.lastSequence !== 'number') return null
    return { runId: parsed.runId, lastSequence: parsed.lastSequence }
  } catch {
    return null
  }
}

function saveRunSnapshot(agentId: string, conversationId: string, snapshot: StoredRunSnapshot) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(runStorageKey(agentId, conversationId), JSON.stringify(snapshot))
  } catch {
    // Session storage is optional (for example in private browser contexts).
  }
}

function removeRunSnapshot(agentId: string, conversationId: string) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.removeItem(runStorageKey(agentId, conversationId))
  } catch {
    // The run still remains recoverable while this hook instance is mounted.
  }
}

function createRunInputRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `run-input-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function buildUserMessageParts(
  content: string,
  images?: ChatImageContent[],
  fileUrls?: ChatFileUrl[]
): MessagePart[] {
  const parts: MessagePart[] = [{ type: 'text', text: content }]
  for (const image of images ?? []) {
    parts.push({ type: 'image', url: image.url } as MessagePart)
  }
  for (const file of fileUrls ?? []) {
    parts.push({ type: 'file', filename: file.filename, size: file.size } as MessagePart)
  }
  return parts
}

function isValidUUID(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
}

function createAssistantStreamStateFromParts(parts: MessagePart[]): AssistantStreamState {
  const state = createAssistantStreamState()
  for (const part of parts) {
    switch (part.type) {
      case 'text':
        state.segments.push({ type: 'text', text: part.text })
        break
      case 'reasoning': {
        const block = {
          text: part.text,
          startTime: Date.now(),
          duration: part.duration,
          state: part.state === 'streaming' ? 'streaming' as const : 'done' as const,
        }
        const reasoningIndex = state.reasoningBlocks.push(block) - 1
        state.currentReasoningIndex = block.state === 'streaming' ? reasoningIndex : -1
        state.segments.push({
          type: 'reasoning',
          reasoningIndex,
          reasoningText: part.text,
          reasoningState: block.state,
          reasoningStartTime: block.startTime,
          reasoningDuration: block.duration,
        })
        break
      }
      case 'task':
        state.segments.push({ type: 'task', task: { ...part } })
        if (part.taskType === 'rag') {
          state.taskState.rag = part.state
          state.taskState.ragSourceCount = typeof part.info === 'number' ? part.info : undefined
        } else if (part.taskType === 'generating') {
          state.taskState.generating = part.state
        } else if (part.taskType === 'compression') {
          state.taskState.compression = part.state
        }
        break
      case 'tool-call': {
        const existingSegment = findToolSegment(state.segments, part.toolCallId)
        if (existingSegment) {
          existingSegment.toolCall = existingSegment.toolCall
            ? mergeStreamToolCall(existingSegment.toolCall, part)
            : setToolCallState(part, existingSegment.toolResult)
        } else {
          state.segments.push({ type: 'tool', toolCall: { ...part } })
        }
        state.taskState.toolCalling = part.state === 'running' ? 'running' : 'completed'
        break
      }
      case 'mcp-tool-call': {
        const existingSegment = findToolSegment(state.segments, part.toolCallId)
        if (existingSegment) {
          existingSegment.toolCall = existingSegment.toolCall
            ? mergeStreamToolCall(existingSegment.toolCall, part)
            : setToolCallState(part, existingSegment.toolResult)
        } else {
          state.segments.push({ type: 'tool', toolCall: { ...part } })
        }
        state.taskState.toolCalling = part.state === 'running' ? 'running' : 'completed'
        break
      }
      case 'tool-result': {
        const existingSegment = findToolSegment(state.segments, part.toolCallId)
        if (existingSegment) {
          existingSegment.toolResult = { ...part }
          if (existingSegment.toolCall) {
            existingSegment.toolCall = setToolCallState(existingSegment.toolCall, part)
          }
        } else {
          state.segments.push({ type: 'tool', toolResult: { ...part } })
        }
        break
      }
      case 'mcp-tool-result': {
        const existingSegment = findToolSegment(state.segments, part.toolCallId)
        if (existingSegment) {
          existingSegment.toolResult = { ...part }
          if (existingSegment.toolCall) {
            existingSegment.toolCall = setToolCallState(existingSegment.toolCall, part)
          }
        } else {
          state.segments.push({ type: 'tool', toolResult: { ...part } })
        }
        break
      }
      case 'source-document':
        state.ragSources.push(part)
        break
      case 'user-input-request':
        state.segments.push({ type: 'user-input-request', userInputRequest: { ...part } })
        break
      case 'media-result':
        state.segments.push({ type: 'media-result', mediaResult: { ...part } })
        break
      case 'truncated':
        state.segments.push({ type: 'truncated' })
        break
      case 'iteration-cap-reached':
        state.segments.push({ type: 'iteration-cap-reached' })
        break
    }
  }
  const toolCalls = state.segments.flatMap((segment) => segment.toolCall ? [segment.toolCall] : [])
  if (toolCalls.length > 0 && toolCalls.every((call) => call.state === 'done' || call.state === 'error')) {
    state.taskState.toolCalling = 'completed'
  }
  return state
}

function appendTimelineTask(segments: ContentSegment[], taskType: TaskPart['taskType']) {
  segments.push({
    type: 'task',
    task: {
      type: 'task',
      taskType,
      state: 'running',
    },
  })
}

function updateLatestTimelineTask(
  segments: ContentSegment[],
  taskType: TaskPart['taskType'],
  state: TaskPart['state'],
  info?: TaskPart['info']
) {
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    const segment = segments[index]
    if (segment.type !== 'task' || segment.task?.taskType !== taskType) continue

    segment.task = {
      ...segment.task,
      state,
      ...(info === undefined ? {} : { info }),
    }
    return true
  }
  return false
}

function ensureTimelineTask(
  segments: ContentSegment[],
  taskType: TaskPart['taskType'],
  state: TaskPart['state'],
  info?: TaskPart['info']
) {
  if (!updateLatestTimelineTask(segments, taskType, state, info)) {
    segments.push({
      type: 'task',
      task: {
        type: 'task',
        taskType,
        state,
        ...(info === undefined ? {} : { info }),
      },
    })
  }
}

interface AssistantStreamState {
  segments: ContentSegment[]
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>
  currentReasoningIndex: number
  ragSources: SourceDocumentPart[]
  taskState: TaskState
}

function createAssistantStreamState(): AssistantStreamState {
  return {
    segments: [],
    reasoningBlocks: [],
    currentReasoningIndex: -1,
    ragSources: [],
    taskState: { rag: 'pending', generating: 'pending', toolCalling: 'pending', compression: 'pending' },
  }
}
function findToolSegment(segments: ContentSegment[], toolCallId: string): ContentSegment | undefined {
  return segments.find((segment) => (
    segment.type === 'tool'
    && (segment.toolCall?.toolCallId === toolCallId || segment.toolResult?.toolCallId === toolCallId)
  ))
}

function mergeMcpToolCall(existing: McpToolCallPart, incoming: McpToolCallPart): McpToolCallPart {
  const merged: McpToolCallPart = {
    ...existing,
    ...(incoming.serverName !== undefined ? { serverName: incoming.serverName } : {}),
    ...(incoming.toolName !== undefined ? { toolName: incoming.toolName } : {}),
    ...(incoming.input !== undefined ? { input: incoming.input } : {}),
    ...(incoming.state !== undefined ? { state: incoming.state } : {}),
  }
  if (existing.state === 'done' || existing.state === 'error') {
    merged.state = existing.state
  }
  return merged
}

function mergeStreamToolCall(existing: StreamToolCallPart, incoming: StreamToolCallPart): StreamToolCallPart {
  if (existing.type === 'tool-call' && incoming.type === 'tool-call') {
    return mergeToolCall(existing, incoming)
  }
  if (existing.type === 'mcp-tool-call' && incoming.type === 'mcp-tool-call') {
    return mergeMcpToolCall(existing, incoming)
  }
  return incoming
}

function setToolCallState(
  toolCall: StreamToolCallPart,
  result: StreamToolResultPart | undefined,
): StreamToolCallPart {
  if (!result) return toolCall
  return { ...toolCall, state: result.isError ? 'error' : 'done' }
}

function applyAssistantStreamEvent(
  state: AssistantStreamState,
  event: { event: string; data: unknown }
): boolean {
  const getCurrentTextSegment = (): ContentSegment => {
    const lastSegment = state.segments[state.segments.length - 1]
    if (lastSegment?.type === 'text') return lastSegment
    const segment: ContentSegment = { type: 'text', text: '' }
    state.segments.push(segment)
    return segment
  }

  const addToolCall = (toolCall: ToolCallPart) => {
    const existingSegment = findToolSegment(state.segments, toolCall.toolCallId)
    if (existingSegment) {
      existingSegment.toolCall = existingSegment.toolCall
        ? mergeStreamToolCall(existingSegment.toolCall, toolCall)
        : setToolCallState(toolCall, existingSegment.toolResult)
      return
    }
    state.segments.push({ type: 'tool', toolCall })
  }

  switch (event.event as SSEEventType) {
    case 'rag_start':
      state.taskState.rag = 'running'
      appendTimelineTask(state.segments, 'rag')
      return true

    case 'reasoning_start': {
      const startTime = Date.now()
      const reasoningIndex = state.reasoningBlocks.push({ text: '', startTime, state: 'streaming' }) - 1
      state.currentReasoningIndex = reasoningIndex
      state.segments.push({
        type: 'reasoning',
        reasoningIndex,
        reasoningText: '',
        reasoningState: 'streaming',
        reasoningStartTime: startTime,
      })
      return true
    }

    case 'reasoning_delta': {
      const data = event.data as { delta: string }
      const block = state.reasoningBlocks[state.currentReasoningIndex]
      if (!block) return false
      block.text += data.delta
      const reasoningSegment = state.segments.find(
        segment => segment.type === 'reasoning' && segment.reasoningIndex === state.currentReasoningIndex
      )
      if (reasoningSegment) reasoningSegment.reasoningText = block.text
      return true
    }

    case 'reasoning_end': {
      const block = state.reasoningBlocks[state.currentReasoningIndex]
      if (!block) return false
      block.duration = Date.now() - block.startTime
      block.state = 'done'
      const reasoningSegment = state.segments.find(
        segment => segment.type === 'reasoning' && segment.reasoningIndex === state.currentReasoningIndex
      )
      if (reasoningSegment) {
        reasoningSegment.reasoningState = 'done'
        reasoningSegment.reasoningDuration = block.duration
        reasoningSegment.reasoningText = block.text
      }
      return true
    }

    case 'content_delta': {
      const data = event.data as SSEContentDelta
      if (state.taskState.generating === 'pending') {
        if (state.taskState.rag === 'running') {
          state.taskState.rag = 'completed'
          updateLatestTimelineTask(state.segments, 'rag', 'completed')
        }
        state.taskState.generating = 'running'
        appendTimelineTask(state.segments, 'generating')
      }

      const textSegment = getCurrentTextSegment()
      textSegment.text = (textSegment.text || '') + data.delta
      const text = textSegment.text
      const xmlMatch = text.match(/<user_input_request>([\s\S]*?)<\/user_input_request>/)
      if (xmlMatch) {
        const question = xmlMatch[1].match(/<question>([\s\S]*?)<\/question>/)?.[1].trim()
        const options = Array.from(
          xmlMatch[1].matchAll(/<option>([\s\S]*?)<\/option>/g),
          match => match[1].trim()
        )
        if (question && options.length >= 2) {
          const start = text.indexOf('<user_input_request>')
          const end = text.indexOf('</user_input_request>') + '</user_input_request>'.length
          textSegment.text = `${text.slice(0, start)}${text.slice(end)}`.trim()
          const segmentIndex = state.segments.indexOf(textSegment)
          state.segments.splice(segmentIndex + 1, 0, {
            type: 'user-input-request',
            userInputRequest: { type: 'user-input-request', question, options, state: 'pending' },
          })
        }
      }
      return true
    }

    case 'rag_context': {
      const data = event.data as SSERagContext
      state.ragSources = data.contexts.map(context => ({
        type: 'source-document' as const,
        sourceId: context.document_id,
        documentId: context.document_id,
        documentName: context.document_name,
        content: context.content,
        metadata: {
          kb_id: context.kb_id,
          kb_name: context.kb_name,
          score: context.score,
        },
      }))
      state.taskState.rag = 'completed'
      state.taskState.ragSourceCount = state.ragSources.length
      ensureTimelineTask(state.segments, 'rag', 'completed', state.ragSources.length)
      return true
    }

    case 'compression_start':
      state.taskState.compression = 'running'
      appendTimelineTask(state.segments, 'compression')
      return true

    case 'compression_end':
      state.taskState.compression = 'completed'
      ensureTimelineTask(
        state.segments,
        'compression',
        'completed',
        event.data as unknown as Record<string, unknown>
      )
      return true

    case 'tool_call': {
      const data = event.data as SSEToolCall
      addToolCall({
        type: 'tool-call',
        toolCallId: data.tool_call_id,
        toolName: data.tool_name,
        toolDisplayName: data.tool_display_name,
        input: data.arguments,
        state: 'running',
      })
      state.taskState.toolCalling = 'running'
      state.taskState.toolCallCount = state.segments.filter(
        segment => segment.type === 'tool' && Boolean(segment.toolCall)
      ).length
      return true
    }

    case 'tool_result': {
      const data = event.data as SSEToolResult
      const result: ToolResultPart = {
        type: 'tool-result',
        toolCallId: data.tool_call_id,
        toolName: data.tool_name,
        toolDisplayName: data.tool_display_name,
        output: parseToolResultOutput(data.result),
        isError: data.is_error,
      }
      const existingSegment = findToolSegment(state.segments, data.tool_call_id)
      if (existingSegment) {
        existingSegment.toolResult = result
        if (existingSegment.toolCall) {
          existingSegment.toolCall = setToolCallState(existingSegment.toolCall, result)
        }
      } else {
        state.segments.push({ type: 'tool', toolResult: result })
      }
      const toolCalls = state.segments.flatMap(segment => segment.toolCall ? [segment.toolCall] : [])
      if (
        toolCalls.every(toolCall => toolCall.state === 'done' || toolCall.state === 'error')
        && state.taskState.toolCalling === 'running'
      ) {
        state.taskState.toolCalling = 'completed'
      }
      return true
    }

    case 'media_result': {
      const data = event.data as SSEMediaResult
      if (!shouldDisplayMediaResultInBody(data)) return false
      state.segments.push({
        type: 'media-result',
        mediaResult: { type: 'media-result', output: data },
      })
      return true
    }

    case 'output_truncated':
      state.segments.push({ type: 'truncated' })
      return true

    case 'iteration_cap_reached': {
      const data = event.data as SSEIterationCapReached
      state.segments.push({ type: 'iteration-cap-reached' })
      if (data.content) state.segments.push({ type: 'text', text: data.content })
      return true
    }

    default:
      return false
  }
}

/**
 * Build message parts from the stream segments in their received order.
 * Citation sources remain a non-streaming footer rather than timeline items.
 */
function buildMessageParts(
  segments: ContentSegment[],
  sources: SourceDocumentPart[],
  isStreaming: boolean
): MessagePart[] {
  const parts: MessagePart[] = []

  for (const segment of segments) {
    if (segment.type === 'text' && segment.text && segment.text.length > 0) {
      const textPart: TextPart = {
        type: 'text',
        text: segment.text,
        state: isStreaming ? 'streaming' : 'done',
      }
      parts.push(textPart)
    } else if (segment.type === 'reasoning') {
      const reasoningPart: ReasoningPart = {
        type: 'reasoning',
        text: segment.reasoningText || '',
        state: segment.reasoningState || 'streaming',
        duration: segment.reasoningDuration,
      }
      parts.push(reasoningPart)
    } else if (segment.type === 'task' && segment.task) {
      parts.push({
        ...segment.task,
        state: !isStreaming && segment.task.state !== 'error' ? 'completed' : segment.task.state,
      })
    } else if (segment.type === 'tool') {
      if (segment.toolCall) parts.push(segment.toolCall)
      if (segment.toolResult) parts.push(segment.toolResult)
    } else if (segment.type === 'user-input-request' && segment.userInputRequest) {
      parts.push(segment.userInputRequest)
    } else if (segment.type === 'media-result' && segment.mediaResult) {
      parts.push(segment.mediaResult)
    } else if (segment.type === 'truncated') {
      parts.push({ type: 'truncated' })
    } else if (segment.type === 'iteration-cap-reached') {
      parts.push({ type: 'iteration-cap-reached' })
    }
  }

  if (sources.length > 0 && !isStreaming) {
    parts.push(...sources)
  }

  return parts
}

function hasRenderableStreamingProgress(
  segments: ContentSegment[],
  ragSources: SourceDocumentPart[],
  taskState: TaskState
): boolean {
  return (
    segments.some((segment) => {
      if (segment.type === 'text') return Boolean(segment.text?.trim())
      if (segment.type === 'reasoning') return true
      if (segment.type === 'tool') return Boolean(segment.toolCall || segment.toolResult)
      if (segment.type === 'task') return Boolean(segment.task)
      if (segment.type === 'user-input-request') return Boolean(segment.userInputRequest)
      if (segment.type === 'media-result') return Boolean(segment.mediaResult)
      return segment.type === 'truncated' || segment.type === 'iteration-cap-reached'
    })
    || ragSources.length > 0
    || taskState.rag !== 'pending'
    || taskState.generating !== 'pending'
    || taskState.toolCalling !== 'pending'
    || taskState.compression !== 'pending'
  )
}

function buildErroredMessageParts(state: {
  segments: ContentSegment[]
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>
  currentReasoningIndex?: number
  ragSources: SourceDocumentPart[]
  taskState: TaskState
  errorText: string
}): { parts: MessagePart[]; preservedProgress: boolean } {
  if (!hasRenderableStreamingProgress(
    state.segments,
    state.ragSources,
    state.taskState
  )) {
    const errorSegment: ContentSegment = { type: 'text', text: state.errorText }
    return {
      parts: buildMessageParts([errorSegment], [], false),
      preservedProgress: false,
    }
  }

  finalizeStreamingState(state)
  return {
    parts: buildMessageParts(state.segments, state.ragSources, false),
    preservedProgress: true,
  }
}

function finalizeStreamingState(state: {
  segments: ContentSegment[]
  reasoningBlocks: Array<{ text: string; startTime: number; duration?: number; state: 'streaming' | 'done' }>
  currentReasoningIndex?: number
  taskState: TaskState
}) {
  state.reasoningBlocks.forEach((block, index) => {
    if (block.state === 'streaming') {
      block.duration = Date.now() - block.startTime
      block.state = 'done'
    }

    const reasoningSegment = state.segments.find(
      segment => segment.type === 'reasoning' && segment.reasoningIndex === index
    )
    if (reasoningSegment) {
      reasoningSegment.reasoningState = 'done'
      reasoningSegment.reasoningDuration = block.duration
      reasoningSegment.reasoningText = block.text
    }
  })

  for (const segment of state.segments) {
    if (segment.type === 'tool' && segment.toolCall?.state === 'running') {
      segment.toolCall = { ...segment.toolCall, state: 'done' }
    }
    if (segment.type === 'task' && segment.task?.state === 'running') {
      segment.task = { ...segment.task, state: 'completed' }
    }
  }

  if (state.taskState.rag === 'running') state.taskState.rag = 'completed'
  if (state.taskState.generating === 'running') state.taskState.generating = 'completed'
  if (state.taskState.toolCalling === 'running') state.taskState.toolCalling = 'completed'
  if (state.taskState.compression === 'running') state.taskState.compression = 'completed'
  state.currentReasoningIndex = -1
}

function appendStoppedPart(parts: MessagePart[]): MessagePart[] {
  return parts.some(part => part.type === 'stopped') ? parts : [...parts, { type: 'stopped' }]
}

/**
 * Merge an incoming tool-call update into an existing one without letting
 * undefined fields clobber defined values, and without regressing a terminal
 * (done/error) state when a duplicate tool_call event arrives mid-stream.
 */
function mergeToolCall(existing: ToolCallPart, incoming: ToolCallPart): ToolCallPart {
  const merged: ToolCallPart = {
    ...existing,
    ...(incoming.toolName !== undefined ? { toolName: incoming.toolName } : {}),
    ...(incoming.toolDisplayName !== undefined ? { toolDisplayName: incoming.toolDisplayName } : {}),
    ...(incoming.input !== undefined ? { input: incoming.input } : {}),
    ...(incoming.state !== undefined ? { state: incoming.state } : {}),
  }
  if (existing.state === 'done' || existing.state === 'error') {
    merged.state = existing.state
  }
  return merged
}

/**
 * Get user-friendly error message based on error type
 * Returns an object with message and optional i18n key
 */
function isLikelyMessageKey(message: string): boolean {
  return /^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(message.trim())
}

function shouldUseChatBackendMessage(message: string): boolean {
  const trimmed = message.trim()
  if (!trimmed || trimmed.length > 200) return false
  if (isLikelyMessageKey(trimmed)) return false
  if (trimmed.includes('\n')) return false

  return !(
    trimmed.includes('Traceback')
    || trimmed.includes('Exception')
    || trimmed.includes('HTTP ')
    || trimmed.includes('Failed to fetch')
  )
}

function getHttpErrorMessage(
  status: number,
  tError: ReturnType<typeof useTranslations>,
  tAuth: ReturnType<typeof useTranslations>
): string {
  if (status === 401 || status === 403) {
    return tAuth('sessionExpired')
  }
  if (status === 404) {
    return tError('resourceNotFound')
  }
  if (status >= 500 && status < 600) {
    return tError('serverErrorDescription')
  }
  return getApiErrorMessage('requestFailed')
}

function getErrorMessage(
  error: ChatError,
  tError: ReturnType<typeof useTranslations>,
  tAuth: ReturnType<typeof useTranslations>
): string {
  const { code, message, quotaType } = error

  if (message?.includes('fetch') || message?.includes('network') || message?.includes('Failed to fetch')) {
    return tError('networkError')
  }

  if (message?.includes('timeout') || message?.includes('Timeout')) {
    return tError('timeout')
  }

  if (code === 6103 || code === 429 || quotaType) {
    const quotaTypeKey = quotaType === 'input'
      ? 'quotaTypeInput'
      : quotaType === 'output'
        ? 'quotaTypeOutput'
        : 'quotaTypeUsage'
    return tError('quotaExceeded', { type: tError(quotaTypeKey) })
  }

  if (code === 6105) {
    return tError('modelVisionNotSupported')
  }

  if (code === 6100 || message?.includes('No model found') || message?.includes('no_default_model') || message?.includes('no_chat_model')) {
    return tError('modelNotFound')
  }

  if (code === 6104) {
    return tError('modelNotAuthorized')
  }

  if ((code && code >= 2000 && code < 3000) || code === 401 || code === 403) {
    return tAuth('sessionExpired')
  }

  if ((code && code >= 4000 && code < 5000) || code === 404) {
    return tError('resourceNotFound')
  }

  if (code && code >= 500 && code < 600) {
    return tError('serverErrorDescription')
  }

  if (message?.includes('model') && message?.includes('configured')) {
    return tError('modelNotConfigured')
  }

  if (message && shouldUseChatBackendMessage(message)) {
    return message.trim()
  }

  return tError('unknown')
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
