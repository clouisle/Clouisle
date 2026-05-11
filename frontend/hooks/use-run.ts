'use client'

import { useMemo } from 'react'
import { useTranslations } from 'next-intl'
import { useChat } from './use-chat'
import { useWorkflowRun } from './use-workflow-run'
import type { ChatMessage, ExecutionNode, ExecutionState } from '@/components/chat/types'
import type { ChatImageContent, ChatFileUrl } from '@/lib/api'

export type RunType = 'agent' | 'workflow'

export interface UseRunOptions {
  id: string
  type: RunType
  conversationId?: string
  variables?: Record<string, unknown>
  isDebug?: boolean
  onConversationChange?: (conversationId: string) => void
  onError?: (error: Error) => void
  onStreamStart?: () => void
  onStreamEnd?: () => void
}

export interface UseRunReturn {
  messages: ChatMessage[]
  executionState: ExecutionState | null
  isStreaming: boolean
  isLoading: boolean
  conversationId?: string | null
  runId?: string | null
  sendMessage: (
    text: string,
    images?: ChatImageContent[],
    files?: ChatFileUrl[]
  ) => Promise<void>
  start?: (inputs: Record<string, unknown>) => Promise<void>
  stop: () => void
  reset: () => void
  regenerate?: (messageId: string) => Promise<void>
  switchVersion?: (messageId: string, versionIndex: number) => Promise<void>
}

/**
 * Unified hook for running both Agents and Workflows
 * Delegates to use-chat for Agents and use-workflow-run for Workflows
 */
export function useRun(options: UseRunOptions): UseRunReturn {
  const { id, type, conversationId, variables, isDebug, onConversationChange, onError, onStreamStart, onStreamEnd } = options
  const tReasoning = useTranslations('chat.reasoning')
  const tTask = useTranslations('chat.task')
  const tAgents = useTranslations('agents.chat.messages')

  // Agent chat hook
  const agentChat = useChat({
    agentId: type === 'agent' ? id : '',
    conversationId,
    variables,
    onConversationChange,
    onError: onError ? (err) => onError(new Error(err.message)) : undefined,
    onStreamStart,
    onStreamEnd,
  })

  // Workflow run hook
  const workflowRun = useWorkflowRun({
    workflowId: type === 'workflow' ? id : '',
    isDebug,
    onError,
    onComplete: onStreamEnd,
  })

  // Convert Agent reasoning/tool calls to virtual execution nodes
  const agentExecutionState = useMemo((): ExecutionState | null => {
    if (type !== 'agent' || agentChat.messages.length === 0) return null

    const nodes = new Map<string, ExecutionNode>()
    let nodeIndex = 0

    // Extract reasoning, tool calls, and tasks from messages
    agentChat.messages.forEach((message) => {
      if (message.role !== 'assistant') return

      message.parts.forEach((part) => {
        if (part.type === 'reasoning') {
          const nodeId = `reasoning-${nodeIndex++}`
          nodes.set(nodeId, {
            id: nodeId,
            type: 'reasoning',
            label: tAgents('reasoning'),
            status: part.state === 'streaming' ? 'running' : 'completed',
            duration: part.duration,
            output: part.text,
          })
        } else if (part.type === 'tool-call') {
          const nodeId = part.toolCallId
          nodes.set(nodeId, {
            id: nodeId,
            type: 'tool',
            label: part.toolDisplayName || part.toolName,
            status: part.state === 'running' ? 'running' : part.state === 'error' ? 'error' : 'completed',
            input: part.input,
          })
        } else if (part.type === 'tool-result') {
          const node = nodes.get(part.toolCallId)
          if (node) {
            nodes.set(part.toolCallId, {
              ...node,
              status: part.isError ? 'error' : 'completed',
              output: part.output,
              error: part.isError ? String(part.output) : undefined,
            })
          }
        } else if (part.type === 'task') {
          const nodeId = `task-${part.taskType}-${nodeIndex++}`
          nodes.set(nodeId, {
            id: nodeId,
            type: part.taskType,
            label: part.taskType === 'rag'
              ? tTask('searchingKnowledge')
              : part.taskType === 'thinking'
                ? tReasoning('thinking')
                : part.taskType === 'compression'
                  ? tTask('compressingContext')
                  : tTask('generating'),
            status: part.state === 'running' ? 'running' : part.state === 'error' ? 'error' : part.state === 'completed' ? 'completed' : 'pending',
            metadata: { info: part.info },
          })
        }
      })
    })

    return {
      nodes,
      progress: { current: nodes.size, total: nodes.size },
    }
  }, [type, agentChat.messages, tAgents, tReasoning, tTask])

  if (type === 'agent') {
    return {
      messages: agentChat.messages,
      executionState: agentExecutionState,
      isStreaming: agentChat.isStreaming,
      isLoading: agentChat.isLoading,
      conversationId: agentChat.conversationId,
      sendMessage: agentChat.sendMessage,
      stop: agentChat.stop,
      reset: agentChat.reset,
      regenerate: agentChat.regenerate,
      switchVersion: agentChat.switchVersion,
    }
  } else {
    return {
      messages: workflowRun.messages,
      executionState: workflowRun.executionState,
      isStreaming: workflowRun.isStreaming,
      isLoading: false,
      runId: workflowRun.runId,
      start: workflowRun.start,
      stop: workflowRun.stop,
      reset: workflowRun.reset,
      sendMessage: async (text: string) => {
        // For workflow, trigger a new run with the text as 'query' input
        await workflowRun.start({ query: text, ...variables })
      },
    }
  }
}
