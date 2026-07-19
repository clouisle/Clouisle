import { describe, expect, test } from 'bun:test'

import { getNodeTypeColor, getNodeTypeLabelKey } from './workflow-validator'

describe('workflow validator display helpers', () => {
  test('maps a known workflow node type to its label and color', () => {
    expect(getNodeTypeLabelKey('media_generation')).toBe('nodeLabels.media_generation')
    expect(getNodeTypeColor('media_generation')).toBe('bg-fuchsia-500')
  })

  test('uses safe fallbacks for an unknown workflow node type', () => {
    expect(getNodeTypeLabelKey('custom_node')).toBe('custom_node')
    expect(getNodeTypeColor('custom_node')).toBe('bg-gray-500')
  })
})
