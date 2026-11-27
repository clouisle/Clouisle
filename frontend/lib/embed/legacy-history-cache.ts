/**
 * Leftovers of the browser-side embed history cache.
 *
 * Embed chat conversations and workflow runs used to be persisted in
 * `localStorage` under keys namespaced only by the resource id
 * (`clouisle:embed:history:agent:*` and `clouisle:embed:runs:workflow:*`), so a
 * second credential on the same origin could read the first one's messages,
 * inputs and outputs. History now comes from the key-scoped server endpoints
 * and nothing is written here any more.
 *
 * The stale entries are deleted rather than re-keyed by credential: every
 * script on the origin can read all of `localStorage`, so salting the key with
 * the API key (or a hash of it) would hide the leak without preventing it.
 * Deleting is what actually retires the content, and both prefixes are scrubbed
 * wholesale so entries of other agents and workflows on the same origin go too.
 */

/** Prefix of the removed embed Agent conversation cache. */
export const LEGACY_EMBED_CHAT_HISTORY_PREFIX = 'clouisle:embed:history:agent:'

/** Prefix of the removed embed workflow run cache. */
export const LEGACY_EMBED_WORKFLOW_RUNS_PREFIX = 'clouisle:embed:runs:workflow:'

const LEGACY_PREFIXES = [
  LEGACY_EMBED_CHAT_HISTORY_PREFIX,
  LEGACY_EMBED_WORKFLOW_RUNS_PREFIX,
] as const

/**
 * Remove every `localStorage` entry left by the retired embed history cache.
 *
 * Both adapters call this, so opening either embed page retires all stale
 * content on the origin instead of leaving the other cache behind.
 *
 * Best effort: storage can be disabled or full, and a restricted storage
 * shim may not implement key enumeration. Leaving an entry behind is
 * harmless - no code reads these keys any more - so every failure is swallowed
 * instead of breaking the embed page.
 */
export function purgeLegacyEmbedHistory(): void {
  try {
    const storage = globalThis.localStorage as Storage | undefined
    if (!storage || typeof storage.key !== 'function') return

    const stale: string[] = []
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (key && LEGACY_PREFIXES.some((prefix) => key.startsWith(prefix))) {
        stale.push(key)
      }
    }
    for (const key of stale) storage.removeItem(key)
  } catch {
    // Storage unavailable: the stale entries cannot be read either way.
  }
}
