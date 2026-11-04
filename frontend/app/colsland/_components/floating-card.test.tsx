import { afterAll, beforeAll, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { NextIntlClientProvider } from 'next-intl'
import platformMessages from '@/i18n/en/platform.json'
import { ProjectSelector } from './project-selector'

beforeAll(() => { if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' }) })
afterAll(async () => { if (GlobalRegistrator.isRegistered) await GlobalRegistrator.unregister() })

test('project card collapses and expands without losing resized dimensions', async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<NextIntlClientProvider locale="en" timeZone="UTC" messages={platformMessages}><ProjectSelector /></NextIntlClientProvider>))
    const toggle = host.querySelector<HTMLButtonElement>('button[aria-expanded]')!
    const resize = host.querySelector<HTMLButtonElement>('[aria-label="Resize Projects card"]')!
    await act(async () => resize.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })))
    expect(host.firstElementChild?.getAttribute('style')).toContain('272px')
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(host.querySelector('[aria-label="Resize Projects card"]')).toBeNull()
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(host.textContent).toContain('No projects available')
    expect(host.firstElementChild?.getAttribute('style')).toContain('272px')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
