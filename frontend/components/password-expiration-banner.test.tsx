import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import { usersApi } from '@/lib/api'
import { PasswordExpirationBanner } from './password-expiration-banner'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { days?: number }) => values?.days == null ? key : `${key}:${values.days}`,
}))

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<PasswordExpirationBanner />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

describe('PasswordExpirationBanner', () => {
  test('shows an expiration warning and allows dismissing it', async () => {
    spyOn(usersApi, 'getPasswordStatus').mockResolvedValue({
      is_expired: false,
      days_until_expiration: 3,
      should_warn: true,
      can_change: true,
      is_exempt: false,
    })

    const renderer = await render()

    expect(JSON.stringify(renderer.toJSON())).toContain('passwordExpiringSoon:3')
    expect(renderer.root.findByType('a').props.href).toBe('/profile')
    act(() => renderer.root.findAllByType('button')[1].props.onClick())
    expect(renderer.toJSON()).toBeNull()
  })

  test('stays hidden for exempt users and request failures', async () => {
    const request = spyOn(usersApi, 'getPasswordStatus')
      .mockResolvedValueOnce({
        is_expired: false,
        days_until_expiration: 3,
        should_warn: false,
        can_change: true,
        is_exempt: true,
      })
      .mockRejectedValueOnce(new Error('unavailable'))

    expect((await render()).toJSON()).toBeNull()
    expect((await render()).toJSON()).toBeNull()
    expect(request).toHaveBeenCalledTimes(2)
  })
})
