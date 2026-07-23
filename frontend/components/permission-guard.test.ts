import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const permissions = {
  hasPermission: mock(() => false),
  hasAnyPermission: mock(() => false),
  hasAllPermissions: mock(() => false),
  loading: false,
}

mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => permissions,
}))

const { PermissionGuard } = await import('./permission-guard')

const guard = (fallback?: ReturnType<typeof createElement>) =>
  createElement(PermissionGuard, { permission: 'user:create', fallback }, createElement('span', null, 'allowed'))

beforeEach(() => {
  permissions.loading = false
  permissions.hasPermission.mockReset()
  permissions.hasAnyPermission.mockReset()
  permissions.hasAllPermissions.mockReset()
})

describe('PermissionGuard', () => {
  test('renders children when the required permission is granted', () => {
    permissions.hasPermission.mockReturnValue(true)

    expect(renderToStaticMarkup(guard())).toBe('<span>allowed</span>')
  })

  test('renders the fallback when permission is denied', () => {
    expect(renderToStaticMarkup(guard(createElement('span', null, 'denied')))).toBe('<span>denied</span>')
  })

  test('renders nothing while permissions are loading', () => {
    permissions.loading = true

    expect(renderToStaticMarkup(guard(createElement('span', null, 'denied')))).toBe('')
  })
})
