import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const promptTextarea = function PromptTextarea() {}
const variableSelector = function VariableSelector() {}
let states: unknown[] = []
let stateIndex = 0
let runEffect = true
let currentTeam: { id: string } | null = { id: 'team-1' }
const getTeamModels = mock(async () => [] as Record<string, unknown>[])

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [states[index], (value: unknown) => { states[index] = typeof value === 'function' ? (value as (old: unknown) => unknown)(states[index]) : value }]
  },
  useMemo: (factory: () => unknown) => factory(),
  useEffect: (effect: () => unknown) => { if (runEffect) effect() },
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ ChevronDown: component, Image: component, Loader2: component, Search: component, Video: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels } }))
mock.module('../utils', () => ({ isValidVariableName: (value: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(value) }))
mock.module('../variable-selector', () => ({ VariableSelector: variableSelector }))
mock.module('../components/prompt-textarea', () => ({ PromptTextarea: promptTextarea }))
mock.module('../../nodes/media-generation-node', () => ({
  defaultMediaGenerationConfig: { mode: 'image', prompt: '', numImages: 1, duration: 5, aspectRatio: '16:9', outputVariable: 'result' },
}))

const { MediaGenerationNodeConfig } = await import('./media-generation-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const variables = [
  { id: 'start.image', name: 'Image', type: 'Image' },
  { id: 'start.file', name: 'File', type: 'File' },
  { id: 'start.array', name: 'Array', type: 'Array' },
  { id: 'start.object', name: 'Object', type: 'Object' },
  { id: 'start.upload', name: 'Upload', type: 'String', isFile: true },
  { id: 'start.text', name: 'Text', type: 'String' },
]
const getAvailableVariables = mock(() => variables)
function render(config: Record<string, unknown> = {}, onChange?: ReturnType<typeof mock>) {
  stateIndex = 0
  const change = onChange ?? mock(() => {})
  const tree = MediaGenerationNodeConfig({ config: config as never, onChange: change, getAvailableVariables: getAvailableVariables as never }) as TreeNode
  return { tree, onChange: change }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
const models = [
  { id: 'openai-image', is_enabled: true, model: { name: 'DALL-E', provider: 'OpenAI', provider_display_name: 'Acme Images', model_id: 'dall-e-3' } },
  { id: 'replicate-image', is_enabled: true, model: { name: 'Flux', provider: 'Replicate', model_id: 'flux-1' } },
  { id: 'disabled', is_enabled: false, model: { name: 'Hidden', provider: 'OpenAI', model_id: 'hidden' } },
]

beforeEach(() => {
  states = []
  stateIndex = 0
  currentTeam = { id: 'team-1' }
  runEffect = true
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue(models)
  getAvailableVariables.mockClear()
})

test('loads enabled models by mode, groups, searches, and selects one', async () => {
  const onChange = mock(() => {})
  let current = render({ mode: 'image', prompt: '', outputVariable: 'result' }, onChange)
  expect(getTeamModels).toHaveBeenCalledWith('team-1', 'text_to_image')
  await settle()
  current = render({ mode: 'image', prompt: '', outputVariable: 'result' }, onChange)
  expect(findAll(current.tree, (node) => node.props.children === 'Acme Images')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'Replicate')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'Hidden')).toHaveLength(0)

  const choices = findAll(current.tree, (node) => node.type === 'button')
  ;(choices[1].props.onClick as () => void)()
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ modelId: 'replicate-image', modelName: 'Flux' }))

  const search = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.searchModel')[0]
  change(search, 'ACME IMAGES')
  states = [models, false, 'ACME IMAGES', false, false]
  runEffect = false
  current = render({ mode: 'image', prompt: '', outputVariable: 'result' }, onChange)
  expect(findAll(current.tree, (node) => node.props.children === 'DALL-E')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'Flux')).toHaveLength(0)

  states = []
  runEffect = true
  render({ mode: 'video', prompt: '', outputVariable: 'result' })
  expect(getTeamModels).toHaveBeenLastCalledWith('team-1', 'text_to_video')
})

test('handles model loading errors and a missing team', async () => {
  getTeamModels.mockRejectedValueOnce(new Error('offline'))
  render()
  await settle()
  let tree = render().tree
  expect(findAll(tree, (node) => node.props.children === 'configCommon.noAvailableModels')).toHaveLength(1)

  states = []
  getTeamModels.mockClear()
  currentTeam = null
  tree = render().tree
  expect(getTeamModels).not.toHaveBeenCalled()
  expect(findAll(tree, (node) => node.props.children === 'configCommon.noAvailableModels')).toHaveLength(1)
})

