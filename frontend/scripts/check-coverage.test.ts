import { describe, expect, test } from 'bun:test'

import { eligibleSource, missingCoverageSources } from './check-coverage'

describe('coverage source census', () => {
  test('includes application sources and excludes tests and declarations', () => {
    expect(eligibleSource('lib/api/client.ts')).toBe(true)
    expect(eligibleSource('components/chat/message.tsx')).toBe(true)
    expect(eligibleSource('lib/api/client.test.ts')).toBe(false)
    expect(eligibleSource('i18n/types/generated.ts')).toBe(false)
    expect(eligibleSource('lib/global.d.ts')).toBe(false)
    expect(eligibleSource('components/onboarding/steps/types.ts')).toBe(false)
  })

  test('returns eligible tracked files absent from LCOV', () => {
    const tracked = ['lib/a.ts', 'components/b.tsx', 'lib/a.test.ts', 'scripts/build.ts']
    const lcov = 'TN:\nSF:./lib/a.ts\nDA:1,1\nend_of_record\n'

    expect(missingCoverageSources(tracked, lcov)).toEqual(['components/b.tsx'])
  })
})
