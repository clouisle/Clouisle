import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { RunDetailResponse, RunSummary, ToolPayloadDetail, TrajectoryEntry, TrajectoryEntryDetail } from '@/lib/api/admin/observability'

const translate = Object.assign((key: string) => key, { has: () => false })
const push = mock<(url: string) => void>(() => {})

const run: RunSummary = {
  run_id: 'run-1',
  source: 'agent',
  resource_id: 'agent-1',
  resource_name: 'Support agent',
  team_id: 'team-1',
  team_name: 'Support',
  status: 'failed',
  submitted_at: '2026-10-08T10:30:00Z',
  started_at: '2026-10-08T10:30:01Z',
  message_started_at: null,
  worker_bootstrap_ms: null,
  finished_at: '2026-10-08T10:30:03Z',
  queue_duration_ms: 1000,
  execution_duration_ms: 2000,
  total_duration_ms: 3000,
  first_token_ms: 350,
  total_tokens: 22,
  error_category: 'provider',
  error_code: 'UPSTREAM',
  trace_available: true,
  trace_complete: true,
}

const modelEntry: TrajectoryEntry = {
  id: 'model-1',
  parent_id: null,
  kind: 'model',
  name: 'Model call 1',
  status: 'completed',
  started_at: '2026-10-08T10:30:01.000Z',
  finished_at: '2026-10-08T10:30:02.200Z',
  duration_ms: 1200,
  model: 'gpt-test',
  token_usage: { prompt: 10, completion: 5, total: 15 },
  tool_call_ids: ['call-1'],
  payload_state: 'recorded',
  preview: 'User asks about the weather',
}

const toolEntry: TrajectoryEntry = {
  id: 'tool-1',
  parent_id: 'model-1',
  kind: 'tool',
  name: 'weather',
  status: 'failed',
  started_at: '2026-10-08T10:30:02.000Z',
  finished_at: '2026-10-08T10:30:02.300Z',
  duration_ms: 300,
  model: null,
  token_usage: null,
  tool_call_ids: ['call-1'],
  payload_state: 'recorded',
  preview: 'Paris lookup',
}

const modelDetail: TrajectoryEntryDetail = {
  id: 'model-1',
  kind: 'model',
  input: {
    model: 'gpt-test',
    model_id: 'model-row-1',
    provider: 'test',
    streaming: true,
    scope: 'application',
    fallback: true,
    messages: [
      { role: 'system', content: 'You are a helpful assistant' },
      { role: 'user', content: 'What is the weather in Paris?' },
      { role: 'tool', content: 'sunny 21C', tool_call_id: 'call-1', name: 'weather' },
    ],
    tools: [
      { type: 'function', function: { name: 'weather', description: 'Weather lookup', parameters: { city: 'string' } } },
      { type: 'function', function: { name: 'search', description: 'Search' } },
    ],
    options: { temperature: 0.2 },
    limits: { context_limit: 128000, configured_max_output_tokens: 4096 },
  },
  output: {
    content: 'It is sunny in Paris',
    reasoning: 'Use the weather tool result',
    tool_calls: [{ id: 'call-1', name: 'weather', arguments: '{"city":"Paris"}' }],
    finish_reason: 'tool_calls',
    error: 'provider timeout',
  },
  partial: false,
  recorded: true,
}

const toolDetail: TrajectoryEntryDetail = {
  id: 'tool-1',
  kind: 'tool',
  input: { tool_call_id: 'call-1', name: 'weather', arguments: '{"city":"Paris"}' },
  output: { tool_call_id: 'call-1', tool_name: 'weather', display: '巴黎 晴 21°C', model_input: 'sunny 21C' },
  partial: true,
  recorded: true,
}

const retrievalEntry: TrajectoryEntry = {
  ...toolEntry,
  id: 'retrieval-1',
  kind: 'retrieval',
  name: 'knowledge_search',
  status: 'completed',
  tool_call_ids: ['call-retrieval'],
  preview: 'Refund policy lookup',
}

const retrievalDetail: TrajectoryEntryDetail = {
  id: 'retrieval-1',
  kind: 'retrieval',
  input: { tool_call_id: 'call-retrieval', name: 'knowledge_search', arguments: '{"query":"refund policy"}' },
  output: { tool_name: 'knowledge_search', display: 'Policy excerpt', model_input: 'Refund policy text' },
  partial: false,
  recorded: true,
}

const workflowEntry: TrajectoryEntry = {
  ...modelEntry,
  id: 'node-1',
  kind: 'workflow_node',
  name: 'LLM node',
  tool_call_ids: [],
  status: 'completed',
  token_usage: { total: 8 },
  preview: 'Summarize the ticket',
}

