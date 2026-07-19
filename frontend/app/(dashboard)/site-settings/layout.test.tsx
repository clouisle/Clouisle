import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const hasPermission = (permission: string) => permission === 'settings:read'

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next/link', () => ({ default: function Link() {} }))
mock.module('next/navigation', () => ({ usePathname: () => '/site-settings/security' }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => `siteSettings.${key}` }))
mock.module('@/components/auth/permission-guard', () => ({
  RoutePermissionGuard: function RoutePermissionGuard() {},
}))
mock.module('@/components/layout/header', () => ({ Header: function Header() {} }))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission, isSuperuser: false }),
}))
mock.module('@/lib/route-permissions', () => ({
  SITE_SETTINGS_NAV_ITEMS: [
    {
      path: '/site-settings/security',
      translationKey: 'security',
      descriptionKey: 'securityDescription',
    },
    { path: '/site-settings/sso', translationKey: 'sso', descriptionKey: 'ssoDescription' },
    {
      path: '/site-settings/root',
      translationKey: 'root',
      descriptionKey: 'rootDescription',
      requiresSuperuser: true,
    },
  ],
  getRoutePermissionConfig: (path: string) =>
    path === '/site-settings/sso' ? { permission: 'settings:write' } : undefined,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: string[]) => values.filter(Boolean).join(' '),
}))

const { default: SiteSettingsLayout } = await import('./layout')

test('filters settings navigation by permission and marks the active route', () => {
  const tree = SiteSettingsLayout({ children: 'settings content' }) as {
    props: Record<string, unknown>
  }
  const page = tree.props.children as { props: Record<string, unknown> }
  const content = (page.props.children as Array<{ props: Record<string, unknown> }>)[1]
  const main = content.props.children as Array<{ props: Record<string, unknown> }>
  const layout = main[1]
  const navWrapper = (layout.props.children as Array<{ props: Record<string, unknown> }>)[0]
  const nav = navWrapper.props.children as { props: Record<string, unknown> }
  const links = nav.props.children as Array<{ props: Record<string, unknown> }>

  expect(links).toHaveLength(1)
  expect(links[0].props).toMatchObject({
    href: '/site-settings/security',
    className:
      'px-4 py-2 text-sm rounded-md whitespace-nowrap transition-colors bg-muted font-medium',
    children: 'siteSettings.security',
  })
})
