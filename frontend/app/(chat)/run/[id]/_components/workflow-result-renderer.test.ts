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
  test('prefers streamed answer over persisted outputs', () => {
    expect(selectWorkflowResults({ answer: 'saved' }, [], 'live')).toEqual([
      { kind: 'markdown', text: 'live' },
    ])
  })

  test('uses canonical answer and stacks remaining output nodes', () => {
    expect(selectWorkflowResults({ answer: 'saved' }, [node({ order: 2 })])).toEqual([
      { kind: 'markdown', text: 'saved' },
      { kind: 'node', node: node({ order: 2 }) },
    ])
  })

  test('uses the last-executed answer node text and stacks the other nodes', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'answer', outputs: { answer: 'answer node' }, order: 1 }),
      node({ order: 2 }),
    ])).toEqual([
      { kind: 'markdown', text: 'answer node' },
      { kind: 'node', node: node({ order: 2 }) },
    ])
  })

  test('stacks every completed output node in execution order', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'code', outputs: { result: 'code out' }, order: 2 }),
      node({ nodeType: 'media_generation', outputs: { image: '/a.png' }, order: 1 }),
    ])).toEqual([
      { kind: 'node', node: node({ nodeType: 'media_generation', outputs: { image: '/a.png' }, order: 1 }) },
      { kind: 'node', node: node({ nodeType: 'code', outputs: { result: 'code out' }, order: 2 }) },
    ])
  })

  test('skips start/trigger echo nodes and incomplete nodes', () => {
    expect(selectWorkflowResults(null, [
      node({ nodeType: 'start', outputs: { query: 'echo' }, order: 0 }),
      node({ nodeType: 'code', outputs: { result: 'done' }, order: 1, status: 'running' }),
      node({ nodeType: 'trigger', outputs: { event: 'echo' }, order: 2 }),
    ])).toEqual([{ kind: 'empty' }])
  })

  test('falls back to JSON outputs when no answer or node output exists', () => {
    expect(selectWorkflowResults({ value: { ok: true } }, [])).toEqual([
      { kind: 'json', outputs: { value: { ok: true } } },
    ])
    expect(selectWorkflowResults(null, [])).toEqual([{ kind: 'empty' }])
  })
})
