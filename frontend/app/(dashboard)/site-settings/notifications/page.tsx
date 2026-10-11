'use client'

import { useCanPerform } from '@/components/permission-guard'
import { AutoNotificationsSettingsTab } from './_components'

export default function SiteSettingsNotificationsPage() {
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')

  return <AutoNotificationsSettingsTab canUpdate={canUpdate} />
}
