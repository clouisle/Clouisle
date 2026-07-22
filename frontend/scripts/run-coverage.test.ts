import { describe, expect, test } from 'bun:test'

import { coverageSummary } from './run-coverage'

describe('coverage summary', () => {
  test('reads Bun function and line totals', () => {
    expect(coverageSummary('All files | 95.03 | 97.95 |\n')).toEqual({
      functions: 95.03,
      lines: 97.95,
    })
  })

  test('rejects output without the aggregate row', () => {
    expect(coverageSummary('no coverage here')).toBeNull()
  })
})
