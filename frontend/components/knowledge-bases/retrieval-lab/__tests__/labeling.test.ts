import { describe, expect, it } from 'bun:test'
import {
  clearDrafts,
  computeDocumentRelevance,
  computeQueryKey,
  getDraft,
  gradesToRelevance,
  migrateStorage,
  normalizeQuery,
  setDraft,
  setGrade,
  type StorageEnvelope,
} from '../labeling'

describe('normalizeQuery', () => {
  it('trims leading and trailing whitespace', () => {
    expect(normalizeQuery('  hello  ')).toBe('hello')
    expect(normalizeQuery('\n\tquery\t\n')).toBe('query')
  })

  it('collapses consecutive whitespace to single space', () => {
    expect(normalizeQuery('hello    world')).toBe('hello world')
    expect(normalizeQuery('a  \n  b')).toBe('a b')
  })

  it('normalizes Unicode to NFKC', () => {
    expect(normalizeQuery('café')).toBe('café') // Already NFKC
    expect(normalizeQuery('ﬁ')).toBe('fi') // Ligature fi -> NFKC
  })

  it('handles fullwidth spaces', () => {
    expect(normalizeQuery('hello　world')).toBe('hello world') // U+3000 -> U+0020
  })

  it('preserves case and punctuation', () => {
    expect(normalizeQuery('Hello, World!')).toBe('Hello, World!')
  })
})

describe('computeQueryKey', () => {
  it('returns normalized query', () => {
    expect(computeQueryKey('  test query  ')).toBe('test query')
  })

  it('produces same key for equivalent queries', () => {
    const key1 = computeQueryKey('test   query')
    const key2 = computeQueryKey('  test query  ')
    expect(key1).toBe(key2)
  })

  it('produces different keys for different queries', () => {
    const key1 = computeQueryKey('query A')
    const key2 = computeQueryKey('query B')
    expect(key1).not.toBe(key2)
  })
})

describe('migrateStorage', () => {
  it('returns null for invalid input', () => {
    expect(migrateStorage(null)).toBeNull()
    expect(migrateStorage(undefined)).toBeNull()
    expect(migrateStorage('string')).toBeNull()
    expect(migrateStorage(123)).toBeNull()
  })

  it('preserves v2 envelope unchanged', () => {
    const v2: StorageEnvelope = {
      version: 2,
      presets: [{ name: 'test', config: {} }],
      drafts: {
        'query a': { query: 'query a', grades: { 'chunk-1': 'relevant' } },
      },
    }
    const result = migrateStorage(v2)
    expect(result).toEqual(v2)
  })

  it('migrates v1 legacy format', () => {
    const v1 = {
      presets: [{ name: 'preset1', config: { top_k: 5 } }],
      grades: { 'chunk-1': 'relevant', 'chunk-2': 'irrelevant' },
    }
    const result = migrateStorage(v1)
    expect(result).toEqual({
      version: 2,
      presets: [{ name: 'preset1', config: { top_k: 5 } }],
      drafts: {}, // Legacy grades discarded
    })
  })

  it('handles missing presets in legacy format', () => {
    const v1 = { grades: { 'chunk-1': 'relevant' } }
    const result = migrateStorage(v1)
    expect(result).toEqual({
      version: 2,
      presets: [],
      drafts: {},
    })
  })

  it('handles empty object', () => {
    const result = migrateStorage({})
    expect(result).toEqual({
      version: 2,
      presets: [],
      drafts: {},
    })
  })
})

describe('getDraft', () => {
  it('returns empty draft for new query', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }
    const draft = getDraft(envelope, 'new query')
    expect(draft).toEqual({ query: 'new query', grades: {} })
  })

  it('returns existing draft for known query', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'test query': { query: 'test query', grades: { 'chunk-1': 'relevant' } },
      },
    }
    const draft = getDraft(envelope, 'test query')
    expect(draft).toEqual({ query: 'test query', grades: { 'chunk-1': 'relevant' } })
  })

  it('normalizes query key for lookup', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'test query': { query: 'test query', grades: { 'chunk-1': 'partial' } },
      },
    }
    const draft = getDraft(envelope, '  test   query  ')
    expect(draft.grades).toEqual({ 'chunk-1': 'partial' })
  })
})

describe('setDraft', () => {
  it('adds new draft for query', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }
    const updated = setDraft(envelope, 'query A', { 'chunk-1': 'relevant' })
    expect(updated.drafts['query A']).toEqual({
      query: 'query A',
      grades: { 'chunk-1': 'relevant' },
    })
  })

  it('updates existing draft', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant' } },
      },
    }
    const updated = setDraft(envelope, 'query A', { 'chunk-2': 'irrelevant' })
    expect(updated.drafts['query A'].grades).toEqual({ 'chunk-2': 'irrelevant' })
  })

  it('does not mutate original envelope', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }
    const updated = setDraft(envelope, 'query A', { 'chunk-1': 'partial' })
    expect(envelope.drafts).toEqual({})
    expect(updated.drafts['query A']).toBeDefined()
  })

  it('normalizes query key', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }
    const updated = setDraft(envelope, '  query A  ', { 'chunk-1': 'relevant' })
    expect(updated.drafts['query A']).toBeDefined()
  })
})

