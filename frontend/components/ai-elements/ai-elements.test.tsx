import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const codeToHtml = mock(async (code: string, options: { theme: string }) =>
  `<pre data-theme="${options.theme}">${code}</pre>`,
)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('shiki', () => ({ codeToHtml }))

mock.module('motion/react', () => ({
  motion: new Proxy({}, {
    get: (_, tag) => ({ children, animate, initial, transition, ...props }: Record<string, unknown>) =>
      createElement(tag as string, {
        ...props,
        'data-animate': JSON.stringify(animate),
        'data-initial': JSON.stringify(initial),
        'data-duration': (transition as { duration: number }).duration,
      }, children),
  }),
}))

let streamdownComponents: Record<string, unknown> | undefined
mock.module('streamdown', () => ({
  Streamdown: ({ children, components, className }: { children?: React.ReactNode, components?: Record<string, unknown>, className?: string }) => {
    streamdownComponents = components
    return createElement('div', { className }, children)
  },
}))

mock.module('@/components/ui/hover-card', () => ({
  HoverCard: ({ children }: { children?: React.ReactNode }) => createElement('div', { 'data-slot': 'hover-card' }, children),
  HoverCardContent: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) =>
    createElement('div', { 'data-slot': 'hover-card-content', ...props }, children),
  HoverCardTrigger: ({ children, render: renderProp }: { children?: React.ReactNode, render: React.ReactElement }) =>
    createElement('div', { 'data-slot': 'hover-card-trigger' }, renderProp ? createElement(renderProp.type, { ...renderProp.props }, children) : children),
}))
mock.module('@/components/ui/carousel', () => ({
  Carousel: ({ children, ...props }: { children?: React.ReactNode, setApi?: unknown } & Record<string, unknown>) => {
    const { setApi, ...divProps } = props
    void setApi
    return createElement('div', divProps, children)
  },
  CarouselContent: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) =>
    createElement('div', props, children),
  CarouselItem: ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) =>
    createElement('div', props, children),
}))

let ChainOfThought: typeof import('./chain-of-thought').ChainOfThought
let ChainOfThoughtContent: typeof import('./chain-of-thought').ChainOfThoughtContent
let ChainOfThoughtHeader: typeof import('./chain-of-thought').ChainOfThoughtHeader
let CodeBlock: typeof import('./code-block').CodeBlock
let CodeBlockCopyButton: typeof import('./code-block').CodeBlockCopyButton
let highlightCode: typeof import('./code-block').highlightCode
let InlineCitation: typeof import('./inline-citation').InlineCitation
let InlineCitationCard: typeof import('./inline-citation').InlineCitationCard
let InlineCitationCardBody: typeof import('./inline-citation').InlineCitationCardBody
let InlineCitationCardTrigger: typeof import('./inline-citation').InlineCitationCardTrigger
let InlineCitationCarousel: typeof import('./inline-citation').InlineCitationCarousel
let InlineCitationCarouselContent: typeof import('./inline-citation').InlineCitationCarouselContent
let InlineCitationCarouselHeader: typeof import('./inline-citation').InlineCitationCarouselHeader
let InlineCitationCarouselIndex: typeof import('./inline-citation').InlineCitationCarouselIndex
let InlineCitationCarouselItem: typeof import('./inline-citation').InlineCitationCarouselItem
let InlineCitationCarouselNext: typeof import('./inline-citation').InlineCitationCarouselNext
let InlineCitationCarouselPrev: typeof import('./inline-citation').InlineCitationCarouselPrev
let InlineCitationSource: typeof import('./inline-citation').InlineCitationSource
let InlineCitationText: typeof import('./inline-citation').InlineCitationText
let InlineCitationQuote: typeof import('./inline-citation').InlineCitationQuote
let Message: typeof import('./message').Message
let MessageAction: typeof import('./message').MessageAction
let MessageActions: typeof import('./message').MessageActions
let MessageAttachment: typeof import('./message').MessageAttachment
let MessageAttachments: typeof import('./message').MessageAttachments
let MessageBranch: typeof import('./message').MessageBranch
let MessageBranchContent: typeof import('./message').MessageBranchContent
let MessageBranchNext: typeof import('./message').MessageBranchNext
let MessageBranchPage: typeof import('./message').MessageBranchPage
let MessageBranchPrevious: typeof import('./message').MessageBranchPrevious
let MessageBranchSelector: typeof import('./message').MessageBranchSelector
let MessageContent: typeof import('./message').MessageContent
let MessageResponse: typeof import('./message').MessageResponse
let MessageToolbar: typeof import('./message').MessageToolbar
let Shimmer: typeof import('./shimmer').Shimmer
let Tool: typeof import('./tool').Tool
let ToolContent: typeof import('./tool').ToolContent
let ToolHeader: typeof import('./tool').ToolHeader
let ToolOutput: typeof import('./tool').ToolOutput

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

