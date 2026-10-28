import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { RunInteraction, RunInteractionResponseInput } from '@/lib/api'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('lucide-react', () => ({
  AlertTriangle: () => <span data-icon="warning" />,
  ExternalLink: () => <span data-icon="external" />,
  Loader2: () => <span data-icon="loader" />,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/lib/utils/idempotency', () => ({
  createIdempotencyKey: (prefix: string) => `${prefix}-fixed`,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span data-badge>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, render, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
    if (render && React.isValidElement(render)) {
      return React.cloneElement(render, props, children)
    }
    return <button {...props}>{children}</button>
  },
}))
mock.module('@/lib/api', () => ({
  getElicitationUrl: (payload: { mode: string; url?: string }) =>
    payload.mode === 'url' && payload.url && /^https?:\/\//.test(payload.url) ? payload.url : null,
}))

const { InteractionRequestCard } = await import('./interaction-request-card')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function baseInteraction(overrides: Partial<RunInteraction>): RunInteraction {
  return {
    id: 'interaction-1',
    kind: 'elicitation',
    status: 'pending',
    run_kind: 'agent',
    run_id: 'run-1',
    execution_id: 'execution-1',
    tool_id: 'tool-1',
    tool_call_id: 'call-1',
    tool_name: 'mcp_tool',
    team_id: 'team-1',
    payload: {
      mode: 'form',
      message: 'Please confirm',
      requested_schema: { type: 'object', properties: {} },
    },
    audience: { user_ids: ['user-1'], roles: [] },
    expires_at: null,
    responded_at: null,
    responded_by_id: null,
    outcome: null,
    response: null,
    created_at: '2026-10-26T00:00:00Z',
    ...overrides,
  }
}

function renderCard(interaction: RunInteraction, onRespond: (id: string, input: RunInteractionResponseInput) => Promise<unknown>) {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(<InteractionRequestCard interaction={interaction} onRespond={onRespond} />)
  })
  renderers.push(renderer)
  return renderer
}

function textOfChildren(children: React.ReactNode): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(textOfChildren).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(children)) {
    return textOfChildren(children.props.children)
  }
  return ''
}

function textOf(node: { props: Record<string, unknown> }): string {
  return textOfChildren(node.props.children as React.ReactNode)
}

function buttonByText(renderer: ReactTestRenderer, text: string) {
  return renderer.root
    .findAllByType('button')
    .find((button) => textOf(button).includes(text))
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('InteractionRequestCard', () => {
  test('submits only validated form values on accept', async () => {
    const onRespond = mock(async () => ({}))
    const interaction = baseInteraction({
      payload: {
        mode: 'form',
        message: 'Please confirm',
        requested_schema: {
          type: 'object',
          required: ['name', 'count'],
          properties: {
            name: { type: 'string', title: 'Name' },
            count: { type: 'number' },
            enabled: { type: 'boolean', default: true },
          },
        },
      },
    })
    const renderer = renderCard(interaction, onRespond)

    const accept = buttonByText(renderer, 'accept')
    act(() => accept?.props.onClick())
    await flush()
    expect(onRespond).not.toHaveBeenCalled()
    expect(renderer.root.findAll((node) => textOf(node).includes('fieldRequired')).length).toBeGreaterThan(0)

    const nameInput = renderer.root.findAllByType('input').find((input) => String(input.props.id).endsWith('-name'))
    const countInput = renderer.root.findAllByType('input').find((input) => String(input.props.id).endsWith('-count'))
    act(() => nameInput?.props.onChange({ target: { value: 'Ada' } }))
    act(() => countInput?.props.onChange({ target: { value: '4' } }))
    act(() => accept?.props.onClick())
    await flush()

    expect(onRespond).toHaveBeenCalledWith('interaction-1', {
      action: 'accept',
      content: { name: 'Ada', count: 4, enabled: true },
      idempotency_key: 'interaction-accept-fixed',
    })
  })

  test('declines with a null content payload', async () => {
    const onRespond = mock(async () => ({}))
    const renderer = renderCard(baseInteraction({}), onRespond)

    act(() => buttonByText(renderer, 'decline')?.props.onClick())
    await flush()

    expect(onRespond).toHaveBeenCalledWith('interaction-1', {
      action: 'decline',
      content: null,
      idempotency_key: 'interaction-decline-fixed',
    })
  })

  test('accepts sampling without client content', async () => {
    const onRespond = mock(async () => ({}))
    const renderer = renderCard(
      baseInteraction({
        kind: 'sampling',
        payload: {
          mode: 'sampling',
          system_prompt: 'Be concise',
          messages: [{ role: 'user', content: 'Hello' }],
          max_tokens: 128,
          model_preferences: null,
        },
      }),
      onRespond
    )

    expect(renderer.root.findAll((node) => textOf(node).includes('Be concise')).length).toBeGreaterThan(0)
    act(() => buttonByText(renderer, 'acceptSampling')?.props.onClick())
    await flush()

    expect(onRespond).toHaveBeenCalledWith('interaction-1', {
      action: 'accept',
      content: null,
      idempotency_key: 'interaction-accept-fixed',
    })
  })

  test('blocks credential-shaped forms and invalid authorization URLs', () => {
    const secretRenderer = renderCard(
      baseInteraction({
        payload: {
          mode: 'form',
          message: 'Enter password',
          requested_schema: {
            type: 'object',
            required: ['password'],
            properties: { password: { type: 'string' } },
          },
        },
      }),
      mock(async () => ({}))
    )
    const secretAccept = buttonByText(secretRenderer, 'accept')
    expect(secretAccept?.props.disabled).toBe(true)
    expect(secretRenderer.root.findAll((node) => textOf(node).includes('secretFieldsBlocked')).length).toBeGreaterThan(0)

    const invalidUrlRenderer = renderCard(
      baseInteraction({
        payload: { mode: 'url', message: 'Authorize', url: 'javascript:alert(1)' },
      }),
      mock(async () => ({}))
    )
    expect(buttonByText(invalidUrlRenderer, 'accept')?.props.disabled).toBe(true)

    const validUrlRenderer = renderCard(
      baseInteraction({
        payload: { mode: 'url', message: 'Authorize', url: 'https://example.com/auth' },
      }),
      mock(async () => ({}))
    )
    expect(buttonByText(validUrlRenderer, 'accept')?.props.disabled).toBe(false)
    expect(validUrlRenderer.root.findAllByType('a')[0].props.href).toBe('https://example.com/auth')
  })
})
