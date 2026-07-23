import { beforeEach, describe, expect, mock, test } from 'bun:test'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
const component = (name: string) => Object.assign(() => null, { displayName: name })

const Button = component('Button')
const Switch = component('Switch')
const Input = component('Input')
const Select = component('Select')
const PromptEditor = component('PromptEditor')
const PromptGenerateDialog = component('PromptGenerateDialog')
const VariableEditor = component('VariableEditor')
const AddVariableButton = component('AddVariableButton')
const KnowledgeBaseSelector = component('KnowledgeBaseSelector')
const AddKnowledgeBaseButton = component('AddKnowledgeBaseButton')
const ToolSelector = component('ToolSelector')
const AddToolButton = component('AddToolButton')

let states: unknown[] = []
let stateIndex = 0
let effects: Array<{ deps: unknown[]; cleanup?: () => void }> = []
let effectIndex = 0
let currentTeam: { id: string } | null = { id: 'team-1' }

const dependenciesChanged = (previous: unknown[] | undefined, next: unknown[]) =>
  !previous || previous.length !== next.length || previous.some((value, index) => value !== next[index])

const getKnowledgeBases = mock(() => Promise.resolve({ items: [] as Array<Record<string, unknown>> }))
const listFileParsers = mock(() => Promise.resolve([] as Array<Record<string, unknown>>))
const getTeamModels = mock(() => Promise.resolve([] as Array<Record<string, unknown>>))
const createNewVariable = mock((type: string) => ({ name: '', label: '', type, required: false }))
const availableTools = [
  { id: 'custom-1', type: 'custom', name: 'custom-tool', display_name: 'Custom Tool', description: 'Does work' },
  { id: 'mcp-1', type: 'mcp', name: 'mcp-tool' },
]

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [
      states[index] as T,
      (value: T | ((current: T) => T)) => {
        states[index] = typeof value === 'function'
          ? (value as (current: T) => T)(states[index] as T)
          : value
      },
    ] as const
  },
  useEffect: (effect: () => void | (() => void), deps: unknown[]) => {
    const index = effectIndex++
    if (dependenciesChanged(effects[index]?.deps, deps)) {
      effects[index]?.cleanup?.()
      const cleanup = effect()
      effects[index] = { deps, cleanup: typeof cleanup === 'function' ? cleanup : undefined }
    }
  },
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('next-intl', () => ({
  useLocale: () => 'zh',
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getKnowledgeBases },
  toolsApi: { listFileParsers },
  teamModelsApi: { getTeamModels },
}))
mock.module('lucide-react', () => ({
  Sparkles: component('Sparkles'), HelpCircle: component('HelpCircle'), ChevronRight: component('ChevronRight'),
  Database: component('Database'), Wrench: component('Wrench'), Eye: component('Eye'), Variable: component('Variable'),
  FileUp: component('FileUp'), MessageSquare: component('MessageSquare'), Brain: component('Brain'),
  ImageIcon: component('ImageIcon'), Clapperboard: component('Clapperboard'),
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/switch', () => ({ Switch }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/label', () => ({ Label: component('Label') }))
mock.module('@/components/ui/select', () => ({
  Select, SelectContent: component('SelectContent'), SelectItem: component('SelectItem'),
  SelectTrigger: component('SelectTrigger'), SelectValue: component('SelectValue'),
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: component('Tooltip'), TooltipContent: component('TooltipContent'), TooltipTrigger: component('TooltipTrigger'),
}))
mock.module('./variable-editor', () => ({ VariableEditor, AddVariableButton, createNewVariable }))
mock.module('./knowledge-base-selector', () => ({ KnowledgeBaseSelector, AddKnowledgeBaseButton }))
mock.module('./tool-selector', () => ({
  ToolSelector, AddToolButton, useTools: () => ({ tools: availableTools }),
}))
mock.module('./prompt-editor', () => ({ PromptEditor }))
mock.module('@/components/ai-elements/prompt-generate-dialog', () => ({ PromptGenerateDialog }))

const { AgentOrchestrationForm } = await import('./agent-orchestration-form')

const agent = {
  id: 'agent-1',
  name: 'Researcher',
  description: 'Find evidence',
  system_prompt: '',
  variables: [],
  knowledge_bases: [],
  tools_config: [],
  enable_vision: false,
  enable_file_upload: false,
  enable_user_input_request: false,
  enable_memory: false,
  enable_image_generation: false,
  enable_video_generation: false,
  rag_mode: 'agentic',
} as never

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children), ...descendants(node.props.action)]
}

function render(onUpdate = mock(() => undefined), currentAgent = agent) {
  stateIndex = 0
  effectIndex = 0
  return {
    tree: AgentOrchestrationForm({ agent: currentAgent, onUpdate }) as Node,
    onUpdate,
  }
}

