import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const provider = {
  id: 'provider-1',
  display_name: 'Acme SSO',
  protocol: 'oidc',
  is_enabled: true,
  allow_signup: true,
  icon_url: '',
}
const listProviders = mock(() => Promise.resolve([provider]))
const updateProvider = mock(() => Promise.resolve())
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
mock.module('lucide-react', () => ({
  Plus: () => null,
  Pencil: () => null,
  Trash2: () => null,
  TestTube2: () => null,
  Power: () => null,
  PowerOff: () => null,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))
mock.module('@/components/ui/table', () => ({
  Table: ({ children }: React.PropsWithChildren) => <table>{children}</table>,
  TableBody: ({ children }: React.PropsWithChildren) => <tbody>{children}</tbody>,
  TableCell: ({ children }: React.PropsWithChildren) => <td>{children}</td>,
  TableHead: ({ children }: React.PropsWithChildren) => <th>{children}</th>,
  TableHeader: ({ children }: React.PropsWithChildren) => <thead>{children}</thead>,
  TableRow: ({ children }: React.PropsWithChildren) => <tr>{children}</tr>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/lib/api/admin/sso', () => ({
  ssoApi: {
    listProviders,
    updateProvider,
    deleteProvider: mock(() => Promise.resolve()),
    testConnection: mock(() => Promise.resolve({ status: 'success', message: 'connected' })),
  },
}))
mock.module('./_components/provider-dialog', () => ({ ProviderDialog: () => null }))

const { default: SSOSettingsPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SSOSettingsPage />)
  })
  return renderer!
}

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
})

test('toggles an enabled provider and refreshes its list', async () => {
  const renderer = await render()
  const toggle = renderer.root
    .findAllByType('button')
    .find((button) => button.props.title === 'disable')!

  await act(async () => toggle.props.onClick())

  expect(updateProvider).toHaveBeenCalledWith('provider-1', { is_enabled: false })
  expect(listProviders).toHaveBeenCalledTimes(2)
  act(() => renderer.unmount())
})

test('hides provider management actions from viewers without update permission', async () => {
  canUpdate = false
  const renderer = await render()

  expect(
    renderer.root.findAllByType('button').some((button) => button.props.title === 'disable'),
  ).toBe(false)
  expect(
    renderer.root.findAllByType('button').some((button) => button.children.includes('addProvider')),
  ).toBe(false)
  act(() => renderer.unmount())
})
