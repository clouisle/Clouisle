import { beforeAll, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

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

let ChainOfThought: typeof import('./chain-of-thought').ChainOfThought
let ChainOfThoughtContent: typeof import('./chain-of-thought').ChainOfThoughtContent
let ChainOfThoughtHeader: typeof import('./chain-of-thought').ChainOfThoughtHeader
let highlightCode: typeof import('./code-block').highlightCode
let Message: typeof import('./message').Message
let MessageAttachment: typeof import('./message').MessageAttachment
let Shimmer: typeof import('./shimmer').Shimmer
let Tool: typeof import('./tool').Tool
let ToolContent: typeof import('./tool').ToolContent
let ToolHeader: typeof import('./tool').ToolHeader
let ToolOutput: typeof import('./tool').ToolOutput

beforeAll(async () => {
  ({ ChainOfThought, ChainOfThoughtContent, ChainOfThoughtHeader } = await import('./chain-of-thought'));
  ({ highlightCode } = await import('./code-block'));
  ({ Message, MessageAttachment } = await import('./message'));
  ({ Shimmer } = await import('./shimmer'));
  ({ Tool, ToolContent, ToolHeader, ToolOutput } = await import('./tool'));
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
