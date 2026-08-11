import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'
import { ApiError } from '@/lib/api/client'

const getSecurity = mock(() => Promise.resolve(settings))
const updateSecurity = mock(() => Promise.resolve())
const getRoles = mock(() => Promise.resolve({ items: roles }))
const getTeams = mock(() => Promise.resolve({ items: teams }))
const success = mock(() => {})
let canUpdate = true

const roles = [{ id: 'role-1', name: 'Member', description: null, is_system_role: false, permissions: [] }]
const teams = [{ id: 'team-1', name: 'Platform', description: null }]

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
  model_endpoint_allowlist: ['https://api.openai.com'],
}

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({ onChange, ...props }: { onChange: (value: number | '') => void; id: string }) => (
    <input {...props} onChange={(event) => onChange(event.target.value === '' ? '' : Number(event.target.value))} />
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
  Switch: ({ onCheckedChange, ...props }: { onCheckedChange: (checked: boolean) => void; checked: boolean; disabled?: boolean }) => (
    <input {...props} type="checkbox" onChange={(event) => onCheckedChange(event.target.checked)} />
  ),
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, ...props }: React.PropsWithChildren<{ onValueChange: (value: string | null) => void; value: string; disabled?: boolean }>) => (
    <div {...props} data-select onChange={onValueChange}>{children}</div>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectEmpty: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-value={value}>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getSecurity, updateSecurity },
}))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => canUpdate ? <>{children}</> : null,
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))

const { default: SiteSettingsSecurityPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsSecurityPage />)
  })
  renderers.push(renderer!)
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!
const selects = (renderer: ReactTestRenderer) => renderer.root.findAllByProps({ 'data-select': true })

beforeEach(() => {
  getSecurity.mockImplementation(() => Promise.resolve(settings))
  updateSecurity.mockImplementation(() => Promise.resolve())
  getRoles.mockImplementation(() => Promise.resolve({ items: roles }))
  getTeams.mockImplementation(() => Promise.resolve({ items: teams }))
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.clearAllMocks()
  canUpdate = true
  Object.assign(settings, originalSettings)
})

const originalSettings = { ...settings }

describe('SiteSettingsSecurityPage', () => {
  test('shows loading placeholders and recovers to the default form after a load failure', async () => {
    let rejectLoad!: (error: Error) => void
    getSecurity.mockImplementationOnce(() => new Promise((_, reject) => { rejectLoad = reject }))
    const consoleError = mock(() => {})
    const originalConsoleError = console.error
    console.error = consoleError
    let renderer: ReactTestRenderer

    act(() => { renderer = create(<SiteSettingsSecurityPage />) })
    renderers.push(renderer!)
    expect(renderer!.root.findAllByType('section')).toHaveLength(3)

    await act(async () => rejectLoad(new Error('offline')))
    expect(consoleError).toHaveBeenCalledWith('Failed to load settings:', expect.any(Error))
    expect(renderer!.root.findByProps({ id: 'minLength' }).props.value).toBe(8)
    console.error = originalConsoleError
  })

  test('loads options, drives every form callback, and saves the resulting payload', async () => {
    const renderer = await render()

    expect(getRoles).toHaveBeenCalledWith()
    expect(getTeams).toHaveBeenCalledWith(1, 200)
    expect(renderer.root.findByProps({ 'data-value': 'role-1' }).children).toContain('Member')
    expect(renderer.root.findByProps({ 'data-value': 'team-1' }).children).toContain('Platform')

    act(() => selects(renderer)[0].props.onChange('role-1'))
    act(() => selects(renderer)[1].props.onChange('team-1'))
    act(() => selects(renderer)[2].props.onChange('admin'))

    for (let index = 0; index < renderer.root.findAllByType('input').filter((node) => node.props.type === 'checkbox').length; index++) {
      const control = renderer.root.findAllByType('input').filter((node) => node.props.type === 'checkbox')[index]
      act(() => control.props.onChange({ target: { checked: !control.props.checked } }))
    }

    const values: Record<string, number | ''> = {
      minLength: 12,
      expirationDays: 120,
      warningDays: 14,
      historyCount: 8,
      minAgeDays: 2,
      sessionTimeout: 10,
      maxAttempts: 7,
      lockoutDuration: 20,
    }
    for (const [id, value] of Object.entries(values)) {
      act(() => renderer.root.findByProps({ id }).props.onChange(''))
      act(() => renderer.root.findByProps({ id }).props.onChange(value))
    }
    act(() => renderer.root.findByProps({ id: 'modelEndpointAllowlist' }).props.onChange({
      target: {
        value: 'https://api.example.com/v1\n\nhttp://ollama:11434',
      },
    }))

    await act(async () => saveButton(renderer).props.onClick())

    expect(updateSecurity).toHaveBeenCalledWith(expect.objectContaining({
      allow_registration: false,
      default_role_id: 'role-1',
      default_team_id: 'team-1',
      default_team_role: 'admin',
      min_password_length: 12,
      password_expiration_enabled: true,
      password_expiration_days: 120,
      sso_enabled: true,
      require_totp: true,
      model_endpoint_allowlist: [
        'https://api.example.com/v1',
        'http://ollama:11434',
      ],
    }))
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('blocks every invalid numeric boundary, clears errors on edits, and retries successfully', async () => {
    settings.password_expiration_enabled = true
    Object.assign(settings, {
      min_password_length: 33,
      password_expiration_days: 366,
      password_expiration_warning_days: 31,
      password_history_count: 25,
      password_min_age_days: 31,
      session_timeout_days: 0,
      max_login_attempts: 11,
      lockout_duration_minutes: 0,
    })
    const renderer = await render()

    await act(async () => saveButton(renderer).props.onClick())
    expect(updateSecurity).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(8)

    const validValues = {
      minLength: '8', expirationDays: '90', warningDays: '7', historyCount: '5',
      minAgeDays: '0', sessionTimeout: '30', maxAttempts: '5', lockoutDuration: '15',
    }
    for (const [id, value] of Object.entries(validValues)) {
      act(() => renderer.root.findByProps({ id }).props.onChange(Number(value)))
    }
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(0)

    await act(async () => saveButton(renderer).props.onClick())
    expect(updateSecurity).toHaveBeenCalledTimes(1)
  })

  test('maps API field and summary errors, clears the edited field, and succeeds on retry', async () => {
    const originalConsoleError = console.error
    console.error = mock(() => {})
    updateSecurity.mockRejectedValueOnce(new ApiError(1001, 'invalid', {
      errors: { 'settings.default_team_id': 'Choose a team', policy: ['Policy conflict'] },
    }))
    const renderer = await render()

    await act(async () => saveButton(renderer).props.onClick())
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(' '))).toEqual([
      'Policy conflict', 'Choose a team',
    ])

    act(() => selects(renderer)[1].props.onChange('team-1'))
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(' '))).toEqual(['Policy conflict'])
    updateSecurity.mockResolvedValueOnce(undefined)
    await act(async () => saveButton(renderer).props.onClick())

    expect(updateSecurity).toHaveBeenCalledTimes(2)
    expect(success).toHaveBeenCalledWith('saveSuccess')
    console.error = originalConsoleError
  })

  test('keeps controls and dependent settings disabled and hides save without permission', async () => {
    canUpdate = false
    settings.default_team_id = 'team-1'
    settings.sso_enabled = true
    const renderer = await render()

    expect(renderer.root.findAllByType('input').every((node) => node.props.disabled)).toBe(true)
    expect(selects(renderer).every((node) => node.props.disabled)).toBe(true)
    expect(saveButton(renderer)).toBeUndefined()
  })
})
