import { beforeEach, describe, expect, it, mock } from 'bun:test'

let stateSlots: unknown[] = []
let stateCursor = 0
let effectStarted = false
let getCurrentUser: () => Promise<unknown>
const getCurrentUserCalls: unknown[][] = []

mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateCursor++
    if (index === stateSlots.length) stateSlots.push(initial)
    return [stateSlots[index] as T, (value: T) => { stateSlots[index] = value }]
  },
  useEffect: (effect: () => void | (() => void)) => {
    if (!effectStarted) {
      effectStarted = true
      effect()
    }
  },
  useMemo: <T,>(factory: () => T) => factory(),
}))

mock.module('@/lib/api', () => ({
  authApi: {
    getCurrentUser: (...args: unknown[]) => {
      getCurrentUserCalls.push(args)
      return getCurrentUser()
    },
  },
}))

const { canAccessMenuItem, MENU_PERMISSION_MAP, usePermissions } = await import('./use-permissions')

function usePermissionsHarness() {
  // eslint-disable-next-line react-hooks/globals -- reset the test-only mocked hook cursor.
  stateCursor = 0
  return usePermissions()
}

function user(overrides: Record<string, unknown> = {}) {
  return {
    id: 'user-1',
    username: 'member',
    email: 'member@example.com',
    is_active: true,
    approval_status: 'approved',
    status: 'active',
    is_superuser: false,
    email_verified: true,
    avatar_url: null,
    locale: 'en',
    created_at: '2026-01-01',
    last_login: null,
    auth_source: 'local',
    external_id: null,
    force_password_change: false,
    password_expiration_exempt: false,
    roles: [],
    sso_connections: [],
    ...overrides,
  }
}

beforeEach(() => {
  stateSlots = []
  stateCursor = 0
  effectStarted = false
  getCurrentUserCalls.length = 0
})

describe('usePermissions', () => {
  it('collects role permissions and finishes loading after fetching the user', async () => {
    getCurrentUser = async () => user({
      roles: [
        { permissions: [{ code: 'admin:dashboard:access' }, { code: 'team:read' }] },
        { permissions: [{ code: 'team:read' }] },
      ],
    })

    expect(usePermissionsHarness().loading).toBe(true)
    await Promise.resolve()

    const permissions = usePermissionsHarness()
    expect(getCurrentUserCalls).toEqual([[{ skipAuthRedirect: true }]])
    expect(permissions.loading).toBe(false)
    expect(permissions.hasPermission('team:read')).toBe(true)
    expect(permissions.hasAnyPermission(['missing', 'team:read'])).toBe(true)
    expect(permissions.hasAllPermissions(['team:read', 'admin:dashboard:access'])).toBe(true)
    expect(permissions.canAccessDashboard).toBe(true)
  })

  it('grants all permissions to superusers', async () => {
    getCurrentUser = async () => user({ is_superuser: true })

    usePermissionsHarness()
    await Promise.resolve()

    const permissions = usePermissionsHarness()
    expect(permissions.isSuperuser).toBe(true)
    expect(permissions.hasPermission('any:permission')).toBe(true)
    expect(permissions.permissions).toEqual(new Set(['*']))
  })

  it('cleans up loading after a failed user request', async () => {
    getCurrentUser = async () => { throw new Error('unauthenticated') }

    usePermissionsHarness()
    await Promise.resolve()

    const permissions = usePermissionsHarness()
    expect(permissions.user).toBeNull()
    expect(permissions.loading).toBe(false)
    expect(permissions.permissions).toEqual(new Set())
    expect(permissions.hasAnyPermission(['team:read'])).toBe(false)
  })

  it('allows unmapped routes and delegates mapped routes to permission checks', () => {
    const hasPermission = mock(() => false)
    const [url, permission] = Object.entries(MENU_PERMISSION_MAP)[0]

    expect(canAccessMenuItem('/unmapped', hasPermission)).toBe(true)
    expect(hasPermission).not.toHaveBeenCalled()
    expect(canAccessMenuItem(url, hasPermission)).toBe(false)
    expect(hasPermission).toHaveBeenCalledWith(permission)
  })
})
