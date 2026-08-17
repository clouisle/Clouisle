import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const promptTextarea = function PromptTextarea() {}
const parameterEditDialog = function ParameterEditDialog() {}
let states: unknown[] = []
let stateIndex = 0
let runEffect = true
let currentTeam: { id: string } | null = { id: 'team-1' }
const getTeam = mock(async () => ({ members: [] }))

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [states[index], (value: unknown) => { states[index] = typeof value === 'function' ? (value as (old: unknown) => unknown)(states[index]) : value }]
  },
  useMemo: (factory: () => unknown) => factory(),
  useEffect: (effect: () => unknown) => { if (runEffect) effect() },
  useRef: (value: unknown) => ({ current: value }),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: { count?: number; name?: string }) => values?.count === undefined && values?.name === undefined ? key : `${key}:${values.count ?? values.name}` }))
mock.module('lucide-react', () => ({ Pencil: component, Plus: component, Trash2: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/combobox', ['Combobox', 'ComboboxChip', 'ComboboxChips', 'ComboboxChipsInput', 'ComboboxContent', 'ComboboxEmpty', 'ComboboxItem', 'ComboboxList', 'useComboboxAnchor']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({ teamsApi: { getTeam } }))
mock.module('../components/prompt-textarea', () => ({ PromptTextarea: promptTextarea }))
mock.module('../dialogs/parameter-edit-dialog', () => ({ ParameterEditDialog: parameterEditDialog }))
mock.module('../constants', () => ({
  parameterTypeConfig: {
    text: { labelKey: 'text' },
    number: { labelKey: 'number' },
  },
}))

const { PauseNodeConfig, defaultPauseNodeConfig } = await import('./pause-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function collectText(node: unknown): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(collectText).join('')
  if (typeof node === 'object' && 'props' in node) {
    return collectText((node as TreeNode).props.children)
  }
  return ''
}
function render(config = defaultPauseNodeConfig) {
  stateIndex = 0
  const onConfigChange = mock(() => {})
  return {
    tree: PauseNodeConfig({
      config,
      onConfigChange,
      getAvailableVariables: () => [
        { id: 'start.doc', name: 'doc', type: 'File' },
        { id: 'start.price', name: 'price', type: 'Number' },
      ],
    }) as TreeNode,
    onConfigChange,
  }
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
const members = [
  { id: 'm1', user_id: 'u-alice', username: 'alice', email: 'alice@example.com', avatar_url: null, role: 'admin' as const, joined_at: '2026-01-01T00:00:00Z' },
  { id: 'm2', user_id: 'u-bob', username: 'bob', email: 'bob@example.com', avatar_url: null, role: 'member' as const, joined_at: '2026-01-01T00:00:00Z' },
]

beforeEach(() => {
  states = []
  stateIndex = 0
  currentTeam = { id: 'team-1' }
  runEffect = true
  getTeam.mockReset()
  getTeam.mockResolvedValue({ members: [] })
})

test('switches between variables and approval modes', () => {
  const { tree, onConfigChange } = render()
  const modeButtons = findAll(tree, (node) => node.type === 'button')

  ;(modeButtons[1].props.onClick as () => void)()

  expect(onConfigChange).toHaveBeenCalledWith({ ...defaultPauseNodeConfig, mode: 'approval' })
})

test('adds, edits, and removes requested variables via the parameter dialog', () => {
  const { tree } = render()
  const addButton = findAll(tree, (node) => node.type === component && node.props.children?.[1] === 'configCommon.add')[0]
  expect(addButton).toBeDefined()
  ;(addButton.props.onClick as () => void)()

  // 再次渲染使 paramDialogOpen 状态生效（模拟 React 重渲染）
  const opened = render()
  const dialog = findAll(opened.tree, (node) => node.type === parameterEditDialog)[0]
  expect(dialog).toBeDefined()
  expect(dialog.props.open).toBe(true)
  expect(dialog.props.editingParam).toBeNull()
  expect(dialog.props.existingParams).toEqual([])

  const newParam = { id: 'pause-var-1', name: 'price', label: '预算价格', type: 'number' as const, required: true, defaultValue: '' }
  ;(dialog.props.onSave as (param: typeof newParam) => void)(newParam)
  expect(opened.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    inputVariables: [newParam],
  }))

  const variable = { id: 'price', name: 'price', type: 'number' as const, required: true, defaultValue: '' }
  const edited = render({ ...defaultPauseNodeConfig, inputVariables: [variable] })
  const editButton = findAll(edited.tree, (node) => node.props['aria-label'] === 'configPause.editVariable:price')[0]
  expect(editButton).toBeDefined()
  ;(editButton.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock() })

  // 再次渲染使 editingParam 状态生效（模拟 React 重渲染）
  const editedPass = render({ ...defaultPauseNodeConfig, inputVariables: [variable] })
  const editDialog = findAll(editedPass.tree, (node) => node.type === parameterEditDialog)[0]
  expect(editDialog.props.editingParam).toEqual(variable)
  ;(editDialog.props.onSave as (param: typeof variable) => void)({ ...variable, name: 'approved_price' })
  expect(editedPass.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    inputVariables: [expect.objectContaining({ name: 'approved_price' })],
  }))

  const removeButton = findAll(editedPass.tree, (node) => node.props['aria-label'] === 'configCommon.remove')[0]
  ;(removeButton.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock() })
  expect(editedPass.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputVariables: [] }))
})

