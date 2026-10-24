import { describe, expect, test } from 'bun:test'
import { getIntegrationIconUrl } from './integrations'

describe('getIntegrationIconUrl', () => {
  test('preserves a configured provider icon', () => {
    expect(getIntegrationIconUrl('feishu', 'https://cdn.example/feishu.svg')).toBe(
      'https://cdn.example/feishu.svg',
    )
  })

  test('uses the bundled Feishu icon when no custom icon is configured', () => {
    expect(getIntegrationIconUrl('feishu', null)).toBe('/integrations/feishu.png')
  })

  test('does not invent icons for other providers', () => {
    expect(getIntegrationIconUrl('oidc', null)).toBeNull()
  })
})
