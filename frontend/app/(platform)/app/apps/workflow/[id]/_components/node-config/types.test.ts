import { expect, test } from 'bun:test'

import { extractVariableDisplayName } from './types'

test('extracts display names from plain and templated variable references', () => {
  expect(extractVariableDisplayName('nodeId.paramName')).toBe('paramName')
  expect(extractVariableDisplayName('{{nodeId.paramName}}')).toBe('paramName')
  expect(extractVariableDisplayName('')).toBe('')
  expect(extractVariableDisplayName('{{value}}')).toBe('value')
})