test('updates pause titles and variable metadata via the dialog', () => {
  const variable = { id: 'price', name: 'price', type: 'number' as const, required: true, defaultValue: '' }
  const { tree, onConfigChange } = render({ ...defaultPauseNodeConfig, inputVariables: [variable] })

  const titleInput = findAll(tree, (node) => node.props.placeholder === 'configPause.titlePlaceholder')[0]
  ;(titleInput.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'Review budget' } })
  expect(onConfigChange).toHaveBeenCalledWith({ ...defaultPauseNodeConfig, inputVariables: [variable], title: 'Review budget' })

  // 行点击打开编辑弹窗；类型/显示名称/必填均在弹窗内配置，保存后整体替换
  const editButton = findAll(tree, (node) => node.props['aria-label'] === 'configPause.editVariable:price')[0]
  expect(editButton).toBeDefined()
  ;(editButton.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock() })

  const refreshed = render({ ...defaultPauseNodeConfig, inputVariables: [variable] })
  const dialog = findAll(refreshed.tree, (node) => node.type === parameterEditDialog)[0]
  expect(dialog.props.editingParam).toEqual(variable)
  ;(dialog.props.onSave as (param: typeof variable) => void)({
    ...variable,
    type: 'text',
    label: 'Approved price',
    required: false,
  })
  expect(refreshed.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    inputVariables: [expect.objectContaining({ type: 'text', label: 'Approved price', required: false })],
  }))
})

test('edits the request description in variables mode like approval', () => {
  const { tree, onConfigChange } = render({ ...defaultPauseNodeConfig, mode: 'variables' })
  const textarea = findAll(tree, (node) => node.type === promptTextarea)[0]
  expect(textarea).toBeDefined()
  expect(textarea.props.variables.length).toBeGreaterThan(0)

  ;(textarea.props.onChange as (value: string) => void)('请上传预算文件：{{start.doc}}')

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    mode: 'variables',
    description: '请上传预算文件：{{start.doc}}',
  }))
})

test('switches the approval strategy between any-one and require-all', () => {
  const { tree, onConfigChange } = render({ ...defaultPauseNodeConfig, mode: 'approval' })
  const allButton = findAll(tree, (node) => node.type === 'button' && collectText(node).includes('configPause.approvalAll'))[0]
  expect(allButton).toBeDefined()
  ;(allButton.props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ requireAllApprovals: true }))

  const anyOneButton = findAll(tree, (node) => node.type === 'button' && collectText(node).includes('configPause.approvalAnyOne'))[0]
  ;(anyOneButton.props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenLastCalledWith(expect.objectContaining({ requireAllApprovals: false }))
})

test('edits the approval description with variable support in approval mode', () => {
  const { tree, onConfigChange } = render({ ...defaultPauseNodeConfig, mode: 'approval' })
  const textarea = findAll(tree, (node) => node.type === promptTextarea)[0]
  expect(textarea).toBeDefined()
  expect(textarea.props.variables.length).toBeGreaterThan(0)

  ;(textarea.props.onChange as (value: string) => void)('Review {{start.doc}}')

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    mode: 'approval',
    description: 'Review {{start.doc}}',
  }))
})

test('loads team members and selects approvers via the multi-select combobox', async () => {
  getTeam.mockResolvedValueOnce({ members })
  render()
  await settle()
  runEffect = false
  const { tree, onConfigChange } = render()
  expect(getTeam).toHaveBeenCalledWith('team-1')

  const combobox = findAll(tree, (node) => node.type === component && node.props.multiple === true)[0]
  expect(combobox).toBeDefined()
  expect(combobox.props.items).toHaveLength(2)
  expect(combobox.props.value).toEqual([])

  // 选择 alice -> approverIds 更新
  ;(combobox.props.onValueChange as (next: { value: string }[]) => void)([
    { value: 'u-alice', label: 'alice', email: 'alice@example.com' },
  ])
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ approverIds: ['u-alice'] }))

  // 预选中 bob -> 值回显为已选选项
  const preSelected = render({ ...defaultPauseNodeConfig, approverIds: ['u-bob'] })
  const preCombobox = findAll(preSelected.tree, (node) => node.type === component && node.props.multiple === true)[0]
  expect((preCombobox.props.value as { value: string }[]).map((option) => option.value)).toEqual(['u-bob'])

  // 清空选择 -> approverIds 清空
  ;(preCombobox.props.onValueChange as (next: { value: string }[]) => void)([])
  expect(preSelected.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ approverIds: [] }))
})

test('shows empty approver state and skips loading without a team', async () => {
  currentTeam = null
  const { tree } = render()
  await settle()
  expect(findAll(tree, (node) => node.props.children === 'configPause.noApprovers')).toHaveLength(1)
  expect(getTeam).not.toHaveBeenCalled()

  currentTeam = { id: 'team-1' }
  getTeam.mockResolvedValueOnce({ members: [] })
  render()
  await settle()
  runEffect = false
  const empty = render()
  expect(findAll(empty.tree, (node) => node.props.children === 'configPause.noApprovers')).toHaveLength(1)
})
