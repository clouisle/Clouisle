import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const element = (tag: string) => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

const knownKeys: Record<string, true> = {
  // The drawer builds `action${log.action}` without normalizing case.
  actionlogin: true,
  operationCreate: true,
  resourceTypeWorkflowRun: true,
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => {
    const translate = (key: string) => `${namespace}.${key}`
    return Object.assign(translate, { has: (key: string) => knownKeys[key] === true })
  },
}))
mock.module('@/components/ui/sheet', () => ({
  Sheet: element('div'), SheetContent: element('section'), SheetDescription: element('p'),
  SheetHeader: element('header'), SheetTitle: element('h2'),
}))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/separator', () => ({ Separator: element('hr') }))

// The drawer is imported after the module mocks above are registered, which a
// static import cannot guarantee.
const { AuditLogDrawer } = await import('./audit-log-drawer')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function render(node: React.ReactNode) {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(node)
  })
  renderers.push(renderer)
  return JSON.stringify(renderer.toJSON())
}

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
})

describe('AuditLogDrawer', () => {
  test('renders failure details, changes, metadata, and fallbacks', () => {
    const tree = render(
      <AuditLogDrawer
        open
        onOpenChange={mock(() => {})}
        log={{
          id: 'log-1', created_at: '2026-01-02T03:04:05Z', status: 'failed', action: 'login',
          operation: 'create', username: null, user_id: null, auth_method: null,
          resource_type: 'workflow_run', resource_name: null, resource_id: null,
          ip_address: null, user_agent: null, error_message: 'denied',
          changes: { before: { role: 'user' }, after: { role: 'admin' } },
          metadata: { source: 'sso' },
        }}
      />,
    )

    expect(tree).toContain('auditLogs.statusFailed')
    expect(tree).toContain('auditLogs.actionlogin')
    expect(tree).toContain('auditLogs.operationCreate')
    expect(tree).toContain('auditLogs.resourceTypeWorkflowRun')
    expect(tree).toContain('auditLogs.system')
    expect(tree).toContain('denied')
    expect(tree).toContain('\\"role\\": \\"admin\\"')
    expect(tree).toContain('\\"source\\": \\"sso\\"')
  })

  test('renders success status and falls back for unknown or empty values', () => {
    const tree = render(
      <AuditLogDrawer
        open
        onOpenChange={mock(() => {})}
        log={{
          id: 'log-2', created_at: '2026-01-02T03:04:05Z', status: 'success', action: 'logout',
          operation: '', username: 'ada', resource_type: '', resource_name: null,
          ip_address: '127.0.0.1', changes: null, metadata: null,
        }}
      />,
    )

    expect(tree).toContain('auditLogs.statusSuccess')
    expect(tree).toContain('logout')
    expect(tree).toContain('127.0.0.1')
    expect(tree).not.toContain('auditLogs.errorMessage')
    expect(tree).not.toContain('auditLogs.metadata')
  })

  test('renders nothing without a selected log', () => {
    expect(render(<AuditLogDrawer open onOpenChange={mock(() => {})} log={null} />)).toBe('null')
  })
})
