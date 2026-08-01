import { describe, expect, test } from 'bun:test'
import { selectWorkflowResult, type WorkflowResultNode } from './workflow-result-renderer'

const node = (overrides: Partial<WorkflowResultNode>): WorkflowResultNode => ({
  nodeType: 'llm',
  outputs: { text: 'node result' },
  order: 1,
  status: 'success',
  ...overrides,
})

describe('selectWorkflowResult', () => {
  test('prefers streamed answer over persisted outputs', () => {
    expect(selectWorkflowResult({ answer: 'saved' }, [], 'live')).toEqual({ kind: 'markdown', text: 'live' })
  })

  test('uses canonical answer before node output', () => {
    expect(selectWorkflowResult({ answer: 'saved' }, [node({ order: 2 })])).toEqual({
      kind: 'markdown',
      text: 'saved',
    })
  })

  test('uses answer node output before other nodes', () => {
    expect(selectWorkflowResult(null, [
      node({ nodeType: 'answer', outputs: { answer: 'answer node' }, order: 1 }),
      node({ order: 2 }),
    ])).toEqual({ kind: 'markdown', text: 'answer node' })
  })

  test('falls back to an ordered typed node, then JSON', () => {
    expect(selectWorkflowResult(null, [node({ order: 3 })])).toMatchObject({ kind: 'node' })
    expect(selectWorkflowResult({ value: { ok: true } }, [])).toEqual({
      kind: 'json',
      outputs: { value: { ok: true } },
    })
  })
})
