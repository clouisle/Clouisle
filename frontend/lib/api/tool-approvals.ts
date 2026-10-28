import { api } from './client'
import type { PageData } from './users'

/** Decision recorded by one approver for one approval gate. */
export type ToolApprovalVote = 'approve' | 'reject'
/** Lifecycle of one persisted approval gate. */
export type ToolApprovalRequestStatus = 'pending' | 'approved' | 'rejected' | 'expired' | 'cancelled'
/** Lifecycle of the bound tool execution. */
export type ToolExecutionStatus =
  | 'awaiting_approval'
  | 'ready'
  | 'executing'
  | 'succeeded'
  | 'failed'
  | 'outcome_unknown'
  | 'cancelled'
/** Why an execution ended without performing a side effect. */
export type ToolExecutionCancelReason =
  | 'rejected'
  | 'expired'
  | 'revoked'
  | 'cancelled'
  | 'binding_changed'
  | 'run_stopped'
  | 'policy_denied'
/** Durable run kind that owns an execution, when any. */
export type ToolExecutionRunKind = 'agent' | 'workflow'
/** Who requested one execution. */
export type ToolExecutionEntrypoint =
  | 'chat'
  | 'agent_run'
  | 'workflow'
  | 'api_key'
  | 'schedule'
  | 'channel'
  | 'feishu_channel'
  | 'wechat_channel'
  | 'embed'
  | 'subworkflow'
  | 'nested_agent'
  | 'tool_test'
  | 'admin_test'
/** Who may decide one gate. */
export type ToolApprovalGateKind = 'caller' | 'user' | 'team_role'

/** Secret-safe connection metadata attached to an execution preview. */
export interface ToolApprovalDisplayConnection {
  connection_id: string
  scope: string | null
  account_label: string | null
  effective_user_id: string | null
}

/**
 * Redacted metadata frozen onto an approval gate. Values under
 * `parameters` have already been masked by the backend; never render the
 * execution ciphertext (it is not returned at all).
 */
export interface ToolApprovalMaskedDisplay {
  tool_id?: string
  tool_name?: string | null
  operation?: string
  parameters?: Record<string, unknown>
  entrypoint?: ToolExecutionEntrypoint | string
  entrypoint_id?: string | null
  run_kind?: ToolExecutionRunKind | null
  run_id?: string | null
  tool_call_id?: string | null
  connection?: ToolApprovalDisplayConnection | null
  policy_sources?: string[]
  note?: string
}

/** One approval gate awaiting or holding a decision. */
export interface ToolApprovalRequest {
  id: string
  execution_id: string
  stage_index: number
  stage_key: string
  gate_kind: ToolApprovalGateKind
  approver_user_ids: string[]
  approver_roles: string[]
  allow_self_approval: boolean
  masked_display: ToolApprovalMaskedDisplay
  status: ToolApprovalRequestStatus
  expires_at: string | null
  resolved_at: string | null
  created_at: string
}

/** Secret-safe execution projection (no ciphertext, secrets or claim tokens). */
export interface ToolExecution {
  id: string
  tool_id: string
  tool_definition_version: number
  operation: string
  actor_user_id: string
  effective_user_id: string | null
  team_id: string
  entrypoint: ToolExecutionEntrypoint
  entrypoint_id: string | null
  run_kind: ToolExecutionRunKind | null
  run_id: string | null
  tool_call_id: string | null
  connection_id: string | null
  connection_version: number | null
  connection_scope: string | null
  connection_account_label: string | null
  parameters_preview: Record<string, unknown>
  parameters_digest: string
  policy_hash: string
  status: ToolExecutionStatus
  cancel_reason: ToolExecutionCancelReason | null
  result_ref: Record<string, unknown> | null
  error_code: string | null
  expires_at: string | null
  claimed_at: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

/** Immutable decision record returned after approving or rejecting. */
export interface ToolApprovalDecision {
  id: string
  request_id: string
  execution_id: string
  decision: ToolApprovalVote
  decided_by_id: string | null
  reason: string | null
  created_at: string
}

/** Result of one decision, including the server-authoritative execution state. */
export interface ToolApprovalDecisionResult {
  decision: ToolApprovalDecision
  execution_status: ToolExecutionStatus
  remaining_approvals: number
}

export interface ToolApprovalDecisionInput {
  decision: ToolApprovalVote
  /** Optional approver note (max 2000 characters). */
  reason?: string | null
  /** Deduplicates retries of the same decision. */
  idempotency_key: string
}

export interface ToolApprovalListParams {
  page?: number
  page_size?: number
}

export interface ToolExecutionListParams {
  page?: number
  page_size?: number
  status?: ToolExecutionStatus
  tool_id?: string
  run_kind?: ToolExecutionRunKind
  run_id?: string
}

function compactParams(params: Record<string, string | number | undefined>): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue
    result[key] = value
  }
  return result
}

export const toolApprovalsApi = {
  /** Pending gates whose audience includes the current user. */
  list: async (
    params: ToolApprovalListParams = {},
    config?: { silent?: boolean }
  ): Promise<PageData<ToolApprovalRequest>> =>
    api.get<PageData<ToolApprovalRequest>>('/tool-approvals', {
      params: compactParams({
        page: params.page,
        page_size: params.page_size,
      }),
      silent: config?.silent,
    }),

  get: async (requestId: string): Promise<ToolApprovalRequest> =>
    api.get<ToolApprovalRequest>(`/tool-approvals/${requestId}`),

  /**
   * Record approve/reject for this exact gate. Parameters are never accepted
   * here; the decision only moves the durable execution to `ready` or
   * `cancelled`, and the worker performs the side effect.
   */
  decide: async (
    requestId: string,
    input: ToolApprovalDecisionInput
  ): Promise<ToolApprovalDecisionResult> =>
    api.post<ToolApprovalDecisionResult>(
      `/tool-approvals/${requestId}/decision`,
      input
    ),
}

export const toolExecutionsApi = {
  /** Executions initiated by the current user, optionally scoped to one run. */
  list: async (
    params: ToolExecutionListParams = {},
    config?: { silent?: boolean }
  ): Promise<PageData<ToolExecution>> =>
    api.get<PageData<ToolExecution>>('/tool-executions', {
      params: compactParams({
        page: params.page,
        page_size: params.page_size,
        status: params.status,
        tool_id: params.tool_id,
        run_kind: params.run_kind,
        run_id: params.run_id,
      }),
      silent: config?.silent,
    }),

  get: async (executionId: string, config?: { silent?: boolean }): Promise<ToolExecution> =>
    api.get<ToolExecution>(`/tool-executions/${executionId}`, {
      silent: config?.silent,
    }),

  /** Directly record an approve/reject decision for an execution in chat. */
  decide: async (
    executionId: string,
    input: ToolApprovalDecisionInput
  ): Promise<ToolApprovalDecisionResult> =>
    api.post<ToolApprovalDecisionResult>(
      `/tool-executions/${executionId}/decision`,
      input
    ),
}
