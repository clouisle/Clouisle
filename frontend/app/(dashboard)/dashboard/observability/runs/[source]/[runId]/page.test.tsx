import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const replace = mock(() => {})
const pathname = '/dashboard/observability/runs/agent/run-private'
let allowed = false
let loading = false
const hasPermission = (permission: string) => allowed && permission === 'admin:dashboard:access'
mock.module('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace }),
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission, isSuperuser: false, loading }),
}))
mock.module('@/components/layout/header', () => ({ Header: () => <header /> }))
const mounted = mock(() => {})
mock.module('./_components/run-inspector', () => ({
  RunInspector: () => { mounted(); return <section>Execution details</section> },
}))
// Load after mock.module registration so the real guard uses the permission test seam.
const { default: Page } = await import('./page')
let renderer: ReactTestRenderer | undefined

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  replace.mockClear()
  mounted.mockClear()
  allowed = false
  loading = false
})

test('denies a direct diagnostic URL without mounting sensitive execution content', async () => {
  const page = await Page({ params: Promise.resolve({ source: 'agent', runId: 'run-private' }) })
  await act(async () => { renderer = create(page) })
  expect(renderer!.toJSON()).toBeNull()
  expect(mounted).not.toHaveBeenCalled()
  expect(replace).toHaveBeenCalledWith('/app')
})

test('waits for permissions before exposing execution content', async () => {
  loading = true
  const page = await Page({ params: Promise.resolve({ source: 'workflow', runId: 'run-private' }) })
  await act(async () => { renderer = create(page) })
  expect(renderer!.toJSON()).toBeNull()
  expect(mounted).not.toHaveBeenCalled()
  expect(replace).not.toHaveBeenCalled()

  allowed = true
  loading = false
  // A fresh route render observes the resolved permission state.
  await act(async () => { renderer!.update(await Page({ params: Promise.resolve({ source: 'workflow', runId: 'run-private' }) })) })
  expect(JSON.stringify(renderer!.toJSON())).toContain('Execution details')
  expect(replace).not.toHaveBeenCalled()
})