test('changes modes while clearing incompatible model and image settings', () => {
  const image = render({ mode: 'image', modelId: 'model', modelName: 'Model', referenceImageVariable: '{{start.image}}', startImageVariable: '{{old}}' })
  const videoButton = findAll(image.tree, (node) => node.type === component && node.props.variant === 'outline' && node.props.size === 'sm')[0]
  ;(videoButton.props.onClick as () => void)()
  expect(image.onChange).toHaveBeenCalledWith(expect.objectContaining({ mode: 'video', modelId: undefined, modelName: undefined, referenceImageVariable: undefined, startImageVariable: '{{old}}' }))

  const video = render({ mode: 'video', modelId: 'model', referenceImageVariable: '{{old}}', startImageVariable: '{{start.image}}' })
  const imageButton = findAll(video.tree, (node) => node.type === component && node.props.variant === 'outline' && node.props.size === 'sm')[0]
  ;(imageButton.props.onClick as () => void)()
  expect(video.onChange).toHaveBeenCalledWith(expect.objectContaining({ mode: 'image', modelId: undefined, referenceImageVariable: '{{old}}', startImageVariable: undefined }))
  expect(() => render({}, undefined)).not.toThrow()
})

test('forwards prompt variables and filters and selects image variables', () => {
  const image = render({ mode: 'image', prompt: 'Draw this', outputVariable: 'result' })
  expect(getAvailableVariables).toHaveBeenCalledWith('all')
  const prompt = findAll(image.tree, (node) => node.type === promptTextarea)[0]
  expect(prompt.props).toMatchObject({ value: 'Draw this', variables, minHeight: 'min-h-24' })
  ;(prompt.props.onChange as (value: string) => void)('Paint this')
  expect(image.onChange).toHaveBeenCalledWith(expect.objectContaining({ prompt: 'Paint this' }))

  const selector = findAll(image.tree, (node) => node.type === variableSelector)[0]
  expect((selector.props.variables as unknown[])).toHaveLength(5)
  ;(selector.props.onSelect as (variable: { id: string }) => void)({ id: 'start.image' })
  expect(image.onChange).toHaveBeenCalledWith(expect.objectContaining({ referenceImageVariable: '{{start.image}}' }))

  const video = render({ mode: 'video', startImageVariable: '{{start.file}}' })
  const videoSelector = findAll(video.tree, (node) => node.type === variableSelector)[0]
  expect(videoSelector.props.selectedValue).toBe('{{start.file}}')
  ;(videoSelector.props.onSelect as (variable: { id: string }) => void)({ id: 'start.upload' })
  expect(video.onChange).toHaveBeenCalledWith(expect.objectContaining({ startImageVariable: '{{start.upload}}' }))

  const empty = render({}, mock(() => {}))
  getAvailableVariables.mockImplementationOnce(() => [])
  const noVariables = render().tree
  expect(findAll(noVariables, (node) => node.props.children === 'configMediaGeneration.noImageVariables')).toHaveLength(1)
  expect(empty.tree).toBeDefined()
})

test('updates image settings and validates the output variable', () => {
  const current = render({ mode: 'image', width: 512, height: 512, numImages: 2, outputVariable: 'bad-name' })
  const numeric = findAll(current.tree, (node) => node.type === component && node.props.type === 'number')
  change(numeric[0], '1024')
  change(numeric[1], '')
  change(numeric[2], '0')
  expect(current.onChange).toHaveBeenNthCalledWith(1, expect.objectContaining({ width: 1024 }))
  expect(current.onChange).toHaveBeenNthCalledWith(2, expect.objectContaining({ height: undefined }))
  expect(current.onChange).toHaveBeenNthCalledWith(3, expect.objectContaining({ numImages: 1 }))
  expect(findAll(current.tree, (node) => node.props.children === 'configCommon.invalidVariableName')).toHaveLength(1)
  const output = findAll(current.tree, (node) => node.props.value === 'bad-name')[0]
  expect(String(output.props.className)).toContain('border-destructive!')
  change(output, 'valid_name')
  expect(current.onChange).toHaveBeenLastCalledWith(expect.objectContaining({ outputVariable: 'valid_name' }))
})

test('updates video duration and aspect ratio defaults', () => {
  const current = render({ mode: 'video', duration: 8, aspectRatio: '9:16', outputVariable: 'video' })
  const duration = findAll(current.tree, (node) => node.type === component && node.props.type === 'number')[0]
  change(duration, '')
  expect(current.onChange).toHaveBeenCalledWith(expect.objectContaining({ duration: 5 }))
  const aspectRatio = findAll(current.tree, (node) => node.type === component && node.props.value === '9:16' && node.props.onValueChange)[0]
  ;(aspectRatio.props.onValueChange as (value: string | null) => void)(null)
  expect(current.onChange).toHaveBeenLastCalledWith(expect.objectContaining({ aspectRatio: undefined }))
  expect(findAll(current.tree, (node) => ['16:9', '9:16', '1:1', '4:3', '3:4'].includes(String(node.props.children)))).toHaveLength(5)
})
