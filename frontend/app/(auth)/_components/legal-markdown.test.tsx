import { afterEach, describe, expect, mock, test } from 'bun:test'
import { createElement, type ComponentType, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import MDEditor from '@uiw/react-md-editor'

let theme: string | undefined = 'light'
let showLoading = false

mock.module('next/dynamic', () => ({
  default: (
    _loader: () => Promise<unknown>,
    options: { loading: ComponentType },
  ) => (props: { source: string }) => createElement(
    showLoading ? options.loading : MDEditor.Markdown,
    props,
  ),
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
  test('renders supported legal markdown as visible semantic content', () => {
    const html = renderToStaticMarkup(
      <LegalMarkdown source={'# Terms\n\n**Important** notice.\n\n- First\n- Second\n\n`code`'} />,
    )

    expect(html).toContain('<h1')
    expect(html).toContain('Terms</h1>')
    expect(html).toContain('<strong>Important</strong>')
    expect(html).toContain('<li>First</li>')
    expect(html).toContain('<code>code</code>')
  })

  test('renders safe links and strips unsafe link destinations', () => {
    const html = renderToStaticMarkup(
      <LegalMarkdown source={'[Policy](https://example.com/policy) [Email](mailto:legal@example.com) [Unsafe](javascript:alert(1))'} />,
    )

    expect(html).toContain('href="https://example.com/policy"')
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

  test('defaults to visible light mode before client mounting', () => {
    theme = 'dark'

    const html = renderToStaticMarkup(<LegalMarkdown source="Privacy" />)

    expect(html).toContain('data-color-mode="light"')
    expect(html).toContain('Privacy')
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

  test('preload is safe with and without a browser window', () => {
    expect(preloadLegalMarkdown()).toBeUndefined()

    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {},
    })
    expect(preloadLegalMarkdown()).toBeUndefined()
  })
})
