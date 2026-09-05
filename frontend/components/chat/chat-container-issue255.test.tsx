import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'
import type { ChatMessage } from './types'

let states: unknown[] = []
let refs: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let effects: Array<() => void | (() => void)> = []
let memoCompare: ((previous: Record<string, unknown>, next: Record<string, unknown>) => boolean) | undefined

const useState = (initial: unknown) => {
  const index = stateIndex++
  if (states.length <= index) states[index] = initial
  return [states[index], (value: unknown) => {
    states[index] = typeof value === 'function'
      ? (value as (previous: unknown) => unknown)(states[index])
      : value
  }]
}
const useRef = (initial: unknown) => {
  const index = refIndex++
  if (!refs[index]) refs[index] = { current: initial }
  return refs[index]
}
const useEffect = (effect: () => void | (() => void)) => effects.push(effect)

mock.module('react', () => ({
  memo: (component: unknown, compare: typeof memoCompare) => {
    memoCompare = compare
    return component
  },
  useCallback: (callback: unknown) => callback,
  useEffect,
  useLayoutEffect: useEffect,
  useMemo: (factory: () => unknown) => factory(),
  useRef,
  useState,
}))

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => `${key}:${values?.count ?? ''}`,
}))
mock.module('lucide-react', () => ({
  ArrowDown: (props: Record<string, unknown>) => jsx('arrow-down', props),
  ChevronDown: (props: Record<string, unknown>) => jsx('chevron-down', props),
  ChevronUp: (props: Record<string, unknown>) => jsx('chevron-up', props),
  Download: (props: Record<string, unknown>) => jsx('download', props),
  Eye: (props: Record<string, unknown>) => jsx('eye', props),
  FileAudio: (props: Record<string, unknown>) => jsx('file-audio', props),
  FileCode: (props: Record<string, unknown>) => jsx('file-code', props),
  FileIcon: (props: Record<string, unknown>) => jsx('file-icon', props),
  FileImage: (props: Record<string, unknown>) => jsx('file-image', props),
  FileText: (props: Record<string, unknown>) => jsx('file-text', props),
  FileType: (props: Record<string, unknown>) => jsx('file-type', props),
  FileVideo: (props: Record<string, unknown>) => jsx('file-video', props),
  Link: (props: Record<string, unknown>) => jsx('link', props),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/button', () => ({ Button: (props: Record<string, unknown>) => jsx('button', props) }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: (props: Record<string, unknown>) => jsx('tooltip', props),
  TooltipTrigger: (props: Record<string, unknown>) => jsx('tooltip-trigger', props),
  TooltipContent: (props: Record<string, unknown>) => jsx('tooltip-content', props),
}))
mock.module('./message', () => ({
  Message: (props: Record<string, unknown>) => jsx('message', props),
}))

const { ChatContainer } = await import('./chat-container')
type Props = Parameters<typeof ChatContainer>[0]
type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  if (typeof tree.type === 'function') {
    return resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
  }
  if (tree.type && typeof tree.type === 'object' && 'type' in tree.type) {
    return resolve(((tree.type as { type: (props: Record<string, unknown>) => ReactNode }).type)(tree.props))
  }
  return tree
}

function findAll(node: ReactNode, type: unknown): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, type))
  const tree = resolve(node)
  if (!tree || typeof tree !== 'object' || !('type' in tree)) return []
  const children = (tree as Tree).props.children
  return [
    ...((tree as Tree).type === type ? [tree as Tree] : []),
    ...(Array.isArray(children) ? children : [children]).flatMap((child) => findAll(child as ReactNode, type)),
  ]
}

function render(props: Props, runEffects = false) {
  stateIndex = 0
  refIndex = 0
  effects = []
  const tree = ChatContainer(props)
  if (runEffects) effects.forEach((effect) => effect())
  return tree
}

const message = (id: string, role: 'user' | 'assistant' = 'assistant', text = id): ChatMessage => ({
  id,
  role,
  parts: [{ type: 'text', text }],
})

beforeEach(() => {
  states = []
  refs = []
  stateIndex = 0
  refIndex = 0
  effects = []
})