const workflowDetail: TrajectoryEntryDetail = {
  id: 'node-1',
  kind: 'workflow_node',
  input: {
    node_type: 'llm',
    node_name: 'LLM node',
    config: { prompt: 'Summarize {{text}}', model: 'gpt-test' },
    inputs: { text: 'Customer cannot log in' },
  },
  output: { outputs: { text: 'Login issue summary' }, model_used: 'gpt-test', token_usage: { total: 8 }, error_type: 'provider', error_message: 'rate limited' },
  partial: false,
  recorded: true,
}

const meta = { window_start: '2026-10-08T10:00:00Z', window_end: '2026-10-08T11:00:00Z', sampled_at: '2026-10-08T11:00:00Z', period: '1h', state: 'fresh' as const, sample_count: 4 }

const getRun = mock(async (): Promise<RunDetailResponse> => ({
  run,
  spans: [],
  trajectory: [modelEntry, toolEntry],
  trace: { complete: true, expired: false, truncated: true, recorded_count: 2 },
  meta,
}))
const getTrajectoryEntry = mock(async (_source: string, _runId: string, entryId: string): Promise<TrajectoryEntryDetail> => entryId === 'tool-1' ? toolDetail : modelDetail)
const getRunToolPayload = mock(async () => ({ tool_call_id: 'call-1', tool_name: 'weather', display: '巴黎 晴 21°C', model_input: 'sunny 21C', display_bytes: 12, model_bytes: 8, model_sha256: null, renderer: null, eof: true, has_cursor: false, partial: false, error: null, recorded: true }))

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => translate }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }), useSearchParams: () => new URLSearchParams('tab=runs&period=24h') }))
mock.module('lucide-react', () => {
  const Icon = () => null
  return { AlertTriangle: Icon, ArrowLeft: Icon, Clock3: Icon, RefreshCw: Icon, Search: Icon }
})
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange?: (value: string) => void }>) => (
    <div data-select-root data-selected-value={value} onValueChange={onValueChange}>{children}</div>
  ),
  SelectTrigger: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-value={value}>{children}</div>,
}))
const TabContext = React.createContext<{ value: string; onChange: (value: string) => void }>({ value: '', onChange: () => {} })
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => (
    <TabContext.Provider value={{ value, onChange: onValueChange }}>{children}</TabContext.Provider>
  ),
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: React.PropsWithChildren<{ value: string }>) => {
    const context = React.useContext(TabContext)
    return <button data-tab={value} aria-pressed={context.value === value} onClick={() => context.onChange(value)}>{children}</button>
  },
}))
mock.module('@/lib/api/admin/observability', () => ({ observabilityApi: { getRun, getTrajectoryEntry, getRunToolPayload } }))

// Import after registering mocks: bun's mock.module must be installed before the component graph resolves.
const { RunInspector } = await import('./run-inspector')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function render(source = 'agent', runId = 'run-1', selectFirst = true) {
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<RunInspector source={source} runId={runId} />) })
  await flush()
  if (selectFirst) {
    const first = renderer!.root.findAll((node) => node.type === 'button' && typeof node.props['data-step-id'] === 'string')[0]
    if (first) {
      await act(async () => { first.props.onClick(); await Promise.resolve() })
      await flush()
    }
  }
  return renderer!
}

const row = (renderer: ReactTestRenderer, id: string) => renderer.root.findByProps({ 'data-step-id': id })
const tab = (renderer: ReactTestRenderer, value: string) => renderer.root.findByProps({ 'data-tab': value })
const renderedText = (renderer: ReactTestRenderer) => renderer.root
  .findAll(() => true)
  .flatMap((node) => node.children.filter((child): child is string => typeof child === 'string'))
  .join('\n')

afterEach(() => {
  mock.clearAllMocks()
})

test('keeps steps full-width without loading details until a step is clicked', async () => {
  const renderer = await render('agent', 'run-1', false)
  expect(getTrajectoryEntry).not.toHaveBeenCalled()
  expect(renderer.root.findAllByProps({ 'data-tab': 'preview' })).toHaveLength(0)
  await act(async () => { row(renderer, 'tool-1').props.onClick(); await Promise.resolve() })
  await flush()
  expect(getTrajectoryEntry).toHaveBeenLastCalledWith('agent', 'run-1', 'tool-1')
  expect(tab(renderer, 'preview')).toBeDefined()
  act(() => renderer.unmount())
})

