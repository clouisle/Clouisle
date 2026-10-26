import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const refresh = mock(async () => undefined)
const respond = mock(async () => ({ id: 'interaction-1', outcome: 'accept' }))
const toastSuccess = mock(() => undefined)
let hookState: Record<string, unknown> = {}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: mock(() => undefined) } }))
mock.module('lucide-react', () => ({
  Loader2: () => <span data-icon="loader" />,
  RefreshCw: () => <span data-icon="refresh" />,
  ServerCog: () => <span data-icon="server" />,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/tool-interactions', () => ({
  InteractionRequestCard: ({
    interaction,
    onRespond,
  }: {
    interaction: { id: string }
    onRespond: (id: string, input: Record<string, unknown>) => Promise<unknown>
  }) => (
    <div data-testid={`card-${interaction.id}`}>
      <button onClick={() => void onRespond(interaction.id, {
        action: 'accept',
        content: null,
        idempotency_key: 'key',
      })}>accept</button>
    </div>
  ),
}))
mock.module('@/hooks/use-run-interactions', () => ({
  useRunInteractions: () => hookState,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { RunInteractionPanel } = await import('./run-interaction-panel')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function textOfChildren(children: React.ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(textOfChildren).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(children)) {
    return textOfChildren(children.props.children)
  }
  return ''
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('RunInteractionPanel', () => {
  test('renders pending requests and refreshes the run after a response', async () => {
    const onRefreshRun = mock(async () => undefined)
    hookState = {
      interactions: [{
        id: 'interaction-1',
        kind: 'sampling',
        status: 'pending',
        payload: { mode: 'sampling', system_prompt: null, messages: [], max_tokens: 12, model_preferences: null },
      }],
      isLoading: false,
      error: null,
      refresh,
      respond,
    }
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<RunInteractionPanel runId="run-1" enabled onRefreshRun={onRefreshRun} />)
    })
    renderers.push(renderer)
    await flush()

    expect(renderer.root.findAllByProps({ 'data-testid': 'card-interaction-1' })).toHaveLength(1)
    const accept = renderer.root.findAllByType('button').find((button) => textOfChildren(button.props.children) === 'accept')
    act(() => accept?.props.onClick())
    await flush()

    expect(respond).toHaveBeenCalledWith('interaction-1', {
      action: 'accept',
      content: null,
      idempotency_key: 'key',
    })
    expect(toastSuccess).toHaveBeenCalledWith('acceptedToast')
    expect(onRefreshRun).toHaveBeenCalled()
  })

  test('stays hidden without requests and shows a retryable error', async () => {
    hookState = { interactions: [], isLoading: false, error: null, refresh, respond }
    let renderer!: ReactTestRenderer
    act(() => {
      renderer = create(<RunInteractionPanel runId="run-1" enabled />)
    })
    renderers.push(renderer)
    await flush()
    expect(renderer.toJSON()).toBeNull()

    hookState = { interactions: [], isLoading: false, error: new Error('offline'), refresh, respond }
    act(() => renderer.update(<RunInteractionPanel runId="run-1" enabled />))
    await flush()
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('interactionRefreshFailed')
    expect(text).toContain('retry')
  })
})