const find = (tree: Node, type: unknown) => descendants(tree).filter((node) => node.type === type)
const findByTestId = (tree: Node, testId: string) => descendants(tree).find((node) => node.props['data-testid'] === testId)!
const renderComponent = (node: Node) => (node.type as (props: Record<string, unknown>) => Node)(node.props)
const change = (node: Node, value: string) =>
  (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  states = []
  effects = []
  currentTeam = { id: 'team-1' }
  getKnowledgeBases.mockReset()
  getKnowledgeBases.mockResolvedValue({ items: [] })
  listFileParsers.mockReset()
  listFileParsers.mockResolvedValue([])
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue([])
  createNewVariable.mockClear()
})

describe('AgentOrchestrationForm', () => {
  test('publishes normalized defaults and skips team data loading without a team', () => {
    currentTeam = null
    const { onUpdate } = render()

    expect(getKnowledgeBases).not.toHaveBeenCalled()
    expect(onUpdate).toHaveBeenLastCalledWith(expect.objectContaining({
      system_prompt: null,
      knowledge_base_configs: [],
      tools_config: [],
      enable_memory: false,
      memory_config: null,
      enable_file_upload: false,
      file_upload_config: null,
      image_generation_config: null,
      video_generation_config: null,
      rag_mode: 'agentic',
    }))
  })

  test('loads only current-team resources and tolerates a rejected resource request', async () => {
    getKnowledgeBases.mockResolvedValue({
      items: [
        { id: 'kb-1', name: 'Current', team: { id: 'team-1' } },
        { id: 'kb-2', name: 'Other', team: { id: 'team-2' } },
      ],
    })
    listFileParsers.mockResolvedValue([{ id: 'parser-1', type: 'custom', name: 'parser' }])
    getTeamModels
      .mockResolvedValueOnce([{ id: 'image-team-model', model: { id: 'image-1', name: 'Image One' } }])
      .mockResolvedValueOnce([{ id: 'video-team-model', model: { id: 'video-1', name: 'Video One' } }])

    render()
    await flush()
    const { tree } = render()

    expect(getKnowledgeBases).toHaveBeenCalledTimes(1)
    expect(listFileParsers).toHaveBeenCalledWith('team-1')
    expect(getTeamModels.mock.calls).toEqual([
      ['team-1', 'text_to_image'],
      ['team-1', 'text_to_video'],
    ])
    expect(find(tree, AddKnowledgeBaseButton)[0].props.knowledgeBases).toEqual([
      expect.objectContaining({ id: 'kb-1' }),
    ])

    effects = []
    states = []
    getKnowledgeBases.mockRejectedValue(new Error('offline'))
    render()
    await flush()
    expect(states[27]).toEqual([])
  })

  test('applies prompt, variable, knowledge-base, and every tool-kind callback', () => {
    const onUpdate = mock(() => undefined)
    let tree = render(onUpdate).tree

    const dialog = find(tree, PromptGenerateDialog)[0]
    ;(dialog.props.onApply as (value: string) => void)('Generated prompt')
    const promptEditor = find(tree, PromptEditor)[0]
    ;(promptEditor.props.onAddVariable as (name: string, type: string) => void)('topic', 'text')
    const addKnowledgeBase = find(tree, AddKnowledgeBaseButton)[0]
    ;(addKnowledgeBase.props.onAdd as (kb: { id: string }) => void)({ id: 'kb-9' })

    tree = render(onUpdate).tree
    for (const tool of [
      { id: 'builtin-1', type: 'builtin', name: 'search' },
      { id: 'mcp-1', type: 'mcp', name: 'server' },
      { id: 'skill-1', type: 'skill', name: 'writer' },
      { id: 'custom-1', type: 'custom', name: 'custom' },
    ]) {
      const addTool = find(tree, AddToolButton)[0]
      ;(addTool.props.onAdd as (value: typeof tool) => void)(tool)
      tree = render(onUpdate).tree
    }

    expect(createNewVariable).toHaveBeenCalledWith('text', [], ['variables.defaultOptions.option1', 'variables.defaultOptions.option2'])
    expect(onUpdate).toHaveBeenLastCalledWith(expect.objectContaining({
      system_prompt: 'Generated prompt',
      variables: [expect.objectContaining({ name: 'topic', label: 'topic', type: 'text' })],
      knowledge_base_configs: [{ knowledge_base_id: 'kb-9', retrieval_top_k: 3, score_threshold: 0.3, search_mode: 'hybrid' }],
      tools_config: [
        { type: 'builtin', name: 'search' },
        { type: 'mcp', server_id: 'mcp-1' },
        { type: 'skill', skill_id: 'skill-1', name: 'writer' },
        { type: 'custom', tool_id: 'custom-1', name: 'custom' },
      ],
    }))

    const latestAddTool = find(tree, AddToolButton)[0]
    ;(latestAddTool.props.onRemove as (value: { id: string; type: string; name: string }) => void)(
      { id: 'mcp-1', type: 'mcp', name: 'server' },
    )
    render(onUpdate)
    expect(onUpdate.mock.calls.at(-1)?.[0].tools_config).not.toContainEqual({ type: 'mcp', server_id: 'mcp-1' })
  })

  test('clamps enabled capability inputs and ignores invalid truncate values', () => {
    const enabledAgent = {
      ...agent,
      enable_file_upload: true,
      enable_memory: true,
      enable_image_generation: true,
      enable_video_generation: true,
    } as never
    const onUpdate = mock(() => undefined)
    let tree = render(onUpdate, enabledAgent).tree
    const inputs = find(tree, Input)
    const byBounds = (min: number, max: number) => inputs.find((node) => node.props.min === min && node.props.max === max)!

    ;(byBounds(1000, 500000).props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '999999' } })
    ;(byBounds(1, 50).props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '0' } })
    ;(byBounds(256, 4096).props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '100' } })
    ;(byBounds(500, 30000).props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '99999' } })

    tree = render(onUpdate, enabledAgent).tree
    const truncateSelect = find(tree, Select).find((node) => node.props.value === 'end')!
    ;(truncateSelect.props.onValueChange as (value: string) => void)('invalid')
    render(onUpdate, enabledAgent)

    expect(onUpdate).toHaveBeenLastCalledWith(expect.objectContaining({
      file_upload_config: expect.objectContaining({ max_content_length: 500000, truncate_strategy: 'end' }),
      memory_config: expect.objectContaining({ max_memories_per_retrieval: 10 }),
      image_generation_config: expect.objectContaining({ default_width: 256 }),
      video_generation_config: expect.objectContaining({ poll_interval_ms: 30000 }),
    }))
  })

  test('covers card actions, selection callbacks, and all remaining validation bounds', async () => {
    getKnowledgeBases.mockResolvedValue({ items: [{ id: 'kb-1', name: 'Docs', description: 'Evidence', team: { id: 'team-1' } }] })
    listFileParsers.mockResolvedValue([{ id: 'parser-1', type: 'custom', name: 'parser', display_name: 'Parser' }])
    getTeamModels
      .mockResolvedValueOnce([{ id: 'image-team-model', model: { id: 'image-1', name: 'Image One' } }])
      .mockResolvedValueOnce([{ id: 'video-team-model', model: { id: 'video-1', name: 'Video One' } }])
    const enabledAgent = {
      ...agent,
      knowledge_bases: [{ knowledge_base: { id: 'kb-1' }, retrieval_top_k: 3, score_threshold: 0.3, search_mode: 'hybrid' }],
      enable_file_upload: true,
      enable_memory: true,
      enable_image_generation: true,
      enable_video_generation: true,
      image_generation_config: {
        default_model_ref: 'missing-image', default_width: 1024, default_height: 1024,
        max_images: 4, allow_reference_images: true, allowed_providers: [], require_confirmation: false,
      },
      video_generation_config: {
        default_model_ref: 'missing-video', default_duration: 5, max_duration: 10,
        default_aspect_ratio: '16:9', poll_interval_ms: 3000, poll_timeout_s: 120,
        allowed_providers: [], require_confirmation: false,
      },
    } as never
    const onUpdate = mock(() => undefined)
    render(onUpdate, enabledAgent)
    await flush()
    let tree = render(onUpdate, enabledAgent).tree

    for (const testId of [
      'agent-variables-section', 'agent-kb-section', 'agent-tools-section', 'agent-vision-section',
      'agent-file-upload-section', 'agent-user-input-section', 'agent-memory-section',
      'agent-image-generation-section', 'agent-video-generation-section',
    ]) {
      const card = findByTestId(tree, testId)
      ;(card.props.onToggle as () => void)()
      tree = render(onUpdate, enabledAgent).tree
    }

    const addVariable = find(tree, AddVariableButton)[0]
    ;(addVariable.props.onAdd as (type: string) => void)('select')
    tree = render(onUpdate, enabledAgent).tree
    const variableEditor = find(tree, VariableEditor)[0]
    ;(variableEditor.props.onEditingIndexChange as (index: number | null) => void)(null)
    ;(variableEditor.props.onChange as (variables: unknown[]) => void)([{ name: 'region', type: 'text' }])

    const select = (value: string) => find(tree, Select).find((node) => node.props.value === value)!
    const choose = (current: string, next: string) => {
      ;(select(current).props.onValueChange as (value: string) => void)(next)
      tree = render(onUpdate, enabledAgent).tree
    }
    const input = (min: number, max: number, index = 0) =>
      find(tree, Input).filter((node) => node.props.min === min && node.props.max === max)[index]
    const enter = (min: number, max: number, value: string, index = 0) => {
      change(input(min, max, index), value)
      tree = render(onUpdate, enabledAgent).tree
    }

    choose('agentic', 'auto')
    expect(onUpdate.mock.calls.at(-1)?.[0].rag_mode).toBe('auto')
    choose('builtin:markitdown', 'custom:parser-1')
    expect(onUpdate.mock.calls.at(-1)?.[0].file_upload_config.parser).toEqual({ type: 'custom', tool_id: 'parser-1' })
    choose('custom:parser-1', '')
    choose('end', 'middle')
    expect(onUpdate.mock.calls.at(-1)?.[0].file_upload_config).toEqual(expect.objectContaining({ parser: null, truncate_strategy: 'middle' }))
    choose('missing-image', 'image-1')
    choose('missing-video', '__default__')
    choose('16:9', '9:16')
    enter(256, 4096, '9999', 1)
    enter(1, 10, '-5')
    expect(onUpdate.mock.calls.at(-1)?.[0].image_generation_config).toEqual(expect.objectContaining({ default_model_ref: 'image-1', default_height: 4096, max_images: 1 }))
    enter(1, 30, '99')
    enter(1, 30, '-5', 1)
    enter(5, 600, '9999')

    const payload = onUpdate.mock.calls.at(-1)?.[0]
    expect(payload).toEqual(expect.objectContaining({
      rag_mode: 'auto',
      variables: [{ name: 'region', type: 'text' }],
      file_upload_config: expect.objectContaining({ parser: null, truncate_strategy: 'middle' }),
      image_generation_config: expect.objectContaining({ default_model_ref: 'image-1', default_height: 4096, max_images: 1 }),
      video_generation_config: expect.objectContaining({ default_model_ref: null, default_duration: 30, max_duration: 1, default_aspect_ratio: '9:16', poll_timeout_s: 600 }),
    }))

    const promptButton = find(tree, Button).find((node) => node.props['data-testid'] === 'agent-prompt-ai-generate')!
    ;(promptButton.props.onClick as () => void)()
    tree = render(onUpdate, enabledAgent).tree
    expect(find(tree, PromptGenerateDialog)[0].props.open).toBe(true)
    expect(find(tree, PromptGenerateDialog)[0].props.context).toEqual(expect.objectContaining({
      agent_name: 'Researcher',
      knowledge_bases: [expect.objectContaining({ name: 'Docs', config: expect.objectContaining({ knowledge_base_id: 'kb-1' }) })],
      rag_mode: 'auto',
    }))

    const renderedCard = renderComponent(findByTestId(tree, 'agent-variables-section'))
    expect(renderedCard.props['data-testid']).toBe('agent-variables-section')
  })

  test('synchronizes replacement agent data and reloads after team/API recovery', async () => {
    getKnowledgeBases.mockRejectedValueOnce(new Error('forbidden'))
    const onUpdate = mock(() => undefined)
    render(onUpdate)
    await flush()
    expect(states[27]).toEqual([])

    currentTeam = { id: 'team-2' }
    getKnowledgeBases.mockResolvedValue({ items: [{ id: 'kb-2', name: 'Recovered', team: { id: 'team-2' } }] })
    effects = []
    render(onUpdate)
    await flush()
    let tree = render(onUpdate).tree
    expect(find(tree, AddKnowledgeBaseButton)[0].props.knowledgeBases).toEqual([expect.objectContaining({ id: 'kb-2' })])

    const replacement = {
      ...agent,
      system_prompt: 'Replacement',
      variables: [{ name: 'query', type: 'text' }],
      knowledge_bases: [{ knowledge_base: { id: 'kb-2' }, retrieval_top_k: 7, score_threshold: 0.8, search_mode: null }],
      tools_config: [{ type: 'skill', skill_id: 'skill-1', name: 'writer' }],
      enable_vision: true,
      rag_mode: 'off',
    } as never
    tree = render(onUpdate, replacement).tree
    tree = render(onUpdate, replacement).tree
    expect(find(tree, PromptEditor)[0].props.value).toBe('Replacement')
    expect(onUpdate).toHaveBeenLastCalledWith(expect.objectContaining({
      variables: [{ name: 'query', type: 'text' }],
      knowledge_base_configs: [{ knowledge_base_id: 'kb-2', retrieval_top_k: 7, score_threshold: 0.8, search_mode: 'hybrid' }],
      tools_config: [{ type: 'skill', skill_id: 'skill-1', name: 'writer' }],
      enable_vision: true,
      rag_mode: 'off',
    }))
  })
})
