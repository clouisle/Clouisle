import { expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create } from 'react-test-renderer'

let settings = {
  sidebarVariant: 'inset',
  layoutVariant: 'default',
  direction: 'ltr',
  mounted: true,
}

mock.module('@/hooks/use-settings', () => ({ useSettings: () => settings }))
mock.module('@/components/auth-guard', () => ({
  AuthGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/sidebar', () => ({
  SidebarProvider: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SidebarInset: ({ children }: React.PropsWithChildren) => <main>{children}</main>,
}))
mock.module('@/components/layout/app-sidebar', () => ({
  AppSidebar: (props: Record<string, unknown>) => <aside data-sidebar={JSON.stringify(props)} />,
}))

const { default: DashboardLayout } = await import('./layout')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const sidebarProps = (layout: React.ReactElement) => {
  let renderer: ReturnType<typeof create>
  act(() => {
    renderer = create(layout)
  })
  const props = JSON.parse(renderer!.root.findByType('aside').props['data-sidebar'])
  act(() => renderer!.unmount())
  return props
}

test('passes mounted layout settings to the sidebar', () => {
  expect(sidebarProps(<DashboardLayout>content</DashboardLayout>)).toMatchObject({
    variant: 'inset',
    collapsible: 'offExamples',
    side: 'left',
  })
})

test('uses hydration-safe sidebar defaults before settings mount', () => {
  settings = { sidebarVariant: 'floating', layoutVariant: 'full', direction: 'rtl', mounted: false }

  expect(sidebarProps(<DashboardLayout>content</DashboardLayout>)).toMatchObject({
    variant: 'inset',
    collapsible: 'offExamples',
    side: 'left',
  })
})