test('renders the run summary, timeline lanes, numbered steps, and selection-linked summary', async () => {
  const renderer = await render()
  await flush()
  expect(getRun).toHaveBeenCalledWith('agent', 'run-1')
  expect(getTrajectoryEntry).toHaveBeenCalledWith('agent', 'run-1', 'model-1')
  const rendered = renderedText(renderer)
  expect(rendered).toContain('Support agent')
  expect(rendered).toContain('runInspector.timeline.title')
  expect(rendered).toContain('runInspector.timeline.input')
  expect(renderer.root.findAllByProps({ 'aria-label': 'runInspector.timeline.inputBoundary: Model call 1' }).length).toBeGreaterThan(0)
  expect(rendered).toContain('runInspector.trace.truncated')
  expect(rendered).toContain('runInspector.steps.callNumber')
  expect(rendered).toContain('runInspector.steps.toolNumber')
  expect(rendered).toContain('1.20 s')
  expect(rendered).toContain('300 ms')
  expect(rendered).toContain('User asks about the weather')
  expect(rendered).toContain('runInspector.inspector.payloadPreview')
  expect(rendered).toContain('What is the weather in Paris?')
  expect(rendered).toContain('It is sunny in Paris')
  expect(rendered).toContain('runInspector.inspector.toolCalls')
  expect(rendered).toContain('call-1')
  const callLink = renderer.root.findAllByType('button').find((node) => node.children.includes('call-1'))
  expect(callLink).toBeDefined()
  await act(async () => { callLink!.props.onClick(); await Promise.resolve() })
  await flush()
  expect(getTrajectoryEntry).toHaveBeenLastCalledWith('agent', 'run-1', 'tool-1')
  act(() => renderer.unmount())
})

test('shows the actual model message list and response in preview, with raw JSON on demand', async () => {
  const renderer = await render()
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  const preview = renderedText(renderer)
  expect(preview).toContain('You are a helpful assistant')
  expect(preview).toContain('What is the weather in Paris?')
  expect(preview).toContain('sunny 21C')
  expect(preview).toContain('It is sunny in Paris')
  expect(preview).toContain('weather')
  expect(preview).toContain('Weather lookup')
  expect(preview).toContain('{"city":"Paris"}')
  expect(preview).toContain('runInspector.inspector.messages')
  expect(preview).toContain('runInspector.inspector.reasoning')
  expect(preview).toContain('runInspector.inspector.modelScope')
  expect(preview).toContain('runInspector.inspector.fallbackInvocation')
  expect(preview).toContain('model-row-1')
  expect(preview).toContain('runInspector.inspector.limits')
  expect(preview).toContain('runInspector.inspector.limitsNote')
  expect(preview).toContain('runInspector.inspector.modelError')
  expect(preview).toContain('provider timeout')
  await act(async () => { tab(renderer, 'raw').props.onClick(); await Promise.resolve() })
  expect(renderedText(renderer)).toContain('"messages"')
  act(() => renderer.unmount())
})

test('renders retrieval payloads with tool request and result context', async () => {
  getRun.mockResolvedValueOnce({
    run,
    spans: [],
    trajectory: [retrievalEntry],
    trace: { complete: true, expired: false, truncated: false, recorded_count: 1 },
    meta,
  })
  getTrajectoryEntry.mockResolvedValueOnce(retrievalDetail)
  const renderer = await render()
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  const preview = renderedText(renderer)
  expect(preview).toContain('knowledge_search')
  expect(preview).toContain('{"query":"refund policy"}')
  expect(preview).toContain('runInspector.inspector.modelResult')
  expect(preview).toContain('Refund policy text')
  expect(preview).toContain('Policy excerpt')
  act(() => renderer.unmount())
})

test('renders workflow node config, inputs, and outputs without chat roles', async () => {
  getRun.mockResolvedValueOnce({
    run: { ...run, source: 'workflow', resource_name: 'Ticket workflow' },
    spans: [],
    trajectory: [workflowEntry],
    trace: { complete: true, expired: false, truncated: false, recorded_count: 1 },
    meta,
  })
  getTrajectoryEntry.mockResolvedValueOnce(workflowDetail)
  const renderer = await render('workflow', 'run-1')
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  const preview = renderedText(renderer)
  expect(preview).toContain('runInspector.timeline.nodes')
  expect(preview).toContain('runInspector.inspector.nodeType')
  expect(preview).toContain('llm')
  expect(preview).toContain('runInspector.inspector.config')
  expect(preview).toContain('Summarize {{text}}')
  expect(preview).toContain('Customer cannot log in')
  expect(preview).toContain('Login issue summary')
  expect(preview).toContain('runInspector.inspector.tokens')
  expect(preview).toContain('runInspector.inspector.errorMessage')
  expect(preview).toContain('rate limited')
  expect(preview).not.toContain('"role"')
  act(() => renderer.unmount())
})

