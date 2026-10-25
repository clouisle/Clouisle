import { describe, expect, test } from 'bun:test'

import { AutoNotificationsSettingsTab } from './index'
import { AutoNotificationsSettingsTab as Direct } from './auto-notifications-settings'

describe('notification settings barrel', () => {
  test('re-exports the implemented tab', () => {
    expect(AutoNotificationsSettingsTab).toBe(Direct)
  })
})
