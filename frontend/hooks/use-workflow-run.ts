'use client'

import { useState, useCallback, useRef } from 'react'
import { getErrorMessage as getApiErrorMessage } from '@/lib/api/client'
import { workflowsApi, type WorkflowEvent } from '@/lib/api/workflows'
import type { ChatMessage, ExecutionNode, ExecutionState } from '@/components/chat/types'

export interface UseWorkflowRunOptions {
  workflowId: string
  isDebug?: boolean
  onError?: (error: Error) => void
  onComplete?: () => void
}

export type WorkflowRunState = 'idle' | 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface UseWorkflowRunReturn {
  messages: ChatMessage[]
  executionState: ExecutionState
  isStreaming: boolean
  runId: string | null
  status: WorkflowRunState
  outputs: Record<string, unknown> | null
  submittedInputs: Record<string, unknown> | null
  error: string | null
  isCancelling: boolean
  start: (inputs: Record<string, unknown>) => Promise<void>
  stop: () => Promise<void>
  reset: () => void
}

/**
 * Hook for running workflows with SSE streaming
 * Converts workflow events to ChatMessage and ExecutionNode formats
 */
function isLikelyMessageKey(message: string): boolean {
  return /^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(message.trim())
}

function resolveWorkflowErrorMessage(message: unknown, fallback: string): string {
  if (typeof message !== 'string') return fallback

  const trimmed = message.trim()
  if (!trimmed || trimmed.length > 200) return fallback
  if (isLikelyMessageKey(trimmed)) return fallback
  if (trimmed.includes('\n')) return fallback
  if (
    trimmed.includes('Traceback')
    || trimmed.includes('Exception')
    || trimmed.includes('HTTP ')
    || trimmed.includes('Failed to fetch')
  ) {
    return fallback
  }

  return trimmed
}

