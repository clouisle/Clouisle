import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { WebSearchConfig, WebSearchTestResponse } from '@/lib/api'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLInputElement: window.HTMLInputElement,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const getWebSearchConfig = mock(async () => savedConfig)
const updateWebSearchConfig = mock(async (data: unknown) => ({ ...savedConfig, ...(data as object) }))
const testWebSearchConfig = mock(async () => ({ success: true, results: [] }))
const toastSuccess = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => ({
  AlertCircle: () => <span>alert-icon</span>,
  CheckCircle2: () => <span>check-icon</span>,
  Loader2: () => <span>loader</span>,
  Play: () => <span>play-icon</span>,
}))
mock.module('@/lib/api/admin', () => ({
  adminToolsApi: { getWebSearchConfig, updateWebSearchConfig, testWebSearchConfig },
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.HTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked?: boolean; onCheckedChange?: (value: boolean) => void } & Record<string, unknown>) => (
    <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange?.(event.currentTarget.checked)} {...props} />
  ),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
const SelectContext = React.createContext<(value: string) => void>(() => {})
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (value: string) => void }) => (
    <SelectContext.Provider value={onValueChange || (() => {})}>{children}</SelectContext.Provider>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const onValueChange = React.useContext(SelectContext)
    return <button data-select-value={value} onClick={() => onValueChange(value)}>{children}</button>
  },
  SelectTrigger: ({ children, ...props }: { children: React.ReactNode } & Record<string, unknown>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

const savedConfig: WebSearchConfig = {
  default_engine: 'tavily',
  tavily_enabled: true,
  bocha_enabled: false,
  searxng_enabled: false,
  searxng_base_url: 'https://search.example.test/searxng',
  tavily_api_key_configured: true,
  bocha_api_key_configured: false,
  searxng_auth_token_configured: true,
  legacy_credentials_present: true,
}

// Static import cannot work here: the component under test imports the modules
// mocked above, so it must be loaded after the mock registrations.
const { WebSearchConfigDialog } = await import('./web-search-config-dialog')

const roots: Root[] = []

beforeEach(() => {
  getWebSearchConfig.mockClear()
  getWebSearchConfig.mockResolvedValue(savedConfig)
  updateWebSearchConfig.mockClear()
  updateWebSearchConfig.mockImplementation(async (data: unknown) => ({ ...savedConfig, ...(data as Partial<WebSearchConfig>) }))
  testWebSearchConfig.mockClear()
  testWebSearchConfig.mockResolvedValue({ success: true, results: [] })
  toastSuccess.mockClear()
})

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

async function renderDialog() {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  await act(async () => {
    root.render(<WebSearchConfigDialog open onOpenChange={() => {}} />)
    await Promise.resolve()
    await Promise.resolve()
  })
  return container
}

function button(container: HTMLElement, label: string) {
  const found = [...container.querySelectorAll('button')].find((item) => item.textContent?.includes(label))
  if (!found) throw new Error(`Missing button ${label}: ${container.textContent}`)
  return found
}

function onInput(container: HTMLElement, selector: string, value: string) {
  const input = container.querySelector(selector) as HTMLInputElement | null
  if (!input) throw new Error(`Missing input ${selector}`)
  const propsKey = Object.keys(input).find((key) => key.startsWith('__reactProps$'))
  if (!propsKey) throw new Error(`Missing React props for ${selector}`)
  const props = (input as unknown as Record<string, { onChange: (event: { target: { value: string } }) => void }>)[propsKey]
  act(() => props.onChange({ target: { value } }))
}

function toggleProvider(container: HTMLElement, provider: 'tavily' | 'bocha' | 'searxng', checked: boolean) {
  const label = `tools.webSearch.${provider} tools.webSearch.providerEnabled`
  const input = container.querySelector(`input[aria-label="${label}"]`) as HTMLInputElement | null
  if (!input) throw new Error(`Missing provider switch ${label}`)
  const propsKey = Object.keys(input).find((key) => key.startsWith('__reactProps$'))
  if (!propsKey) throw new Error(`Missing React props for ${label}`)
  const props = (input as unknown as Record<string, { onChange: (event: { currentTarget: { checked: boolean } }) => void }>)[propsKey]
  act(() => props.onChange({ currentTarget: { checked } }))
}

describe('WebSearchConfigDialog', () => {
  test('loads the saved site config, keeps secrets blank, and shows the legacy warning', async () => {
    const container = await renderDialog()

    expect(getWebSearchConfig).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('tools.webSearch.legacyWarning')
    expect(container.textContent).toContain('tools.webSearch.keyConfigured')
    expect(container.textContent).toContain('tools.webSearch.searxngUrlChangeHint')
    expect((container.querySelector('#web-search-tavily-api-key') as HTMLInputElement).value).toBe('')
    expect((container.querySelector('#web-search-bocha-api-key') as HTMLInputElement).value).toBe('')
    expect((container.querySelector('#web-search-searxng-auth-token') as HTMLInputElement).value).toBe('')
    expect((container.querySelector('#web-search-searxng-base-url') as HTMLInputElement).value).toBe('https://search.example.test/searxng')
  })

  test('preserves saved secrets when saving without touching the secret fields', async () => {
    const container = await renderDialog()

    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(updateWebSearchConfig).toHaveBeenCalledTimes(1)
    const payload = updateWebSearchConfig.mock.calls[0][0] as Record<string, unknown>
    expect(payload).toEqual({
      default_engine: 'tavily',
      tavily_enabled: true,
      bocha_enabled: false,
      searxng_enabled: false,
      searxng_base_url: 'https://search.example.test/searxng',
    })
    expect(payload).not.toHaveProperty('tavily_api_key')
    expect(payload).not.toHaveProperty('bocha_api_key')
    expect(payload).not.toHaveProperty('searxng_auth_token')
    expect(toastSuccess).toHaveBeenCalledWith('tools.webSearch.saved')
  })

  test('clears a saved secret explicitly and can undo the clear', async () => {
    const container = await renderDialog()

    act(() => button(container, 'tools.webSearch.clearKey').click())
    expect(container.textContent).toContain('tools.webSearch.willClear')
    act(() => button(container, 'tools.webSearch.undoClear').click())
    await act(async () => button(container, 'tools.webSearch.save').click())
    expect(updateWebSearchConfig.mock.calls[0][0]).not.toHaveProperty('tavily_api_key')

    updateWebSearchConfig.mockClear()
    act(() => button(container, 'tools.webSearch.clearKey').click())
    await act(async () => button(container, 'tools.webSearch.save').click())
    expect(updateWebSearchConfig.mock.calls[0][0]).toMatchObject({ tavily_api_key: '' })
  })

  test('sends only entered replacement secrets, trimmed', async () => {
    const container = await renderDialog()

    onInput(container, '#web-search-tavily-api-key', '  tvly-new  ')
    onInput(container, '#web-search-bocha-api-key', ' sk-new ')
    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(updateWebSearchConfig.mock.calls[0][0]).toMatchObject({
      tavily_api_key: 'tvly-new',
      bocha_api_key: 'sk-new',
    })
  })

  test('enables SearXNG as default and saves a trimmed URL and bearer token', async () => {
    const container = await renderDialog()

    toggleProvider(container, 'searxng', true)
    onInput(container, '#web-search-searxng-base-url', '  https://search.example.test/searxng/  ')
    onInput(container, '#web-search-searxng-auth-token', '  bearer-token  ')
    act(() => (container.querySelectorAll('button[data-select-value="searxng"]')[0] as HTMLButtonElement).click())
    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(updateWebSearchConfig.mock.calls[0][0]).toMatchObject({
      default_engine: 'searxng',
      searxng_enabled: true,
      searxng_base_url: 'https://search.example.test/searxng/',
      searxng_auth_token: 'bearer-token',
    })
  })

  test('requires a base URL before enabling SearXNG', async () => {
    const container = await renderDialog()

    toggleProvider(container, 'searxng', true)
    onInput(container, '#web-search-searxng-base-url', '   ')
    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(container.textContent).toContain('tools.webSearch.searxngBaseUrlRequired')
    expect(updateWebSearchConfig).not.toHaveBeenCalled()
  })

  test('requires token replacement or explicit clear when the SearXNG URL changes', async () => {
    const container = await renderDialog()

    onInput(container, '#web-search-searxng-base-url', 'https://other.example.test/searxng')
    await act(async () => button(container, 'tools.webSearch.save').click())
    expect(container.textContent).toContain('tools.webSearch.searxngTokenConfirmationRequired')
    expect(updateWebSearchConfig).not.toHaveBeenCalled()

    // A trailing-slash-only difference is the same normalized URL.
    onInput(container, '#web-search-searxng-base-url', 'https://search.example.test/searxng/')
    await act(async () => button(container, 'tools.webSearch.save').click())
    expect(container.textContent).not.toContain('tools.webSearch.searxngTokenConfirmationRequired')
    expect(updateWebSearchConfig).toHaveBeenCalledWith(expect.objectContaining({
      searxng_base_url: 'https://search.example.test/searxng/',
    }))
  })

  test('clears a saved SearXNG bearer token explicitly', async () => {
    const container = await renderDialog()

    const clearButtons = [...container.querySelectorAll('button')].filter((item) => item.textContent?.includes('tools.webSearch.clearKey'))
    act(() => clearButtons.at(-1)!.click())
    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(updateWebSearchConfig.mock.calls[0][0]).toMatchObject({ searxng_auth_token: '' })
  })

  test('surfaces save errors without duplicating secrets', async () => {
    updateWebSearchConfig.mockRejectedValue(new Error('save failed'))
    const container = await renderDialog()

    onInput(container, '#web-search-tavily-api-key', 'tvly-secret')
    await act(async () => button(container, 'tools.webSearch.save').click())

    expect(container.textContent).toContain('save failed')
    expect(container.textContent).not.toContain('tvly-secret')
  })

  test('ignores a test response that resolves after the dialog is closed and reopened', async () => {
    let resolveTest!: (result: WebSearchTestResponse) => void
    testWebSearchConfig.mockImplementationOnce(() => {
      const pending = Promise.withResolvers<WebSearchTestResponse>()
      resolveTest = pending.resolve
      return pending.promise
    })
    const container = await renderDialog()
    const root = roots[roots.length - 1]

    onInput(container, 'input[aria-label="tools.webSearch.testQuery"]', 'slow query')
    await act(async () => button(container, 'tools.webSearch.runTest').click())

    await act(async () => {
      root.render(<WebSearchConfigDialog open={false} onOpenChange={() => {}} />)
      await Promise.resolve()
    })
    await act(async () => {
      root.render(<WebSearchConfigDialog open onOpenChange={() => {}} />)
      await Promise.resolve()
      await Promise.resolve()
    })
    await act(async () => {
      resolveTest({ success: true, results: [{ title: 'Stale result', url: 'https://stale.test' }] })
      await Promise.resolve()
    })

    expect(container.textContent).not.toContain('Stale result')
  })

  test('runs the saved-config test and renders provider errors and result links', async () => {
    testWebSearchConfig.mockRejectedValueOnce(new Error('network error'))
    const container = await renderDialog()

    onInput(container, 'input[aria-label="tools.webSearch.testQuery"]', 'clouisle')
    await act(async () => button(container, 'tools.webSearch.runTest').click())
    expect(container.textContent).toContain('network error')
    expect(testWebSearchConfig).toHaveBeenLastCalledWith({ query: 'clouisle', engine: 'auto' })

    testWebSearchConfig.mockResolvedValueOnce({ success: false, error: 'provider unavailable', results: [] })
    await act(async () => button(container, 'tools.webSearch.runTest').click())
    expect(container.textContent).toContain('provider unavailable')

    testWebSearchConfig.mockResolvedValueOnce({
      success: true,
      search_engine: 'tavily',
      results: [{ title: 'Clouisle docs', url: 'https://example.test/docs', content: 'Docs' }],
    })
    await act(async () => button(container, 'tools.webSearch.runTest').click())
    expect(container.textContent).toContain('Clouisle docs')
    const link = container.querySelector('a[href="https://example.test/docs"]')
    expect(link).not.toBeNull()
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer')

    toggleProvider(container, 'searxng', true)
    const searxngOptions = container.querySelectorAll('button[data-select-value="searxng"]')
    act(() => (searxngOptions[searxngOptions.length - 1] as HTMLButtonElement).click())
    testWebSearchConfig.mockResolvedValueOnce({ success: true, search_engine: 'searxng', results: [] })
    await act(async () => button(container, 'tools.webSearch.runTest').click())
    expect(testWebSearchConfig).toHaveBeenLastCalledWith({ query: 'clouisle', engine: 'searxng' })
  })
})
