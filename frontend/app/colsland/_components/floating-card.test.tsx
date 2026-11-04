import { afterAll, beforeAll, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { NextIntlClientProvider } from 'next-intl'
import platformMessages from '@/i18n/en/platform.json'
import { ProjectCardStack } from './project-card-stack'

beforeAll(() => { if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' }) })
afterAll(async () => { if (GlobalRegistrator.isRegistered) await GlobalRegistrator.unregister() })

test('cards share height, resize together, and restore the split after collapse', async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    await act(async () => root.render(<NextIntlClientProvider locale="en" timeZone="UTC" messages={platformMessages}><ProjectCardStack /></NextIntlClientProvider>))
    const stack = host.querySelector<HTMLElement>('[aria-label="Project panels"]')!
    stack.getBoundingClientRect = () => ({ top: 0, height: 600 } as DOMRect)
    const toggle = host.querySelector<HTMLButtonElement>('button[aria-expanded]')!
    const separator = host.querySelector<HTMLElement>('[role="separator"]')!
    await act(async () => separator.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })))
    const first = stack.firstElementChild as HTMLElement
    const resized = first.style.flex
    expect(resized).not.toBe('50 1 0%')
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(host.querySelector('[role="separator"]')).toBeNull()
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(first.style.flex).toBe(resized)
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
