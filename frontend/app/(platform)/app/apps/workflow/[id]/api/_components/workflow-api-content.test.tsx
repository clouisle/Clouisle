import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const writeText = mock(() => Promise.resolve())
const success = mock(() => {})
const open = mock(() => {})

Object.assign(globalThis, {
  navigator: { clipboard: { writeText } },
  window: { open },
})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('lucide-react', () => ({
  Copy: () => <span data-icon="copy" />,
  Check: () => <span data-icon="check" />,
  ExternalLink: () => null,
  Key: () => null,
  AlertCircle: () => null,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertTitle: ({ children }: React.PropsWithChildren) => <strong>{children}</strong>,
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))

const { WorkflowApiContent } = await import('./workflow-api-content')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
const originalSetTimeout = globalThis.setTimeout
const originalApiUrl = process.env.NEXT_PUBLIC_API_URL

function render(workflow: Record<string, unknown>) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WorkflowApiContent workflow={workflow as never} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function output(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  writeText.mockClear()
  success.mockClear()
  open.mockClear()
  globalThis.setTimeout = originalSetTimeout
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_URL
  else process.env.NEXT_PUBLIC_API_URL = originalApiUrl
})

describe('WorkflowApiContent', () => {
  test('shows only the webhook configuration error when no token exists', () => {
    const renderer = render({ webhook_token: null, variables: [] })
    const rendered = output(renderer)

    expect(rendered).toContain('noWebhookTitle')
    expect(rendered).toContain('noWebhookDescription')
    expect(rendered).not.toContain('endpointDescription')
  })

  test('builds endpoint examples from the workflow token and variables', () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test'
    const renderer = render({
      webhook_token: 'hook-token',
      variables: [
        { name: 'query', type: 'text', required: true, description: 'Question' },
        { name: 'count', type: 'number', required: false },
      ],
    })
    const rendered = output(renderer)

    expect(rendered).toContain('https://api.example.test/api/v1/workflows/webhook/hook-token')
    expect(rendered).toContain('Question')
    expect(rendered).toContain('required')
    const jsonExamples = renderer.root.findAllByProps({ className: 'language-json' })
    expect(jsonExamples.some((node) => node.children.join('').includes('"query": ""'))).toBe(true)
    expect(jsonExamples.some((node) => node.children.join('').includes('"count": 0'))).toBe(true)
  })

  test('opens API key management and copies a code sample with confirmation reset', async () => {
    let resetCopied: (() => void) | undefined
    globalThis.setTimeout = ((callback: () => void) => {
      resetCopied = callback
      return 0 as unknown as ReturnType<typeof setTimeout>
    }) as typeof setTimeout
    const renderer = render({ webhook_token: 'hook-token', variables: [] })
    const buttons = renderer.root.findAllByType('button')

    act(() => buttons[0].props.onClick())
    expect(open).toHaveBeenCalledWith('/app/api-keys', '_blank')

    await act(async () => buttons[1].props.onClick())
    expect(writeText).toHaveBeenCalledWith('Authorization: Bearer YOUR_API_KEY')
    expect(success).toHaveBeenCalledWith('copiedToClipboard')
    expect(renderer.root.findAllByProps({ 'data-icon': 'check' })).toHaveLength(1)

    act(() => resetCopied?.())
    expect(renderer.root.findAllByProps({ 'data-icon': 'check' })).toHaveLength(0)
  })

  test('documents the pause node flow and its endpoints', () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test'
    const renderer = render({ webhook_token: 'hook-token', variables: [] })
    const rendered = output(renderer)

    // Section + flow steps
    expect(rendered).toContain('pauseNode')
    expect(rendered).toContain('pauseNodeDescription')
    expect(rendered).toContain('pauseFlowStep1')
    expect(rendered).toContain('pauseFlowStep2')
    expect(rendered).toContain('pauseFlowStep3')

    // workflow_waiting event documented in the SSE tables/example
    expect(rendered).toContain('workflow_waiting')
    expect(rendered).toContain('eventWorkflowWaiting')

    // Pause-request endpoints
    expect(rendered).toContain('pause-request')
    expect(rendered).toContain('pause-requests/')
    expect(rendered).toContain('{workflow_id}')
    expect(rendered).toContain('{run_id}')
    expect(rendered).toContain('{pause_request_id}')
    expect(rendered).toContain('/submit')

    // Response schema covers variable types and approval fields
    expect(rendered).toContain('input_variables')
    expect(rendered).toContain('files')
    expect(rendered).toContain('fileConfig')
    expect(rendered).toContain('can_submit')
    expect(rendered).toContain('require_all')
    expect(rendered).toContain('decision')
  })
})
