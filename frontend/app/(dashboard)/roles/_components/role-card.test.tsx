import { describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => ({
    systemRole: 'System role',
    assignedUsers: 'assigned users',
  })[key] ?? key,
}))

const { RoleCard } = await import('./role-card')

function renderRoleCard(overrides: Partial<Parameters<typeof RoleCard>[0]['role']> = {}) {
  return renderToStaticMarkup(createElement(RoleCard, {
    role: {
      name: 'Editor',
      description: 'Can edit shared content',
      permissions: [],
      isSystem: false,
      users: 2,
      ...overrides,
    },
  }))
}

describe('RoleCard', () => {
  test('identifies system roles and summarizes permissions beyond the visible limit', () => {
    const html = renderRoleCard({
      isSystem: true,
      permissions: ['knowledge:read', 'knowledge:write', 'agents:run', 'models:use'],
      users: 7,
    })

    expect(html).toContain('System role')
    expect(html).toContain('knowledge:read')
    expect(html).toContain('knowledge:write')
    expect(html).toContain('agents:run')
    expect(html).toContain('+1')
    expect(html).not.toContain('models:use')
    expect(html).toContain('7 assigned users')
  })

  test('omits the system marker and overflow summary for ordinary roles with three permissions', () => {
    const html = renderRoleCard({
      permissions: ['knowledge:read', 'knowledge:write', 'agents:run'],
    })

    expect(html).not.toContain('System role')
    expect(html).not.toContain('+1')
    expect(html).toContain('knowledge:read')
    expect(html).toContain('knowledge:write')
    expect(html).toContain('agents:run')
  })
})