test('marks storage-only workflow payloads as partial and unavailable', async () => {
  getRun.mockResolvedValueOnce({
    run: { ...run, source: 'workflow', resource_name: 'Ticket workflow' },
    spans: [],
    trajectory: [workflowEntry],
    trace: { complete: false, expired: false, truncated: true, recorded_count: 1 },
    meta,
  })
  getTrajectoryEntry.mockResolvedValueOnce({
    id: 'node-1',
    kind: 'workflow_node',
    input: { node_type: 'llm', inputs_storage_key: 'kb://node-1/inputs.json' },
    output: { outputs_storage_key: 'kb://node-1/outputs.json' },
    partial: true,
    recorded: false,
  })
  const renderer = await render('workflow', 'run-1')
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  const preview = renderedText(renderer)
  expect(preview).toContain('runInspector.inspector.partial')
  expect(preview).toContain('runInspector.inspector.unrecorded')
  expect(preview).toContain('runInspector.inspector.storedUnavailable')
  expect(preview).toContain('kb://node-1/inputs.json')
  expect(preview).toContain('kb://node-1/outputs.json')
  act(() => renderer.unmount())
})

test('filters steps by type, name, and failures while keeping selection linked', async () => {
  const renderer = await render()
  expect(row(renderer, 'model-1')).toBeDefined()
  expect(row(renderer, 'tool-1')).toBeDefined()
  const select = renderer.root.findAllByProps({ 'data-select-root': true })[0]!
  await act(async () => { select.props.onValueChange('tool'); await Promise.resolve() })
  await flush()
  expect(renderer.root.findAllByProps({ 'data-step-id': 'model-1' })).toHaveLength(0)
  expect(row(renderer, 'tool-1')).toBeDefined()
  await act(async () => { row(renderer, 'tool-1').props.onClick(); await Promise.resolve() })
  await flush()
  expect(getTrajectoryEntry).toHaveBeenLastCalledWith('agent', 'run-1', 'tool-1')

  const name = renderer.root.findByProps({ 'aria-label': 'runInspector.steps.filterName' })
  await act(async () => { name.props.onChange({ target: { value: 'nope' } }); await Promise.resolve() })
  expect(renderedText(renderer)).toContain('runInspector.steps.empty')
  await act(async () => { name.props.onChange({ target: { value: '' } }); await Promise.resolve() })
  await act(async () => { select.props.onValueChange('all'); await Promise.resolve() })
  const failures = renderer.root.findAllByType('button').find((node) => node.children.includes('runInspector.steps.failuresOnly'))
  expect(failures).toBeDefined()
  await act(async () => { failures!.props.onClick(); await Promise.resolve() })
  expect(renderer.root.findAllByProps({ 'data-step-id': 'model-1' })).toHaveLength(0)
  expect(row(renderer, 'tool-1')).toBeDefined()
  act(() => renderer.unmount())
})

test('clears active filters when a linked parent would otherwise be hidden', async () => {
  const renderer = await render()
  const select = renderer.root.findAllByProps({ 'data-select-root': true })[0]!
  await act(async () => { select.props.onValueChange('tool'); await Promise.resolve() })
  await flush()
  expect(row(renderer, 'tool-1')).toBeDefined()
  await act(async () => { row(renderer, 'tool-1').props.onClick(); await Promise.resolve() })
  await flush()
  const parentLink = renderer.root.findAllByType('button').find((node) => node.children.includes('Model call 1'))
  expect(parentLink).toBeDefined()
  await act(async () => { parentLink!.props.onClick(); await Promise.resolve() })
  await flush()
  expect(getTrajectoryEntry).toHaveBeenLastCalledWith('agent', 'run-1', 'model-1')
  expect(renderer.root.findAllByProps({ 'data-select-root': true })[0]!.props['data-selected-value']).toBe('all')
  expect(row(renderer, 'model-1')).toBeDefined()
  act(() => renderer.unmount())
})

