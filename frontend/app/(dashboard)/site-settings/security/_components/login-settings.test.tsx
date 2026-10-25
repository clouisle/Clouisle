import { afterEach, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { integrationsApi, type LoginSettings } from '@/lib/api/admin/integrations'

const success = mock(() => undefined)
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
}))
mock.module('@/components/ui/label', () => ({ Label: ({ children }: React.PropsWithChildren) => <label>{children}</label> }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: { id: string; checked: boolean; disabled: boolean; onCheckedChange: (checked: boolean) => void }) => <button {...props} /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button> }))

const { LoginSettingsCard } = await import('./login-settings')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const settings: LoginSettings = { sso_enabled: true, sso_allow_password_login: true, sso_auto_create_users: true, sso_require_approval: false, sso_match_by_email: true }
const renderers: ReactTestRenderer[] = []

function render(canUpdate: boolean, initialSettings = settings) {
  let renderer: ReactTestRenderer
  function Harness() {
    const [current, setCurrent] = React.useState(initialSettings)
    return <LoginSettingsCard settings={current} onSettingsChange={setCurrent} canUpdate={canUpdate} />
  }
  act(() => { renderer = create(<Harness />) })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  act(() => renderers.splice(0).forEach((renderer) => renderer.unmount()))
  mock.restore()
  success.mockClear()
})

test('saves global login policy through the integration login domain endpoint', async () => {
  const save = spyOn(integrationsApi, 'updateLoginSettings').mockResolvedValue({ ...settings, sso_require_approval: true })
  const renderer = render(true)
  act(() => renderer.root.findByProps({ id: 'sso_require_approval' }).props.onCheckedChange(true))
  await act(async () => renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))?.props.onClick())
  expect(save).toHaveBeenCalledWith({ ...settings, sso_require_approval: true })
  expect(success).toHaveBeenCalledWith('saveSuccess')
})

test('read-only policy shows disabled switches and no save action', () => {
  const renderer = render(false)
  expect(renderer.root.findAllByType('button').every((button) => button.props.disabled)).toBe(true)
  expect(renderer.root.findAllByType('button').some((button) => button.children.includes('saveChanges'))).toBe(false)
})

test('disabling login integration authentication keeps subordinate policy controls disabled', () => {
  const renderer = render(true, { ...settings, sso_enabled: false })
  expect(renderer.root.findByProps({ id: 'sso_enabled' }).props.disabled).toBe(false)
  expect(renderer.root.findByProps({ id: 'sso_allow_password_login' }).props.disabled).toBe(true)
  expect(renderer.root.findByProps({ id: 'sso_match_by_email' }).props.disabled).toBe(true)
})
