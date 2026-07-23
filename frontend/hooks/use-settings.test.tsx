import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { SettingsProvider, useSettings } from './use-settings'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
const documentDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'document')
const renders: ReturnType<typeof useSettings>[] = []
let renderer: ReactTestRenderer | undefined

function Consumer() {
  renders.push(useSettings())
  return null
}

function installEnvironment(stored?: string) {
  const values = new Map<string, string>()
  if (stored !== undefined) values.set('clouisle-settings', stored)
  const writes: string[] = []

  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value)
        writes.push(value)
      },
    },
  })
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { documentElement: { dir: '' } },
  })

  return writes
}

async function renderProvider() {
  await act(async () => {
    renderer = create(<SettingsProvider><Consumer /></SettingsProvider>)
  })
  return renders.at(-1)!
}

function restoreDescriptor(key: 'localStorage' | 'document', descriptor?: PropertyDescriptor) {
  if (descriptor) Object.defineProperty(globalThis, key, descriptor)
  else delete (globalThis as Record<string, unknown>)[key]
}

afterEach(() => {
  if (renderer) act(() => renderer?.unmount())
  renderer = undefined
  renders.length = 0
  mock.restore()
  restoreDescriptor('localStorage', storageDescriptor)
  restoreDescriptor('document', documentDescriptor)
})

describe('SettingsProvider', () => {
  test('uses defaults when no settings are stored', async () => {
    const writes = installEnvironment()

    expect(await renderProvider()).toMatchObject({
      sidebarVariant: 'inset',
      layoutVariant: 'default',
      direction: 'ltr',
      platformHeaderVariant: 'centered',
    })
    expect(JSON.parse(writes.at(-1)!)).toEqual({
      sidebarVariant: 'inset',
      layoutVariant: 'default',
      direction: 'ltr',
      platformHeaderVariant: 'centered',
    })
  })

  test('merges stored settings with defaults', async () => {
    installEnvironment(JSON.stringify({ layoutVariant: 'compact', direction: 'rtl' }))

    expect(await renderProvider()).toMatchObject({
      sidebarVariant: 'inset',
      layoutVariant: 'compact',
      direction: 'rtl',
      platformHeaderVariant: 'centered',
    })
    expect(document.documentElement.dir).toBe('rtl')
  })

  test('keeps defaults when stored settings are malformed', async () => {
    installEnvironment('{bad json')
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})

    expect(await renderProvider()).toMatchObject({
      sidebarVariant: 'inset',
      layoutVariant: 'default',
      direction: 'ltr',
      platformHeaderVariant: 'centered',
    })
    expect(consoleError).toHaveBeenCalledWith('Failed to parse settings', expect.any(SyntaxError))
    consoleError.mockRestore()
  })

  test('persists setters and resetSettings', async () => {
    const writes = installEnvironment()
    await renderProvider()

    act(() => {
      const settings = renders.at(-1)!
      settings.setSidebarVariant('floating')
      settings.setLayoutVariant('full')
      settings.setDirection('rtl')
      settings.setPlatformHeaderVariant('minimal')
    })
    expect(JSON.parse(writes.at(-1)!)).toEqual({
      sidebarVariant: 'floating',
      layoutVariant: 'full',
      direction: 'rtl',
      platformHeaderVariant: 'minimal',
    })

    act(() => renders.at(-1)!.resetSettings())
    expect(JSON.parse(writes.at(-1)!)).toEqual({
      sidebarVariant: 'inset',
      layoutVariant: 'default',
      direction: 'ltr',
      platformHeaderVariant: 'centered',
    })
  })

  test('reports mounting and applies direction changes', async () => {
    installEnvironment()

    const settings = await renderProvider()
    expect(renders[0].mounted).toBe(false)
    expect(settings.mounted).toBe(true)
    expect(document.documentElement.dir).toBe('ltr')

    act(() => settings.setDirection('rtl'))
    expect(document.documentElement.dir).toBe('rtl')
  })
})
