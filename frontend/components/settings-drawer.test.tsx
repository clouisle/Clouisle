import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { act } from 'react'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.Event = window.Event as unknown as typeof Event
globalThis.Blob = window.Blob as unknown as typeof Blob
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const setTheme = mock<(theme: string) => void>()
const resetSettings = mock<() => void>()
const setSidebarVariant = mock<(value: string) => void>()
const setLayoutVariant = mock<(value: string) => void>()
const setDirection = mock<(value: string) => void>()
const setPlatformHeaderVariant = mock<(value: string) => void>()
const changeLocale = mock<(value: string) => void>()

let settings = {
  sidebarVariant: 'inset',
  layoutVariant: 'default',
  direction: 'ltr',
  platformHeaderVariant: 'default',
  mounted: true,
}

mock.module('next-themes', () => ({
  useTheme: () => ({ theme: 'dark', setTheme }),
}))

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))

mock.module('@/hooks/use-settings', () => ({
  useSettings: () => ({
    ...settings,
    setSidebarVariant,
    setLayoutVariant,
    setDirection,
    setPlatformHeaderVariant,
    resetSettings,
  }),
}))

mock.module('@/hooks/use-locale-change', () => ({
  useLocaleChange: () => ({ changeLocale }),
}))

mock.module('@/i18n/config', () => ({
  locales: ['en', 'zh'],
  localeNames: { en: 'English', zh: '中文' },
}))

mock.module('@/components/ui/sheet', () => ({
  Sheet: ({ open, onOpenChange, children }: { open: boolean; onOpenChange: (open: boolean) => void; children: React.ReactNode }) => (
    open ? <div data-testid="sheet"><button onClick={() => onOpenChange(false)}>close-sheet</button>{children}</div> : null
  ),
  SheetContent: ({ children, side }: { children: React.ReactNode; side: string }) => <section data-side={side}>{children}</section>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  SheetFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))

mock.module('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))

mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

let container: HTMLDivElement
let root: Root

async function render(ui: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(ui))
}

async function click(text: string) {
  const button = [...container.querySelectorAll('button')].find((node) => node.textContent === text)
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

beforeEach(() => {
  settings = {
    sidebarVariant: 'inset',
    layoutVariant: 'default',
    direction: 'ltr',
    platformHeaderVariant: 'default',
    mounted: true,
  }
  for (const fn of [setTheme, resetSettings, setSidebarVariant, setLayoutVariant, setDirection, setPlatformHeaderVariant, changeLocale]) {
    fn.mockReset()
  }
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('SettingsDrawer', () => {
  test('renders default sections and propagates dialog close/reset/actions', async () => {
    const onOpenChange = mock<(open: boolean) => void>()
    const { SettingsDrawer } = await import('./settings-drawer')

    await render(<SettingsDrawer open onOpenChange={onOpenChange} />)
    expect(container.querySelector('[data-testid="settings-sidebar-section"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="settings-layout-section"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="settings-header-layout-section"]')).toBeNull()
    expect(container.querySelector('section')?.getAttribute('data-side')).toBe('right')

    for (const theme of ['system', 'light', 'dark']) await click(theme)
    expect(setTheme.mock.calls.map((call) => call[0])).toEqual(['system', 'light', 'dark'])

    for (const variant of ['sidebarInset', 'sidebarFloating', 'sidebarDefault']) await click(variant)
    expect(setSidebarVariant.mock.calls.map((call) => call[0])).toEqual(['inset', 'floating', 'sidebar'])

    for (const variant of ['layoutDefault', 'layoutCompact', 'layoutFull']) await click(variant)
    expect(setLayoutVariant.mock.calls.map((call) => call[0])).toEqual(['default', 'compact', 'full'])

    for (const direction of ['directionLTR', 'directionRTL']) await click(direction)
    expect(setDirection.mock.calls.map((call) => call[0])).toEqual(['ltr', 'rtl'])

    for (const locale of ['English', '中文']) await click(locale)
    expect(changeLocale.mock.calls.map((call) => call[0])).toEqual(['en', 'zh'])

    await click('reset')
    expect(setTheme).toHaveBeenLastCalledWith('system')
    expect(resetSettings).toHaveBeenCalledTimes(1)

    await click('close-sheet')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('switches to platform header controls and honors mounted RTL drawer side', async () => {
    settings.direction = 'rtl'
    const { SettingsDrawer } = await import('./settings-drawer')

    await render(<SettingsDrawer open onOpenChange={mock()} showSidebarStyle={false} showPlatformHeader />)
    expect(container.querySelector('[data-testid="settings-sidebar-section"]')).toBeNull()
    expect(container.querySelector('[data-testid="settings-layout-section"]')).toBeNull()
    expect(container.querySelector('[data-testid="settings-header-layout-section"]')).toBeTruthy()
    expect(container.querySelector('section')?.getAttribute('data-side')).toBe('left')

    for (const variant of ['headerDefault', 'headerCentered', 'headerMinimal']) await click(variant)
    expect(setPlatformHeaderVariant.mock.calls.map((call) => call[0])).toEqual(['default', 'centered', 'minimal'])
  })
})
