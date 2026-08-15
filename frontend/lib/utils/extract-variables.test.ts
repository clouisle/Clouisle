import { describe, expect, test } from 'bun:test'

import { extractVariables } from './extract-variables'

describe('extractVariables', () => {
  test('returns agent variables unchanged', () => {
    const variables = [{ name: 'query', type: 'text', required: true, default: 'hello' }]

    expect(extractVariables({ variables }, 'agent')).toBe(variables)
  })

  test('normalizes explicit workflow variables', () => {
    expect(extractVariables({
      variables: [
        { name: 'limit', type: 'number', required: false, default: 0, description: null },
        { name: 'topic', type: '', required: true, default: 'AI', description: 'Subject' },
      ],
    }, 'workflow')).toEqual([
      { name: 'limit', type: 'number', required: false, default: 0, description: null, label: 'limit' },
      { name: 'topic', type: 'text', required: true, default: 'AI', description: 'Subject', label: 'topic' },
    ])
  })

  test('falls back to start-node parameters and rejects invalid metadata', () => {
    const workflow = {
      variables: [],
      definition: {
        nodes: [
          { data: { type: 'other', config: { parameters: [{ name: 'ignored' }] } } },
          { data: { type: 'trigger', config: { parameters: [{ name: 'event', required: false, label: '' }] } } },
        ],
      },
    }

    expect(extractVariables(workflow, 'workflow')).toEqual([
      { name: 'event', type: 'text', required: false, default: null, description: null, label: 'event' },
    ])
    expect(extractVariables(null, 'workflow')).toEqual([])
    expect(extractVariables('not metadata', 'agent')).toEqual([])
    expect(extractVariables({ definition: { nodes: [{ data: { type: 'user_input' } }] } }, 'workflow')).toEqual([])
  })

  test('falls back to user_input node parameters with options and fileConfig', () => {
    expect(extractVariables({
      variables: [],
      definition: {
        nodes: [
          { data: { type: 'user_input', parameters: [
            { name: 'doc', type: 'file', required: true, label: 'Document', fileConfig: { maxSize: 5, accept: ['.pdf'] } },
            { name: 'mode', type: 'select', required: false, options: ['a', 'b'] },
          ] } },
        ],
      },
    }, 'workflow')).toEqual([
      { name: 'doc', type: 'file', required: true, default: null, description: null, label: 'Document', fileConfig: { maxSize: 5, accept: ['.pdf'] } },
      { name: 'mode', type: 'select', required: false, default: null, description: null, label: 'mode', options: ['a', 'b'] },
    ])
  })
})
