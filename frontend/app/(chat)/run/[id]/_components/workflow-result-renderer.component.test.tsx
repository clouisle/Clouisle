import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { WorkflowResultNode } from './workflow-result-renderer'

const textWithCitations = mock(() => <span data-mock="text" />)
mock.module('@/components/chat/message', () => ({ TextWithCitations: textWithCitations }))
mock.module('@/components/chat/types', () => ({}))

const { WorkflowResultRenderer: Renderer } = await import('./workflow-result-renderer')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const node = (overrides: Partial<WorkflowResultNode>): WorkflowResultNode => ({
  nodeType: 'answer',
  outputs: { answer: 'node text' },
  order: 1,
  status: 'success',
  ...overrides,
})

const renderers: ReactTestRenderer[] = []
afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  textWithCitations.mockClear()
})

function render(props: Record<string, unknown>) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<Renderer outputs={null} nodes={[]} {...props} />)
  })
  renderers.push(renderer!)
  return renderer!
}

describe('WorkflowResultRenderer', () => {
  test('renders the accumulated answer text with markdown formatting', () => {
    const renderer = render({ answerText: 'live answer' })
    expect(JSON.stringify(renderer.toJSON())).toContain('data-mock')
    expect(textWithCitations.mock.calls[0][0]).toMatchObject({ text: 'live answer', isStreaming: false })
  })

  test('stacks multiple markdown selections in separate blocks', () => {
    render({
      nodes: [
        node({ nodeType: 'answer', outputs: { answer: 'first' }, order: 1 }),
        node({ nodeType: 'answer', outputs: { answer: 'second' }, order: 2 }),
      ],
    })
    expect(textWithCitations.mock.calls.map((call) => call[0].text)).toEqual(['first', 'second'])
  })

  test('renders the JSON fallback for non-answer outputs', () => {
    const renderer = render({ outputs: { value: { ok: true } } })
    const json = JSON.stringify(renderer.toJSON())
    expect(json).toContain('{')
    expect(json).toContain('value')
    expect(json).toContain('ok')
  })

  test('renders nothing for an empty selection', () => {
    const renderer = render({})
    expect(JSON.stringify(renderer.toJSON())).toBe('null')
  })
})
