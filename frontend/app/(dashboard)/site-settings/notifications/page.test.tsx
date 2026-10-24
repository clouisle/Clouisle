import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

let canUpdate = true

mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))
mock.module('./_components', () => ({
  AutoNotificationsSettingsTab: (props: Record<string, unknown>) => (
    <div data-auto={JSON.stringify(props)} />
  ),
}))

const { default: SiteSettingsNotificationsPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsNotificationsPage />)
  })
  return renderer!
}

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
})

test('renders automatic notification settings directly without a tab wrapper', async () => {
  const renderer = await render()
  const auto = renderer.root.findAll((node) => typeof node.props['data-auto'] === 'string')[0]
  expect(JSON.parse(auto.props['data-auto']).canUpdate).toBe(true)
  expect(renderer.root.findAllByType('button')).toHaveLength(0)
  act(() => renderer.unmount())
})

test('passes read-only permission to automatic notification settings', async () => {
  canUpdate = false
  const renderer = await render()
  const auto = renderer.root.findAll((node) => typeof node.props['data-auto'] === 'string')[0]

  expect(JSON.parse(auto.props['data-auto']).canUpdate).toBe(false)
  act(() => renderer.unmount())
})
