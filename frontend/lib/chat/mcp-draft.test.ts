import { beforeEach, describe, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })

import {
  MCP_DRAFT_LIMITS,
  consumeMcpDraft,
  mcpDraftKey,
  storeMcpDraft,
} from './mcp-draft'

beforeEach(() => {
  window.localStorage.clear()
  window.sessionStorage.clear()
})

describe('MCP chat draft handoff', () => {
  test('stores one actor/team/agent scoped draft and consumes it once', () => {
    window.localStorage.setItem('access_token', 'token-a')
    expect(storeMcpDraft({ agentId: 'agent-1', teamId: 'team-1', text: 'resource text', source: 'r' }).stored).toBe(true)
    expect(mcpDraftKey('agent-1', 'team-1')).toContain('team-1:agent-1')
    expect(consumeMcpDraft('agent-1', 'team-1')).toBe('resource text')
    expect(consumeMcpDraft('agent-1', 'team-1')).toBeNull()
  })

  test('does not expose drafts to another actor, team, or agent', () => {
    window.localStorage.setItem('access_token', 'token-a')
    expect(storeMcpDraft({ agentId: 'agent-1', teamId: 'team-1', text: 'private', source: 'r' }).stored).toBe(true)

    expect(consumeMcpDraft('agent-2', 'team-1')).toBeNull()
    expect(consumeMcpDraft('agent-1', 'team-2')).toBeNull()

    window.localStorage.setItem('access_token', 'token-b')
    expect(consumeMcpDraft('agent-1', 'team-1')).toBeNull()
  })

  test('expires after ten minutes and rejects oversized content', () => {
    window.localStorage.setItem('access_token', 'token-a')
    storeMcpDraft({ agentId: 'agent-1', teamId: 'team-1', text: 'short', source: 'r' })
    const key = mcpDraftKey('agent-1', 'team-1')!
    const payload = JSON.parse(window.sessionStorage.getItem(key)!)
    payload.expiresAt = Date.now() - 1
    window.sessionStorage.setItem(key, JSON.stringify(payload))
    expect(consumeMcpDraft('agent-1', 'team-1')).toBeNull()
    expect(window.sessionStorage.getItem(key)).toBeNull()

    const oversized = 'x'.repeat(MCP_DRAFT_LIMITS.maxChars + 1)
    expect(storeMcpDraft({ agentId: 'agent-1', teamId: 'team-1', text: oversized, source: 'r' })).toEqual({
      stored: false,
      reason: 'too_large',
    })
    expect(MCP_DRAFT_LIMITS.ttlMs).toBe(600_000)
  })
})
