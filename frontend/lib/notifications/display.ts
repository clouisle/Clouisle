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

export function getNotificationDisplayMeta(notification: Pick<NotificationItem, 'type' | 'source' | 'scope' | 'level'>): NotificationDisplayMeta {
  const isAnnouncement = notification.type === 'system_announcement'
    || (notification.source === 'system' && notification.type.endsWith('_announcement'))

  const kind = getNotificationDisplayKind(notification.type, isAnnouncement)
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

  if (SECURITY_PREFIXES.some((prefix) => type.startsWith(prefix))) {
    return 'security'
  }

  if (ACTION_TYPES.has(type)) {
    return 'action'
  }

  if (DELIVERY_PREFIXES.some((prefix) => type.startsWith(prefix))) {
    return 'delivery'
  }

  return 'general'
}
