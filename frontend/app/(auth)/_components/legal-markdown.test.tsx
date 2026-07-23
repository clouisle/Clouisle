import { Window } from 'happy-dom'
import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import { act, createElement, type ComponentType, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import MDEditor from '@uiw/react-md-editor'

let theme: string | undefined = 'light'
let showLoading = false
let markdownLoad: Promise<unknown>

mock.module('next/dynamic', () => ({
  default: (
    loader: () => Promise<unknown>,
    options: { loading: ComponentType },
  ) => {
    markdownLoad = loader()
    return (props: { source: string }) => createElement(
      showLoading ? options.loading : MDEditor.Markdown,
      props,
    )
  },
}))

mock.module('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: theme }),
}))

mock.module('@/components/ui/dialog', () => ({
  DialogContent: ({ children }: { children: ReactNode }) => <section>{children}</section>,
  DialogHeader: ({ children }: { children: ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}))

const { LegalMarkdown, LegalMarkdownDialogContent, preloadLegalMarkdown } = await import('./legal-markdown')

afterEach(() => {
  theme = 'light'
  showLoading = false
  delete (globalThis as { window?: unknown }).window
})

describe('LegalMarkdown', () => {
  test('renders supported legal markdown as visible semantic content', async () => {
    await markdownLoad
    const html = renderToStaticMarkup(
      <LegalMarkdown source={'# Terms\n\n## Details\n\nParagraph with **strong** and *emphasis*.\n\n- First\n- Second\n\n1. Ordered\n\n> Quote\n\n`inline`\n\n```text\nblock\n```'} />,
    )

    expect(html).toContain('<h1')
    expect(html).toContain('Terms</h1>')
    expect(html).toContain('<h2')
    expect(html).toContain('<p>Paragraph with <strong>strong</strong> and <em>emphasis</em>.</p>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>First</li>')
    expect(html).toContain('<ol>')
    expect(html).toContain('<blockquote>')
    expect(html).toContain('<code>inline</code>')
    expect(html).toContain('<pre class="language-text"><code class="language-text code-highlight">')
  })

  test('renders safe links and strips unsafe link destinations', () => {
    const html = renderToStaticMarkup(
      <LegalMarkdown source={'[Policy](https://example.com/policy) [Section](/legal#terms) [Email](mailto:legal@example.com) [Unsafe](javascript:alert(1))'} />,
    )

    expect(html).toContain('href="https://example.com/policy"')
    expect(html).toContain('href="/legal#terms"')
    expect(html).toContain('href="mailto:legal@example.com"')
    expect(html).toContain('>Unsafe</a>')
    expect(html).toContain('React has blocked a javascript: URL as a security precaution')
    expect(html).not.toContain('href="javascript:alert(1)"')
  })

  test('keeps malformed and boundary input visible', () => {
    const html = renderToStaticMarkup(
      <LegalMarkdown source={'\n\nUnclosed **bold and [link](<bad url>)\n\n'} />,
    )

    expect(html).toContain('Unclosed **bold')
    expect(html).toContain('href="bad%20url"')
    expect(html).toContain('>link</a>')
  })

  test('defaults to light mode, then applies the mounted client theme', async () => {
    theme = 'dark'

    const html = renderToStaticMarkup(<LegalMarkdown source="Privacy" />)
    expect(html).toContain('data-color-mode="light"')
    expect(html).toContain('Privacy')

    const window = new Window()
    Object.assign(globalThis, {
      window,
      document: window.document,
      navigator: window.navigator,
      IS_REACT_ACT_ENVIRONMENT: true,
    })
    const container = document.createElement('div')
    const root = createRoot(container)
    await act(async () => root.render(<LegalMarkdown source="Privacy" />))
    expect(container.firstElementChild?.getAttribute('data-color-mode')).toBe('dark')
    act(() => root.unmount())
  })

  test('shows the legal title and loading placeholder in dialog context', () => {
    showLoading = true

    const html = renderToStaticMarkup(
      <LegalMarkdownDialogContent title="Privacy Policy" source="Pending policy" />,
    )

    expect(html).toContain('<h2>Privacy Policy</h2>')
    expect(html).toContain('aria-hidden="true"')
    expect(html).not.toContain('Pending policy')
  })

  test('preload is safe with and without a browser window', async () => {
    expect(preloadLegalMarkdown()).toBeUndefined()

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {},
    })
    const caught = Promise.resolve()
    const catchSpy = spyOn(Promise.prototype, 'catch').mockImplementation((onRejected) => {
      onRejected?.(new Error('load failed'))
      return caught
    })
    expect(preloadLegalMarkdown()).toBeUndefined()
    await caught
    catchSpy.mockRestore()
  })
})
