import { describe, expect, test } from 'bun:test'

import { EmailSettingsTab, FeishuIntegrationTab, FeishuKnowledgeSync, WebhookSettingsTab } from './index'
import { EmailSettingsTab as EmailSettingsTabDirect } from './email-settings'
import { FeishuIntegrationTab as FeishuIntegrationTabDirect } from './feishu-integration'
import { FeishuKnowledgeSync as FeishuKnowledgeSyncDirect } from './feishu-knowledge-sync'
import { WebhookSettingsTab as WebhookSettingsTabDirect } from './webhook-settings'

describe('integration settings barrel', () => {
  test('re-exports the implemented components rather than copies', () => {
    expect(EmailSettingsTab).toBe(EmailSettingsTabDirect)
    expect(FeishuIntegrationTab).toBe(FeishuIntegrationTabDirect)
    expect(FeishuKnowledgeSync).toBe(FeishuKnowledgeSyncDirect)
    expect(WebhookSettingsTab).toBe(WebhookSettingsTabDirect)
  })
})
