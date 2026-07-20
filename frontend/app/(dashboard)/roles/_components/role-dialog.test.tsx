import { beforeEach, expect, mock, test } from 'bun:test'

const state: unknown[] = []
const effects: Array<readonly unknown[] | undefined> = []
let hookIndex = 0
let validationErrors: Record<string, string> = {}

const rolesApi = {
  createRole: mock(() => Promise.resolve({})),
  updateRole: mock(() => Promise.resolve({})),
  updateRolePermissions: mock(() => Promise.resolve({})),
}
const permissionsApi = {
  getPermissions: mock(() => Promise.resolve({ items: [] })),
}
const toast = { success: mock(() => undefined) }

mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    if (!(index in state)) state[index] = initial
    return [state[index] as T, (value: T | ((current: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (current: T) => T)(state[index] as T)
        : value
    }]
  },
  useEffect: (effect: () => void, dependencies?: readonly unknown[]) => {
    const index = hookIndex++
    const previous = effects[index]
    if (!previous || !dependencies?.every((value, dependencyIndex) => Object.is(value, previous[dependencyIndex]))) {
      effects[index] = dependencies
      effect()
    }
  },
  useMemo: <T,>(factory: () => T) => {
    hookIndex++
    return factory()
  },
}))
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const jsxRuntime = { jsx, jsxs: jsx, jsxDEV: jsx, Fragment: Symbol('fragment') }
mock.module('react/jsx-runtime', () => jsxRuntime)
mock.module('react/jsx-dev-runtime', () => jsxRuntime)
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi, permissionsApi }))
mock.module('@/lib/validation', () => ({
  normalizeValidationErrors: () => validationErrors,
  clearValidationError: (errors: Record<string, string>, key: string) => {
    const next = { ...errors }
    delete next[key]
    return next
  },
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => key !== prefix && !key.startsWith(`${prefix}.`))),
  getValidationSummaryEntries: (errors: Record<string, string>, inlineFields: string[]) =>
    Object.entries(errors).filter(([key]) => !inlineFields.includes(key)),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

for (const modulePath of [
  '@/components/ui/button', '@/components/ui/input', '@/components/ui/label',
  '@/components/ui/textarea', '@/components/ui/checkbox', '@/components/ui/badge',
  '@/components/ui/field',
]) {
  mock.module(modulePath, () => ({
    Button: 'Button', Input: 'Input', Label: 'Label', Textarea: 'Textarea',
    Checkbox: 'Checkbox', Badge: 'Badge', FieldError: 'FieldError',
  }))
}
mock.module('@/components/ui/dialog', () => ({
  Dialog: 'Dialog', DialogContent: 'DialogContent', DialogDescription: 'DialogDescription',
  DialogFooter: 'DialogFooter', DialogHeader: 'DialogHeader', DialogTitle: 'DialogTitle',
}))
mock.module('lucide-react', () => ({ Search: 'Search', Shield: 'Shield', ChevronRight: 'ChevronRight' }))

const { RoleDialog } = await import('./role-dialog')

type Node = { type: unknown; props: Record<string, unknown> }

function nodes(value: unknown): Node[] {
  if (!value || typeof value !== 'object') return []
  if (Array.isArray(value)) return value.flatMap(nodes)
  const node = value as Node
  return [node, ...nodes(node.props?.children)]
}

function render(role: Parameters<typeof RoleDialog>[0]['role'] = null) {
  hookIndex = 0
  return RoleDialog({ open: true, role, onOpenChange, onSuccess })
}

function find(tree: unknown, predicate: (node: Node) => boolean) {
  const node = nodes(tree).find(predicate)
  if (!node) throw new Error('Expected node was not rendered')
  return node
}

const onOpenChange = mock(() => undefined)
const onSuccess = mock(() => undefined)

beforeEach(() => {
  state.length = 0
  effects.length = 0
  validationErrors = {}
  rolesApi.createRole.mockClear()
  rolesApi.updateRole.mockClear()
  rolesApi.updateRolePermissions.mockClear()
  permissionsApi.getPermissions.mockClear()
  toast.success.mockClear()
  onOpenChange.mockClear()
  onSuccess.mockClear()
})

test('requires a role name before creating', () => {
  const tree = render()

  expect(find(tree, (node) => node.props.type === 'submit').props.disabled).toBe(true)
  expect(permissionsApi.getPermissions).toHaveBeenCalledWith(1, 100)
})

test('creates a role and closes after a successful save', async () => {
  render()
  let tree = render()
  const name = find(tree, (node) => node.props.id === 'name')
  ;(name.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'Editor' } })
  tree = render()

  await (find(tree, (node) => node.type === 'form').props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({
    preventDefault: () => undefined,
  })

  expect(rolesApi.createRole).toHaveBeenCalledWith({ name: 'Editor', description: '', permissions: [] })
  expect(toast.success).toHaveBeenCalledWith('roleCreated')
  expect(onSuccess).toHaveBeenCalledTimes(1)
  expect(onOpenChange).toHaveBeenCalledWith(false)
})

test('initializes and saves edits with updated permissions', async () => {
  const role = {
    id: 'role-1', name: 'Editor', description: 'Existing role', is_system_role: false,
    permissions: [{ id: 'permission-1', scope: 'users', code: 'users.read', description: null, is_system: false }],
  }
  render(role)
  let tree = render(role)
  const description = find(tree, (node) => node.props.id === 'description')
  ;(description.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'Updated role' } })
  tree = render(role)

  await (find(tree, (node) => node.type === 'form').props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({
    preventDefault: () => undefined,
  })

  expect(rolesApi.updateRole).toHaveBeenCalledWith('role-1', { name: 'Editor', description: 'Updated role' })
  expect(rolesApi.updateRolePermissions).toHaveBeenCalledWith('role-1', ['users.read'])
  expect(toast.success).toHaveBeenCalledWith('roleUpdated')
})

test('shows and clears server validation errors', async () => {
  validationErrors = { name: 'Name already exists', __all__: 'Request rejected' }
  rolesApi.createRole.mockImplementationOnce(() => Promise.reject(new Error('validation')))
  render()
  let tree = render()
  const name = find(tree, (node) => node.props.id === 'name')
  ;(name.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'Editor' } })
  tree = render()

  await (find(tree, (node) => node.type === 'form').props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({
    preventDefault: () => undefined,
  })
  tree = render()

  expect(find(tree, (node) => node.props.id === 'name').props['aria-invalid']).toBe(true)
  expect(nodes(tree).some((node) => node.type === 'FieldError' && node.props.children === 'Request rejected')).toBe(true)

  ;(find(tree, (node) => node.props.id === 'name').props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'New editor' } })
  tree = render()

  expect(find(tree, (node) => node.props.id === 'name').props['aria-invalid']).toBe(false)
})
