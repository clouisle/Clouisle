import { api } from './client'

export type McpConnectionMode = 'personal' | 'team'

export interface McpIdentityInput {
  connection_mode?: McpConnectionMode
  connection_id?: string
  /** Resume one previously returned pending execution after approval. */
  execution_id?: string
}

export interface McpCapabilities {
  protocol_version: string | null
  server_name: string | null
  server_version: string | null
  instructions: string | null
  tools: boolean
  tools_list_changed: boolean
  resources: boolean
  resources_subscribe: boolean
  resources_list_changed: boolean
  resource_templates: boolean
  prompts: boolean
  prompts_list_changed: boolean
  completions: boolean
  logging: boolean
  experimental: boolean
}

export interface McpEnumeration<T> {
  items: T[]
  pages_fetched: number
  truncated: boolean
  truncation_reason: string | null
  next_cursor: string | null
  total_items: number
}

export interface McpTool {
  name: string
  title: string | null
  description: string | null
  parameters: Record<string, unknown>
  output_schema: Record<string, unknown> | null
  annotations: Record<string, unknown> | null
  meta: Record<string, unknown> | null
}

export interface McpResource {
  uri: string
  name: string | null
  title: string | null
  description: string | null
  mime_type: string | null
  size: number | null
  annotations: Record<string, unknown> | null
  meta: Record<string, unknown> | null
}

export interface McpResourceTemplate {
  uri_template: string
  name: string | null
  title: string | null
  description: string | null
  mime_type: string | null
  annotations: Record<string, unknown> | null
  meta: Record<string, unknown> | null
}

export interface McpPromptArgument {
  name: string
  description: string | null
  required: boolean
}

export interface McpPrompt {
  name: string
  title: string | null
  description: string | null
  arguments: McpPromptArgument[]
  meta: Record<string, unknown> | null
}

export interface McpResourceContents {
  uri: string
  mime_type: string | null
  text: string | null
  blob: string | null
  meta: Record<string, unknown> | null
}

export interface McpPromptMessage {
  role: string
  content: Record<string, unknown>
}

export interface McpPromptResult {
  messages: McpPromptMessage[]
  description: string | null
  meta: Record<string, unknown> | null
}

export interface McpPendingApproval {
  execution_id: string
  tool_name: string
  status: 'awaiting_approval'
}

export interface McpOperation<T> {
  status: 'completed' | 'pending_approval'
  operation: string
  execution_id: string | null
  result: T | null
  pending_approval: McpPendingApproval | null
}

export interface McpListParams extends McpIdentityInput {
  teamId: string
  maxItems?: number
  cursor?: string
  execution_id?: string
}

export interface McpResourceSubscriptionOpened {
  subscription_id: string
  tool_id: string
  team_id: string
  uri: string
  connection_id: string | null
  connection_scope: 'user' | 'team' | 'site' | null
  account_label: string | null
  expires_at: string
}

export interface McpResourceUpdated {
  subscription_id: string
  uri: string
  sequence: number
  received_at: string
}

export type McpSubscriptionCloseReason = 'ttl_expired' | 'connection_lost'

export interface McpSubscribeCallbacks {
  onOpened: (event: McpResourceSubscriptionOpened) => void
  onUpdated: (event: McpResourceUpdated) => void
  onClosed: (reason: McpSubscriptionCloseReason) => void
  onPendingApproval?: (executionId: string) => void
}

function queryUrl(path: string, values: Array<[string, string | number | undefined]>): string {
  const query = new URLSearchParams()
  for (const [key, value] of values) {
    if (value === undefined || value === '') continue
    query.append(key, String(value))
  }
  const suffix = query.toString()
  return suffix ? `${path}?${suffix}` : path
}