export function useWorkflowRun(options: UseWorkflowRunOptions): UseWorkflowRunReturn {
  const { workflowId, isDebug = false, onError, onComplete } = options

  const [runId, setRunId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [executionState, setExecutionState] = useState<ExecutionState>({
    nodes: new Map(),
    progress: { current: 0, total: 0 },
  })
  const [isStreaming, setIsStreaming] = useState(false)
  const [status, setStatus] = useState<WorkflowRunState>('idle')
  const [outputs, setOutputs] = useState<Record<string, unknown> | null>(null)
  const [submittedInputs, setSubmittedInputs] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const closeConnectionRef = useRef<(() => void) | null>(null)
  const currentMessageRef = useRef<ChatMessage | null>(null)
  const handleWorkflowEventRef = useRef<((event: WorkflowEvent) => void) | null>(null)
  // Track node types to determine token routing (answer vs LLM)
  const nodeTypesRef = useRef<Map<string, string>>(new Map())

  const stop = useCallback(async () => {
    const activeRunId = runId
    if (!activeRunId || status === 'success' || status === 'failed' || status === 'cancelled') {
      return
    }

    closeConnectionRef.current?.()
    closeConnectionRef.current = null
    setIsStreaming(false)
    setIsCancelling(true)
    try {
      await workflowsApi.cancelWorkflowRun(activeRunId)
      setStatus('cancelled')
    } catch (cancelError) {
      console.error('Failed to cancel workflow:', cancelError)
      onError?.(cancelError as Error)
    } finally {
      setIsCancelling(false)
    }
  }, [runId, status, onError])

  const reset = useCallback(() => {
    closeConnectionRef.current?.()
    closeConnectionRef.current = null
    setRunId(null)
    setMessages([])
    setExecutionState({
      nodes: new Map(),
      progress: { current: 0, total: 0 },
    })
    setIsStreaming(false)
    setStatus('idle')
    setOutputs(null)
    setSubmittedInputs(null)
    setError(null)
    setIsCancelling(false)
    currentMessageRef.current = null
    nodeTypesRef.current.clear()
  }, [])

  const start = useCallback(
    async (inputs: Record<string, unknown>) => {
      try {
        setIsStreaming(true)
        setStatus('pending')
        setSubmittedInputs({ ...inputs })
        setOutputs(null)
        setError(null)

        // Add user message with the query input
        const userQuery = inputs.query as string | undefined
        if (userQuery) {
          const userMessage: ChatMessage = {
            id: `user-${Date.now()}`,
            role: 'user',
            parts: [{ type: 'text', text: userQuery }],
          }
          setMessages((prev) => [...prev, userMessage])
        }

        setExecutionState({
          nodes: new Map(),
          progress: { current: 0, total: 0 },
        })
        currentMessageRef.current = null
        nodeTypesRef.current.clear()

        // Start workflow run
        const runApi = isDebug ? workflowsApi.debugWorkflow : workflowsApi.runWorkflow
        const { run_id } = await runApi(workflowId, { inputs })
        setRunId(run_id)

        // Connect to SSE stream
        const closeConnection = workflowsApi.streamWorkflowRun(run_id, {
          onEvent: (event: WorkflowEvent) => {
            handleWorkflowEventRef.current?.(event)
          },
          onError: (error: Error) => {
            console.error('Workflow SSE error:', error)
            setIsStreaming(false)
            setError(getApiErrorMessage('requestFailed'))
            onError?.(error)
          },
          onComplete: () => {
            setIsStreaming(false)
            onComplete?.()
          },
        })

        closeConnectionRef.current = closeConnection
      } catch (startError) {
        console.error('Failed to start workflow:', startError)
        const safeError = getApiErrorMessage('requestFailed')
        setIsStreaming(false)
        setStatus('failed')
        setError(safeError)
        onError?.(startError as Error)
      }
    },
    [workflowId, isDebug, onError, onComplete]
  )

  const handleWorkflowEvent = useCallback((event: WorkflowEvent) => {
    const { type, data } = event

    switch (type) {
      case 'workflow_start': {
        setStatus('running')
        // Initialize execution state
        const totalNodes = (data.total_nodes as number) || 0
        setExecutionState((prev) => ({
          ...prev,
          progress: { current: 0, total: totalNodes },
        }))
        break
      }

      case 'node_start': {
        const nodeId = data.node_id as string
        const nodeType = data.node_type as string
        const nodeLabel = (data.node_label as string) || nodeType
        const isAnswerNode = nodeType === 'answer'

        // Track node type for token routing
        nodeTypesRef.current.set(nodeId, nodeType)

        const node: ExecutionNode = {
          id: nodeId,
          type: nodeType,
          label: nodeLabel,
          status: 'running',
          startTime: new Date(),
          input: data.inputs,
        }

        setExecutionState((prev) => {
          const newNodes = new Map(prev.nodes)
          newNodes.set(nodeId, node)
          return {
            ...prev,
            nodes: newNodes,
            currentNodeId: nodeId,
          }
        })

        // Skip adding tool-call for answer nodes - they will output text directly
        if (isAnswerNode) {
          break
        }

        // Add node execution as a tool-call part in the message
        if (!currentMessageRef.current) {
          const newMessage: ChatMessage = {
            id: `msg-${Date.now()}`,
            role: 'assistant',
            parts: [
              {
                type: 'tool-call',
                toolCallId: nodeId,
                toolName: nodeType,
                toolDisplayName: nodeLabel,
                input: (data.inputs as Record<string, unknown>) || {},
                state: 'running',
              },
            ],
          }
          currentMessageRef.current = newMessage
          setMessages((prev) => [...prev, newMessage])
        } else {
          // Add tool-call part to existing message
          setMessages((prev) => {
            const updated = [...prev]
            const lastMsg = updated[updated.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              const parts = [
                ...lastMsg.parts,
                {
                  type: 'tool-call' as const,
                  toolCallId: nodeId,
                  toolName: nodeType,
                  toolDisplayName: nodeLabel,
                  input: (data.inputs as Record<string, unknown>) || {},
                  state: 'running' as const,
                },
              ]
              updated[updated.length - 1] = { ...lastMsg, parts }
            }
            return updated
          })
        }
        break
      }

      case 'token': {
        const nodeId = data.node_id as string
        const token = data.token as string

        // Only route answer node tokens to visible text output
        // LLM node tokens are tracked in executionState only (like the debug drawer)
        const nodeType = nodeTypesRef.current.get(nodeId)
        if (nodeType !== 'answer') {
          // Update execution state with streaming content for non-answer nodes
          setExecutionState((prev) => {
            const newNodes = new Map(prev.nodes)
            const node = newNodes.get(nodeId)
            if (node) {
              newNodes.set(nodeId, {
                ...node,
                metadata: {
                  ...node.metadata,
                  streamingContent: ((node.metadata?.streamingContent as string) || '') + token,
                },
              })
            }
            return { ...prev, nodes: newNodes }
          })
          break
        }

        // Append answer token to current message text
        if (!currentMessageRef.current) {
          const newMessage: ChatMessage = {
            id: `msg-${Date.now()}`,
            role: 'assistant',
            parts: [{ type: 'text', text: token, state: 'streaming' }],
          }
          currentMessageRef.current = newMessage
          setMessages((prev) => [...prev, newMessage])
        } else {
          // Update the last text part
          setMessages((prev) => {
            const updated = [...prev]
            const lastMsg = updated[updated.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              const parts = [...lastMsg.parts]
              const lastPart = parts[parts.length - 1]
              if (lastPart && lastPart.type === 'text') {
                parts[parts.length - 1] = {
                  ...lastPart,
                  text: lastPart.text + token,
                }
              } else {
                parts.push({ type: 'text', text: token, state: 'streaming' })
              }
              updated[updated.length - 1] = { ...lastMsg, parts }
            }
            return updated
          })
        }
        break
      }

      case 'node_complete': {
        const nodeId = data.node_id as string
        const nodeType = data.node_type as string
        const outputs = data.outputs
        const duration = data.duration_ms as number
        const isAnswerNode = nodeType === 'answer'

        setExecutionState((prev) => {
          const newNodes = new Map(prev.nodes)
          const node = newNodes.get(nodeId)
          if (node) {
            newNodes.set(nodeId, {
              ...node,
              status: 'completed',
              endTime: new Date(),
              duration,
              output: outputs,
            })
          }
          return {
            ...prev,
            nodes: newNodes,
            progress: {
              ...prev.progress,
              current: prev.progress.current + 1,
            },
          }
        })

        // For answer nodes, mark streaming text as done (tokens already pushed the content)
        if (isAnswerNode) {
          setMessages((prev) => {
            const updated = [...prev]
            const lastMsg = updated[updated.length - 1]
            if (lastMsg && lastMsg.role === 'assistant') {
              const parts = lastMsg.parts.map((part) => {
                if (part.type === 'text' && part.state === 'streaming') {
                  return { ...part, state: 'done' as const }
                }
                return part
              })
              updated[updated.length - 1] = { ...lastMsg, parts }
            }
            return updated
          })
          break
        }

        // For non-answer nodes, update tool-call to done and add tool-result
        setMessages((prev) => {
          const updated = [...prev]
          const lastMsg = updated[updated.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            const parts = lastMsg.parts.map((part) => {
              if (part.type === 'text' && part.state === 'streaming') {
                return { ...part, state: 'done' as const }
              }
              if (part.type === 'tool-call' && part.toolCallId === nodeId && part.state === 'running') {
                return { ...part, state: 'done' as const }
              }
              return part
            })

            // Add tool-result part
            const toolCallPart = parts.find(p => p.type === 'tool-call' && (p as { toolCallId?: string }).toolCallId === nodeId) as { toolName?: string; toolDisplayName?: string } | undefined
            parts.push({
              type: 'tool-result',
              toolCallId: nodeId,
              toolName: toolCallPart?.toolName || '',
              toolDisplayName: toolCallPart?.toolDisplayName,
              output: outputs,
              isError: false,
            })

            updated[updated.length - 1] = { ...lastMsg, parts }
          }
          return updated
        })

        break
      }

      case 'node_error': {
        const nodeId = data.node_id as string
        const errorMessage = resolveWorkflowErrorMessage(data.error, getApiErrorMessage('requestFailed'))

        setExecutionState((prev) => {
          const newNodes = new Map(prev.nodes)
          const node = newNodes.get(nodeId)
          if (node) {
            newNodes.set(nodeId, {
              ...node,
              status: 'error',
              endTime: new Date(),
              error: errorMessage,
            })
          }
          return {
            ...prev,
            nodes: newNodes,
          }
        })

        // Update tool-call to error and add tool-result with error
        setMessages((prev) => {
          const updated = [...prev]
          const lastMsg = updated[updated.length - 1]
          if (lastMsg && lastMsg.role === 'assistant') {
            const parts = lastMsg.parts.map((part) => {
              if (part.type === 'tool-call' && part.toolCallId === nodeId && part.state === 'running') {
                return { ...part, state: 'error' as const }
              }
              return part
            })

            // Add tool-result part with error
            const toolCallPart = parts.find(p => p.type === 'tool-call' && (p as { toolCallId?: string }).toolCallId === nodeId) as { toolName?: string; toolDisplayName?: string } | undefined
            parts.push({
              type: 'tool-result',
              toolCallId: nodeId,
              toolName: toolCallPart?.toolName || '',
              toolDisplayName: toolCallPart?.toolDisplayName,
              output: errorMessage,
              isError: true,
            })

            updated[updated.length - 1] = { ...lastMsg, parts }
          }
          return updated
        })
        currentMessageRef.current = null
        break
      }

      case 'node_skip': {
        const nodeId = data.node_id as string

        setExecutionState((prev) => {
          const newNodes = new Map(prev.nodes)
          const node = newNodes.get(nodeId)
          if (node) {
            newNodes.set(nodeId, {
              ...node,
              status: 'skipped',
            })
          }
          return {
            ...prev,
            nodes: newNodes,
          }
        })
        break
      }

      case 'output': {
        const eventOutputs = data.outputs ?? data.output ?? data
        if (eventOutputs && typeof eventOutputs === 'object' && !Array.isArray(eventOutputs)) {
          setOutputs(eventOutputs as Record<string, unknown>)
        } else {
          setOutputs({ result: eventOutputs })
        }
        break
      }

      case 'workflow_complete': {
        const finalOutputs = data.outputs
        if (finalOutputs && typeof finalOutputs === 'object' && !Array.isArray(finalOutputs)) {
          setOutputs(finalOutputs as Record<string, unknown>)
        }
        setStatus('success')
        setIsStreaming(false)
        onComplete?.()
        break
      }

      case 'workflow_error': {
        const errorMessage = resolveWorkflowErrorMessage(data.error, getApiErrorMessage('requestFailed'))
        const errorMsg: ChatMessage = {
          id: `error-${Date.now()}`,
          role: 'assistant',
          parts: [{ type: 'text', text: `${errorMessage}` }],
        }
        setMessages((prev) => [...prev, errorMsg])
        setError(errorMessage)
        setStatus('failed')
        setIsStreaming(false)
        break
      }
    }
  }, [onComplete])

  // Store the handler in ref so it can be accessed in start callback
  handleWorkflowEventRef.current = handleWorkflowEvent

  return {
    messages,
    executionState,
    isStreaming,
    runId,
    status,
    outputs,
    submittedInputs,
    error,
    isCancelling,
    start,
    stop,
    reset,
  }
}