function render(element: React.ReactNode) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  renderers.push(renderer!)
  return renderer!
}

beforeAll(async () => {
  ({ ChainOfThought, ChainOfThoughtContent, ChainOfThoughtHeader } = await import('./chain-of-thought'));
  ({ CodeBlock, CodeBlockCopyButton, highlightCode } = await import('./code-block'));
  ;({
    InlineCitation,
    InlineCitationCard,
    InlineCitationCardBody,
    InlineCitationCardTrigger,
    InlineCitationCarousel,
    InlineCitationCarouselContent,
    InlineCitationCarouselHeader,
    InlineCitationCarouselIndex,
    InlineCitationCarouselItem,
    InlineCitationCarouselNext,
    InlineCitationCarouselPrev,
    InlineCitationSource,
    InlineCitationText,
    InlineCitationQuote,
  } = await import('./inline-citation'));
  ({
    Message,
    MessageAction,
    MessageActions,
    MessageAttachment,
    MessageAttachments,
    MessageBranch,
    MessageBranchContent,
    MessageBranchNext,
    MessageBranchPage,
    MessageBranchPrevious,
    MessageBranchSelector,
    MessageContent,
    MessageResponse,
    MessageToolbar,
  } = await import('./message'));
  ({ Shimmer } = await import('./shimmer'));
  ({ Tool, ToolContent, ToolHeader, ToolOutput } = await import('./tool'));
})

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
})

