import type { NotificationItem, NotificationLevel } from '@/lib/api'

export type NotificationDisplayKind = 'announcement' | 'security' | 'action' | 'delivery' | 'general'

export interface NotificationDisplayMeta {
  kind: NotificationDisplayKind
  priorityScore: number
  isAnnouncement: boolean
  isProminent: boolean
}

const LEVEL_PRIORITY: Record<NotificationLevel, number> = {
  low: 1,
  medium: 2,
  high: 3,
}

const ACTION_TYPES = new Set([
  'team_invite',
  'user_pending_approval',
  'password_force_change',
  'user_mention',
  'user_assigned',
])

const DELIVERY_PREFIXES = ['kb_doc_', 'workflow_run_', 'agent_', 'apikey_', 'model_', 'quota_']
const SECURITY_PREFIXES = ['security_', 'password_']

export function normalizeNotificationType(type: string) {
  return type.replaceAll('.', '_')
}

export function getNotificationDisplayMeta(notification: Pick<NotificationItem, 'type' | 'source' | 'scope' | 'level'>): NotificationDisplayMeta {
  const normalizedType = normalizeNotificationType(notification.type)
  const isAnnouncement = normalizedType === 'system_announcement'
    || (notification.source === 'system' && normalizedType.endsWith('_announcement'))

  const kind = getNotificationDisplayKind(normalizedType, isAnnouncement)
  const priorityScore = LEVEL_PRIORITY[notification.level] + (isAnnouncement ? 2 : 0) + (kind === 'security' ? 1 : 0)

  return {
    kind,
    priorityScore,
    isAnnouncement,
    isProminent: isAnnouncement || notification.level === 'high' || kind === 'security',
  }
}

function getNotificationDisplayKind(type: string, isAnnouncement: boolean): NotificationDisplayKind {
  if (isAnnouncement) {
    return 'announcement'
  }

  if (ACTION_TYPES.has(type)) {
    return 'action'
  }

  if (SECURITY_PREFIXES.some((prefix) => type.startsWith(prefix))) {
    return 'security'
  }

  if (DELIVERY_PREFIXES.some((prefix) => type.startsWith(prefix))) {
    return 'delivery'
  }

  return 'general'
}
