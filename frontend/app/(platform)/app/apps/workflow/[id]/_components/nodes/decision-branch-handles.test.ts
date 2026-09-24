import { describe, expect, test } from 'bun:test'
import {
  getDecisionOutputHandles,
  migrateLegacyDecisionBranchEdges,
  remapDecisionBranchEdges,
} from './decision-branch-handles'

describe('decision branch handles', () => {
  test('exposes named choice outputs and fixed Noul outputs', () => {
    expect(getDecisionOutputHandles({
      questionType: 'choice',
      options: ['support', 'billing'],
    })).toEqual(['support', 'billing', 'default'])
    expect(getDecisionOutputHandles({
      questionType: 'noul',
      defaultHandle: 'fallback',
    })).toEqual(['yes', 'no', 'fallback'])
  })

  test('migrates legacy yes-no edges to two configured option labels', () => {
    const nodes = [{
      id: 'decision',
      type: 'decision',
      data: {
        decisionConfig: {
          questionType: 'choice',
          options: ['support', 'billing'],
        },
      },
    }]
    const edges = [
      { id: 'support-edge', source: 'decision', target: 'support', sourceHandle: 'yes' },
      { id: 'billing-edge', source: 'decision', target: 'billing', sourceHandle: 'no' },
      { id: 'other-edge', source: 'other', target: 'untouched', sourceHandle: 'yes' },
    ]

    expect(migrateLegacyDecisionBranchEdges(nodes, edges)).toEqual([
      { ...edges[0], sourceHandle: 'support' },
      { ...edges[1], sourceHandle: 'billing' },
      edges[2],
    ])
  })

  test('keeps connected edges attached when option labels are edited', () => {
    const edges = [
      { id: 'support-edge', source: 'decision', target: 'support', sourceHandle: 'yes' },
      { id: 'billing-edge', source: 'decision', target: 'billing', sourceHandle: 'no' },
      { id: 'other-edge', source: 'other', target: 'untouched', sourceHandle: 'yes' },
    ]

    expect(remapDecisionBranchEdges(
      edges,
      'decision',
      { questionType: 'choice', options: ['yes', 'no'] },
      { questionType: 'choice', options: ['support', 'billing'] }
    )).toEqual([
      { ...edges[0], sourceHandle: 'support' },
      { ...edges[1], sourceHandle: 'billing' },
      edges[2],
    ])
  })

  test('preserves a branch label through reordering and does not guess removed options', () => {
    const edges = [
      { id: 'support-edge', source: 'decision', target: 'support', sourceHandle: 'support' },
      { id: 'billing-edge', source: 'decision', target: 'billing', sourceHandle: 'billing' },
    ]
    const reordered = remapDecisionBranchEdges(
      edges,
      'decision',
      { questionType: 'choice', options: ['support', 'billing'] },
      { questionType: 'choice', options: ['billing', 'support'] }
    )
    expect(reordered.map((edge) => edge.sourceHandle)).toEqual(['support', 'billing'])

    const reduced = remapDecisionBranchEdges(
      edges,
      'decision',
      { questionType: 'choice', options: ['support', 'billing'] },
      { questionType: 'choice', options: ['billing'] }
    )
    expect(reduced).toBe(edges)
    expect(reduced[0].sourceHandle).toBe('support')
  })

  test('renames a connected fallback handle', () => {
    const edges = [
      { id: 'fallback-edge', source: 'decision', target: 'fallback', sourceHandle: 'default' },
    ]

    expect(remapDecisionBranchEdges(
      edges,
      'decision',
      { questionType: 'noul', defaultHandle: 'default' },
      { questionType: 'noul', defaultHandle: 'uncertain' }
    )).toEqual([{ ...edges[0], sourceHandle: 'uncertain' }])
  })
})
