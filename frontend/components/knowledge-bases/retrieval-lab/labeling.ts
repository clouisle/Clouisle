/**
 * Query-scoped labeling state management for Retrieval Lab.
 *
 * Stage 3: Query isolation prevents cross-query label pollution by storing
 * grades keyed by normalized query fingerprint rather than flat chunk ID.
 */

export type Grade = 'relevant' | 'partial' | 'irrelevant'

export interface LabelingDraft {
  query: string
  grades: Record<string, Grade> // chunk_id -> grade
}

export interface StorageEnvelope {
  version: 2
  presets: Array<{ name: string; config: unknown }>
  drafts: Record<string, LabelingDraft> // queryKey -> draft
}

/**
 * Normalize query for fingerprinting: NFKC + trim + collapse whitespace.
 * Matches backend `normalize_query` in retrieval_evaluation_store.py
 */
export function normalizeQuery(query: string): string {
  const normalized = query.normalize('NFKC').trim()
  return normalized.replace(/\s+/g, ' ')
}

/**
 * Compute query key for draft storage.
 * Uses normalized query as key (not SHA-256) for human readability in localStorage.
 */
export function computeQueryKey(query: string): string {
  return normalizeQuery(query)
}

/**
 * Migrate legacy storage format to versioned envelope.
 * Old format: { presets, grades: Record<chunkId, Grade> }
 * New format: { version: 2, presets, drafts: Record<queryKey, LabelingDraft> }
 */
export function migrateStorage(raw: unknown): StorageEnvelope | null {
  if (!raw || typeof raw !== 'object') return null

  const obj = raw as Record<string, unknown>

  // Already v2
  if (obj.version === 2) {
    return {
      version: 2,
      presets: Array.isArray(obj.presets) ? obj.presets : [],
      drafts: typeof obj.drafts === 'object' && obj.drafts ? obj.drafts as Record<string, LabelingDraft> : {},
    }
  }

  // Legacy v1: discard flat grades (can't determine query), keep presets
  return {
    version: 2,
    presets: Array.isArray(obj.presets) ? obj.presets : [],
    drafts: {},
  }
}

/**
 * Get labeling draft for a specific query.
 */
export function getDraft(envelope: StorageEnvelope, query: string): LabelingDraft {
  const key = computeQueryKey(query)
  return envelope.drafts[key] ?? { query, grades: {} }
}

/**
 * Update labeling draft for a specific query.
 */
export function setDraft(envelope: StorageEnvelope, query: string, grades: Record<string, Grade>): StorageEnvelope {
  const key = computeQueryKey(query)
  return {
    ...envelope,
    drafts: {
      ...envelope.drafts,
      [key]: { query, grades },
    },
  }
}

/**
 * Set grade for a single chunk within a query's draft.
 */
export function setGrade(
  envelope: StorageEnvelope,
  query: string,
  chunkId: string,
  grade: Grade | null
): StorageEnvelope {
  const draft = getDraft(envelope, query)
  const nextGrades = { ...draft.grades }

  if (grade === null) {
    delete nextGrades[chunkId]
  } else {
    nextGrades[chunkId] = grade
  }

  return setDraft(envelope, query, nextGrades)
}

/**
 * Clear all drafts (used when switching knowledge bases).
 */
export function clearDrafts(envelope: StorageEnvelope): StorageEnvelope {
  return {
    ...envelope,
    drafts: {},
  }
}
