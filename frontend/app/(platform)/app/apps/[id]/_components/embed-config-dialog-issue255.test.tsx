import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import type { Agent } from '@/lib/api'
import type { Workflow } from '@/lib/api/workflows'

const updateAgent = mock(async () => ({ id: 'agent-1', status: 'published' }))
const updateWorkflow = mock(async () => ({ id: 'workflow-1', status: 'published' }))
const success = mock(() => undefined)
const writeText = mock(async () => undefined)
const clearValidationError = mock((errors: Record<string, string>, field: string) => {
  const next = { ...errors }
  delete next[field]
  return next
})
const normalizeValidationErrors = mock((): Record<string, string> => ({}))

const component = (name: string) => Object.assign(
  function Component(props: Record<string, unknown>) {
    return createElement(name, props)
  },
  { displayName: name }
)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { value?: string }) =>
    values?.value ? `${key}:${values.value}` : key,
}))
mock.module('next/link', () => ({ default: component('mock-link') }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ Copy: component('mock-copy'), Check: component('mock-check') }))
mock.module('@/lib/api', () => ({
  agentsApi: { updateAgent },
  clearValidationError,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors,
}))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { updateWorkflow } }))
mock.module('@/lib/validation', () => ({
  formatValidationSummaryMessage: (field: string, message: string) => `${field}:${message}`,
}))
mock.module('@/components/ui/button', () => ({
  Button: component('mock-button'),
  buttonVariants: () => 'mock-button-variants',
}))

for (const [path, names] of [
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogDescription', 'DialogHeader', 'DialogTitle']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/tabs', ['Tabs', 'TabsList', 'TabsTrigger']],
] as const) {
  mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(`mock-${name.toLowerCase()}`)])))
}
mock.module('@/components/ui/label', () => ({ Label: component('mock-label') }))
mock.module('@/components/ui/input', () => ({ Input: component('mock-input') }))
mock.module('@/components/ui/switch', () => ({ Switch: component('mock-switch') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: component('mock-textarea') }))
mock.module('@/components/ui/field', () => ({ FieldError: component('mock-field-error') }))

let EmbedConfigDialog: typeof import('./embed-config-dialog').EmbedConfigDialog
const renderers: ReactTestRenderer[] = []

const agent = {
  id: 'agent-1',
  status: 'published',
  embed_config: {
    enabled: true,
    allowed_domains: ['example.com'],
    theme: { mode: 'dark', primary_color: '#123456' },
    bubble: { position: 'bottom-left', icon: null, greeting: 'Hello' },
  },
} as unknown as Agent

function render(props: Partial<React.ComponentProps<typeof EmbedConfigDialog>> = {}) {
  const onOpenChange = mock(() => undefined)
  const onUpdate = mock(() => undefined)
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(createElement(EmbedConfigDialog, {
      open: true,
      agent,
      onOpenChange,
      onUpdate,
      updateAgent,
      updateWorkflow,
      ...props,
    }))
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onOpenChange, onUpdate }
}

const all = (renderer: ReactTestRenderer, type: string): ReactTestInstance[] =>
  renderer.root.findAll((node) => node.type === type)

const button = (renderer: ReactTestRenderer, label: string): ReactTestInstance =>
  all(renderer, 'mock-button').find((node) => node.children.includes(label))!

beforeAll(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  Object.defineProperty(globalThis.navigator, 'clipboard', { configurable: true, value: { writeText } })
  ;({ EmbedConfigDialog } = await import('./embed-config-dialog'))
})