describe('setGrade', () => {
  it('adds grade to empty draft', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }
    const updated = setGrade(envelope, 'query A', 'chunk-1', 'relevant')
    expect(updated.drafts['query A'].grades).toEqual({ 'chunk-1': 'relevant' })
  })

  it('updates existing grade', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant' } },
      },
    }
    const updated = setGrade(envelope, 'query A', 'chunk-1', 'irrelevant')
    expect(updated.drafts['query A'].grades['chunk-1']).toBe('irrelevant')
  })

  it('removes grade when null', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant', 'chunk-2': 'partial' } },
      },
    }
    const updated = setGrade(envelope, 'query A', 'chunk-1', null)
    expect(updated.drafts['query A'].grades).toEqual({ 'chunk-2': 'partial' })
  })

  it('isolates grades by query', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant' } },
        'query B': { query: 'query B', grades: { 'chunk-1': 'irrelevant' } },
      },
    }
    const updated = setGrade(envelope, 'query A', 'chunk-1', 'partial')
    expect(updated.drafts['query A'].grades['chunk-1']).toBe('partial')
    expect(updated.drafts['query B'].grades['chunk-1']).toBe('irrelevant')
  })

  it('does not mutate original envelope', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant' } },
      },
    }
    const updated = setGrade(envelope, 'query A', 'chunk-2', 'partial')
    expect(envelope.drafts['query A'].grades).toEqual({ 'chunk-1': 'relevant' })
    expect(updated.drafts['query A'].grades).toEqual({ 'chunk-1': 'relevant', 'chunk-2': 'partial' })
  })
})

describe('clearDrafts', () => {
  it('removes all drafts', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [{ name: 'test', config: {} }],
      drafts: {
        'query A': { query: 'query A', grades: { 'chunk-1': 'relevant' } },
        'query B': { query: 'query B', grades: { 'chunk-2': 'partial' } },
      },
    }
    const updated = clearDrafts(envelope)
    expect(updated.drafts).toEqual({})
    expect(updated.presets).toEqual([{ name: 'test', config: {} }])
  })

  it('does not mutate original envelope', () => {
    const envelope: StorageEnvelope = {
      version: 2,
      presets: [],
      drafts: { 'query A': { query: 'query A', grades: {} } },
    }
    const updated = clearDrafts(envelope)
    expect(envelope.drafts['query A']).toBeDefined()
    expect(updated.drafts).toEqual({})
  })
})

describe('query isolation', () => {
  it('prevents cross-query label pollution', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }

    // Label chunk-1 as relevant in query A
    const step1 = setGrade(envelope, 'query A', 'chunk-1', 'relevant')
    expect(step1.drafts['query A'].grades['chunk-1']).toBe('relevant')

    // Label chunk-1 as irrelevant in query B
    const step2 = setGrade(step1, 'query B', 'chunk-1', 'irrelevant')
    expect(step2.drafts['query A'].grades['chunk-1']).toBe('relevant')
    expect(step2.drafts['query B'].grades['chunk-1']).toBe('irrelevant')

    // Return to query A - label unchanged
    const draftA = getDraft(step2, 'query A')
    expect(draftA.grades['chunk-1']).toBe('relevant')
  })

  it('shares labels for same normalized query', () => {
    const envelope: StorageEnvelope = { version: 2, presets: [], drafts: {} }

    const step1 = setGrade(envelope, 'test query', 'chunk-1', 'relevant')
    const step2 = setGrade(step1, '  test   query  ', 'chunk-2', 'partial')

    // Both grades stored under same normalized key
    const draft = getDraft(step2, 'test query')
    expect(draft.grades).toEqual({
      'chunk-1': 'relevant',
      'chunk-2': 'partial',
    })
  })
})

describe('gradesToRelevance', () => {
  it('converts grades to numeric scores', () => {
    const grades = {
      'chunk-1': 'relevant' as const,
      'chunk-2': 'partial' as const,
      'chunk-3': 'irrelevant' as const,
    }
    const relevance = gradesToRelevance(grades)
    expect(relevance).toEqual({
      'chunk-1': 3,
      'chunk-2': 2,
      'chunk-3': 0,
    })
  })

  it('handles empty grades', () => {
    const relevance = gradesToRelevance({})
    expect(relevance).toEqual({})
  })
})

describe('computeDocumentRelevance', () => {
  it('computes max chunk relevance per document', () => {
    const chunkRelevance = {
      'chunk-1': 3,
      'chunk-2': 2,
      'chunk-3': 3,
      'chunk-4': 0,
    }
    const chunkToDocument = new Map([
      ['chunk-1', 'doc-1'],
      ['chunk-2', 'doc-1'],
      ['chunk-3', 'doc-2'],
      ['chunk-4', 'doc-2'],
    ])

    const docRelevance = computeDocumentRelevance(chunkRelevance, chunkToDocument)
    expect(docRelevance).toEqual({
      'doc-1': 3, // max(3, 2)
      'doc-2': 3, // max(3, 0)
    })
  })

  it('handles chunks with no document mapping', () => {
    const chunkRelevance = {
      'chunk-1': 3,
      'chunk-2': 2,
    }
    const chunkToDocument = new Map([
      ['chunk-1', 'doc-1'],
      // chunk-2 missing
    ])

    const docRelevance = computeDocumentRelevance(chunkRelevance, chunkToDocument)
    expect(docRelevance).toEqual({
      'doc-1': 3,
      // doc-2 not present
    })
  })

  it('handles empty inputs', () => {
    const docRelevance = computeDocumentRelevance({}, new Map())
    expect(docRelevance).toEqual({})
  })
})
