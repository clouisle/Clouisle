import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getSecurity = mock(() => Promise.resolve(settings))
const updateSecurity = mock(() => Promise.resolve())
const getRoles = mock(() => Promise.resolve({ items: [] }))
const getTeams = mock(() => Promise.resolve({ items: [] }))
let canUpdate = true

const settings = {
  allow_registration: true,
  require_approval: false,
  email_verification: true,
  allow_account_deletion: true,
  default_role_id: '',
  default_team_id: '',
  default_team_role: 'member',
  min_password_length: 8,
  require_uppercase: true,
  require_number: true,
  require_special_char: false,
  session_timeout_days: 30,
  single_session: false,
  max_login_attempts: 5,
  lockout_duration_minutes: 15,
  enable_captcha: false,
  sso_enabled: false,
  sso_allow_password_login: true,
  sso_auto_create_users: true,
  sso_require_approval: false,
  sso_match_by_email: true,
  password_expiration_enabled: false,
  password_expiration_days: 90,
  password_expiration_warning_days: 7,
  password_history_count: 5,
  password_min_age_days: 0,
  force_password_change_first_login: false,
  require_totp: false,
}

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({ onChange, ...props }: { onChange: (value: number) => void; id: string }) => (
    <input {...props} onChange={(event) => onChange(Number(event.target.value))} />
  ),
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input {...props} type="checkbox" />,
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectEmpty: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getSecurity, updateSecurity },
}))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))

const { default: SiteSettingsSecurityPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsSecurityPage />)
  })
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
  settings.min_password_length = 8
})

test('blocks invalid security settings before calling the update API', async () => {
  settings.min_password_length = 5
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())

  expect(updateSecurity).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'minLength' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
  act(() => renderer.unmount())
})

test('disables security controls for viewers without update permission', async () => {
  canUpdate = false
  const renderer = await render()

  expect(renderer.root.findByProps({ id: 'minLength' }).props.disabled).toBe(true)
  expect(renderer.root.findByProps({ id: 'maxAttempts' }).props.disabled).toBe(true)
  act(() => renderer.unmount())
})
