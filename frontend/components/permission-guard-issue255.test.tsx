import { beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act, create } from '@/test-utils/rtl-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const permissions = {
  hasPermission: mock((permission: string) => permission === 'item:read'),
  hasAnyPermission: mock((values: string[]) => values.includes('item:read')),
  hasAllPermissions: mock((values: string[]) => values.every(value => value === 'item:read')),
  loading: false,
  isSuperuser: false,
}

mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => permissions,
}))

const { PermissionGuard, useCanPerform } = await import('./permission-guard')

function Harness({ capture }: { capture: (value: ReturnType<typeof useCanPerform>) => void }) {
  capture(useCanPerform())
  return null
}

beforeEach(() => {
  permissions.loading = false
  permissions.isSuperuser = false
})

describe('PermissionGuard', () => {
  test('renders loading, single, any, all, and fallback states', () => {
    permissions.loading = true
    expect(renderToStaticMarkup(<PermissionGuard permission="item:read">allowed</PermissionGuard>)).toBe('')

    permissions.loading = false
    expect(renderToStaticMarkup(<PermissionGuard permission="item:read">allowed</PermissionGuard>)).toBe('allowed')
    expect(renderToStaticMarkup(<PermissionGuard permission="item:write" fallback="denied">allowed</PermissionGuard>)).toBe('denied')
    expect(renderToStaticMarkup(<PermissionGuard permission={['item:write', 'item:read']}>any</PermissionGuard>)).toBe('any')
    expect(renderToStaticMarkup(<PermissionGuard permission={['item:read', 'item:write']} requireAll fallback="denied">all</PermissionGuard>)).toBe('denied')
  })
})

describe('useCanPerform', () => {
  test('handles loading, superuser, single, any, and all permission checks', () => {
    let result: ReturnType<typeof useCanPerform> | undefined
    const capture = (value: ReturnType<typeof useCanPerform>) => { result = value }
    let renderer: ReturnType<typeof create>
    act(() => {
      renderer = create(<Harness capture={capture} />)
    })

    expect(result!.canPerform('item:read')).toBe(true)
    expect(result!.canPerform('item:write')).toBe(false)
    expect(result!.canPerform(['item:write', 'item:read'])).toBe(true)
    expect(result!.canPerform(['item:read', 'item:write'], true)).toBe(false)

    permissions.loading = true
    act(() => renderer!.update(<Harness capture={capture} />))
    expect(result!.loading).toBe(true)
    expect(result!.canPerform('item:read')).toBe(false)

    permissions.loading = false
    permissions.isSuperuser = true
    act(() => renderer!.update(<Harness capture={capture} />))
    expect(result!.canPerform('item:write')).toBe(true)

    act(() => renderer!.unmount())
  })
})
