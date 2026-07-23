import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const generate = mock(async () => ({}) as Response)
const parseStream = mock(async function* () {
  yield { type: 'content_delta', data: { delta: 'Generated ' } }
  yield { type: 'content_delta', data: { delta: 'prompt' } }
})
const toastSuccess = mock(() => {})
const toastError = mock(() => {})

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error { isValidationError() { return false } },
  promptsApi: { generate },
  parsePromptSSEStream: parseStream,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: Record<string, unknown>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <span>{children}</span> : null }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: (value: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} /> }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, onOpenChange }: React.PropsWithChildren<{ onOpenChange: (open: boolean) => void }>) => <><button data-collapsible onClick={() => onOpenChange(true)} />{children}</>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))

const { PromptGenerateDialog } = await import('./prompt-generate-dialog')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

function render(props: Partial<React.ComponentProps<typeof PromptGenerateDialog>> = {}) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<PromptGenerateDialog open onOpenChange={() => {}} onApply={() => {}} {...props} />) })
  renderers.push(renderer!)
  return renderer!
}

function button(renderer: ReactTestRenderer, text: string) {
  return renderer.root.findAllByType('button').find((candidate) => candidate.findAll((node) => node.children.includes(text)).length > 0)!
}

function describePrompt(renderer: ReactTestRenderer, value: string) {
  act(() => renderer.root.findByProps({ id: 'description' }).props.onChange({ target: { value } }))
}

afterEach(() => {
  generate.mockClear()
  parseStream.mockReset()
  parseStream.mockImplementation(async function* () {
    yield { type: 'content_delta', data: { delta: 'Generated ' } }
    yield { type: 'content_delta', data: { delta: 'prompt' } }
  })
  toastSuccess.mockClear()
  toastError.mockClear()
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('prompt generate dialog Issue #255 callbacks', () => {
  test('changes advanced options, generates, copies, and applies', async () => {
    const onApply = mock(() => {})
    const onOpenChange = mock(() => {})
    const writeText = mock(async () => {})
    Object.defineProperty(globalThis.navigator, 'clipboard', { configurable: true, value: { writeText } })
    const renderer = render({ onApply, onOpenChange, language: 'en' })

    describePrompt(renderer, '  Build an agent  ')
    act(() => renderer.root.findByProps({ 'data-collapsible': true }).props.onClick())
    act(() => button(renderer, 'style.tone.friendly').props.onClick())
    act(() => button(renderer, 'style.focus.conversational').props.onClick())
    const switches = renderer.root.findAllByType('input')
    act(() => switches[0]!.props.onChange({ target: { checked: true } }))
    act(() => switches[1]!.props.onChange({ target: { checked: false } }))
    await act(async () => button(renderer, 'generate').props.onClick())

    expect(generate).toHaveBeenCalledWith(expect.objectContaining({
      description: 'Build an agent', language: 'en',
      style: { tone: 'friendly', focus: 'conversational', include_cot: true, include_constraints: false },
    }))
    await act(async () => button(renderer, 'copy').props.onClick())
    expect(writeText).toHaveBeenCalledWith('Generated prompt')
    act(() => button(renderer, 'apply').props.onClick())
    expect(onApply).toHaveBeenCalledWith('Generated prompt')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('clears validation while typing and reports stream and copy errors', async () => {
    const renderer = render()
    const textarea = renderer.root.findByProps({ id: 'description' })
    act(() => textarea.props.onChange({ target: { value: '' } }))
    await act(async () => textarea.props.value || button(renderer, 'generate').props.onClick())
    expect(renderer.root.findAll((node) => node.children.includes('errors.descriptionRequired')).length).toBeGreaterThan(0)
    describePrompt(renderer, 'retry')
    expect(renderer.root.findAll((node) => node.children.includes('errors.descriptionRequired'))).toHaveLength(0)

    parseStream.mockImplementation(async function* () {
      yield { type: 'error', data: { msg: 'stream failed' } }
    })
    await act(async () => button(renderer, 'generate').props.onClick())
    expect(toastError).toHaveBeenCalledWith('errors.generateFailed')

    parseStream.mockImplementation(async function* () { yield { type: 'content_delta', data: { delta: 'result' } } })
    await act(async () => button(renderer, 'generate').props.onClick())
    Object.defineProperty(globalThis.navigator, 'clipboard', { configurable: true, value: { writeText: mock(async () => { throw new Error('denied') }) } })
    await act(async () => button(renderer, 'copy').props.onClick())
    expect(toastError).toHaveBeenCalledWith('errors.copyFailed')
  })
})
