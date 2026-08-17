import { describe, expect, test } from 'bun:test'
import { selectWorkflowResults, type WorkflowResultNode } from './workflow-result-renderer'

const node = (overrides: Partial<WorkflowResultNode>): WorkflowResultNode => ({
  nodeType: 'llm',
  outputs: { text: 'node result' },
  order: 1,
  status: 'success',
  ...overrides,
})

describe('selectWorkflowResults', () => {
  test('live run renders only the accumulated answer stream', () => {
    expect(selectWorkflowResults(
      { answer: 'saved' },
      [node({ order: 2 }), node({ nodeType: 'answer', outputs: { answer: 'node answer' }, order: 1 })],
      'live streamed',
    )).toEqual([{ kind: 'markdown', text: 'live streamed' }])
  })

  test('history stacks every answer node in execution order, ignoring other nodes', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'code', outputs: { result: 'code out' }, order: 3 }),
      node({ nodeType: 'answer', outputs: { answer: 'first answer' }, order: 1 }),
      node({ nodeType: 'answer', outputs: { answer: 'second answer' }, order: 2 }),
    ])).toEqual([
      { kind: 'markdown', text: 'first answer' },
      { kind: 'markdown', text: 'second answer' },
    ])
  })

  test('intermediate nodes are never displayed even without answer nodes', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'code', outputs: { result: 'code out' }, order: 1 }),
      node({ nodeType: 'media_generation', outputs: { image: '/a.png' }, order: 2 }),
    ])).toEqual([{ kind: 'empty' }])
  })

  test('skips incomplete answer nodes and start echoes', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'start', outputs: { query: 'echo' }, order: 0 }),
      node({ nodeType: 'answer', outputs: { answer: 'still running' }, order: 1, status: 'running' }),
    ])).toEqual([{ kind: 'empty' }])
  })

  test('falls back to the canonical persisted answer, then JSON outputs', () => {
    expect(selectWorkflowResults({ answer: 'saved' }, [])).toEqual([
      { kind: 'markdown', text: 'saved' },
    ])
    expect(selectWorkflowResults({ value: { ok: true } }, [])).toEqual([
      { kind: 'json', outputs: { value: { ok: true } } },
    ])
    expect(selectWorkflowResults(null, [])).toEqual([{ kind: 'empty' }])
  })
})
