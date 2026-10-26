import type { AgentRunStatus } from '@/lib/api/agents'

/** Minimal server-authoritative run fields used to derive chat interactions. */
export interface RunInteractionStatusLike {
  status: AgentRunStatus | string
  pending_tool_call_id?: string | null
  pending_tool_name?: string | null
  pending_tool_input?: Record<string, unknown> | null
}

/** One durable tool execution that is waiting for an approval decision. */
export interface PendingToolApproval {
  executionId: string
  toolCallId: string | null
  toolName: string | null
}

/**
 * Derive the pending approval from a waiting AgentRun.
 *
 * Approval-bound tool calls reuse the durable ask_user pause primitive: the
 * original tool name stays in `pending_tool_name` and the marker
 * `interaction_kind=tool_approval` lives in `pending_tool_input`. This is not
 * an ask_user question and must never be answered through the answer API.
 */
export function getPendingToolApproval(
  status: RunInteractionStatusLike | null | undefined
): PendingToolApproval | null {
  if (!status || status.status !== 'waiting') return null

  const input = status.pending_tool_input
  if (!input || input.interaction_kind !== 'tool_approval') return null

  const executionId = typeof input.execution_id === 'string' ? input.execution_id.trim() : ''
  if (!executionId) return null

  return {
    executionId,
    toolCallId: status.pending_tool_call_id ?? null,
    toolName: status.pending_tool_name ?? null,
  }
}

/**
 * Only an actual ask_user tool call may render the questionnaire/answer form.
 * Any other waiting tool call (approval, MCP callback) is not answerable.
 */
export function getPendingAskUserToolCallId(
  status: RunInteractionStatusLike | null | undefined
): string | null {
  if (!status || status.status !== 'waiting') return null
  if (status.pending_tool_name !== 'ask_user') return null
  const input = status.pending_tool_input
  if (input?.interaction_kind !== undefined && input.interaction_kind !== null) return null
  return status.pending_tool_call_id ?? null
}

/** Whether an active/waiting run may still receive MCP interaction responses. */
export function isRunOpenForInteractions(
  status: AgentRunStatus | string | null | undefined
): boolean {
  return (
    status === 'queued'
    || status === 'running'
    || status === 'stopping'
    || status === 'completing'
    || status === 'waiting'
  )
}
