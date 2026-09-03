import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer, type ReactTestInstance } from '@/test-utils/rtl-renderer'

const getCurrentUser = mock(() => Promise.resolve({
  username: 'Alice Smith',
  email: 'alice@example.com',
  avatar_url: null,
}))
const logout = mock(() => Promise.resolve())
const push = mock(() => {})
const toastSuccess = mock(() => {})
const removeItem = mock(() => {})
let pathname = '/knowledge-bases/detail'
let allowedPermissions = new Set(['teams:read', 'knowledge_bases:read'])
let canAccessDashboard = false

mock.module('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push }),
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}))
mock.module('next/image', () => ({
  default: ({ alt = '', ...props }: React.ComponentProps<'img'>) => <img alt={alt} {...props} />,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({ authApi: { getCurrentUser, logout } }))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({
    hasPermission: (permission: string) => allowedPermissions.has(permission),
    canAccessDashboard,
  }),
}))
mock.module('@/lib/route-permissions', () => ({
  ROUTE_PERMISSION_MAP: {
    '/dashboard': 'dashboard:read',
    '/teams': 'teams:read',
    '/knowledge-bases': 'knowledge_bases:read',
    '/activities': 'activities:read',
    '/users': 'users:read',
    '/roles': 'roles:read',
    '/permissions': 'permissions:read',
    '/models': 'models:read',
    '/apps': 'apps:read',
    '/capabilities': 'capabilities:read',
    '/api-keys': 'api_keys:read',
    '/memories': 'memories:read',
    '/dashboard/observability': 'observability:read',
    '/notifications': 'notifications:read',
    '/audit-logs': 'audit_logs:read',
    '/site-settings': 'settings:read',
  },
}))
mock.module('@/contexts/site-settings-context', () => ({
  useSiteSettings: () => ({ settings: { site_name: 'Test Site', site_icon: '', theme_branding_display: 'both' } }),
}))
mock.module('@/lib/theme-config', () => ({
  getBrandingVisibility: () => ({ showIcon: true, showName: true }),
}))
mock.module('@/components/default-site-icon', () => ({ DefaultSiteIcon: () => <svg /> }))
mock.module('@/components/settings-dialog', () => ({
  SettingsDialog: ({ open }: { open: boolean }) => <div data-settings-open={open} />,
}))
mock.module('@/components/ui/avatar', () => ({
  Avatar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AvatarFallback: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  AvatarImage: ({ alt = '', ...props }: React.ComponentProps<'img'>) => <img alt={alt} {...props} />,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ render }: { render: (props: object) => React.ReactNode }) => render({}),
}))

const container = (tag: string) => {
  function TestContainer({ children, ...props }: { children?: React.ReactNode }) {
    return React.createElement(tag, props, children)
  }
  return TestContainer
}
mock.module('@/components/ui/sidebar', () => ({
  Sidebar: container('aside'),
  SidebarContent: container('main'),
  SidebarFooter: container('footer'),
  SidebarGroup: container('section'),
  SidebarGroupContent: container('div'),
  SidebarGroupLabel: container('h2'),
  SidebarHeader: container('header'),
  SidebarMenu: container('ul'),
  SidebarMenuButton: ({ children, isActive, ...props }: { children: React.ReactNode; isActive?: boolean }) => <button data-active={isActive} {...props}>{children}</button>,
  SidebarMenuItem: container('li'),
}))
const Icon = () => <svg />
mock.module('lucide-react', () => ({
  Activity: Icon, AppWindow: Icon, Bell: Icon, Bot: Icon, Brain: Icon, ChevronUp: Icon,
  Database: Icon, FileText: Icon, HelpCircle: Icon, Key: Icon, KeyRound: Icon,
  LayoutDashboard: Icon, LogOut: Icon, Settings: Icon, Shield: Icon, User: Icon,
  Users: Icon, UsersRound: Icon, Wrench: Icon,
}))

const { AppSidebar } = await import('./app-sidebar')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

async function renderSidebar() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AppSidebar />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

function buttonWithText(renderer: ReactTestRenderer, text: string): ReactTestInstance {
  return renderer.root.findAllByType('button').find((button) =>
    button.findAll((node) => node.children.includes(text)).length > 0
  )!
}

beforeEach(() => {
  pathname = '/knowledge-bases/detail'
  allowedPermissions = new Set(['teams:read', 'knowledge_bases:read'])
  canAccessDashboard = false
  getCurrentUser.mockClear()
  logout.mockReset()
  logout.mockResolvedValue(undefined)
  push.mockClear()
  toastSuccess.mockClear()
  removeItem.mockClear()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { removeItem } })
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('AppSidebar', () => {
  test('shows permitted navigation and marks the current nested route active', async () => {
    const renderer = await renderSidebar()
    const output = JSON.stringify(renderer.toJSON())

    expect(output).toContain('teams')
    expect(output).toContain('knowledgeBases')
    expect(output).toContain('helpCenter')
    expect(output).not.toContain('activities')
    expect(output).not.toContain('users')
    expect(renderer.root.findByProps({ href: '/knowledge-bases' }).findByProps({ 'data-active': true })).toBeTruthy()
  })

  test('loads the user and opens profile settings', async () => {
    const renderer = await renderSidebar()

    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
    expect(JSON.stringify(renderer.toJSON())).toContain('alice@example.com')
    expect(JSON.stringify(renderer.toJSON())).toContain('AS')

    act(() => buttonWithText(renderer, 'profile').props.onClick())
    expect(renderer.root.findByProps({ 'data-settings-open': true })).toBeTruthy()
    expect(renderer.root.findByProps({ href: '/app' })).toBeTruthy()
  })

  test('clears the client session and redirects when server logout fails', async () => {
    logout.mockRejectedValueOnce(new Error('unavailable'))
    const renderer = await renderSidebar()

    await act(async () => buttonWithText(renderer, 'logout').props.onClick())

    expect(removeItem).toHaveBeenCalledWith('access_token')
    expect(toastSuccess).toHaveBeenCalledWith('logoutSuccess')
    expect(push).toHaveBeenCalledWith('/login')
  })
})
