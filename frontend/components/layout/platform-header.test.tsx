import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const push = mock(() => {})
const logout = mock(async () => {})
const getCurrentUser = mock(async () => ({
  username: 'Ada Lovelace',
  email: 'ada@example.com',
  avatar_url: null,
}))
const unreadCount = mock(async () => ({ total: 105 }))
const removeItem = mock(() => {})
const toastSuccess = mock(() => {})
const requestPermission = mock(async () => 'granted')
const startTour = mock(() => {})

let canAccessDashboard = false
let canAccessCapabilities = false
let currentTeam: { id: string } | null = { id: 'team-1' }
let headerVariant: 'default' | 'centered' | 'minimal' = 'centered'
let onboarding: { isTourCompleted: (tourId: string) => boolean; startTour: (tourId: string) => void } | null = null
const tourConfigs: Array<{ id: string; title: string; showInPlatformMenu?: boolean }> = []

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))

mock.module('next/navigation', () => ({
  usePathname: () => '/app/apps',
  useRouter: () => ({ push }),
}))

mock.module('next/link', () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href?.toString()} {...props}>{children}</a>
  ),
}))

mock.module('next/image', () => ({
  default: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ''} />,
}))

mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  authApi: { getCurrentUser, logout },
  notificationsApi: { unreadCount },
}))
mock.module('@/contexts/site-settings-context', () => ({
  useSiteSettings: () => ({
    settings: {
      site_name: 'Test Site',
      site_icon: '',
      theme_branding_display: 'icon_and_name',
    },
  }),
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({
    canAccessDashboard,
    hasAnyPermission: () => canAccessCapabilities,
  }),
}))
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam, isLoading: false }),
}))
mock.module('@/hooks/use-settings', () => ({
  useSettings: () => ({ platformHeaderVariant: headerVariant, mounted: true }),
}))
mock.module('@/components/onboarding/onboarding-provider', () => ({
  useOptionalOnboarding: () => onboarding,
}))
mock.module('@/components/onboarding/steps/platform-steps', () => ({ allTourConfigs: tourConfigs }))
mock.module('@/lib/theme-config', () => ({
  getBrandingVisibility: () => ({ showIcon: true, showName: true }),
}))
mock.module('@/components/default-site-icon', () => ({
  DefaultSiteIcon: () => <span>site-icon</span>,
}))
mock.module('@/components/team-switcher', () => ({
  TeamSwitcher: () => <span>team-switcher</span>,
}))
mock.module('@/components/settings-drawer', () => ({
  SettingsDrawer: ({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) => (
    <button data-settings-open={open} onClick={() => onOpenChange(false)} />
  ),
}))
mock.module('@/components/settings-dialog', () => ({
  SettingsDialog: ({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) => (
    <button data-profile-open={open} onClick={() => onOpenChange(false)} />
  ),
}))
mock.module('@/components/ui/avatar', () => ({
  Avatar: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  AvatarFallback: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  AvatarImage: (props: React.ImgHTMLAttributes<HTMLImageElement>) => <img {...props} alt={props.alt ?? ''} />,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string; size?: string }) => {
    delete props.variant
    delete props.size
    return <button {...props}>{children}</button>
  },
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render }: { render: React.ReactElement }) => render,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ render }: { render: (props: object) => React.ReactNode }) => <>{render({})}</>,
  DropdownMenuSub: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuSubTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  DropdownMenuSubContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

import { PlatformHeader } from './platform-header'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

async function renderHeader() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<PlatformHeader />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

