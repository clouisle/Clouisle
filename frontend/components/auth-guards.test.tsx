import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import {
  PathnameContext,
  SearchParamsContext,
} from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import * as permissionsHook from '@/hooks/use-permissions'
import { authApi } from '@/lib/api'
import { AuthGuard } from './auth-guard'
import { PermissionGuard as FlexiblePermissionGuard } from './permission-guard'
import {
  AllPermissionsGuard,
  AnyPermissionGuard,
  PermissionGuard,
  RoutePermissionGuard,
  SuperuserGuard,
} from './auth/permission-guard'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const router = {
  back: mock(() => {}),
  forward: mock(() => {}),
  refresh: mock(() => {}),
  push: mock(() => {}),
  replace: mock(() => {}),
  prefetch: mock(() => Promise.resolve()),
}

function render(component: React.ReactNode, pathname = '/dashboard', search = '') {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <AppRouterContext.Provider value={router}>
        <PathnameContext.Provider value={pathname}>
          <SearchParamsContext.Provider value={new URLSearchParams(search)}>
            {component}
          </SearchParamsContext.Provider>
        </PathnameContext.Provider>
      </AppRouterContext.Provider>,
    )
  })
  return renderer!
}

function permissionsState(
  granted: string[] = [],
  options: { loading?: boolean; isSuperuser?: boolean } = {},
): ReturnType<typeof permissionsHook.usePermissions> {
  const permissions = new Set(granted)
  const hasPermission = (permission: string) => permissions.has(permission)
  return {
    user: null,
    loading: options.loading ?? false,
    permissions,
    hasPermission,
    hasAnyPermission: values => values.some(hasPermission),
    hasAllPermissions: values => values.every(hasPermission),
    canAccessDashboard: hasPermission('admin:dashboard:access'),
    isSuperuser: options.isSuperuser ?? false,
  }
}

function usePermissions(state: ReturnType<typeof permissionsState>) {
  spyOn(permissionsHook, 'usePermissions').mockReturnValue(state)
}

const json = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())

afterEach(() => {
  mock.restore()
  Object.values(router).forEach(fn => fn.mockClear())
  delete (globalThis as { localStorage?: Storage }).localStorage
})