beforeEach(() => {
  updateAgent.mockClear()
  updateWorkflow.mockClear()
  success.mockClear()
  writeText.mockClear()
  clearValidationError.mockClear()
  normalizeValidationErrors.mockClear()
  normalizeValidationErrors.mockImplementation(() => ({}))
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('EmbedConfigDialog uncovered callbacks', () => {
  test('updates every embed field and clears its corresponding validation error', () => {
    const { renderer } = render()

    act(() => all(renderer, 'mock-switch')[0].props.onCheckedChange(false))
    act(() => all(renderer, 'mock-switch')[0].props.onCheckedChange(true))
    act(() => all(renderer, 'mock-textarea')[0].props.onChange({ target: { value: 'one.test, two.test' } }))

    const selects = all(renderer, 'mock-select')
    act(() => selects[0].props.onValueChange(''))
    act(() => selects[1].props.onValueChange(''))

    const inputs = all(renderer, 'mock-input')
    act(() => inputs[0].props.onChange({ target: { value: '#abcdef' } }))
    act(() => inputs[1].props.onChange({ target: { value: '' } }))
    act(() => inputs[2].props.onChange({ target: { value: '' } }))
    act(() => inputs[3].props.onChange({ target: { value: 'clou_secret' } }))
    act(() => all(renderer, 'mock-tabs')[0].props.onValueChange('fullscreen'))

    expect(clearValidationError.mock.calls.map((call) => call[1])).toEqual([
      'allowed_domains',
      'theme.primary_color',
      'theme.primary_color',
      'apiKey',
    ])
    expect(renderer.root.findByType('code').children.join('')).toContain('<iframe')
  })

  test('rejects invalid domains and colors before saving', async () => {
    const invalidDomain = render()
    act(() => all(invalidDomain.renderer, 'mock-textarea')[0].props.onChange({ target: { value: 'valid.test, bad_domain' } }))
    await act(async () => button(invalidDomain.renderer, 'save').props.onClick())
    expect(updateAgent).not.toHaveBeenCalled()
    expect(all(invalidDomain.renderer, 'mock-field-error').some((node) => node.children.includes('allowed_domains:invalidDomain:bad_domain'))).toBe(true)

    const invalidColor = render({
      agent: { ...agent, embed_config: { ...agent.embed_config, theme: { mode: 'auto', primary_color: 'red' } } } as Agent,
    })
    await act(async () => button(invalidColor.renderer, 'save').props.onClick())
    expect(updateAgent).not.toHaveBeenCalled()
    expect(all(invalidColor.renderer, 'mock-field-error').some((node) => node.children.includes('theme.primary_color:invalidPrimaryColor'))).toBe(true)
  })

  test('saves normalized agent domains and handles API validation errors', async () => {
    const { renderer, onOpenChange, onUpdate } = render()
    act(() => all(renderer, 'mock-textarea')[0].props.onChange({ target: { value: ' one.test,\n*.two.test, ' } }))
    await act(async () => button(renderer, 'save').props.onClick())

    expect(updateAgent).toHaveBeenCalledWith('agent-1', {
      embed_config: expect.objectContaining({ allowed_domains: ['one.test', '*.two.test'] }),
    })
    expect(onUpdate).toHaveBeenCalled()
    expect(success).toHaveBeenCalledWith('save')
    expect(onOpenChange).toHaveBeenCalledWith(false)

    normalizeValidationErrors.mockImplementation(() => ({ apiKey: 'invalid key' }))
    updateAgent.mockImplementationOnce(async () => { throw new Error('invalid') })
    await act(async () => button(renderer, 'save').props.onClick())
    expect(all(renderer, 'mock-field-error').some((node) => node.children.includes('apiKey:invalid key'))).toBe(true)
  })

  test('uses the workflow updater, copies mobile code, resets copy state, and cancels', async () => {
    const workflow = {
      id: 'workflow-1',
      status: 'published',
      embed_config: { ...agent.embed_config },
    } as unknown as Workflow
    const { renderer, onOpenChange } = render({ agent: undefined, workflow })

    act(() => all(renderer, 'mock-tabs')[0].props.onValueChange('mobile'))
    await act(async () => button(renderer, 'save').props.onClick())
    expect(updateWorkflow).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ embed_config: expect.any(Object) }))

    const originalSetTimeout = globalThis.setTimeout
    let resetCopied: (() => void) | undefined
    globalThis.setTimeout = ((callback: () => void) => {
      resetCopied = callback
      return 1
    }) as typeof setTimeout
    try {
      act(() => all(renderer, 'mock-button').find((node) => typeof node.props.onClick === 'function' && !node.children.includes('save') && !node.children.includes('preview'))!.props.onClick())
      expect(writeText.mock.calls[0][0]).toContain('position: fixed')
      expect(all(renderer, 'mock-check')).toHaveLength(1)
      act(() => resetCopied?.())
      expect(all(renderer, 'mock-copy')).toHaveLength(1)
    } finally {
      globalThis.setTimeout = originalSetTimeout
    }

    act(() => button(renderer, 'preview').props.onClick())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