describe('ai elements', () => {
  test('renders chain-of-thought open and closed accessibility states', () => {
    const open = renderToStaticMarkup(
      <ChainOfThought open>
        <ChainOfThoughtHeader title="Reasoning" />
        <ChainOfThoughtContent>details</ChainOfThoughtContent>
      </ChainOfThought>,
    )
    const closed = renderToStaticMarkup(
      <ChainOfThought open={false}>
        <ChainOfThoughtHeader title="Reasoning" />
        <ChainOfThoughtContent>details</ChainOfThoughtContent>
      </ChainOfThought>,
    )

    expect(open).toContain('data-state="open"')
    expect(open).toContain('aria-expanded="true"')
    const contentId = open.match(/aria-controls="([^"]+)"/)?.[1]
    expect(contentId).toBeDefined()
    expect(open).toContain(`id="${contentId}"`)
    expect(closed).toContain('data-state="closed"')
    expect(closed).toContain('aria-expanded="false"')
    expect(closed).toContain(' hidden')
  })

  test('toggles chain-of-thought state and renders streaming defaults', () => {
    const changes = mock(() => {})
    const renderer = render(
      <ChainOfThought defaultOpen={false} isStreaming onOpenChange={changes}>
        <ChainOfThoughtHeader />
        <ChainOfThoughtContent>details</ChainOfThoughtContent>
      </ChainOfThought>,
    )

    const button = renderer.root.findByType('button')
    expect(button.props['aria-expanded']).toBe(false)
    expect(JSON.stringify(renderer.toJSON())).toContain('thinkingDefault')

    act(() => button.props.onClick())
    expect(renderer.root.findByType('button').props['aria-expanded']).toBe(true)
    expect(changes).toHaveBeenCalledWith(true)
  })

  test('auto-closes chain-of-thought once after streaming ends', () => {
    const previousSetTimeout = globalThis.setTimeout
    const previousClearTimeout = globalThis.clearTimeout
    const changes = mock(() => {})

    try {
      globalThis.setTimeout = ((callback: () => void) => {
        callback()
        return 1 as unknown as ReturnType<typeof setTimeout>
      }) as typeof setTimeout
      globalThis.clearTimeout = mock(() => {}) as unknown as typeof clearTimeout

      render(
        <ChainOfThought defaultOpen onOpenChange={changes}>
          <ChainOfThoughtHeader title="Reasoning" />
          <ChainOfThoughtContent>details</ChainOfThoughtContent>
        </ChainOfThought>,
      )

      expect(changes).toHaveBeenCalledWith(false)
    } finally {
      globalThis.setTimeout = previousSetTimeout
      globalThis.clearTimeout = previousClearTimeout
    }
  })

  test('contains nested chain-of-thought wheel scrolling', () => {
    let wheelHandler: ((event: { deltaY: number; stopPropagation: () => void }) => void) | undefined
    const stopPropagation = mock(() => {})
    const node = {
      scrollTop: 4,
      scrollHeight: 20,
      clientHeight: 10,
      addEventListener: mock((_type: string, handler: typeof wheelHandler) => { wheelHandler = handler }),
      removeEventListener: mock(() => {}),
    }
    let renderer: ReactTestRenderer

    act(() => {
      renderer = create(
        <ChainOfThought>
          <ChainOfThoughtContent containScroll>details</ChainOfThoughtContent>
        </ChainOfThought>,
        { createNodeMock: () => node },
      )
    })
    renderers.push(renderer!)

    wheelHandler?.({ deltaY: 1, stopPropagation })
    expect(stopPropagation).toHaveBeenCalledTimes(1)
    node.scrollTop = 0
    wheelHandler?.({ deltaY: -1, stopPropagation })
    expect(stopPropagation).toHaveBeenCalledTimes(1)
  })

  test('renders inline citation wrappers and source card variations', () => {
    const citation = renderToStaticMarkup(
      <InlineCitation className="cite">
        <InlineCitationText className="text">label</InlineCitationText>
      </InlineCitation>,
    )
    expect(citation).toContain('cite')
    expect(citation).toContain('text')
    expect(citation).toContain('label')

    const known = renderToStaticMarkup(
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={['https://docs.example.com/path', 'https://other.example.com']} />
      </InlineCitationCard>,
    )
    expect(known).toContain('docs.example.com')
    expect(known).toContain('+1')

    const single = renderToStaticMarkup(
      <InlineCitationCard>
        <InlineCitationCardTrigger sources={['https://docs.example.com']} />
      </InlineCitationCard>,
    )
    expect(single).toContain('docs.example.com')
    expect(single).not.toContain('+')

    const unknown = renderToStaticMarkup(<InlineCitationCard><InlineCitationCardTrigger sources={[]} /></InlineCitationCard>)
    expect(unknown).toContain('unknown')

    const body = renderToStaticMarkup(<InlineCitationCardBody className="wide">body</InlineCitationCardBody>)
    expect(body).toContain('wide')
    expect(body).toContain('body')

    const source = renderToStaticMarkup(
      <InlineCitationSource title="Title" url="https://example.com" description="Snippet" className="src">
        <span>extra</span>
      </InlineCitationSource>,
    )
    expect(source).toContain('Title')
    expect(source).toContain('https://example.com')
    expect(source).toContain('Snippet')
    expect(source).toContain('extra')

    const quote = renderToStaticMarkup(<InlineCitationQuote className="q">quoted</InlineCitationQuote>)
    expect(quote).toContain('quoted')
    expect(quote).toContain('q')
  })

  test('renders inline citation carousel chrome and layout defaults', () => {
    const carousel = renderToStaticMarkup(
      <InlineCitationCarousel className="track">
        <InlineCitationCarouselHeader className="head">header</InlineCitationCarouselHeader>
        <InlineCitationCarouselContent className="content">
          <InlineCitationCarouselItem className="item">item</InlineCitationCarouselItem>
        </InlineCitationCarouselContent>
        <InlineCitationCarouselPrev className="prev" />
        <InlineCitationCarouselNext className="next" />
        <InlineCitationCarouselIndex className="index" />
      </InlineCitationCarousel>,
    )

    expect(carousel).toContain('track')
    expect(carousel).toContain('head')
    expect(carousel).toContain('header')
    expect(carousel).toContain('content')
    expect(carousel).toContain('item')
    expect(carousel).toContain('aria-label="Previous"')
    expect(carousel).toContain('aria-label="Next"')
    expect(carousel).toContain('0/0')
  })

  test('uses shimmer animation properties derived from its text', () => {
    const html = renderToStaticMarkup(<Shimmer as="span" duration={4} spread={3}>hello</Shimmer>)

    expect(html).toStartWith('<span')
    expect(html).toContain('--spread:15px')
    expect(html).toContain('data-duration="4"')
    expect(html).toContain('data-animate="{&quot;backgroundPosition&quot;:&quot;0% center&quot;}"')
  })

  test('highlights both themes and adds line numbers only when requested', async () => {
    const output = await highlightCode('let value = 1', 'ts', true)

    expect(output).toEqual([
      '<pre data-theme="one-light">let value = 1</pre>',
      '<pre data-theme="one-dark-pro">let value = 1</pre>',
    ])
    expect(codeToHtml).toHaveBeenCalledTimes(2)
    expect(codeToHtml).toHaveBeenNthCalledWith(1, 'let value = 1', {
      lang: 'ts',
      theme: 'one-light',
      transformers: [expect.any(Object)],
    })
    expect(codeToHtml).toHaveBeenNthCalledWith(2, 'let value = 1', {
      lang: 'ts',
      theme: 'one-dark-pro',
      transformers: [expect.any(Object)],
    })

    const transformer = codeToHtml.mock.calls[0][1].transformers[0]
    const line = { children: [] as unknown[] }
    transformer.line(line, 7)
    expect(line.children).toEqual([
      {
        type: 'element',
        tagName: 'span',
        properties: {
          className: [
            'inline-block',
            'min-w-10',
            'mr-4',
            'text-right',
            'select-none',
            'text-muted-foreground',
          ],
        },
        children: [{ type: 'text', value: '7' }],
      },
    ])
  })

  test('renders highlighted code and child copy controls', async () => {
    let renderer: ReactTestRenderer

    await act(async () => {
      renderer = create(
        <CodeBlock code="const value = 1" className="panel" language="ts">
          <CodeBlockCopyButton aria-label="Copy code" />
        </CodeBlock>,
      )
      await Promise.resolve()
    })
    renderers.push(renderer!)

    const html = JSON.stringify(renderer!.toJSON())
    expect(html).toContain('panel')
    expect(html).toContain('one-light')
    expect(html).toContain('one-dark-pro')
    expect(renderer!.root.findByType('button').props['aria-label']).toBe('Copy code')
  })

  test('copies code and reports clipboard failures', async () => {
    const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
    const previousNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
    const writeText = mock(async () => {})
    const onCopy = mock(() => {})
    const onError = mock(() => {})
    let renderer: ReactTestRenderer

    try {
      Object.defineProperty(globalThis, 'window', { configurable: true, value: {} })
      Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText } } })

      await act(async () => {
        renderer = create(
          <CodeBlock code="npm test" language="bash">
            <CodeBlockCopyButton onCopy={onCopy} onError={onError}>copy</CodeBlockCopyButton>
          </CodeBlock>,
        )
        await Promise.resolve()
      })
      renderers.push(renderer!)

      await act(async () => { await renderer!.root.findByType('button').props.onClick() })
      expect(writeText).toHaveBeenCalledWith('npm test')
      expect(onCopy).toHaveBeenCalledTimes(1)
      expect(onError).not.toHaveBeenCalled()

      Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} })
      await act(async () => { await renderer!.root.findByType('button').props.onClick() })
      expect(onError.mock.calls.at(-1)?.[0].message).toBe('Clipboard API not available')

      const clipboardError = new Error('clipboard denied')
      writeText.mockRejectedValueOnce(clipboardError)
      Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText } } })
      await act(async () => { await renderer!.root.findByType('button').props.onClick() })
      expect(onError.mock.calls.at(-1)?.[0]).toBe(clipboardError)
    } finally {
      if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow)
      else delete (globalThis as typeof globalThis & { window?: unknown }).window
      if (previousNavigator) Object.defineProperty(globalThis, 'navigator', previousNavigator)
      else delete (globalThis as typeof globalThis & { navigator?: unknown }).navigator
    }
  })

  test('maps tool states and conditionally renders tool content', () => {
    const html = renderToStaticMarkup(
      <Tool defaultOpen={false}>
        <ToolHeader type="tool-weather" state="output-error" />
        <ToolContent>forecast</ToolContent>
      </Tool>,
    )

    expect(html).toContain('data-state="closed"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('weather')
    expect(html).toContain('error')
    expect(html).not.toContain('forecast')
  })

  test('renders explicit tool errors and omits empty output', () => {
    const errorOutput = renderToStaticMarkup(<ToolOutput output={undefined} errorText="connection failed" />)
    const elementOutput = renderToStaticMarkup(<ToolOutput output={<strong>ready</strong>} errorText={undefined} />)

    expect(errorOutput).toContain('error')
    expect(errorOutput).toContain('connection failed')
    expect(elementOutput).toContain('<strong>ready</strong>')
    expect(renderToStaticMarkup(<ToolOutput output={undefined} errorText={undefined} />)).toBe('')
  })

  test('switches message branches with accessible controls', () => {
    const changes = mock(() => {})
    const renderer = render(
      <MessageBranch onBranchChange={changes}>
        <MessageBranchContent>
          <span key="first">First answer</span>
          <span key="second">Second answer</span>
        </MessageBranchContent>
        <MessageBranchSelector>
          <MessageBranchPrevious />
          <MessageBranchPage />
          <MessageBranchNext />
        </MessageBranchSelector>
      </MessageBranch>,
    )

    const buttons = renderer.root.findAllByType('button')
    expect(buttons.map(button => button.props['aria-label'])).toEqual([
      'Previous branch',
      'Next branch',
    ])
    expect(renderer.root.findByProps({ 'data-slot': 'button-group-text' }).children).toEqual(['1', ' of ', '2'])

    act(() => buttons[1].props.onClick())
    expect(renderer.root.findByProps({ 'data-slot': 'button-group-text' }).children).toEqual(['2', ' of ', '2'])
    expect(changes).toHaveBeenLastCalledWith(1)

    act(() => renderer.root.findAllByType('button')[1].props.onClick())
    expect(changes).toHaveBeenLastCalledWith(0)
    act(() => renderer.root.findAllByType('button')[0].props.onClick())
    expect(changes).toHaveBeenLastCalledWith(1)
  })

  test('renders message content, actions, and markdown paragraph variants', () => {
    streamdownComponents = undefined
    const content = renderToStaticMarkup(<MessageContent className="custom">answer</MessageContent>)
    const action = renderToStaticMarkup(<MessageAction label="Copy">copy</MessageAction>)
    const tooltip = renderToStaticMarkup(<MessageAction tooltip="Retry">retry</MessageAction>)
    const response = renderToStaticMarkup(createElement(MessageResponse, null, 'answer'))
    const paragraph = streamdownComponents?.p as ((props: Record<string, unknown>) => React.ReactElement) | undefined

    expect(content).toContain('custom')
    expect(action).toContain('Copy')
    expect(tooltip).toContain('Retry')
    expect(response).toContain('answer')
    expect(paragraph).toBeDefined()
    expect(paragraph!({ children: 'plain' }).type).toBe('p')
    expect(paragraph!({ children: <img alt="preview" />, node: { children: [] } }).type).toBe('div')
    expect(paragraph!({ children: 'preview', node: { children: [{ tagName: 'img' }] } }).type).toBe('div')
  })

  test('hides single-branch selector and wires message chrome callbacks', () => {
    const removeImage = mock(() => {})
    const removeDocument = mock(() => {})
    const single = render(
      <MessageBranch>
        <MessageBranchContent><span key="only">Only answer</span></MessageBranchContent>
        <MessageBranchSelector data-testid="selector"><MessageBranchPage /></MessageBranchSelector>
      </MessageBranch>,
    )
    const image = MessageAttachment({ data: { filename: 'photo.png', mediaType: 'image/png', url: '/photo.png' } as never, onRemove: removeImage })
    const document = MessageAttachment({ data: { filename: 'notes.pdf', mediaType: 'application/pdf', url: '/notes.pdf' } as never, onRemove: removeDocument })
    const toolbar = renderToStaticMarkup(<MessageToolbar className="compact">tools</MessageToolbar>)
    const actions = renderToStaticMarkup(<MessageActions className="stacked">copy</MessageActions>)

    expect(single.root.findAllByProps({ 'data-slot': 'button-group' })).toHaveLength(0)
    image.props.children[1].props.onClick({ stopPropagation: mock(() => {}) })
    document.props.children[0].props.render.props.children[2].props.onClick({ preventDefault: mock(() => {}), stopPropagation: mock(() => {}) })
    expect(removeImage).toHaveBeenCalledTimes(1)
    expect(removeDocument).toHaveBeenCalledTimes(1)
    expect(toolbar).toContain('compact')
    expect(actions).toContain('stacked')

    expect(renderToStaticMarkup(<MessageAttachments>{null}</MessageAttachments>)).toBe('')
    const wrapped = renderToStaticMarkup(<MessageAttachments className="wrap"><span>file</span></MessageAttachments>)
    expect(wrapped).toContain('wrap')
    expect(wrapped).toContain('file')
  })

  test('distinguishes user messages and attachment media types', () => {
    const user = renderToStaticMarkup(<Message from="user">hello</Message>)
    const assistant = renderToStaticMarkup(<Message from="assistant">hello</Message>)
    const image = renderToStaticMarkup(<MessageAttachment data={{ filename: 'photo.png', mediaType: 'image/png', url: '/photo.png' } as never} />)
    const document = renderToStaticMarkup(<MessageAttachment data={{ filename: 'notes.pdf', mediaType: 'application/pdf', url: '/notes.pdf' } as never} />)
    const spreadsheet = renderToStaticMarkup(<MessageAttachment data={{ filename: 'report.csv', mediaType: 'text/csv', url: '/report.csv' } as never} />)

    expect(user).toContain('is-user')
    expect(user).toContain('ml-auto')
    expect(assistant).toContain('is-assistant')
    expect(image).toContain('<img')
    expect(image).toContain('alt="photo.png"')
    expect(document).toContain('href="/notes.pdf"')
    expect(document).toContain('download="notes.pdf"')
    expect(document).toContain('text-red-500')
    expect(spreadsheet).toContain('text-green-500')
  })
})
