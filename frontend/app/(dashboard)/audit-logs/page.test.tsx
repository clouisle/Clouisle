import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const getTranslations = mock(() => Promise.resolve((key: string) => key))

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-intl/server', () => ({ getTranslations }))
mock.module('@/components/auth/permission-guard', () => ({
  RoutePermissionGuard: function RoutePermissionGuard() {},
}))
mock.module('@/components/layout/header', () => ({ Header: function Header() {} }))
mock.module('./_components/audit-logs-client', () => ({
  AuditLogsClient: function AuditLogsClient() {},
}))

const { default: AuditLogsPage, generateMetadata } = await import('./page')

test('generates audit log metadata from its translations', async () => {
  expect(await generateMetadata()).toEqual({ title: 'title', description: 'description' })
  expect(getTranslations).toHaveBeenCalledWith('auditLogs')
})

test('renders audit logs inside the permission-protected dashboard layout', () => {
  const tree = AuditLogsPage() as { props: Record<string, unknown> }
  const page = tree.props.children as { props: Record<string, unknown> }
  const [header, content] = page.props.children as Array<{ props: Record<string, unknown> }>

  expect((tree.type as Function).name).toBe('RoutePermissionGuard')
  expect(page.props.className).toBe('flex h-full flex-col')
  expect((header.type as Function).name).toBe('Header')
  expect(content.props.className).toBe('flex flex-1 flex-col gap-4 overflow-auto p-4')
  expect(((content.props.children as { type: Function }).type as Function).name).toBe(
    'AuditLogsClient',
  )
})
