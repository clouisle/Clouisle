import { api } from './client'

export interface FeishuAgentPreference {
  enabled: boolean
  is_enabled: boolean
  linked: boolean
  agent_id: string | null
  agent_name: string | null
  agent_available: boolean
}

export interface FeishuPersonalAgent {
  id: string
  name: string
  description: string
  team_name: string
}

export const feishuAgentApi = {
  config: (): Promise<FeishuAgentPreference> => api.get('/feishu-agent/config'),
  agents: (): Promise<FeishuPersonalAgent[]> => api.get('/feishu-agent/agents'),
  update: (agent_id: string | null): Promise<FeishuAgentPreference> => api.put('/feishu-agent/config', { agent_id }),
  setEnabled: (is_enabled: boolean): Promise<FeishuAgentPreference> => api.put('/feishu-agent/config', { is_enabled }),
}
