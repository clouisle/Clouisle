import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const push = mock(() => {})
const canAccessRoute = mock((path: string) => path !== '/users')
let pathname = '/dashboard'

const iconNames = [
  'Activity', 'BarChart3', 'Bell', 'Bot', 'Brain', 'Database', 'FileText', 'Key',
  'KeyRound', 'LayoutDashboard', 'Palette', 'Search', 'Settings', 'Shield', 'Users',
  'UsersRound', 'Wrench',
]

mock.module('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push }),
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => Object.assign(
    (key: string) => `${namespace}.${key}`,
    { has: (key: string) => key !== 'missing' },
  ),
}))
mock.module('lucide-react', () => Object.fromEntries(
  iconNames.map((name) => [name, (props: Record<string, unknown>) => <i data-icon={name} {...props} />]),
))
mock.module('@/components/ui/sidebar', () => ({
  SidebarTrigger: (props: Record<string, unknown>) => <button {...props} />,
}))
mock.module('@/components/ui/separator', () => ({
  Separator: (props: Record<string, unknown>) => <hr {...props} />,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))
mock.module('@/components/settings-drawer', () => ({
  SettingsDrawer: (props: { open: boolean; onOpenChange: (open: boolean) => void }) => (
    <aside data-open={String(props.open)}>
      <button onClick={() => props.onOpenChange(false)}>close settings</button>
    </aside>
  ),
}))
mock.module('@/lib/route-permissions', () => ({ canAccessRoute }))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true, isSuperuser: false }),
}))

const { Header } = await import('./header')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer

beforeEach(() => {
  pathname = '/dashboard'
  push.mockClear()
  canAccessRoute.mockClear()
  canAccessRoute.mockImplementation((path: string) => path !== '/users')
  act(() => { renderer = create(<Header />) })
})

afterEach(() => act(() => renderer.unmount()))

function searchInput() {
  return renderer.root.findByType('input')
}

function changeSearch(value: string) {
  act(() => searchInput().props.onChange({ target: { value } }))
}

describe('Header', () => {
  test('filters accessible dashboard destinations and preserves route parameters on selection', () => {
    changeSearch('skills')

    const results = renderer.root.findAllByType('button').filter((button) =>
      button.findAll((node) => node.type === 'span' && node.children.includes('/capabilities?tab=skills')).length > 0,
    )
    expect(results).toHaveLength(1)
    expect(canAccessRoute).toHaveBeenCalledWith('/capabilities', expect.any(Function), false)
    expect(JSON.stringify(renderer.toJSON())).not.toContain('/users')

    const preventDefault = mock(() => {})
    results[0].props.onMouseDown({ preventDefault })
    expect(preventDefault).toHaveBeenCalledTimes(1)
    act(() => results[0].props.onClick())

    expect(push).toHaveBeenCalledWith('/capabilities?tab=skills&search=skills')
    expect(JSON.stringify(renderer.toJSON())).not.toContain('/capabilities?tab=skills')
  })

  test('Enter searches the current dashboard section before the first matching destination', () => {
    act(() => renderer.unmount())
    pathname = '/activities'
    act(() => { renderer = create(<Header />) })
    changeSearch('failed')

    act(() => searchInput().props.onKeyDown({ key: 'Escape' }))
    expect(push).not.toHaveBeenCalled()
    act(() => searchInput().props.onKeyDown({ key: 'Enter' }))

    expect(push).toHaveBeenCalledWith('/activities?search=failed')
  })

  test('shows an empty result state and closes suggestions only when focus leaves search', () => {
    changeSearch('destination-that-does-not-exist')
    expect(JSON.stringify(renderer.toJSON())).toContain('common.noResults')

    const searchContainer = renderer.root.find((node) => typeof node.props.onBlur === 'function')
    act(() => searchContainer.props.onBlur({
      currentTarget: { contains: () => true },
      relatedTarget: {},
    }))
    expect(JSON.stringify(renderer.toJSON())).toContain('common.noResults')

    act(() => searchContainer.props.onBlur({
      currentTarget: { contains: () => false },
      relatedTarget: null,
    }))
    expect(JSON.stringify(renderer.toJSON())).not.toContain('common.noResults')
    expect(push).not.toHaveBeenCalled()
  })

  test('ignores blank searches and controls the appearance settings drawer', () => {
    changeSearch('   ')
    act(() => searchInput().props.onKeyDown({ key: 'Enter' }))
    expect(push).not.toHaveBeenCalled()

    const settingsButton = renderer.root.findByProps({ 'aria-label': 'common.appearanceSettings' })
    act(() => settingsButton.props.onClick())
    expect(renderer.root.findByType('aside').props['data-open']).toBe('true')
    act(() => renderer.root.findByProps({ children: 'close settings' }).props.onClick())
    expect(renderer.root.findByType('aside').props['data-open']).toBe('false')
  })
})
