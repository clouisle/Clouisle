import { afterEach, describe, expect, it, spyOn } from 'bun:test'

import { api } from './client'
import { siteSettingsApi } from './site-settings'

let getSpy: ReturnType<typeof spyOn> | undefined

afterEach(() => {
  getSpy?.mockRestore()
})

describe('siteSettingsApi', () => {
  it('gets public settings from the public route', async () => {
    const settings = { site_name: 'Clouisle', allow_registration: true }
    getSpy = spyOn(api, 'get').mockResolvedValue(settings)

    await expect(siteSettingsApi.getPublic()).resolves.toBe(settings)
    expect(getSpy).toHaveBeenCalledTimes(1)
    expect(getSpy).toHaveBeenCalledWith('/site-settings/public')
  })

  it('propagates public settings request errors', async () => {
    const error = new Error('settings unavailable')
    getSpy = spyOn(api, 'get').mockRejectedValue(error)

    await expect(siteSettingsApi.getPublic()).rejects.toBe(error)
  })
})
