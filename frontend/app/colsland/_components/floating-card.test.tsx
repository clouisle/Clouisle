import { afterAll, beforeAll, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { NextIntlClientProvider } from 'next-intl'
import platformMessages from '@/i18n/en/platform.json'
import { ProjectCardStack } from './project-card-stack'

beforeAll(() => { if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' }) })
afterAll(async () => { if (GlobalRegistrator.isRegistered) await GlobalRegistrator.unregister() })

test('cards resize independently within the available height and restore after collapse', async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  try {
    const originalHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientHeight')!
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => 600 })
    try {
      await act(async () => root.render(<NextIntlClientProvider locale="en" timeZone="UTC" messages={platformMessages}><ProjectCardStack /></NextIntlClientProvider>))
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', originalHeight)
    }
    const stack = host.querySelector<HTMLElement>('[aria-label="Project panels"]')!
    const toggle = host.querySelector<HTMLButtonElement>('button[aria-expanded]')!
    const resize = host.querySelectorAll<HTMLButtonElement>('[aria-label="Resize project panels"]')[0]
    const first = stack.firstElementChild as HTMLElement
    const second = stack.lastElementChild as HTMLElement
    await act(async () => resize.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })))
    expect(first.style.height).toBe('136px')
    expect(second.style.height).toBe('120px')
    await act(async () => toggle.click())
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(second.style.height).toBe('120px')
    await act(async () => toggle.click())
    expect(first.style.height).toBe('136px')
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
