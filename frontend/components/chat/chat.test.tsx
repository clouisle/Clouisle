import { describe, expect, mock, test } from 'bun:test'

mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))
mock.module('@/lib/utils', () => ({
  cn: (...classes: unknown[]) => classes.filter(Boolean).join(' '),
}))
mock.module('./chat-container', () => ({ ChatContainer: 'ChatContainer' }))
mock.module('./chat-input', () => ({ ChatInput: 'ChatInput' }))

const { Chat } = await import('./chat')

type ElementNode = {
  type?: unknown
  props?: Record<string, unknown>
}

function find(node: unknown, type: string): ElementNode {
  if (Array.isArray(node)) {
    for (const child of node) {
      try { return find(child, type) } catch { /* keep searching */ }
    }
  }
  if (node && typeof node === 'object') {
    const element = node as ElementNode
    if (element.type === type) return element
    if (element.props?.children !== undefined) return find(element.props.children, type)
  }
  throw new Error(`${type} not found`)
}

const messages = [{ id: 'message-1', role: 'user', content: 'Hello' }] as never

function render(overrides: Partial<Parameters<typeof Chat>[0]> = {}) {
  return Chat({ messages, ...overrides })
}

describe('Chat', () => {
  test('composes the message container and input with defaults', () => {
    const tree = render()
    const container = find(tree, 'ChatContainer')
    const input = find(tree, 'ChatInput')

    expect(container.props).toMatchObject({ messages, isStreaming: false, autoScroll: true })
    expect(input.props).toMatchObject({
      disabled: false,
      isLoading: false,
      isStreaming: false,
      allowAttachments: true,
    })
  })

  test('forwards loading, streaming, layout, and interaction callbacks', () => {
    const onInputChange = mock(() => undefined)
    const onSubmit = mock(() => undefined)
    const onStop = mock(() => undefined)
    const onSelectOption = mock(() => undefined)
    const tree = render({
      className: 'chat-shell',
      containerClassName: 'message-list',
      inputClassName: 'composer',
      inputPosition: 'sticky',
      inputValue: 'Draft',
      isLoading: true,
      isStreaming: true,
      inputDisabled: true,
      allowAttachments: false,
      onInputChange,
      onSubmit,
      onStop,
      onSelectOption,
    })
    const container = find(tree, 'ChatContainer')
    const input = find(tree, 'ChatInput')
    const inputArea = ((tree as ElementNode).props?.children as ElementNode[])[1]

    expect(container.props).toMatchObject({ className: 'message-list', isStreaming: true, onSelectOption })
    expect(input.props).toMatchObject({
      value: 'Draft',
      className: 'composer',
      disabled: true,
      isLoading: true,
      isStreaming: true,
      allowAttachments: false,
    })
    expect(input.props?.onChange).toBe(onInputChange)
    expect(input.props?.onSubmit).toBe(onSubmit)
    expect(input.props?.onStop).toBe(onStop)
    expect((tree as ElementNode).props?.className).toContain('chat-shell')
    expect(inputArea.props?.className).toContain('sticky bottom-0')

    ;(input.props?.onChange as (value: string) => void)('Updated')
    ;(input.props?.onSubmit as (message: string) => void)('Send')
    ;(input.props?.onStop as () => void)()
    ;(container.props?.onSelectOption as (option: string) => void)('Option A')

    expect(onInputChange).toHaveBeenCalledWith('Updated')
    expect(onSubmit).toHaveBeenCalledWith('Send')
    expect(onStop).toHaveBeenCalledTimes(1)
    expect(onSelectOption).toHaveBeenCalledWith('Option A')
  })
})