test('shows explicit unrecorded payloads and legacy spans when no trajectory exists', async () => {
  getRun.mockResolvedValueOnce({
    run,
    spans: [{ span_id: 'span-1', parent_span_id: null, kind: 'tool', name: 'Legacy HTTP request', status: 'completed', started_at: '2026-10-08T10:30:01Z', finished_at: '2026-10-08T10:30:02Z', duration_ms: 1000, attempt: null, model: null, tool: 'http', error_category: null, token_usage: null, metadata: { tool_call_id: 'call-1' } }],
    trajectory: [],
    trace: { complete: false, expired: true, truncated: false, recorded_count: 1 },
    meta,
  })
  const renderer = await render()
  const rendered = renderedText(renderer)
  expect(rendered).toContain('runInspector.steps.legacyTitle')
  expect(rendered).toContain('runInspector.steps.legacyNotice')
  expect(rendered).toContain('Legacy HTTP request')
  expect(rendered).toContain('runInspector.trace.expired')
  expect(getTrajectoryEntry).not.toHaveBeenCalled()
  act(() => renderer.unmount())
})

test('keeps the latest selected payload when earlier requests settle late', async () => {
  const pendingModel = Promise.withResolvers<TrajectoryEntryDetail>()
  const pendingTool = Promise.withResolvers<TrajectoryEntryDetail>()
  getTrajectoryEntry.mockImplementation((_source: string, _runId: string, entryId: string) => entryId === 'tool-1' ? pendingTool.promise : pendingModel.promise)
  const renderer = await render()
  await act(async () => { row(renderer, 'tool-1').props.onClick(); await Promise.resolve() })
  await act(async () => {
    pendingTool.resolve(toolDetail)
    await Promise.resolve()
  })
  await act(async () => {
    pendingModel.resolve(modelDetail)
    await Promise.resolve()
  })
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  const preview = renderedText(renderer)
  expect(preview).toContain('巴黎 晴 21°C')
  expect(preview).not.toContain('You are a helpful assistant')
  act(() => renderer.unmount())
})

test('renders a direct-route not-found state and returns to the runs list', async () => {
  getRun.mockRejectedValueOnce(Object.assign(new Error('not found'), { status: 404 }))
  const renderer = await render()
  const rendered = renderedText(renderer)
  expect(rendered).toContain('runInspector.notFound')
  expect(rendered).toContain('runInspector.back')
  const back = renderer.root.findAllByType('button').find((node) => node.children.includes('runInspector.back'))
  await act(async () => { back!.props.onClick(); await Promise.resolve() })
  expect(push).toHaveBeenCalledWith('/dashboard/observability?tab=runs&period=24h')
  act(() => renderer.unmount())
})

test('does not show a previous legacy tool result while a new call loads', async () => {
  const unrecordedTool = { ...toolEntry, payload_state: 'unrecorded', status: 'completed' }
  const secondTool = { ...unrecordedTool, id: 'tool-2', name: 'search', tool_call_ids: ['call-2'], preview: 'Second lookup' }
  getRun.mockResolvedValueOnce({
    run,
    spans: [],
    trajectory: [unrecordedTool, secondTool],
    trace: { complete: false, expired: false, truncated: false, recorded_count: 2 },
    meta,
  })
  getTrajectoryEntry.mockImplementation(async (_source: string, _runId: string, entryId: string): Promise<TrajectoryEntryDetail> => ({
    id: entryId,
    kind: 'tool',
    input: null,
    output: null,
    partial: true,
    recorded: false,
  }))
  const second = Promise.withResolvers<ToolPayloadDetail>()
  const legacy = (toolCallId: string, text: string): ToolPayloadDetail => ({
    tool_call_id: toolCallId,
    tool_name: 'weather',
    display: null,
    model_input: text,
    display_bytes: 0,
    model_bytes: text.length,
    model_sha256: null,
    renderer: null,
    eof: true,
    has_cursor: false,
    partial: false,
    error: null,
    recorded: true,
  })
  getRunToolPayload.mockImplementation((_source: string, _runId: string, toolCallId: string) => (
    toolCallId === 'call-2' ? second.promise : Promise.resolve(legacy('call-1', 'first legacy result'))
  ))

  const renderer = await render()
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  expect(renderedText(renderer)).toContain('first legacy result')

  await act(async () => { row(renderer, 'tool-2').props.onClick(); await Promise.resolve() })
  await act(async () => { tab(renderer, 'preview').props.onClick(); await Promise.resolve() })
  await flush()
  expect(renderedText(renderer)).not.toContain('first legacy result')

  await act(async () => {
    second.resolve(legacy('call-2', 'second legacy result'))
    await Promise.resolve()
  })
  await flush()
  expect(renderedText(renderer)).toContain('second legacy result')
  act(() => renderer.unmount())
})
