import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import * as React from 'react'
import * as navigation from 'next/navigation'
import * as teamContext from '@/contexts/team-context'
import { authApi, type User } from '@/lib/api'

type EffectSlot = {
  dependencies?: readonly unknown[]
}

let states: unknown[] = []
let effects: EffectSlot[] = []
let stateIndex = 0
let effectIndex = 0

function beginRender() {
  stateIndex = 0
  effectIndex = 0
}

const router = { replace() {}, refresh() {} }

beforeEach(() => {
  states = []
  effects = []
  beginRender()

  spyOn(React, 'useState').mockImplementation(<T,>(initial: T | (() => T)) => {
    const index = stateIndex++
    if (!(index in states)) {
      states[index] = typeof initial === 'function' ? (initial as () => T)() : initial
    }
    return [states[index] as T, (value: React.SetStateAction<T>) => {
      states[index] = typeof value === 'function'
        ? (value as (current: T) => T)(states[index] as T)
        : value
    }]
  })
  spyOn(React, 'useEffect').mockImplementation((effect, dependencies) => {
    const index = effectIndex++
    const previous = effects[index]
    const changed = !previous || !dependencies || dependencies.length !== previous.dependencies?.length
      || dependencies.some((dependency, dependencyIndex) => !Object.is(dependency, previous.dependencies?.[dependencyIndex]))
    if (changed) {
      effect()
      effects[index] = { dependencies }
    }
  })
  spyOn(React, 'useMemo').mockImplementation(factory => factory())
  spyOn(navigation, 'useRouter').mockReturnValue(router)
})

afterEach(() => {
  mock.restore()
})

const { canAccessMenuItem, usePermissions } = await import('./use-permissions')
const { useRequireTeam } = await import('./use-require-team')

function render<T>(hook: () => T): T {
  beginRender()
  return hook()
}

const user = (overrides: Partial<User>): User => ({
  id: 'user-1',
  username: 'user',
  email: 'user@example.com',
  is_active: true,
  is_superuser: false,
  roles: [],
  ...overrides,
} as User)

describe('usePermissions', () => {
  test('loads and deduplicates role permissions', async () => {
    const getCurrentUser = spyOn(authApi, 'getCurrentUser').mockResolvedValue(user({
      roles: [
        { permissions: [{ code: 'admin:dashboard:access' }, { code: 'user:read' }] },
        { permissions: [{ code: 'user:read' }] },
      ],
    }) as User['roles'])

    expect(render(usePermissions).loading).toBe(true)
    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
    await Promise.resolve()
    await Promise.resolve()

    const result = render(usePermissions)
    expect([...result.permissions]).toEqual(['admin:dashboard:access', 'user:read'])
    expect(result.hasPermission('user:read')).toBe(true)
    expect(result.hasAnyPermission(['missing', 'user:read'])).toBe(true)
    expect(result.hasAllPermissions(['user:read', 'missing'])).toBe(false)
    expect(result.canAccessDashboard).toBe(true)
    expect(result.isSuperuser).toBe(false)
  })

  test('grants all permissions to superusers', async () => {
    spyOn(authApi, 'getCurrentUser').mockResolvedValue(user({ is_superuser: true }))
    render(usePermissions)
    await Promise.resolve()
    await Promise.resolve()

    const result = render(usePermissions)
    expect([...result.permissions]).toEqual(['*'])
    expect(result.hasAllPermissions(['one', 'two'])).toBe(true)
    expect(result.isSuperuser).toBe(true)
  })

  test('finishes loading without permissions after an unauthenticated request', async () => {
    spyOn(authApi, 'getCurrentUser').mockRejectedValue(new Error('unauthorized'))
    render(usePermissions)
    await Promise.resolve()
    await Promise.resolve()

    const result = render(usePermissions)
    expect(result.loading).toBe(false)
    expect(result.user).toBeNull()
    expect(result.hasAnyPermission(['user:read'])).toBe(false)
  })

  test('allows unmapped menu items and checks mapped items', () => {
    expect(canAccessMenuItem('/unmapped', () => false)).toBe(true)
    expect(canAccessMenuItem('/dashboard', permission => permission === 'admin:dashboard:access')).toBe(true)
    expect(canAccessMenuItem('/dashboard', () => false)).toBe(false)
  })
})

describe('useRequireTeam', () => {
  test('waits while teams load, then redirects when none is available', () => {
    const useTeam = spyOn(teamContext, 'useTeam')
      .mockReturnValueOnce({ currentTeam: null, teams: [], isLoading: true, setCurrentTeam() {}, refreshTeams: async () => {} })
      .mockReturnValueOnce({ currentTeam: null, teams: [], isLoading: false, setCurrentTeam() {}, refreshTeams: async () => {} })
    const replace = spyOn(router, 'replace')

    expect(render(useRequireTeam).hasTeam).toBe(false)
    expect(replace).not.toHaveBeenCalled()
    expect(render(useRequireTeam).hasTeam).toBe(false)
    expect(replace).toHaveBeenCalledWith('/app')
    expect(useTeam).toHaveBeenCalledTimes(2)
  })

  test('returns the selected team without redirecting', () => {
    const currentTeam = { id: 'team-1', name: 'Team One' }
    spyOn(teamContext, 'useTeam').mockReturnValue({
      currentTeam,
      teams: [currentTeam],
      isLoading: false,
      setCurrentTeam() {},
      refreshTeams: async () => {},
    } as ReturnType<typeof teamContext.useTeam>)
    const replace = spyOn(router, 'replace')

    expect(render(useRequireTeam)).toMatchObject({ currentTeam, isLoading: false, hasTeam: true })
    expect(replace).not.toHaveBeenCalled()
  })
})
