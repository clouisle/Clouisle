import { api } from './client'

export type ToolConnectionScope = 'user' | 'team' | 'site'
export type ToolConnectionStatus = 'active' | 'revoked' | 'reauth_required'
export type ConnectionEntrypointType =
  | 'agent'
  | 'workflow'
  | 'api_key'
  | 'schedule'
  | 'channel'
  | 'embed'

export interface ToolConnection {
  id: string
  team_id: string | null
  tool_id: string | null
  builtin_tool_key: string | null
  scope: ToolConnectionScope
  name: string
  account_label: string | null
  status: ToolConnectionStatus
  secret_fields: string[]
  secret_version: number
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface ToolConnectionCreateInput {
  team_id?: string | null
  scope: ToolConnectionScope
  name: string
  account_label?: string | null
  config?: Record<string, string>
  is_default?: boolean
}

export interface ToolConnectionUpdateInput {
  name?: string
  account_label?: string | null
  status?: ToolConnectionStatus
  config_set?: Record<string, string>
  config_remove?: string[]
  is_default?: boolean
  expected_secret_version?: number
}

export interface ConnectionGrant {
  id: string
  connection_id: string
  granted_by_id: string
  entrypoint_type: ConnectionEntrypointType
  entrypoint_id: string
  team_id: string | null
  allowed_operations: string[]
  expires_at: string | null
  revoked_at: string | null
  revoked_by_id: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface ConnectionGrantCreateInput {
  entrypoint_type: ConnectionEntrypointType
  entrypoint_id: string
  team_id?: string | null
  allowed_operations: string[]
  expires_at?: string | null
}

export interface ConnectionOAuthStartInput {
  redirect_path?: string
  client_secret?: string
}

export interface ConnectionOAuthStart {
  authorization_url: string
  state: string
  expires_at: string
  provider_kind: 'mcp' | 'http'
  connection_id: string
}

export interface ConnectionOAuthDisconnect {
  connection_id: string
  local_revoked: boolean
  remote_revocation: 'revoked' | 'unsupported' | 'failed'
  needs_reauth: boolean
}

export interface ConnectionOAuthStatus {
  connection_id: string
  provider_kind: 'mcp' | 'http' | null
  provider_configured: boolean
  authorized: boolean
  needs_reauth: boolean
  status: ToolConnectionStatus
  account_label: string | null
  scopes: string[]
  expires_at: string | null
  client_id: string | null
}

export interface ListToolConnectionsParams {
  teamId: string
  includeSite?: boolean
  includeRevoked?: boolean
}

function appendQuery(url: string, entries: Array<[string, string | boolean | undefined]>): string {
  const query = new URLSearchParams()
  for (const [key, value] of entries) {
    if (value === undefined) continue
    query.append(key, String(value))
  }
  const suffix = query.toString()
  return suffix ? `${url}?${suffix}` : url
}

export const toolConnectionsApi = {
  listForTool: async (
    toolId: string,
    { teamId, includeSite = true, includeRevoked = false }: ListToolConnectionsParams
  ): Promise<ToolConnection[]> =>
    api.get<ToolConnection[]>(
      appendQuery(`/tools/${toolId}/connections`, [
        ['team_id', teamId],
        ['include_site', includeSite],
        ['include_revoked', includeRevoked],
      ])
    ),

  createForTool: async (
    toolId: string,
    data: ToolConnectionCreateInput
  ): Promise<ToolConnection> => api.post<ToolConnection>(`/tools/${toolId}/connections`, data),

  list: async (
    teamId: string,
    options: { toolId?: string; builtinToolKey?: string; includeSite?: boolean; includeRevoked?: boolean } = {}
  ): Promise<ToolConnection[]> =>
    api.get<ToolConnection[]>(
      appendQuery('/tool-connections', [
        ['team_id', teamId],
        ['tool_id', options.toolId],
        ['builtin_tool_key', options.builtinToolKey],
        ['include_site', options.includeSite],
        ['include_revoked', options.includeRevoked],
      ])
    ),

  create: async (data: ToolConnectionCreateInput & { tool_id?: string; builtin_tool_key?: string }): Promise<ToolConnection> =>
    api.post<ToolConnection>('/tool-connections', data),

  get: async (connectionId: string, teamId?: string): Promise<ToolConnection> =>
    api.get<ToolConnection>(
      appendQuery(`/tool-connections/${connectionId}`, [['team_id', teamId]])
    ),

  update: async (connectionId: string, data: ToolConnectionUpdateInput): Promise<ToolConnection> =>
    api.patch<ToolConnection>(`/tool-connections/${connectionId}`, data),

  revoke: async (connectionId: string, reason?: string): Promise<ToolConnection> =>
    api.delete<ToolConnection>(
      appendQuery(`/tool-connections/${connectionId}`, [['reason', reason]])
    ),

  listGrants: async (connectionId: string, includeRevoked = false): Promise<ConnectionGrant[]> =>
    api.get<ConnectionGrant[]>(
      appendQuery(`/tool-connections/${connectionId}/grants`, [
        ['include_revoked', includeRevoked],
      ])
    ),

  createGrant: async (
    connectionId: string,
    data: ConnectionGrantCreateInput
  ): Promise<ConnectionGrant> =>
    api.post<ConnectionGrant>(`/tool-connections/${connectionId}/grants`, data),

  revokeGrant: async (
    connectionId: string,
    grantId: string,
    reason?: string
  ): Promise<ConnectionGrant> =>
    api.delete<ConnectionGrant>(
      appendQuery(`/tool-connections/${connectionId}/grants/${grantId}`, [['reason', reason]])
    ),

  startOAuth: async (
    connectionId: string,
    data: ConnectionOAuthStartInput = {}
  ): Promise<ConnectionOAuthStart> =>
    api.post<ConnectionOAuthStart>(`/tool-connections/${connectionId}/oauth/start`, data),

  getOAuthStatus: async (connectionId: string, teamId?: string): Promise<ConnectionOAuthStatus> =>
    api.get<ConnectionOAuthStatus>(
      appendQuery(`/tool-connections/${connectionId}/oauth`, [['team_id', teamId]])
    ),

  disconnectOAuth: async (connectionId: string): Promise<ConnectionOAuthDisconnect> =>
    api.post<ConnectionOAuthDisconnect>(`/tool-connections/${connectionId}/oauth/disconnect`),
}
