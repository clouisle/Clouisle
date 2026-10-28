const DRAFT_PREFIX = 'clouisle:mcp-draft'
const DRAFT_TTL_MS = 10 * 60 * 1000
const MAX_DRAFT_CHARS = 20_000

interface McpDraftPayload {
  text: string
  createdAt: number
  expiresAt: number
  source: string
}

function actorFingerprint(): string | null {
  if (typeof window === 'undefined') return null
  const token = window.localStorage.getItem('access_token')
  if (!token) return null
  // Non-reversible stable fingerprint; the token itself is never stored in the draft key.
  let hash = 2166136261
  for (let index = 0; index < token.length; index += 1) {
    hash ^= token.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

export function mcpDraftKey(agentId: string, teamId: string): string | null {
  const actor = actorFingerprint()
  if (!actor || !agentId || !teamId) return null
  return `${DRAFT_PREFIX}:${actor}:${teamId}:${agentId}`
}

export function storeMcpDraft(input: {
  agentId: string
  teamId: string
  text: string
  source: string
}): { stored: boolean; reason?: 'too_large' | 'unavailable' } {
  const key = mcpDraftKey(input.agentId, input.teamId)
  if (!key || typeof window === 'undefined') return { stored: false, reason: 'unavailable' }
  const text = input.text.trim()
  if (!text) return { stored: false, reason: 'unavailable' }
  if (text.length > MAX_DRAFT_CHARS) return { stored: false, reason: 'too_large' }
  const now = Date.now()
  const payload: McpDraftPayload = {
    text,
    createdAt: now,
    expiresAt: now + DRAFT_TTL_MS,
    source: input.source,
  }
  try {
    window.sessionStorage.setItem(key, JSON.stringify(payload))
    return { stored: true }
  } catch {
    return { stored: false, reason: 'unavailable' }
  }
}

export function consumeMcpDraft(agentId: string, teamId: string): string | null {
  const key = mcpDraftKey(agentId, teamId)
  if (!key || typeof window === 'undefined') return null
  const raw = window.sessionStorage.getItem(key)
  if (!raw) return null
  window.sessionStorage.removeItem(key)
  try {
    const payload = JSON.parse(raw) as Partial<McpDraftPayload>
    if (typeof payload.text !== 'string' || typeof payload.expiresAt !== 'number') return null
    if (Date.now() > payload.expiresAt) return null
    if (payload.text.length > MAX_DRAFT_CHARS) return null
    return payload.text
  } catch {
    return null
  }
}

export const MCP_DRAFT_LIMITS = {
  ttlMs: DRAFT_TTL_MS,
  maxChars: MAX_DRAFT_CHARS,
}
