import { afterAll, beforeAll, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { NextIntlClientProvider } from 'next-intl'
import platformMessages from '@/i18n/en/platform.json'
import { RichEditor } from './rich-editor'

beforeAll(() => { if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' }) })
afterAll(async () => { if (GlobalRegistrator.isRegistered) await GlobalRegistrator.unregister() })

test('marks only the active block and clears the mark on blur', async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<NextIntlClientProvider locale="en" timeZone="UTC" messages={platformMessages}><RichEditor /></NextIntlClientProvider>))
    const editable = host.querySelector<HTMLElement>('.bn-editor')!
    await act(async () => editable.focus())
    const first = host.querySelector('[data-colsland-focused-block]')
    expect(first?.querySelector(':scope > .bn-block-content')).not.toBeNull()
    const id = first?.getAttribute('data-id')
    await act(async () => editable.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true })))
    expect(host.querySelectorAll('[data-colsland-focused-block]')).toHaveLength(1)
    expect(host.querySelector('[data-colsland-focused-block]')?.getAttribute('data-id')).not.toBe(id)
    await act(async () => editable.blur())
    expect(host.querySelector('[data-colsland-focused-block]')).toBeNull()
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
