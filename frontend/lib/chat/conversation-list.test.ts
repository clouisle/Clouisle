import { describe, expect, test } from 'bun:test'
import type { ConversationListItem } from '@/lib/api'
import { mergeConversationItems } from './conversation-list'

function conversation(id: string, title = id): ConversationListItem {
  return {
    id,
    agent_id: 'agent-1',
    title,
    message_count: 0,
    created_at: '2026-10-08T00:00:00Z',
    updated_at: '2026-10-08T00:00:00Z',
  }
}

describe('mergeConversationItems', () => {
  test('appends only unseen rows from an overlapping page', () => {
    const existing = Array.from({ length: 5 }, (_, index) => conversation(`conv-${index + 1}`))
    const nextPage = [
      conversation('conv-5', 'stale duplicate'),
      ...Array.from({ length: 4 }, (_, index) => conversation(`conv-${index + 6}`)),
    ]

    const merged = mergeConversationItems(existing, nextPage, 9)

    expect(merged.map((item) => item.id)).toEqual(
      Array.from({ length: 9 }, (_, index) => `conv-${index + 1}`),
    )
    expect(merged[4].title).toBe('conv-5')
  })

  test('prefers refreshed first-page rows while retaining older unique rows', () => {
    const existing = Array.from({ length: 10 }, (_, index) => conversation(`conv-${index + 1}`))
    const refreshedPage = [
      conversation('conv-new', 'New chat'),
      conversation('conv-1', 'Updated title'),
      conversation('conv-2'),
      conversation('conv-3'),
      conversation('conv-4'),
    ]

    const merged = mergeConversationItems(refreshedPage, existing, 11)

    expect(merged.map((item) => item.id)).toEqual([
      'conv-new',
      ...Array.from({ length: 10 }, (_, index) => `conv-${index + 1}`),
    ])
    expect(merged[1].title).toBe('Updated title')
  })
})
