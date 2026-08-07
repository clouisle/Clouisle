import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const fetchMock = mock<typeof fetch>()
const eventSources: FakeEventSource[] = []

class FakeEventSource {
  listeners = new Map<string, (event: MessageEvent) => void>()
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  closed = false

  constructor(public url: string) {
    eventSources.push(this)
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, listener)
  }

  close() {
    this.closed = true
  }

  emit(type: string, data: Record<string, unknown>) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent)
  }
}

Object.assign(globalThis, { fetch: fetchMock, EventSource: FakeEventSource })

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({
  default: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a>,
}))
const Icon = (props: React.ComponentProps<'svg'>) => <svg {...props} />
mock.module('lucide-react', () => ({
  AlertCircle: Icon, ArrowRight: Icon, CheckCircle: Icon, Clock: Icon, ExternalLink: Icon,
  Loader2: Icon, Send: Icon, SkipForward: Icon, XCircle: Icon,
}))

function element(tag: keyof React.JSX.IntrinsicElements) {
  function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
  return MockElement
}

mock.module('@/components/ui/card', () => ({
  Card: element('section'), CardContent: element('div'), CardDescription: element('p'),
  CardHeader: element('header'), CardTitle: element('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/alert', () => ({ Alert: element('div'), AlertDescription: element('div') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: element('div') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('span') }))

const { ApiPlayground } = await import('./api-playground')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer | undefined
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL
const variables = [
  { name: 'prompt', type: 'text' },
  { name: 'count', type: 'number' },
  { name: 'enabled', type: 'boolean' },
  { name: 'items', type: 'array' },
  { name: 'config', type: 'object' },
  { name: 'fallback', type: 'unknown' },
]

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function render() {
  act(() => {
    renderer = create(
      <ApiPlayground webhookUrl="https://example.test/hook" variables={variables as never} />,
    )
  })
  return renderer!
}

function change(id: string, value: string) {
  act(() => renderer!.root.findByProps({ id }).props.onChange({ target: { value } }))
}

async function submit() {
  const button = renderer!.root.findAllByType('button').find((node) => node.props.className === 'w-full')!
  await act(async () => button.props.onClick())
}

function output() {
  return JSON.stringify(renderer!.toJSON())
}

function text() {
  return renderer!.root.findAll(() => true)
    .flatMap((node) => node.children)
    .filter((child) => typeof child === 'string')
    .join(' ')
}

beforeEach(() => {
  fetchMock.mockReset()
  eventSources.length = 0
  process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test/api/v1'
})

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = originalApiUrl
})

describe('ApiPlayground', () => {
  test('generates the example payload and submits it with the API key', async () => {
    render()
    const generated = JSON.parse(renderer!.root.findByProps({ id: 'request-body' }).props.value)
    expect(generated).toEqual({
      prompt: 'example text', count: 42, enabled: true, items: ['item1', 'item2'],
      config: { key: 'value' }, fallback: 'value',
    })

    change('api-key', 'secret-key')
    fetchMock.mockResolvedValueOnce(response({ data: { run_id: 'run-1' } }))
    await submit()

    expect(fetchMock).toHaveBeenCalledWith('https://example.test/hook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer secret-key' },
      body: JSON.stringify(generated),
    })
    expect(eventSources[0].url).toBe('https://api.example.test/api/v1/workflows/runs/run-1/stream')
    expect(text()).toContain('Run ID:  run-1')
    expect(output()).toContain('running')
    expect(output()).toContain('apiPlayground.workflowStarted')
  })

  test('validates credentials and JSON before crossing the network boundary', async () => {
    render()
    change('request-body', '{bad json')
    await submit()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(renderer!.root.findByProps({ id: 'api-key' }).props['aria-invalid']).toBe(true)
    expect(renderer!.root.findByProps({ id: 'request-body' }).props['aria-invalid']).toBe(true)
    expect(output()).toContain('required')
    expect(output()).toContain('invalidJSON')
  })

  test('renders streamed completion output and closes the connection', async () => {
    render()
    change('api-key', 'secret-key')
    fetchMock.mockResolvedValueOnce(response({ data: { run_id: 'run-2' } }))
    await submit()

    act(() => eventSources[0].emit('output', {
      event: 'output', node_id: 'answer', data: { output: { answer: 'done' } },
    }))
    act(() => eventSources[0].emit('workflow_complete', {
      event: 'workflow_complete', data: { duration_ms: 25, outputs: { result: 'ok' } },
    }))

    expect(eventSources[0].closed).toBe(true)
    expect(output()).toContain('completed')
    expect(output()).toContain('apiPlayground.nodeOutput')
    expect(text()).toContain('"answer": "done"')
    expect(text()).toContain('"result": "ok"')
  })

  test('maps API validation failures and sanitizes stream errors', async () => {
    render()
    change('api-key', 'secret-key')
    fetchMock.mockResolvedValueOnce(response({
      code: 1001,
      msg: 'validation.failed',
      data: { errors: { 'inputs.prompt': ['Prompt is required'] } },
    }, 422))
    await submit()

    expect(renderer!.root.findByProps({ id: 'request-body' }).props['aria-invalid']).toBe(true)
    expect(output()).toContain('Prompt is required')
    expect(output()).toContain('failed')
    expect(eventSources).toHaveLength(0)

    change('request-body', '{"prompt":"hello"}')
    fetchMock.mockResolvedValueOnce(response({ data: { run_id: 'run-3' } }))
    await submit()
    act(() => eventSources[0].emit('workflow_error', {
      event: 'workflow_error', data: { error: 'HTTP 500 Exception: internal detail' },
    }))

    expect(eventSources[0].closed).toBe(true)
    expect(output()).toContain('runDrawer.executionFailed')
    expect(output()).not.toContain('internal detail')
  })
})
