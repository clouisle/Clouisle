import { beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create } from 'react-test-renderer'

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

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = (props: Omit<React.ComponentProps<typeof PermissionGuard>, 'children'>) => {
  let renderer: ReturnType<typeof create>
  act(() => {
    renderer = create(<PermissionGuard {...props}><span>allowed</span></PermissionGuard>)
  })
  return renderer!.toJSON()
}

beforeEach(() => {
  permissions.loading = false
  permissions.hasPermission.mockReset()
  permissions.hasAnyPermission.mockReset()
  permissions.hasAllPermissions.mockReset()
})

describe('PermissionGuard', () => {
  test('renders children for a granted single permission', () => {
    permissions.hasPermission.mockReturnValue(true)

    expect(render({ permission: 'user:create' })).toMatchObject({ type: 'span', children: ['allowed'] })
    expect(permissions.hasPermission).toHaveBeenCalledWith('user:create')
  })

  test('uses the selected multi-permission check', () => {
    permissions.hasAnyPermission.mockReturnValue(true)
    expect(render({ permission: ['user:create', 'user:update'] })).toMatchObject({ type: 'span', children: ['allowed'] })
    expect(permissions.hasAnyPermission).toHaveBeenCalledWith(['user:create', 'user:update'])

    permissions.hasAllPermissions.mockReturnValue(true)
    expect(render({ permission: ['user:create', 'user:update'], requireAll: true })).toMatchObject({ type: 'span', children: ['allowed'] })
    expect(permissions.hasAllPermissions).toHaveBeenCalledWith(['user:create', 'user:update'])
  })

  test('renders a fallback when access is denied and nothing while loading', () => {
    expect(render({ permission: 'user:create', fallback: <span>denied</span> })).toMatchObject({ type: 'span', children: ['denied'] })
    expect(render({ permission: 'user:create' })).toBeNull()

    permissions.loading = true
    expect(render({ permission: 'user:create', fallback: <span>denied</span> })).toBeNull()
  })
})
