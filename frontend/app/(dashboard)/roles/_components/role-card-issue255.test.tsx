import { describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

const { RoleCard, RoleGrid } = await import('./role-card')

const role = {
  name: 'Administrator',
  description: 'Full access',
  permissions: ['users.read', 'users.write', 'roles.read', 'roles.write'],
  isSystem: true,
  users: 3,
}

function text(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return text((node as ReactElement<{ children?: ReactNode }>).props.children)
  }
  return ''
}

describe('RoleCard', () => {
  test('renders system and overflow branches and forwards clicks', () => {
    const onClick = mock(() => {})
    const card = RoleCard({ role, onClick })

    expect(text(card)).toContain('Administrator')
    expect(text(card)).toContain('Full access')
    expect(text(card)).toContain('systemRole')
    expect(text(card)).toContain('users.read')
    expect(text(card)).toContain('+1')
    expect(text(card)).toContain('3 assignedUsers')

    card.props.onClick?.()
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  test('omits system and overflow badges when they do not apply', () => {
    const card = RoleCard({
      role: { ...role, permissions: ['users.read'], isSystem: false },
    })

    expect(text(card)).not.toContain('systemRole')
    expect(text(card)).not.toContain('+1')
  })
})

describe('RoleGrid', () => {
  test('passes the clicked role to the callback', () => {
    const onRoleClick = mock(() => {})
    const grid = RoleGrid({ roles: [role], onRoleClick })
    const card = grid.props.children[0] as ReactElement<{ onClick: () => void }>

    card.props.onClick()
    expect(onRoleClick).toHaveBeenCalledWith(role)
  })

  test('allows clicks when no callback is provided', () => {
    const grid = RoleGrid({ roles: [role] })
    const card = grid.props.children[0] as ReactElement<{ onClick: () => void }>

    expect(() => card.props.onClick()).not.toThrow()
  })
})
