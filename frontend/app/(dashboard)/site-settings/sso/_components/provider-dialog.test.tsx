import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Node = { type: string; props: Record<string, unknown> }

const createProvider = mock(async () => ({}))
const updateProvider = mock(async () => ({}))
const toastSuccess = mock(() => {})
let canUpdate = true
let states: unknown[] = []
let setters: Array<(value: unknown) => void> = []
let stateCursor = 0
let effectCursor = 0
let effects: Array<() => void> = []
let effectDeps: unknown[][] = []
let lastProps: Parameters<typeof ProviderDialog>[0]
let tree: Node

function node(type: string, props: Record<string, unknown> = {}) {
  return { type, props }
}

function depsChanged(previous: unknown[] | undefined, next: unknown[]) {
  return !previous || previous.length !== next.length || previous.some((value, index) => value !== next[index])
}

function resetHooks() {
  states = []
  setters = []
  effectDeps = []
  stateCursor = 0
  effectCursor = 0
  effects = []
}

function rerender(props = lastProps) {
  lastProps = props
  stateCursor = 0
  effectCursor = 0
  effects = []
  tree = ProviderDialog(props) as Node
  const pending = effects
  effects = []
  pending.forEach((effect) => effect())
  stateCursor = 0
  effectCursor = 0
  tree = ProviderDialog(props) as Node
  return tree
}

function walk(value: unknown): Node[] {
  if (!value) return []
  if (Array.isArray(value)) return value.flatMap(walk)
  if (typeof value !== 'object') return []
  const current = value as Node
  return [current, ...walk(current.props?.children)]
}

function all() {
  return walk(tree)
}

function byId(id: string) {
  const found = all().find((item) => item.props?.id === id)
  if (!found) throw new Error(`Missing #${id}`)
  return found
}

function byType(type: string) {
  return all().filter((item) => item.type === type)
}

function textContent(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(textContent).join('')
  if (value && typeof value === 'object') return textContent((value as Node).props?.children)
  return ''
}

function change(id: string, value: string) {
  byId(id).props.onChange?.({ target: { value } })
  rerender()
}

function submit() {
  return byType('form')[0].props.onSubmit({ preventDefault: mock(() => {}) })
}

mock.module('react/jsx-runtime', () => ({
  jsx: (type: string | ((props: Record<string, unknown>) => Node), props: Record<string, unknown>) =>
    typeof type === 'function' ? type(props ?? {}) : node(type, props ?? {}),
  jsxs: (type: string | ((props: Record<string, unknown>) => Node), props: Record<string, unknown>) =>
    typeof type === 'function' ? type(props ?? {}) : node(type, props ?? {}),
  Fragment: 'Fragment',
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: (type: string | ((props: Record<string, unknown>) => Node), props: Record<string, unknown>) =>
    typeof type === 'function' ? type(props ?? {}) : node(type, props ?? {}),
  Fragment: 'Fragment',
}))
mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateCursor++
    if (states.length <= index) states[index] = typeof initial === 'function' ? initial() : initial
    setters[index] = (value: unknown) => {
      states[index] = typeof value === 'function' ? value(states[index]) : value
    }
    return [states[index], setters[index]]
  },
  useEffect: (effect: () => void, deps: unknown[]) => {
    const index = effectCursor++
    if (depsChanged(effectDeps[index], deps)) {
      effectDeps[index] = deps
      effects.push(effect)
    }
  },
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))
mock.module('@/lib/api/admin/sso', () => ({
  ssoApi: { createProvider, updateProvider },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) => Object.fromEntries(
    Object.entries(errors).filter(([field]) => field !== prefix && !field.startsWith(`${prefix}.`)),
  ),
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) =>
    fields.flatMap((field) => errors[field] ? [[field, errors[field]]] : []),
  mapValidationErrors: (errors: Record<string, string>) => errors,
  normalizeValidationErrors: (error: unknown) => error,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))
for (const [path, exports] of Object.entries({
  '@/components/ui/dialog': ['Dialog', 'DialogContent', 'DialogDescription', 'DialogFooter', 'DialogHeader', 'DialogTitle'],
  '@/components/ui/button': ['Button'],
  '@/components/ui/input': ['Input'],
  '@/components/ui/label': ['Label'],
  '@/components/ui/textarea': ['Textarea'],
  '@/components/ui/select': ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue'],
  '@/components/ui/switch': ['Switch'],
  '@/components/ui/tabs': ['Tabs', 'TabsContent', 'TabsList', 'TabsTrigger'],
  '@/components/ui/field': ['FieldError'],
})) {
  mock.module(path, () => Object.fromEntries((exports as string[]).map((name) => [name, (props: Record<string, unknown>) => node(name, props)])))
}

const { ProviderDialog } = await import('./provider-dialog')

