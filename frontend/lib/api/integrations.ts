export type IntegrationCapability = 'user_login' | 'directory_sync' | 'notification' | 'agent_chat' | 'knowledge_collection'
export type IntegrationProviderType = 'oauth2' | 'oidc' | 'saml2' | 'cas' | 'email' | 'webhook' | 'feishu' | 'wechat'

export interface IntegrationLoginConfig {
  allow_signup: boolean
  require_approval: boolean
  default_role_id: string | null
}

export interface IntegrationLoginPublic {
  id: string
  name: string
  display_name: string
  icon_url: string | null
  button_text: string | null
  provider_type: IntegrationProviderType
}

export function getIntegrationIconUrl(
  providerType: IntegrationProviderType,
  iconUrl: string | null,
): string | null {
  return iconUrl || (providerType === 'feishu' ? '/integrations/feishu.png' : null)
}

export interface Integration extends IntegrationLoginPublic {
  is_enabled: boolean
  enabled_capabilities: IntegrationCapability[]
  supported_capabilities: IntegrationCapability[]
  config: Record<string, unknown>
  credentials_configured: string[]
  attribute_mapping: Record<string, string>
  login_config: IntegrationLoginConfig
  created_at: string
  updated_at: string
}

export interface IntegrationCreate {
  name: string
  provider_type: IntegrationProviderType
  display_name: string
  icon_url?: string | null
  button_text?: string | null
  is_enabled?: boolean
  enabled_capabilities: IntegrationCapability[]
  config: Record<string, unknown>
  credentials?: Record<string, string>
  attribute_mapping?: Record<string, string>
  login_config?: IntegrationLoginConfig
}

export type IntegrationUpdate = Partial<IntegrationCreate>

export interface IntegrationType {
  provider_type: IntegrationProviderType
  display_name: string
  supported_capabilities: IntegrationCapability[]
  singleton: boolean
}

export interface LoginSettings {
  sso_enabled: boolean
  sso_allow_password_login: boolean
  sso_auto_create_users: boolean
  sso_require_approval: boolean
  sso_match_by_email: boolean
}
