import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

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

let ChainOfThought: typeof import('./chain-of-thought').ChainOfThought
let ChainOfThoughtContent: typeof import('./chain-of-thought').ChainOfThoughtContent
let ChainOfThoughtHeader: typeof import('./chain-of-thought').ChainOfThoughtHeader
let highlightCode: typeof import('./code-block').highlightCode
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
  ({ highlightCode } = await import('./code-block'));
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

    expect(user).toContain('is-user')
    expect(user).toContain('ml-auto')
    expect(assistant).toContain('is-assistant')
    expect(image).toContain('<img')
    expect(image).toContain('alt="photo.png"')
    expect(document).toContain('href="/notes.pdf"')
    expect(document).toContain('download="notes.pdf"')
  })
})