describe('ChatContainer issue #255 coverage', () => {
  test('renders the custom empty state and class without mounting messages', () => {
    const tree = render({ messages: [], className: 'custom', emptyState: jsx('empty', {}) })

    expect((tree as Tree).props.className).toContain('custom')
    expect(findAll(tree, 'empty')).toHaveLength(1)
    expect(findAll(tree, 'message')).toHaveLength(0)
  })

  test('pages older messages and labels the remaining batch', () => {
    const messages = Array.from({ length: 45 }, (_, index) => message(`m-${index}`))
    let tree = render({ messages })

    expect(findAll(tree, 'message').map((item) => (item.props.message as ChatMessage).id)).toEqual(
      messages.slice(25).map(({ id }) => id),
    )
    const loadButton = findAll(tree, 'button')[0]
    expect(loadButton.props.children).toBe('message.loadOlderMessages:20')
    ;(loadButton.props.onClick as () => void)()

    tree = render({ messages })
    expect(findAll(tree, 'message')).toHaveLength(40)
    expect(findAll(tree, 'button')[0].props.children).toBe('message.loadOlderMessages:5')
    ;(findAll(tree, 'button')[0].props.onClick as () => void)()
    expect(findAll(render({ messages }), 'message')).toHaveLength(45)
  })

  test('delegates message actions and blocks edits while streaming without sharing thought-panel state', async () => {
    const onRegenerate = mock()
    const onEditMessage = mock(async () => {})
    const onSwitchVersion = mock()
    const onOpenCodePreview = mock()
    const renderPart = mock()
    const messages = [message('user-1', 'user'), message('assistant-1')]
    let tree = render({
      messages,
      onRegenerate,
      onEditMessage,
      onSwitchVersion,
      onOpenCodePreview,
      renderPart,
      hideToolCalls: true,
      isStreaming: true,
    }, true)
    tree = render({ messages, onRegenerate, onEditMessage, onSwitchVersion, onOpenCodePreview, renderPart, hideToolCalls: true, isStreaming: true })
    const [user, assistant] = findAll(tree, 'message')

    expect(user.props).toMatchObject({ isStreaming: false, hideToolCalls: true, onRegenerate: undefined, onEditMessage: undefined })
    expect(assistant.props).toMatchObject({ isStreaming: true, onEditMessage: undefined })
    expect(assistant.props.chainOfThoughtOpen).toBeUndefined()
    expect(assistant.props.onChainOfThoughtOpenChange).toBeUndefined()
    expect(assistant.props.pendingAskUserToolCallId).toBeUndefined()
    expect(assistant.props.onSubmitAskUser).toBeUndefined()

    const idleTree = render({ messages, onRegenerate, onEditMessage, onSwitchVersion, onOpenCodePreview, renderPart, hideToolCalls: true })
    const idleUser = findAll(idleTree, 'message')[0]
    await (idleUser.props.onEditMessage as (content: string) => Promise<void>)('edited')
    ;(assistant.props.onRegenerate as () => void)()
    ;(assistant.props.onSwitchVersion as (index: number) => void)(2)
    ;(assistant.props.onOpenCodePreview as (payload: unknown) => void)({ code: 'x' })

    expect(onEditMessage).toHaveBeenCalledWith('user-1', 'edited')
    expect(onRegenerate).toHaveBeenCalledWith('assistant-1')
    expect(onSwitchVersion).toHaveBeenCalledWith('assistant-1', 2)
    expect(onOpenCodePreview).toHaveBeenCalledWith({ code: 'x' })
  })

  test('does not open previews automatically when streaming finishes', () => {
    const onOpenCodePreview = mock()
    const messages = [message('assistant-1')]

    render({ messages, isStreaming: true, onOpenCodePreview }, true)
    render({ messages, isStreaming: false, onOpenCodePreview }, true)

    expect(onOpenCodePreview).not.toHaveBeenCalled()
  })

  test('tracks scrolling, reveals the bottom control, and navigates to messages', () => {
    const scrollTo = mock()
    const scroller = { scrollHeight: 500, scrollTop: 0, clientHeight: 100, scrollTo }
    const target = { offsetTop: 123 }
    let tree = render({ messages: [message('a')] })
    const divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs.find((div) => typeof div.props.ref === 'function')?.props.ref as (value: unknown) => void)(target)
    ;(divs[1].props.onScroll as () => void)()

    tree = render({ messages: [message('a')] })
    const bottomButton = findAll(tree, 'button')[0]
    expect(findAll(bottomButton.props.children as ReactNode, 'arrow-down')).toHaveLength(1)
    ;(bottomButton.props.onClick as () => void)()
    expect(scrollTo).toHaveBeenCalledWith({ top: 501, behavior: 'smooth' })

    const renderedMessage = findAll(tree, 'message')[0]
    ;(renderedMessage.props.onRequestScrollIntoView as () => void)()
    expect(scrollTo).toHaveBeenCalledWith({ top: 123, behavior: 'smooth' })
  })

  test('preserves loaded history position but follows a locally sent message before streaming starts', () => {
    const scrollTo = mock()
    const attachScroller = (tree: ReactNode, scrollHeight: number) => {
      const ref = findAll(tree, 'div')[1]?.props.ref
      if (!ref || typeof ref !== 'object' || !('current' in ref)) {
        throw new Error('chat scroller ref was not rendered')
      }
      ref.current = { scrollHeight, scrollTop: 0, clientHeight: 100, scrollTo }
    }

    let tree = render({ messages: [], conversationId: 'conversation-1' })
    attachScroller(tree, 500)
    effects.forEach((effect) => effect())
    scrollTo.mockClear()

    const history = [message('user-1', 'user'), message('assistant-1')]
    tree = render({ messages: history, conversationId: 'conversation-1' })
    attachScroller(tree, 500)
    effects.forEach((effect) => effect())
    tree = render({ messages: history, conversationId: 'conversation-1' })
    attachScroller(tree, 500)
    effects.forEach((effect) => effect())
    expect(scrollTo).not.toHaveBeenCalled()

    const sent = [...history, message('user-2', 'user'), message('assistant-2')]
    tree = render({ messages: sent, conversationId: 'conversation-1', isLoading: true })
    expect(findAll(tree, 'message')).toHaveLength(sent.length)
    attachScroller(tree, 600)
    effects.forEach((effect) => effect())
    expect(scrollTo).toHaveBeenCalledWith({ top: 601, behavior: 'auto' })
  })

  test('auto-follows growth and content resize, then cleans up observers', () => {
    const scrollTo = mock()
    const observe = mock()
    const disconnect = mock()
    const cancel = mock()
    let resize: (() => void) | undefined
    globalThis.ResizeObserver = class {
      constructor(callback: () => void) { resize = callback }
      observe = observe
      disconnect = disconnect
      unobserve() {}
    }
    globalThis.requestAnimationFrame = ((callback: FrameRequestCallback) => {
      callback(1)
      return 9
    }) as typeof requestAnimationFrame
    globalThis.cancelAnimationFrame = cancel

    const tree = render({ messages: [message('a'), message('b')] })
    const divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = { scrollHeight: 200, scrollTop: 100, clientHeight: 100, scrollTo }
    ;(divs[2].props.ref as { current: unknown }).current = {}
    const cleanups = effects.map((effect) => effect()).filter(Boolean) as Array<() => void>

    expect(scrollTo).toHaveBeenCalledWith({ top: 201, behavior: 'auto' })
    expect(observe).toHaveBeenCalledTimes(1)
    resize?.()
    expect(scrollTo).toHaveBeenCalledTimes(2)
    cleanups.forEach((cleanup) => cleanup())
    expect(cancel).toHaveBeenCalledWith(9)
    expect(disconnect).toHaveBeenCalledTimes(1)
  })

  test('does not snap while streaming an open fence or when auto-scroll is disabled', () => {
    const scrollTo = mock()
    const openFence = message('code', 'assistant', '```ts\nconst x = 1')
    let tree = render({ messages: [openFence], isStreaming: true })
    let divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = { scrollHeight: 200, scrollTop: 0, clientHeight: 100, scrollTo }
    effects.forEach((effect) => effect())
    expect(scrollTo).not.toHaveBeenCalled()

    tree = render({ messages: [message('closed', 'assistant', '~~~\nx\n~~~')], autoScroll: false })
    divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = { scrollHeight: 200, scrollTop: 0, clientHeight: 100, scrollTo }
    effects.forEach((effect) => effect())
    expect(scrollTo).not.toHaveBeenCalled()
  })

  test('does not yank the view to the bottom when a chunk commits before the scroll event lands', () => {
    const scrollTo = mock()
    const history = Array.from({ length: 100 }, (_, index) => message(`m-${index}`, index % 2 === 0 ? 'user' : 'assistant'))
    const streamed = (n: number) => [...history.slice(0, -1), message('last', 'assistant', `answer ${'x'.repeat(n)}`)]

    // Mount long history and position at the newest message
    let tree = render({ messages: history, conversationId: 'c1' })
    let divs = findAll(tree, 'div')
    const scroller = { scrollHeight: 10000, scrollTop: 9600, clientHeight: 400, scrollTo }
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs[2].props.ref as { current: unknown }).current = {}
    effects.forEach((effect) => effect())
    scrollTo.mockClear()

    // Streaming starts; first chunk while still at the bottom follows
    tree = render({ messages: streamed(10), conversationId: 'c1', isStreaming: true })
    divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs[2].props.ref as { current: unknown }).current = {}
    effects.forEach((effect) => effect())
    scrollTo.mockClear()

    // The user wheels up: the scroller has moved, but the browser has not yet
    // delivered the scroll event (delivered asynchronously), so the follow
    // ref is still stale. A chunk committing inside this window must NOT
    // drag the view back to the bottom.
    scroller.scrollTop = 4000
    scroller.scrollHeight = 10400

    tree = render({ messages: streamed(60), conversationId: 'c1', isStreaming: true })
    divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs[2].props.ref as { current: unknown }).current = {}
    effects.forEach((effect) => effect())

    expect(scrollTo).not.toHaveBeenCalled()
  })

  test('keeps the reading position stable when loading older messages', () => {
    const scrollTo = mock()
    const messages = Array.from({ length: 45 }, (_, index) => message(`m-${index}`))
    let tree = render({ messages })
    let divs = findAll(tree, 'div')
    const scroller = { scrollHeight: 500, scrollTop: 100, clientHeight: 300, scrollTo }
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs[2].props.ref as { current: unknown }).current = {}
    effects.forEach((effect) => effect())
    scrollTo.mockClear()

    // Click "load older": anchor captured, batch inserted above the viewport
    ;(findAll(tree, 'button')[0].props.onClick as () => void)()
    scroller.scrollHeight = 900
    tree = render({ messages })
    divs = findAll(tree, 'div')
    ;(divs[1].props.ref as { current: unknown }).current = scroller
    ;(divs[2].props.ref as { current: unknown }).current = {}
    effects.forEach((effect) => effect())

    expect(scroller.scrollTop).toBe(500)
  })

  test('re-positions at the newest message when the conversation changes', () => {
    const scrollTo = mock()
    const history = Array.from({ length: 50 }, (_, index) => message(`m-${index}`))
    const attach = (tree: ReactNode, scrollTop: number) => {
      const divs = findAll(tree, 'div')
      ;(divs[1].props.ref as { current: unknown }).current = { scrollHeight: 10000, scrollTop, clientHeight: 400, scrollTo }
      ;(divs[2].props.ref as { current: unknown }).current = {}
    }

    let tree = render({ messages: history, conversationId: 'c1' })
    attach(tree, 9600)
    effects.forEach((effect) => effect())
    scrollTo.mockClear()

    // Switch conversation while the scroller still holds the old position
    tree = render({ messages: history, conversationId: 'c2' })
    attach(tree, 4000)
    effects.forEach((effect) => effect())

    expect(scrollTo).toHaveBeenCalledWith({ top: 10001, behavior: 'auto' })
  })

  test('memo comparison notices each delegated prop change', () => {
    const shared = {
      message: message('a'), isCurrentStreaming: false, loadingLabel: 'Queued', renderPart: () => null, afterContent: undefined,
      onRegenerate: () => {}, onEditMessage: () => {}, onSwitchVersion: () => {}, onSelectImageReference: () => {},
      onOpenCodePreview: () => {}, hideToolCalls: false, hideMessageActions: false, hideReasoning: false,
      conversationId: 'conversation', onRequestScrollIntoView: () => {}, setMessageElement: () => {},
    }
    expect(memoCompare?.(shared, shared)).toBe(true)
    const changedProps = [
      { ...shared, message: message('b') },
      { ...shared, isCurrentStreaming: true },
      { ...shared, loadingLabel: 'Running' },
      { ...shared, renderPart: () => null },
      { ...shared, afterContent: null },
      { ...shared, onRegenerate: () => {} },
      { ...shared, onEditMessage: () => {} },
      { ...shared, onSwitchVersion: () => {} },
      { ...shared, onSelectImageReference: () => {} },
      { ...shared, onOpenCodePreview: () => {} },
      { ...shared, hideToolCalls: true },
      { ...shared, hideMessageActions: true },
      { ...shared, hideReasoning: true },
      { ...shared, conversationId: 'other-conversation' },
      { ...shared, onRequestScrollIntoView: () => {} },
      { ...shared, setMessageElement: () => {} },
    ]
    for (const changed of changedProps) expect(memoCompare?.(shared, changed)).toBe(false)
  })
})