describe('ProviderDialog', () => {
  beforeEach(() => {
    createProvider.mockClear()
    updateProvider.mockClear()
    toastSuccess.mockClear()
    createProvider.mockImplementation(async () => ({}))
    updateProvider.mockImplementation(async () => ({}))
    canUpdate = true
    resetHooks()
  })

  test('resets create values when opened and closes only through dialog or cancel', () => {
    const onClose = mock(() => {})
    rerender({ open: true, provider: null, onClose })

    expect(textContent(byType('DialogTitle')[0])).toBe('addProvider')
    expect(byId('name').props.value).toBe('')
    expect(byId('config').props.value).toContain('authorization_url')
    expect(byId('attribute_mapping').props.value).toContain('avatar_url')

    change('name', 'google')
    expect(byId('name').props.value).toBe('google')
    rerender({ open: true, provider: null, onClose })
    expect(byId('name').props.value).toBe('google')

    rerender({ open: false, provider: null, onClose })
    expect(byId('name').props.value).toBe('')
    byType('Dialog')[0].props.onOpenChange()
    byType('Button')[0].props.onClick()
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  test('creates a provider with edited values and cleans loading on success', async () => {
    const onClose = mock(() => {})
    rerender({ open: true, provider: null, onClose })

    change('name', 'google_sso')
    change('display_name', 'Google SSO')
    change('button_text', 'Use Google')
    change('icon_url', 'https://example.com/google.svg')
    change('config', '{"client_id":"id"}')
    change('attribute_mapping', '{"email":"mail"}')
    byType('Switch')[0].props.onCheckedChange(false)
    rerender()
    byType('Switch')[2].props.onCheckedChange(true)
    rerender()

    await submit()
    rerender()

    expect(createProvider).toHaveBeenCalledWith({
      name: 'google_sso',
      protocol: 'oidc',
      display_name: 'Google SSO',
      icon_url: 'https://example.com/google.svg',
      button_text: 'Use Google',
      is_enabled: false,
      allow_signup: true,
      require_approval: true,
      config: { client_id: 'id' },
      attribute_mapping: { email: 'mail' },
    })
    expect(toastSuccess).toHaveBeenCalledWith('createSuccess')
    expect(onClose).toHaveBeenCalledWith(true)
    expect(byType('Button')[1].props.disabled).toBe(false)
  })

  test('loads edit values, locks identity fields, and updates provider', async () => {
    const onClose = mock(() => {})
    rerender({
      open: true,
      provider: {
        id: 'provider-1',
        name: 'okta',
        protocol: 'saml2',
        display_name: 'Okta',
        icon_url: null,
        button_text: null,
        is_enabled: false,
        allow_signup: false,
        require_approval: true,
        config: { idp_entity_id: 'idp' },
        attribute_mapping: { email: 'mail' },
      },
      onClose,
    })

    expect(textContent(byType('DialogTitle')[0])).toBe('editProvider')
    expect(byId('name').props.value).toBe('okta')
    expect(byId('name').props.disabled).toBe(true)
    expect(byType('Select')[0].props.disabled).toBe(true)

    change('display_name', 'Okta Workforce')
    await submit()

    expect(updateProvider).toHaveBeenCalledWith('provider-1', expect.objectContaining({
      name: 'okta',
      protocol: 'saml2',
      display_name: 'Okta Workforce',
      icon_url: null,
      button_text: null,
      config: { idp_entity_id: 'idp' },
      attribute_mapping: { email: 'mail' },
    }))
    expect(toastSuccess).toHaveBeenCalledWith('updateSuccess')
    expect(onClose).toHaveBeenCalledWith(true)
  })

  test('validates fields, clears local errors on edit, and keeps the dialog open', async () => {
    const onClose = mock(() => {})
    rerender({ open: true, provider: null, onClose })

    change('name', 'Bad Name')
    change('icon_url', 'ftp://example.com/icon.svg')
    await submit()
    rerender()

    expect(createProvider).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    expect(textContent(tree)).toContain('name: invalidProviderName')
    expect(textContent(tree)).toContain('icon_url: invalidIconUrl')

    change('name', 'good_name')
    change('icon_url', 'https://example.com/icon.svg')
    expect(textContent(tree)).not.toContain('invalidProviderName')
    expect(textContent(tree)).not.toContain('invalidIconUrl')
  })

  test('shows JSON/API errors and releases loading without closing', async () => {
    const onClose = mock(() => {})
    rerender({ open: true, provider: null, onClose })

    change('name', 'google')
    change('display_name', 'Google')
    change('config', '{bad')
    await submit()
    rerender()

    expect(createProvider).not.toHaveBeenCalled()
    expect(textContent(tree)).toContain('config: invalidConfigJson')
    expect(byType('Button')[1].props.disabled).toBe(false)

    change('config', '{}')
    createProvider.mockImplementationOnce(async () => { throw { display_name: 'Already used' } })
    await submit()
    rerender()

    expect(textContent(tree)).toContain('display_name: Already used')
    expect(onClose).not.toHaveBeenCalled()
    expect(byType('Button')[0].props.disabled).toBe(false)
    expect(byType('Button')[1].props.children).toBe('save')
  })

  test('disables editing, cancel boundaries, and submit when permission is absent', () => {
    canUpdate = false
    const onClose = mock(() => {})
    rerender({ open: true, provider: null, onClose })

    expect(byId('name').props.disabled).toBe(true)
    expect(byId('display_name').props.disabled).toBe(true)
    expect(byId('config').props.disabled).toBe(true)
    expect(byType('Switch')[0].props.disabled).toBe(true)
    expect(byType('Button')[0].props.disabled).toBe(false)
    expect(byType('Button')[1].props.disabled).toBe(true)
  })
})