describe('AuthGuard', () => {
  test('renders nothing while verification is pending, then renders children', async () => {
    globalThis.localStorage = { getItem: () => 'token' } as Storage
    let verify!: () => void
    spyOn(authApi, 'getCurrentUser').mockReturnValue(new Promise(resolve => {
      verify = () => resolve({} as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    }))

    const renderer = render(<AuthGuard><span>Allowed</span></AuthGuard>)
    expect(renderer.toJSON()).toBeNull()
    expect(router.replace).not.toHaveBeenCalled()

    await act(async () => verify())
    expect(json(renderer)).toContain('Allowed')
    act(() => renderer.unmount())
  })

  test('redirects a visitor without a token to login with the current URL', () => {
    globalThis.localStorage = { getItem: () => null } as Storage
    const getCurrentUser = spyOn(authApi, 'getCurrentUser')
    const renderer = render(<AuthGuard><span>Denied</span></AuthGuard>, '/settings', 'tab=profile')

    expect(renderer.toJSON()).toBeNull()
    expect(getCurrentUser).not.toHaveBeenCalled()
    expect(router.replace).toHaveBeenCalledWith('/login?redirect=%2Fsettings%3Ftab%3Dprofile')
    act(() => renderer.unmount())
  })

  test('redirects when token verification fails', async () => {
    globalThis.localStorage = { getItem: () => 'expired' } as Storage
    spyOn(authApi, 'getCurrentUser').mockRejectedValue(new Error('unauthorized'))

    const renderer = render(<AuthGuard><span>Denied</span></AuthGuard>, '/app')
    await act(async () => Promise.resolve())

    expect(renderer.toJSON()).toBeNull()
    expect(router.replace).toHaveBeenCalledWith('/login?redirect=%2Fapp')
    act(() => renderer.unmount())
  })
})

describe('PermissionGuard', () => {
  test('handles loading, allowed, and denied fallback states', () => {
    usePermissions(permissionsState([], { loading: true }))
    const loading = render(<FlexiblePermissionGuard permission="item:read">Allowed</FlexiblePermissionGuard>)
    expect(loading.toJSON()).toBeNull()
    act(() => loading.unmount())

    usePermissions(permissionsState(['item:read']))
    const allowed = render(<FlexiblePermissionGuard permission="item:read">Allowed</FlexiblePermissionGuard>)
    expect(json(allowed)).toContain('Allowed')
    act(() => allowed.unmount())

    usePermissions(permissionsState())
    const denied = render(
      <FlexiblePermissionGuard permission="item:read" fallback={<span>Fallback</span>}>
        Allowed
      </FlexiblePermissionGuard>,
    )
    expect(json(denied)).toContain('Fallback')
    act(() => denied.unmount())
  })

  test('supports any and all permission lists', () => {
    usePermissions(permissionsState(['item:read']))
    const any = render(
      <FlexiblePermissionGuard permission={['item:read', 'item:write']}>Any</FlexiblePermissionGuard>,
    )
    expect(json(any)).toContain('Any')
    act(() => any.unmount())

    const all = render(
      <FlexiblePermissionGuard permission={['item:read', 'item:write']} requireAll fallback="Denied">
        All
      </FlexiblePermissionGuard>,
    )
    expect(json(all)).toContain('Denied')
    act(() => all.unmount())
  })
})

describe('auth permission guards', () => {
  test('single permission guard handles loading, allowed, fallback, and redirect', () => {
    usePermissions(permissionsState([], { loading: true }))
    const loading = render(<PermissionGuard permission="item:read">Allowed</PermissionGuard>)
    expect(loading.toJSON()).toBeNull()
    act(() => loading.unmount())

    usePermissions(permissionsState(['item:read']))
    const allowed = render(<PermissionGuard permission="item:read">Allowed</PermissionGuard>)
    expect(json(allowed)).toContain('Allowed')
    act(() => allowed.unmount())

    usePermissions(permissionsState())
    const fallback = render(
      <PermissionGuard permission="item:read" fallback="Fallback">Allowed</PermissionGuard>,
    )
    expect(json(fallback)).toContain('Fallback')
    act(() => fallback.unmount())

    const redirected = render(
      <PermissionGuard permission="item:read" redirectTo="/app">Allowed</PermissionGuard>,
    )
    expect(redirected.toJSON()).toBeNull()
    expect(router.replace).toHaveBeenCalledWith('/app')
    act(() => redirected.unmount())
  })

  test('any, all, and superuser guards enforce their respective access rules', () => {
    usePermissions(permissionsState(['item:read']))
    const any = render(<AnyPermissionGuard permissions={['item:read', 'item:write']}>Any</AnyPermissionGuard>)
    expect(json(any)).toContain('Any')
    act(() => any.unmount())

    const all = render(
      <AllPermissionsGuard permissions={['item:read', 'item:write']} fallback="All denied">
        All
      </AllPermissionsGuard>,
    )
    expect(json(all)).toContain('All denied')
    act(() => all.unmount())

    usePermissions(permissionsState([], { isSuperuser: true }))
    const superuser = render(<SuperuserGuard>Superuser</SuperuserGuard>)
    expect(json(superuser)).toContain('Superuser')
    act(() => superuser.unmount())
  })

  test('route guard allows permitted routes and redirects denied routes', () => {
    usePermissions(permissionsState(['admin:dashboard:access']))
    const allowed = render(<RoutePermissionGuard>Dashboard</RoutePermissionGuard>)
    expect(json(allowed)).toContain('Dashboard')
    act(() => allowed.unmount())

    usePermissions(permissionsState())
    const denied = render(<RoutePermissionGuard>Dashboard</RoutePermissionGuard>)
    expect(denied.toJSON()).toBeNull()
    expect(router.replace).toHaveBeenCalledWith('/app')
    act(() => denied.unmount())
  })
})
