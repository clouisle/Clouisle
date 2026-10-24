import React from 'react'
import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create } from '@/test-utils/rtl-renderer'

const getWebhook = mock(() => Promise.resolve({ enabled: false, url: '' }))
const list = mock(() => Promise.resolve([]))

const tabProps: Array<Record<string, unknown>> = []

mock.module('next/link', () => ({
  default: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    <a {...props}>{children}</a>,
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/lib/api/admin/integrations', () => ({
  integrationsApi: { getWebhook, list },
}))
mock.module('../_components', () => ({
  WebhookSettingsTab: (props: Record<string, unknown>) => {
    tabProps.push(props)
    return <div data-testid="webhook-tab" />
  },
}))

const { default: WebhookIntegrationPage } = await import('./page')

beforeEach(() => {
  getWebhook.mockClear()
  list.mockClear()
  tabProps.length = 0
})

describe('webhook integration page', () => {
  test('renders the webhook tab with the matching instance credentials', async () => {
    list.mockResolvedValueOnce([
      { provider_type: 'email', credentials_configured: true },
      { provider_type: 'webhook', credentials_configured: false },
    ])
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(<WebhookIntegrationPage />)
    })
    await act(async () => {})

    expect(renderer.root.findByProps({ 'data-testid': 'webhook-tab' })).toBeDefined()
    expect(tabProps[0].settings).toEqual({ enabled: false, url: '' })
    // The email instance must not supply the webhook's credentials state.
    expect(tabProps[0].credentialsConfigured).toBe(false)
  })

  test('stays on the loading label when a provider instance is missing', async () => {
    list.mockResolvedValueOnce([{ provider_type: 'email', credentials_configured: true }])
    act(() => {
      create(<WebhookIntegrationPage />)
    })
    await act(async () => {})

    expect(tabProps).toHaveLength(1)
    expect(tabProps[0].credentialsConfigured).toBeUndefined()
  })
})
