import { beforeEach, describe, expect, mock, test } from 'bun:test'
import React, { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const replace = mock(() => {})
let pathname: string | null = '/dashboard'
const permissions = {
  hasPermission: mock(() => false),
  hasAnyPermission: mock(() => false),
  hasAllPermissions: mock(() => false),
  isSuperuser: false,
  loading: false,
}

mock.module('react', () => ({
  ...React,
  useEffect: (callback: () => void) => callback(),
}))
mock.module('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace }),
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => permissions,
}))
mock.module('@/lib/route-permissions', () => ({
  canAccessRoute: (_pathname: string, hasPermission: (permission: string) => boolean, isSuperuser: boolean) =>
    isSuperuser || hasPermission('route:read'),
}))

const {
  AllPermissionsGuard,
  AnyPermissionGuard,
  PermissionGuard,
  RoutePermissionGuard,
  SuperuserGuard,
} = await import('./permission-guard')

const render = (component: React.ReactNode) => renderToStaticMarkup(createElement(React.Fragment, null, component))
const child = createElement('span', null, 'allowed')
const fallback = createElement('span', null, 'denied')

beforeEach(() => {
  replace.mockClear()
  pathname = '/dashboard'
  permissions.loading = false
  permissions.isSuperuser = false
  permissions.hasPermission.mockReset()
  permissions.hasAnyPermission.mockReset()
  permissions.hasAllPermissions.mockReset()
})

describe('auth permission guards', () => {
  test('PermissionGuard executes its permission callback and render paths', () => {
    permissions.loading = true
    expect(render(createElement(PermissionGuard, { permission: 'item:read' }, child))).toBe('')

    permissions.loading = false
    permissions.hasPermission.mockReturnValueOnce(true)
    expect(render(createElement(PermissionGuard, { permission: 'item:read' }, child))).toBe('<span>allowed</span>')
    expect(permissions.hasPermission).toHaveBeenLastCalledWith('item:read')

    expect(render(createElement(PermissionGuard, { permission: 'item:read', fallback }, child))).toBe('<span>denied</span>')
    expect(render(createElement(PermissionGuard, { permission: 'item:read' }, child))).toBe('')
    expect(render(createElement(PermissionGuard, { permission: 'item:read', redirectTo: '/app' }, child))).toBe('')
    expect(replace).toHaveBeenCalledWith('/app')
  })

  test('AnyPermissionGuard executes its callback and render paths', () => {
    const values = ['item:read', 'item:write']
    permissions.hasAnyPermission.mockReturnValueOnce(true)
    expect(render(createElement(AnyPermissionGuard, { permissions: values }, child))).toBe('<span>allowed</span>')
    expect(permissions.hasAnyPermission).toHaveBeenLastCalledWith(values)

    expect(render(createElement(AnyPermissionGuard, { permissions: values, fallback }, child))).toBe('<span>denied</span>')
    expect(render(createElement(AnyPermissionGuard, { permissions: values }, child))).toBe('')
    expect(render(createElement(AnyPermissionGuard, { permissions: values, redirectTo: '/any' }, child))).toBe('')
    expect(replace).toHaveBeenCalledWith('/any')

    permissions.loading = true
    expect(render(createElement(AnyPermissionGuard, { permissions: values }, child))).toBe('')
  })

  test('AllPermissionsGuard executes its callback and render paths', () => {
    const values = ['item:read', 'item:write']
    permissions.hasAllPermissions.mockReturnValueOnce(true)
    expect(render(createElement(AllPermissionsGuard, { permissions: values }, child))).toBe('<span>allowed</span>')
    expect(permissions.hasAllPermissions).toHaveBeenLastCalledWith(values)

    expect(render(createElement(AllPermissionsGuard, { permissions: values, fallback }, child))).toBe('<span>denied</span>')
    expect(render(createElement(AllPermissionsGuard, { permissions: values }, child))).toBe('')
    expect(render(createElement(AllPermissionsGuard, { permissions: values, redirectTo: '/all' }, child))).toBe('')
    expect(replace).toHaveBeenCalledWith('/all')

    permissions.loading = true
    expect(render(createElement(AllPermissionsGuard, { permissions: values }, child))).toBe('')
  })

  test('SuperuserGuard covers loading, allowed, fallback, empty, and redirect paths', () => {
    permissions.isSuperuser = true
    expect(render(createElement(SuperuserGuard, null, child))).toBe('<span>allowed</span>')

    permissions.isSuperuser = false
    expect(render(createElement(SuperuserGuard, { fallback }, child))).toBe('<span>denied</span>')
    expect(render(createElement(SuperuserGuard, null, child))).toBe('')
    expect(render(createElement(SuperuserGuard, { redirectTo: '/superuser' }, child))).toBe('')
    expect(replace).toHaveBeenCalledWith('/superuser')

    permissions.loading = true
    expect(render(createElement(SuperuserGuard, null, child))).toBe('')
  })

  test('RoutePermissionGuard executes route callbacks and render paths', () => {
    permissions.hasPermission.mockReturnValueOnce(true)
    expect(render(createElement(RoutePermissionGuard, null, child))).toBe('<span>allowed</span>')
    expect(permissions.hasPermission).toHaveBeenLastCalledWith('route:read')

    expect(render(createElement(RoutePermissionGuard, { redirectTo: '', fallback }, child))).toBe('<span>denied</span>')
    expect(render(createElement(RoutePermissionGuard, { redirectTo: '' }, child))).toBe('')
    expect(render(createElement(RoutePermissionGuard, null, child))).toBe('')
    expect(replace).toHaveBeenCalledWith('/app')

    pathname = null
    expect(render(createElement(RoutePermissionGuard, null, child))).toBe('<span>allowed</span>')

    permissions.loading = true
    expect(render(createElement(RoutePermissionGuard, null, child))).toBe('')
  })
})
