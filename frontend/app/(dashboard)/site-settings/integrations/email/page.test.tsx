import React from 'react'
import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create } from '@/test-utils/rtl-renderer'

const getEmail = mock(() => Promise.resolve({ enabled: true, host: 'smtp.test' }))
const list = mock(() => Promise.resolve([]))
let canUpdate = true

const tabProps: Array<Record<string, unknown>> = []

mock.module('next/link', () => ({
  default: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    <a {...props}>{children}</a>,
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))
mock.module('@/lib/api/admin/integrations', () => ({
  integrationsApi: { getEmail, list },
}))
mock.module('../_components', () => ({
  EmailSettingsTab: (props: Record<string, unknown>) => {
    tabProps.push(props)
    return <div data-testid="email-tab" />
  },
}))

const { default: EmailIntegrationPage } = await import('./page')

beforeEach(() => {
  getEmail.mockClear()
  list.mockClear()
  tabProps.length = 0
  canUpdate = true
})

describe('email integration page', () => {
  test('shows the loading label until email settings arrive, then passes them to the tab', async () => {
    list.mockResolvedValueOnce([
      { provider_type: 'email', credentials_configured: true },
      { provider_type: 'webhook', credentials_configured: false },
    ])
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(<EmailIntegrationPage />)
    })

    expect(renderer.root.findAllByType('p')).toHaveLength(1)

    await act(async () => {})

    expect(getEmail.mock.calls).toHaveLength(1)
    expect(list.mock.calls).toHaveLength(1)
    const tab = renderer.root.findByProps({ 'data-testid': 'email-tab' })
    expect(tab).toBeDefined()
    expect(tabProps).toHaveLength(1)
    expect(tabProps[0].settings).toEqual({ enabled: true, host: 'smtp.test' })
    // Only the matching provider instance decides whether credentials exist.
    expect(tabProps[0].credentialsConfigured).toBe(true)
    expect(tabProps[0].canUpdate).toBe(true)
  })

  test('keeps the loading label and reports no credentials when the fetch fails', async () => {
    list.mockRejectedValueOnce(new Error('backend down'))
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(<EmailIntegrationPage />)
    })
    await act(async () => {})

    expect(renderer.root.findAllByProps({ 'data-testid': 'email-tab' })).toHaveLength(0)
    expect(renderer.root.findAllByType('p')).toHaveLength(1)
  })

  test('withholds the update capability when the viewer cannot change settings', async () => {
    canUpdate = false
    list.mockResolvedValueOnce([{ provider_type: 'email', credentials_configured: false }])
    let renderer!: ReturnType<typeof create>
    act(() => {
      renderer = create(<EmailIntegrationPage />)
    })
    await act(async () => {})

    expect(tabProps[0].canUpdate).toBe(false)
    expect(tabProps[0].credentialsConfigured).toBe(false)
    expect(renderer.root.findByProps({ 'data-testid': 'email-tab' })).toBeDefined()
  })
})
