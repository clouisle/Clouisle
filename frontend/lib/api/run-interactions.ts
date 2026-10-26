import { api } from './client'
import type { PageData } from './users'

/**
 * Server-initiated MCP interactions. These are separate from tool approvals:
 * accepting one authorizes an elicitation answer or a sampling model call, it
 * never approves the enclosing tool execution.
 */
export type RunInteractionKind = 'sampling' | 'elicitation'

export type RunInteractionStatus =
  | 'pending'
  | 'responded'
  | 'expired'
  | 'cancelled'
  | 'connection_lost'

export type RunInteractionOutcome = 'accept' | 'decline' | 'cancel'

export interface RunInteractionAudience {
  user_ids: string[]
  roles: string[]
}

export interface SamplingInteractionPayload {
  mode: 'sampling'
  system_prompt: string | null
  messages: Array<{ role: string; content: unknown }>
  max_tokens: number
  model_preferences: Record<string, unknown> | null
}

export interface ElicitationFormPayload {
  mode: 'form'
  message: string
  requested_schema: Record<string, unknown>
}

export interface ElicitationUrlPayload {
  mode: 'url'
  message: string
  url: string
}

export type RunInteractionPayload =
  | SamplingInteractionPayload
  | ElicitationFormPayload
  | ElicitationUrlPayload

export interface RunInteraction {
  id: string
  kind: RunInteractionKind
  status: RunInteractionStatus
  run_kind: 'agent' | 'workflow' | null
  run_id: string | null
  execution_id: string | null
  tool_id: string | null
  tool_call_id: string | null
  tool_name: string | null
  team_id: string | null
  payload: RunInteractionPayload
  audience: RunInteractionAudience
  expires_at: string | null
  responded_at: string | null
  responded_by_id: string | null
  outcome: RunInteractionOutcome | null
  response: Record<string, unknown> | null
  created_at: string
}

export interface RunInteractionListParams {
  page?: number
  page_size?: number
  kind?: RunInteractionKind
  run_id?: string
  status?: RunInteractionStatus
}

export interface RunInteractionResponseInput {
  action: RunInteractionOutcome
  /**
   * Elicitation form answers for `accept`; must be `null` for URL
   * elicitation, sampling and every decline/cancel.
   */
  content: Record<string, unknown> | null
  idempotency_key: string
}

function compactParams(params: Record<string, string | number | undefined>): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue
    result[key] = value
  }
  return result
}

export const runInteractionsApi = {
  /**
   * Pending interactions whose audience includes the current user. The pending
   * list is the durable truth; there is no interaction SSE event stream.
   */
  list: async (
    params: RunInteractionListParams = {},
    config?: { silent?: boolean }
  ): Promise<PageData<RunInteraction>> =>
    api.get<PageData<RunInteraction>>('/run-interactions', {
      params: compactParams({
        page: params.page,
        page_size: params.page_size,
        kind: params.kind,
        run_id: params.run_id,
        status: params.status ?? 'pending',
      }),
      silent: config?.silent,
    }),

  get: async (interactionId: string, config?: { silent?: boolean }): Promise<RunInteraction> =>
    api.get<RunInteraction>(`/run-interactions/${interactionId}`, {
      silent: config?.silent,
    }),

  respond: async (
    interactionId: string,
    input: RunInteractionResponseInput
  ): Promise<RunInteraction> =>
    api.post<RunInteraction>(`/run-interactions/${interactionId}/response`, input),
}

/** Extract a usable external URL from a URL-mode elicitation payload. */
export function getElicitationUrl(payload: RunInteractionPayload): string | null {
  if (payload.mode !== 'url') return null
  try {
    const parsed = new URL(payload.url)
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null
    return parsed.toString()
  } catch {
    return null
  }
}
