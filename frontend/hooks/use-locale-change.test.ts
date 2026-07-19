import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import * as navigation from 'next/navigation'
import { usersApi } from '@/lib/api'
import { useLocaleChange } from './use-locale-change'

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
const restorers: Array<{ mockRestore(): void }> = []

function restoreDescriptor(name: 'window' | 'document' | 'localStorage', descriptor: PropertyDescriptor | undefined) {
  if (descriptor) Object.defineProperty(globalThis, name, descriptor)
  else delete (globalThis as Record<string, unknown>)[name]
}

function installBrowser(token: string | null) {
  const localStorage = { getItem: () => token }
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { localStorage },
  })
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: localStorage })
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { cookie: '' },
  })
}

afterEach(() => {
  restorers.splice(0).reverse().forEach((mock) => mock.mockRestore())
  restoreDescriptor('window', originalWindow)
  restoreDescriptor('document', originalDocument)
  restoreDescriptor('localStorage', originalLocalStorage)
})

describe('useLocaleChange', () => {
  it('persists and refreshes a guest locale without syncing a profile', () => {
    installBrowser(null)
    const refresh = spyOn({ refresh() {} }, 'refresh')
    restorers.push(spyOn(navigation, 'useRouter').mockReturnValue({ refresh } as never))
    const updateProfile = spyOn(usersApi, 'updateProfile')
    restorers.push(updateProfile)

    useLocaleChange().changeLocale('zh')

    expect(document.cookie).toBe('locale=zh;path=/;max-age=31536000')
    expect(updateProfile).not.toHaveBeenCalled()
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('syncs an authenticated locale without waiting before refreshing', () => {
    installBrowser('token')
    const refresh = spyOn({ refresh() {} }, 'refresh')
    restorers.push(spyOn(navigation, 'useRouter').mockReturnValue({ refresh } as never))
    const pending = new Promise<void>(() => {})
    const updateProfile = spyOn(usersApi, 'updateProfile').mockReturnValue(pending)
    restorers.push(updateProfile)

    useLocaleChange().changeLocale('en')

    expect(updateProfile).toHaveBeenCalledWith({ locale: 'en' }, { skipAuthRedirect: true })
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('reports a failed profile sync', async () => {
    installBrowser('token')
    const refresh = spyOn({ refresh() {} }, 'refresh')
    restorers.push(spyOn(navigation, 'useRouter').mockReturnValue({ refresh } as never))
    const failure = new Error('offline')
    const updateProfile = spyOn(usersApi, 'updateProfile').mockRejectedValue(failure)
    restorers.push(updateProfile)
    const error = spyOn(console, 'error').mockImplementation(() => {})
    restorers.push(error)

    useLocaleChange().changeLocale('zh')
    await Promise.resolve()

    expect(error).toHaveBeenCalledWith('Failed to update locale:', failure)
  })
})
