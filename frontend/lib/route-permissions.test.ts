import { describe, expect, test } from 'bun:test'
import {
  canAccessRoute,
  getRequiredPermissionForPath,
  getRoutePermissionConfig,
} from './route-permissions'

describe('route permissions', () => {
  test('matches exact routes and configured prefixes', () => {
    expect(getRoutePermissionConfig('/teams')?.permission).toBe('team:read')
    expect(getRoutePermissionConfig('/teams/member')).toBeNull()
    expect(getRoutePermissionConfig('/apps/agent-1')?.permission).toBe('admin:app:read')
  })

  test('uses the most specific configured route', () => {
    expect(getRequiredPermissionForPath('/site-settings/sso')).toBe('admin:sso:read')
    expect(getRequiredPermissionForPath('/site-settings/other')).toBe('admin:settings:read')
  })

  test('allows unconfigured routes and checks configured permissions', () => {
    const permissions = new Set(['admin:dashboard:access'])
    const hasPermission = (permission: string) => permissions.has(permission)

    expect(canAccessRoute('/unknown', hasPermission)).toBe(true)
    expect(canAccessRoute('/dashboard', hasPermission)).toBe(true)
    expect(canAccessRoute('/roles', hasPermission)).toBe(false)
  })
})
