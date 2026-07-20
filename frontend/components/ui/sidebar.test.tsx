import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let sidebarContext: Record<string, unknown> | null = null
let keydownHandler: ((event: Record<string, unknown>) => void) | undefined
const stateUpdates: unknown[] = []
const toggleSidebar = mock(() => {})
const setOpenMobile = mock(() => {})

function Provider() {}
function Sheet() {}
function SheetContent() {}
function SheetHeader() {}
function SheetTitle() {}
function SheetDescription() {}
function Button() {}
function Input() {}
function Separator() {}
function Skeleton() {}
function Tooltip() {}
function TooltipContent() {}
function TooltipTrigger() {}
function PanelLeftIcon() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  createContext: () => ({ Provider }),
  useContext: () => sidebarContext,
  useState: (value: unknown) => [typeof value === 'function' ? value() : value, (next: unknown) => stateUpdates.push(next)],
  useCallback: (callback: unknown) => callback,
  useMemo: (factory: () => unknown) => factory(),
  useEffect: (effect: () => void | (() => void)) => effect(),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@base-ui/react/merge-props', () => ({ mergeProps: (...props: Record<string, unknown>[]) => Object.assign({}, ...props) }))
mock.module('@base-ui/react/use-render', () => ({
  useRender: ({ defaultTagName, props, render, state }: Record<string, unknown>) => jsx(render ?? defaultTagName, { ...props as Record<string, unknown>, ...Object.fromEntries(Object.entries(state as Record<string, unknown>).map(([key, value]) => [`data-${key}`, value])) }),
}))
mock.module('class-variance-authority', () => ({ cva: (base: string) => () => base }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/separator', () => ({ Separator }))
mock.module('@/components/ui/sheet', () => ({ Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip, TooltipContent, TooltipTrigger }))
mock.module('@/hooks/use-mobile', () => ({ useIsMobile: () => false }))
mock.module('lucide-react', () => ({ PanelLeftIcon }))

const sidebar = await import('./sidebar')

function context(overrides: Record<string, unknown> = {}) {
  sidebarContext = {
    state: 'expanded',
    open: true,
    setOpen: mock(() => {}),
    openMobile: false,
    setOpenMobile,
    isMobile: false,
    toggleSidebar,
    ...overrides,
  }
}

test('renders desktop, fixed, and mobile sidebar variants', () => {
  context({ state: 'collapsed' })
  const desktop = sidebar.Sidebar({ side: 'right', variant: 'floating', collapsible: 'icon', children: 'Menu' }) as { props: Record<string, unknown> }
  const fixed = sidebar.Sidebar({ collapsible: 'none', className: 'fixed', children: 'Menu' }) as { props: Record<string, unknown> }

  expect(desktop.props['data-state']).toBe('collapsed')
  expect(desktop.props['data-side']).toBe('right')
  expect(fixed.props['data-slot']).toBe('sidebar')
  expect(fixed.props.className).toContain('fixed')

  context({ isMobile: true, openMobile: true })
  const mobile = sidebar.Sidebar({ side: 'right', children: 'Menu' }) as { props: Record<string, unknown> }
  const content = mobile.props.children as { props: Record<string, unknown> }
  expect(mobile.type).toBe(Sheet)
  expect(mobile.props.open).toBe(true)
  expect(content.props['data-mobile']).toBe('true')
  expect(content.props.side).toBe('right')
})

test('toggles from trigger and rail while preserving click handlers', () => {
  context()
  const onClick = mock(() => {})
  const trigger = sidebar.SidebarTrigger({ onClick }) as { props: Record<string, (event: unknown) => void> }
  const rail = sidebar.SidebarRail({}) as { props: Record<string, () => void> }

  trigger.props.onClick({})
  rail.props.onClick()

  expect(onClick).toHaveBeenCalledTimes(1)
  expect(toggleSidebar).toHaveBeenCalledTimes(2)
  expect(rail.props['aria-label' as never]).toBe('toggleSidebar')
})

test('provides sidebar state, keyboard toggle, and menu tooltip behavior', () => {
  const originalWindow = globalThis.window
  Object.assign(globalThis, {
    document: { cookie: '' },
    window: {
      addEventListener: (_type: string, handler: (event: Record<string, unknown>) => void) => { keydownHandler = handler },
      removeEventListener: mock(() => {}),
    },
  })

  const provider = sidebar.SidebarProvider({ defaultOpen: false, children: 'Menu' }) as { props: Record<string, unknown> }
  const event = { key: 'b', ctrlKey: true, metaKey: false, preventDefault: mock(() => {}) }
  keydownHandler?.(event)
  expect(provider.props.value.state).toBe('collapsed')
  expect(event.preventDefault).toHaveBeenCalledTimes(1)
  expect(stateUpdates).toHaveLength(1)

  context({ state: 'collapsed' })
  const tooltip = sidebar.SidebarMenuButton({ tooltip: 'Dashboard', isActive: true }) as { props: Record<string, unknown> }
  const content = tooltip.props.children[1] as { props: Record<string, unknown> }
  expect(tooltip.type).toBe(Tooltip)
  expect(content.props.hidden).toBe(false)

  context({ state: 'expanded', isMobile: true })
  const hiddenTooltip = sidebar.SidebarMenuButton({ tooltip: 'Dashboard' }) as { props: Record<string, unknown> }
  expect((hiddenTooltip.props.children[1] as { props: Record<string, unknown> }).props.hidden).toBe(true)

  globalThis.window = originalWindow
})

test('renders sidebar primitives and rejects missing context', () => {
  const group = sidebar.SidebarGroup({ className: 'navigation' }) as { props: Record<string, unknown> }
  const badge = sidebar.SidebarMenuBadge({ children: '3' }) as { props: Record<string, unknown> }
  const skeleton = sidebar.SidebarMenuSkeleton({ showIcon: true }) as { props: Record<string, unknown> }
  const subButton = sidebar.SidebarMenuSubButton({ isActive: true }) as { props: Record<string, unknown> }

  expect(group.props['data-sidebar']).toBe('group')
  expect(group.props.className).toContain('navigation')
  expect(badge.props['data-slot']).toBe('sidebar-menu-badge')
  expect(skeleton.props.children).toHaveLength(2)
  expect(subButton.props['data-active']).toBe(true)

  sidebarContext = null
  expect(() => sidebar.useSidebar()).toThrow('useSidebar must be used within a SidebarProvider.')
})
