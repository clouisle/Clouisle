import { describe, expect, test } from 'bun:test'
import { extractVariables } from './extract-variables'

describe('extractVariables', () => {
  test('returns agent variables and ignores invalid metadata', () => {
    const variables = [{ name: 'query', type: 'text' as const, required: true }]

    expect(extractVariables({ variables }, 'agent')).toBe(variables)
    expect(extractVariables(null, 'agent')).toEqual([])
  })

  test('maps workflow metadata variables', () => {
    expect(
      extractVariables(
        {
          variables: [
            {
              name: 'limit',
              type: 'number',
              required: false,
              default: 10,
              description: 'Maximum results',
            },
          ],
        },
        'workflow'
      )
    ).toEqual([
      {
        name: 'limit',
        type: 'number',
        required: false,
        default: '10',
        description: 'Maximum results',
        label: 'limit',
      },
    ])
  })

  test('falls back to a workflow start node and handles missing inputs', () => {
    expect(
      extractVariables(
        {
          definition: {
            nodes: [
              { data: { type: 'other' } },
              {
                data: {
                  type: 'trigger',
                  config: {
                    parameters: [
                      { name: 'status', description: '', label: 'Status' },
                    ],
                  },
                },
              },
            ],
          },
        },
        'workflow'
      )
    ).toEqual([
      {
        name: 'status',
        type: 'text',
        required: true,
        default: null,
        description: null,
        label: 'Status',
      },
    ])
    expect(extractVariables({ definition: { nodes: [] } }, 'workflow')).toEqual([])
  })
})
