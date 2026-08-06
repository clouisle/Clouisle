import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const push = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('next/navigation', () => ({
  usePathname: () => '/app',
  useRouter: () => ({ push }),
}))

mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
}))

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

import { notificationsApi, type NotificationItem } from '@/lib/api'
import { ProminentNotificationDialog } from './prominent-notification-dialog'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const notification = (id: string, title: string, linkUrl?: string): NotificationItem => ({
  id,
  scope: 'global',
  type: 'announcement',
  source: 'system',
  title,
  content: `${title} content`,
  level: 'high',
  link_url: linkUrl,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_read: false,
})

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  push.mockClear()
})

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<ProminentNotificationDialog />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

describe('ProminentNotificationDialog', () => {
  test('shows announcement content and marks the selected notification read before selecting the next one', async () => {
    spyOn(notificationsApi, 'list').mockResolvedValue({
      items: [notification('one', 'First'), notification('two', 'Second')], total: 2, page: 1, page_size: 50,
    })
    const markRead = spyOn(notificationsApi, 'markRead').mockResolvedValue({ updated: 1 })
    const renderer = await render()

    expect(renderer.root.findByProps({ role: 'dialog' })).toBeTruthy()
    expect(JSON.stringify(renderer.toJSON())).toContain('First content')
    expect(JSON.stringify(renderer.toJSON())).toContain('kindOptions.general')

    await act(async () => renderer.root.findAllByType('button')[0].props.onClick())

    expect(markRead).toHaveBeenCalledWith({ notification_ids: ['one'] })
    expect(JSON.stringify(renderer.toJSON())).toContain('Second content')
  })

  test('routes to a notification link when the user views it', async () => {
    spyOn(notificationsApi, 'list').mockResolvedValue({
      items: [notification('one', 'First', '/app/workflows')], total: 1, page: 1, page_size: 50,
    })

    const renderer = await render()
    act(() => renderer.root.findAllByType('button')[1].props.onClick())

    expect(push).toHaveBeenCalledWith('/app/workflows')
    expect(renderer.toJSON()).toBeNull()
  })

  test('keeps a notification visible when marking it read fails', async () => {
    spyOn(notificationsApi, 'list').mockResolvedValue({
      items: [notification('one', 'First')], total: 1, page: 1, page_size: 50,
    })
    spyOn(notificationsApi, 'markRead').mockRejectedValue(new Error('unavailable'))
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})
    const renderer = await render()

    await act(async () => renderer.root.findAllByType('button')[0].props.onClick())

    expect(consoleError).toHaveBeenCalledWith('Failed to mark notification read:', expect.any(Error))
    expect(JSON.stringify(renderer.toJSON())).toContain('First content')
  })

  test('renders nothing when no prominent notification is available or loading fails', async () => {
    const list = spyOn(notificationsApi, 'list')
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 50 })
      .mockRejectedValueOnce(new Error('unavailable'))
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})

    expect((await render()).toJSON()).toBeNull()
    expect((await render()).toJSON()).toBeNull()
    expect(list).toHaveBeenCalledTimes(2)
    expect(consoleError).toHaveBeenCalled()
  })
})
