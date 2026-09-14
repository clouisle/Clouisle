import { describe, expect, test } from 'bun:test'
import {
  canAccessRoute,
  getRequiredPermissionForPath,
  getRoutePermissionConfig,
} from './route-permissions'

describe('route permissions', () => {
  test('matches exact routes and configured prefixes', () => {
    expect(getRoutePermissionConfig('/teams')?.permission).toBe('admin:team:read')
    expect(getRoutePermissionConfig('/teams/member')).toBeNull()
    expect(getRoutePermissionConfig('/apps/agent-1')?.permission).toBe('admin:app:read')
  })

  test('fails closed for denied team routes and unmapped admin descendants', () => {
    expect(canAccessRoute('/teams', () => false)).toBe(false)
    expect(canAccessRoute('/teams/member', () => false)).toBe(false)
  })

  test('requires every backend permission used by the activities page', () => {
    expect(getRoutePermissionConfig('/activities')?.permission).toEqual([
      'admin:conversation:read',
      'workflow:read',
    ])
    expect(
      canAccessRoute('/activities', (permission) =>
        permission === 'admin:conversation:read' || permission === 'workflow:read'
      )
    ).toBe(true)
    expect(canAccessRoute('/activities', (permission) => permission === 'workflow:read')).toBe(false)
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

  test('protects the user API key route with API key read permission', () => {
    expect(getRequiredPermissionForPath('/app/api-keys')).toBe('apikey:read')

    const hasPermission = (permission: string) => permission === 'apikey:read'
    expect(canAccessRoute('/app/api-keys', hasPermission)).toBe(true)
    expect(canAccessRoute('/app/api-keys', () => false)).toBe(false)
  })
})