export const toolMcpApi = {
  getCapabilities: async (
    toolId: string,
    { teamId, connection_mode, connection_id, execution_id }: McpListParams
  ): Promise<McpOperation<McpCapabilities>> =>
    api.get<McpOperation<McpCapabilities>>(
      queryUrl(`/tools/${toolId}/mcp/capabilities`, [
        ['team_id', teamId],
        ['connection_mode', connection_mode],
        ['connection_id', connection_id],
        ['execution_id', execution_id],
      ])
    ),

  listTools: async (
    toolId: string,
    { teamId, connection_mode, connection_id, maxItems, cursor, execution_id }: McpListParams
  ): Promise<McpOperation<McpEnumeration<McpTool>>> =>
    api.get<McpOperation<McpEnumeration<McpTool>>>(
      queryUrl(`/tools/${toolId}/mcp/tools`, [
        ['team_id', teamId],
        ['connection_mode', connection_mode],
        ['connection_id', connection_id],
        ['max_items', maxItems],
        ['cursor', cursor],
        ['execution_id', execution_id],
      ])
    ),

  listResources: async (
    toolId: string,
    { teamId, connection_mode, connection_id, maxItems, cursor, execution_id }: McpListParams
  ): Promise<McpOperation<McpEnumeration<McpResource>>> =>
    api.get<McpOperation<McpEnumeration<McpResource>>>(
      queryUrl(`/tools/${toolId}/mcp/resources`, [
        ['team_id', teamId],
        ['connection_mode', connection_mode],
        ['connection_id', connection_id],
        ['max_items', maxItems],
        ['cursor', cursor],
        ['execution_id', execution_id],
      ])
    ),

  listResourceTemplates: async (
    toolId: string,
    { teamId, connection_mode, connection_id, maxItems, cursor, execution_id }: McpListParams
  ): Promise<McpOperation<McpEnumeration<McpResourceTemplate>>> =>
    api.get<McpOperation<McpEnumeration<McpResourceTemplate>>>(
      queryUrl(`/tools/${toolId}/mcp/resource-templates`, [
        ['team_id', teamId],
        ['connection_mode', connection_mode],
        ['connection_id', connection_id],
        ['max_items', maxItems],
        ['cursor', cursor],
        ['execution_id', execution_id],
      ])
    ),

  listPrompts: async (
    toolId: string,
    { teamId, connection_mode, connection_id, maxItems, cursor, execution_id }: McpListParams
  ): Promise<McpOperation<McpEnumeration<McpPrompt>>> =>
    api.get<McpOperation<McpEnumeration<McpPrompt>>>(
      queryUrl(`/tools/${toolId}/mcp/prompts`, [
        ['team_id', teamId],
        ['connection_mode', connection_mode],
        ['connection_id', connection_id],
        ['max_items', maxItems],
        ['cursor', cursor],
        ['execution_id', execution_id],
      ])
    ),

  readResource: async (
    toolId: string,
    teamId: string,
    uri: string,
    identity: McpIdentityInput = {}
  ): Promise<McpOperation<McpResourceContents[]>> =>
    api.post<McpOperation<McpResourceContents[]>>(
      queryUrl(`/tools/${toolId}/mcp/resources/read`, [['team_id', teamId]]),
      { uri, ...identity }
    ),

  subscribeResource: (
    toolId: string,
    params: McpListParams & { uri: string },
    callbacks: McpSubscribeCallbacks
  ): (() => void) => {
    const controller = new AbortController()
    const url = queryUrl(`${api.getBaseUrl()}/tools/${toolId}/mcp/resources/subscribe`, [
      ['team_id', params.teamId],
      ['uri', params.uri],
      ['connection_mode', params.connection_mode],
      ['connection_id', params.connection_id],
      ['execution_id', params.execution_id],
    ])
    const connect = async () => {
      const response = await fetch(url, {
        headers: { ...api.getAuthHeaders(), Accept: 'text/event-stream' },
        signal: controller.signal,
      })
      const contentType = response.headers.get('content-type') || ''
      if (!response.ok || !contentType.includes('text/event-stream')) {
        const payload = await response.json().catch(() => null) as McpOperation<unknown> | null
        if (payload?.status === 'pending_approval') {
          callbacks.onPendingApproval?.(payload.execution_id ?? payload.pending_approval?.execution_id ?? '')
          return
        }
        throw new Error(`mcp_subscribe_failed:${response.status}`)
      }
      const reader = response.body?.getReader()
      if (!reader) throw new Error('mcp_subscribe_failed:no_body')
      const decoder = new TextDecoder()
      let buffer = ''
      let eventType = ''
      let eventData = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            eventData = line.slice(5).trim()
          } else if (line === '' && eventData) {
            const payload = JSON.parse(eventData) as Record<string, unknown>
            if (eventType === 'subscription_opened') {
              callbacks.onOpened(payload as unknown as McpResourceSubscriptionOpened)
            } else if (eventType === 'resource_updated') {
              callbacks.onUpdated(payload as unknown as McpResourceUpdated)
            } else if (eventType === 'subscription_closed') {
              callbacks.onClosed((payload.reason as McpSubscriptionCloseReason) || 'connection_lost')
            }
            eventType = ''
            eventData = ''
          }
        }
      }
    }
    void connect().catch(() => {
      if (!controller.signal.aborted) callbacks.onClosed('connection_lost')
    })
    return () => controller.abort()
  },

  getPrompt: async (
    toolId: string,
    teamId: string,
    name: string,
    args?: Record<string, string>,
    identity: McpIdentityInput = {}
  ): Promise<McpOperation<McpPromptResult>> =>
    api.post<McpOperation<McpPromptResult>>(
      queryUrl(`/tools/${toolId}/mcp/prompts/get`, [['team_id', teamId]]),
      { name, arguments: args, ...identity }
    ),
}