beforeEach(() => {
  canAccessDashboard = false
  canAccessCapabilities = false
  currentTeam = { id: 'team-1' }
  headerVariant = 'centered'
  push.mockClear()
  logout.mockClear()
  getCurrentUser.mockClear()
  unreadCount.mockClear()
  removeItem.mockClear()
  toastSuccess.mockClear()
  requestPermission.mockClear()
  onboarding = null
  tourConfigs.splice(0)
  startTour.mockClear()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: { removeItem },
  })
  const notification = { permission: 'default', requestPermission }
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { location: { origin: 'https://example.com' }, focus: mock(() => {}), Notification: notification },
  })
  Object.defineProperty(globalThis, 'Notification', {
    configurable: true,
    value: notification,
  })
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('PlatformHeader', () => {
  test('filters permission-gated navigation and applies the minimal variant', async () => {
    headerVariant = 'minimal'
    const renderer = await renderHeader()

    expect(renderer.root.findAllByProps({ 'data-testid': 'nav-capabilities' })).toHaveLength(0)
    expect(renderer.root.findByProps({ 'data-testid': 'nav-apps' }).props.href).toBe('/app/apps')
    expect(renderer.root.findByProps({ 'data-testid': 'platform-header-nav' }).props.className).not.toContain('left-1/2')
    expect(JSON.stringify(renderer.toJSON())).not.toContain('nav.apps')

    canAccessCapabilities = true
    canAccessDashboard = true
    await act(async () => renderer.update(<PlatformHeader />))

    expect(renderer.root.findByProps({ 'data-testid': 'nav-capabilities' }).props.href).toBe('/app/capabilities')
    expect(renderer.root.findByProps({ 'data-testid': 'user-menu-admin' })).toBeTruthy()
  })

  test('shows unread notifications and requests permission before navigating', async () => {
    const renderer = await renderHeader()

    expect(unreadCount).toHaveBeenCalledWith({ silent: true, skipAuthRedirect: true })
    expect(renderer.root.findByProps({ 'data-testid': 'platform-user-menu' }).findAllByType('span').some((node) => node.children.includes('99+'))).toBe(true)

    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-notifications' }).props.onClick())

    expect(requestPermission).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/app/notifications')
  })

  test('clears local authentication and redirects even when server logout fails', async () => {
    logout.mockRejectedValueOnce(new Error('offline'))
    const renderer = await renderHeader()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-logout' }).props.onClick())

    expect(removeItem).toHaveBeenCalledWith('access_token')
    expect(toastSuccess).toHaveBeenCalledWith('logoutSuccess')
    expect(push).toHaveBeenCalledWith('/login')
  })

  test('opens and closes theme and profile settings', async () => {
    const renderer = await renderHeader()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'platform-theme-button' }).props.onClick())
    const settingsDrawer = renderer.root.findByProps({ 'data-settings-open': true })
    await act(async () => settingsDrawer.props.onClick())
    expect(renderer.root.findByProps({ 'data-settings-open': false })).toBeTruthy()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-settings' }).props.onClick())
    const profileDialog = renderer.root.findByProps({ 'data-profile-open': true })
    await act(async () => profileDialog.props.onClick())
    expect(renderer.root.findByProps({ 'data-profile-open': false })).toBeTruthy()
  })

  test('runs user navigation callbacks', async () => {
    const renderer = await renderHeader()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-api-keys' }).props.onClick())
    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-memories' }).props.onClick())
    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-about' }).props.onClick())

    expect(push).toHaveBeenNthCalledWith(1, '/app/api-keys')
    expect(push).toHaveBeenNthCalledWith(2, '/app/memories')
  })

  test('toggles and closes mobile navigation', async () => {
    const renderer = await renderHeader()
    const toggle = renderer.root.findAllByType('button').find((node) => node.children.some((child) =>
      typeof child === 'object' && child !== null && 'children' in child && child.children.includes('menu')
    ))!

    await act(async () => toggle.props.onClick())
    const mobileNav = renderer.root.findAllByType('nav')[1]
    expect(mobileNav).toBeTruthy()

    await act(async () => mobileNav.findAllByType('a')[0].props.onClick())
    expect(renderer.root.findAllByType('nav')).toHaveLength(1)
  })

  test('skips notification permission when the browser already decided', async () => {
    Object.defineProperty(globalThis.Notification, 'permission', { configurable: true, value: 'denied' })
    const renderer = await renderHeader()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'user-menu-notifications' }).props.onClick())

    expect(requestPermission).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/app/notifications')
  })

  test('hides team navigation when no team is available', async () => {
    currentTeam = null
    const renderer = await renderHeader()

    expect(renderer.root.findAllByProps({ 'data-testid': 'platform-header-nav' })).toHaveLength(0)
    expect(renderer.root.findAllByProps({ 'data-testid': 'platform-team-switcher' })).toHaveLength(0)
    expect(renderer.root.findByProps({ 'data-testid': 'platform-user-menu' })).toBeTruthy()
  })

  test('excludes dashboard-scoped tours from the platform menu', async () => {
    onboarding = { isTourCompleted: () => false, startTour }
    tourConfigs.push(
      { id: 'models', title: 'onboarding.tourModelsTitle' },
      { id: 'adminModelSetup', title: 'onboarding.tourAdminModelSetupTitle', showInPlatformMenu: false },
    )
    const renderer = await renderHeader()

    expect(renderer.root.findByProps({ 'data-testid': 'user-menu-tours' })).toBeTruthy()
    const tourLabels = renderer.root.findAllByType('button').flatMap(button => button.children)
    expect(tourLabels).toContain('tourModelsTitle')
    expect(tourLabels).not.toContain('tourAdminModelSetupTitle')
  })
})
