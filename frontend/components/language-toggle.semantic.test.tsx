import { afterAll, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const changeLocale = mock(() => {})

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key === 'changeLanguage' ? 'Change language' : key,
}))
mock.module('@/hooks/use-locale-change', () => ({
  useLocaleChange: () => ({ changeLocale }),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: 'menu',
  DropdownMenuTrigger: 'trigger',
  DropdownMenuContent: 'content',
  DropdownMenuItem: 'item',
}))

const { LanguageToggle } = await import('./language-toggle')

afterAll(() => mock.restore())

describe('LanguageToggle', () => {
  test('exposes its action and changes to either visible locale', () => {
    const menu = LanguageToggle() as ReactElement<{ children: ReactNode[] }>
    const [trigger, content] = menu.props.children as ReactElement<{ children: ReactNode }>[]
    const triggerChildren = trigger.props.children as ReactElement<{ children: ReactNode }>[]
    const label = triggerChildren[1]
    const items = content.props.children as ReactElement<{
      children: ReactNode
      className: string
      onClick: () => void
    }>[]

    expect(label.props.children).toBe('Change language')
    expect(label.props.className).toBe('sr-only')
    expect(items.map((item) => item.props.children)).toEqual(['English', '中文'])
    expect(items.map((item) => item.props.className)).toEqual(['bg-accent', ''])

    items[0].props.onClick()
    items[1].props.onClick()
    expect(changeLocale.mock.calls).toEqual([['en'], ['zh']])
  })
})
