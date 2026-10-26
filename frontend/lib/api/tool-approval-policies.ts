import { api } from './client'
import type { ToolApprovalGate, ToolApprovalPolicy } from './tools'

/** Layer a persisted approval policy applies to. */
export type ToolApprovalPolicyScope = 'site' | 'team' | 'entrypoint'
/** Entry point kind an entrypoint-scoped policy is bound to. */
export type ToolApprovalPolicyEntrypointKind = 'agent' | 'workflow' | 'api_key'
/** Strength layer returned by the server-side effective-policy evaluation. */
export type ToolApprovalPolicyLayerSource = 'site' | 'team' | 'tool' | 'entrypoint'

/** One persisted policy row, including server-computed edit permission. */
export interface ToolApprovalPolicyRow {
  id: string
  scope: ToolApprovalPolicyScope
  team_id: string | null
  entrypoint_kind: ToolApprovalPolicyEntrypointKind | null
  entrypoint_id: string | null
  /** `null` means the policy applies to every tool. */
  tool_id: string | null
  policy: ToolApprovalPolicy
  policy_hash: string
  version: number
  can_edit: boolean
  created_by_id: string | null
  created_at: string
  updated_at: string
}

export interface ToolApprovalPolicyListParams {
  team_id?: string
  scope?: ToolApprovalPolicyScope
  entrypoint_kind?: ToolApprovalPolicyEntrypointKind
  entrypoint_id?: string
  tool_id?: string
}

export interface ToolApprovalPolicyCreateInput {
  scope: ToolApprovalPolicyScope
  team_id?: string | null
  entrypoint_kind?: ToolApprovalPolicyEntrypointKind | null
  entrypoint_id?: string | null
  tool_id?: string | null
  policy: ToolApprovalPolicy
}

export interface ToolApprovalPolicyUpdateInput {
  policy: ToolApprovalPolicy
  /** Optimistic concurrency; a mismatch returns a 409 version conflict. */
  expected_version?: number
}

export interface ToolApprovalPolicyEffectiveParams {
  team_id: string
  entrypoint_kind: ToolApprovalPolicyEntrypointKind
  entrypoint_id: string
  tool_id?: string
  operation?: string
}

export interface ToolApprovalPolicyEffectiveLayer {
  source: ToolApprovalPolicyLayerSource
  version: number | null
  policy_hash: string | null
  can_edit: boolean
}

/** Server-composed effective policy; never merge layers on the client. */
export interface ToolApprovalPolicyEffective {
  decision: ToolApprovalPolicy['default_decision']
  gates: ToolApprovalGate[]
  policy_hash: string
  sources: string[]
  configuration_error: string | null
  layers: ToolApprovalPolicyEffectiveLayer[]
  can_edit_team: boolean
}

function compactParams(params: Record<string, string | number | undefined>): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue
    result[key] = value
  }
  return result
}

export const toolApprovalPoliciesApi = {
  /**
   * Rows the caller may see. Site rows are returned for a superuser or when a
   * team id is supplied; team/entrypoint rows only for that team.
   */
  list: async (params: ToolApprovalPolicyListParams = {}): Promise<ToolApprovalPolicyRow[]> =>
    api.get<ToolApprovalPolicyRow[]>('/tool-approval-policies', {
      params: compactParams({
        team_id: params.team_id,
        scope: params.scope,
        entrypoint_kind: params.entrypoint_kind,
        entrypoint_id: params.entrypoint_id,
        tool_id: params.tool_id,
      }),
    }),

  /** Server-composed decision and source layers for one concrete call. */
  effective: async (
    params: ToolApprovalPolicyEffectiveParams
  ): Promise<ToolApprovalPolicyEffective> =>
    api.get<ToolApprovalPolicyEffective>('/tool-approval-policies/effective', {
      params: compactParams({
        team_id: params.team_id,
        entrypoint_kind: params.entrypoint_kind,
        entrypoint_id: params.entrypoint_id,
        tool_id: params.tool_id,
        operation: params.operation,
      }),
    }),

  create: async (input: ToolApprovalPolicyCreateInput): Promise<ToolApprovalPolicyRow> =>
    api.post<ToolApprovalPolicyRow>('/tool-approval-policies', input),

  update: async (
    policyId: string,
    input: ToolApprovalPolicyUpdateInput
  ): Promise<ToolApprovalPolicyRow> =>
    api.put<ToolApprovalPolicyRow>(`/tool-approval-policies/${policyId}`, input),

  remove: async (policyId: string): Promise<null> =>
    api.delete<null>(`/tool-approval-policies/${policyId}`),
}
