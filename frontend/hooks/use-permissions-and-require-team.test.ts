import { beforeEach, describe, expect, mock, test } from 'bun:test'

let hookState: unknown[] = []
let stateIndex = 0

mock.module('react', () => ({
  useEffect: (effect: () => void) => effect(),
  useMemo: <T>(factory: () => T) => factory(),
  useState: <T>(initial: T) => {
    const index = stateIndex++
    if (!(index in hookState)) hookState[index] = initial
    return [hookState[index] as T, (value: T) => { hookState[index] = value }] as const
  },
}))

let currentUser: unknown
let userRequestError = false
const getCurrentUser = mock(async () => {
  if (userRequestError) throw new Error('unauthorized')
  return currentUser
})

mock.module('@/lib/api', () => ({ authApi: { getCurrentUser } }))

const replace = mock(() => {})
mock.module('next/navigation', () => ({ useRouter: () => ({ replace }) }))

let currentTeam: unknown = null
let isLoading = false
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam, isLoading }),
}))

const { usePermissions, canAccessMenuItem } = await import('./use-permissions')
const { useRequireTeam } = await import('./use-require-team')

function render<T>(hook: () => T): T {
  stateIndex = 0
  return hook()
}

async function settleUserRequest() {
  await Promise.resolve()
  await Promise.resolve()
}

beforeEach(() => {
  hookState = []
  stateIndex = 0
  currentUser = null
  userRequestError = false
  getCurrentUser.mockClear()
  replace.mockClear()
  currentTeam = null
  isLoading = false
})

describe('usePermissions', () => {
  test('loads role permissions and exposes permission checks', async () => {
    currentUser = {
      is_superuser: false,
      roles: [
        { permissions: [{ code: 'admin:dashboard:access' }, { code: 'user:read' }] },
        { permissions: [{ code: 'user:read' }] },
      ],
    }

    expect(render(usePermissions).loading).toBe(true)
    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
    await settleUserRequest()

    const permissions = render(usePermissions)
    expect([...permissions.permissions]).toEqual(['admin:dashboard:access', 'user:read'])
    expect(permissions.hasPermission('user:read')).toBe(true)
    expect(permissions.hasAnyPermission(['missing', 'user:read'])).toBe(true)
    expect(permissions.hasAllPermissions(['user:read', 'missing'])).toBe(false)
    expect(permissions.canAccessDashboard).toBe(true)
    expect(permissions.isSuperuser).toBe(false)
  })

  test('grants every permission to superusers', async () => {
    currentUser = { is_superuser: true, roles: [] }
    render(usePermissions)
    await settleUserRequest()

    const permissions = render(usePermissions)
    expect([...permissions.permissions]).toEqual(['*'])
    expect(permissions.hasPermission('anything')).toBe(true)
    expect(permissions.hasAllPermissions(['one', 'two'])).toBe(true)
    expect(permissions.isSuperuser).toBe(true)
  })

  test('finishes loading without permissions when the user request fails', async () => {
    userRequestError = true
    render(usePermissions)
    await settleUserRequest()

    const permissions = render(usePermissions)
    expect(permissions.loading).toBe(false)
    expect(permissions.user).toBeNull()
    expect(permissions.hasAnyPermission(['user:read'])).toBe(false)
  })

  test('allows unmapped menu items and checks mapped ones', () => {
    expect(canAccessMenuItem('/unmapped', () => false)).toBe(true)
    expect(canAccessMenuItem('/dashboard', (permission) => permission === 'admin:dashboard:access')).toBe(true)
    expect(canAccessMenuItem('/dashboard', () => false)).toBe(false)
  })
})

describe('useRequireTeam', () => {
  test('does not redirect while teams are loading', () => {
    isLoading = true

    expect(useRequireTeam()).toEqual({ currentTeam: null, isLoading: true, hasTeam: false })
    expect(replace).not.toHaveBeenCalled()
  })

  test('redirects when loading finishes without a team', () => {
    expect(useRequireTeam()).toEqual({ currentTeam: null, isLoading: false, hasTeam: false })
    expect(replace).toHaveBeenCalledWith('/app')
  })

  test('returns the selected team without redirecting', () => {
    currentTeam = { id: 'team-1', name: 'Team One' }

    expect(useRequireTeam()).toEqual({ currentTeam, isLoading: false, hasTeam: true })
    expect(replace).not.toHaveBeenCalled()
  })
})
