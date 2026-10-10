import type { ConversationListItem } from '@/lib/api'

export function mergeConversationItems(
  preferred: ConversationListItem[],
  existing: ConversationListItem[] = [],
  total?: number,
): ConversationListItem[] {
  const seen = new Set<string>()
  const merged: ConversationListItem[] = []

  for (const conversation of [...preferred, ...existing]) {
    if (seen.has(conversation.id)) continue
    seen.add(conversation.id)
    merged.push(conversation)
  }

  return typeof total === 'number' && total >= 0 ? merged.slice(0, total) : merged
}
