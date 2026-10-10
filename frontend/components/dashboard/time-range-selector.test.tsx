import { afterEach, describe, expect, it, mock } from 'bun:test'
import React from 'react'
import { format } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'
import type { DateRange } from 'react-day-picker'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import enDashboard from '@/i18n/en/dashboard.json'
import zhDashboard from '@/i18n/zh/dashboard.json'
import type { TimeRange } from './time-range-selector'

let locale: 'en' | 'zh' = 'en'
mock.module('next-intl', () => ({
  useLocale: () => locale,
  useTranslations: () => (key: string) => (locale === 'zh' ? zhDashboard : enDashboard).dashboard.timeRange[key as keyof typeof enDashboard.dashboard.timeRange],
}))
mock.module('lucide-react', () => ({ CalendarIcon: () => <span data-calendar-icon /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
const PopoverContext = React.createContext<{ open: boolean; onOpenChange: (open: boolean) => void }>({ open: false, onOpenChange: () => {} })
mock.module('@/components/ui/popover', () => ({
  Popover: ({ children, open, onOpenChange }: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) => <PopoverContext.Provider value={{ open, onOpenChange }}>{children}</PopoverContext.Provider>,
  PopoverTrigger: ({ children, render }: React.PropsWithChildren<{ render: React.ReactElement<React.ButtonHTMLAttributes<HTMLButtonElement>> }>) => {
    const { open, onOpenChange } = React.useContext(PopoverContext)
    return React.cloneElement(render, { onClick: () => onOpenChange(!open) }, children)
  },
  PopoverContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => {
    const { open, onOpenChange } = React.useContext(PopoverContext)
    return open ? <div data-range-popover {...props}><button aria-label="dismiss-range" onClick={() => onOpenChange(false)} />{children}</div> : null
  },
}))
const MockCalendar: React.FC<{ selected?: DateRange; onSelect: (range?: DateRange) => void; numberOfMonths: number; locale: { code: string } }> = () => <div data-calendar />
mock.module('@/components/ui/calendar', () => ({ Calendar: MockCalendar }))

// Load after mocks: static imports would initialize the selector with the real portal/calendar boundaries.
const { TimeRangeSelector } = await import('./time-range-selector')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
let renderer: ReactTestRenderer | undefined
const change = mock<(range: TimeRange) => void>(() => {})

async function render(value: TimeRange = '30d', invalid = false) {
  await act(async () => { renderer = create(<TimeRangeSelector value={value} onChange={change} invalid={invalid} />) })
  return renderer!
}
function button(label: string) {
  const popover = renderer!.root.findAllByProps({ 'data-range-popover': true })[0]
  return (popover ?? renderer!.root).findAllByType('button').find((node) => node.children.includes(label))!
}
function openRange() {
  act(() => renderer!.root.findByProps({ 'aria-label': (locale === 'zh' ? zhDashboard : enDashboard).dashboard.timeRange.label }).props.onClick())
}
function selectRange(range?: DateRange) {
  act(() => renderer!.root.findByType(MockCalendar).props.onSelect(range))
}

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  locale = 'en'
  change.mockClear()
})

describe('TimeRangeSelector', () => {
  it('opens two calendar months and puts the four existing presets below Apply and Cancel', async () => {
    await render('7d')
    expect(renderer!.root.findAllByType('label')).toHaveLength(0)
    expect(button('Last 7 Days')).toBeDefined()
    openRange()
    expect(renderer!.root.findByType(MockCalendar).props.numberOfMonths).toBe(2)
    const labels = renderer!.root.findByProps({ 'data-range-popover': true }).findAllByType('button').map((node) => node.children.join(''))
    expect(labels.slice(-6)).toEqual(['Cancel', 'Apply', 'Last 7 Days', 'Last 30 Days', 'Last 90 Days', 'All Time'])
    for (const [preset, label] of [['7d', 'Last 7 Days'], ['30d', 'Last 30 Days'], ['90d', 'Last 90 Days'], ['all', 'All Time']] as const) {
      act(() => button(label).props.onClick())
      expect(change).toHaveBeenLastCalledWith(preset)
      expect(renderer!.root.findAllByProps({ 'data-range-popover': true })).toHaveLength(0)
      openRange()
    }
  })

  it('blocks incomplete, non-finite and reversed drafts and only applies a complete selection', async () => {
    await render('all')
    openRange()
    const from = new Date(2026, 9, 8), to = new Date(2026, 9, 10)
    for (const draft of [undefined, { from }, { from: new Date(NaN), to }, { from: to, to: from }]) {
      selectRange(draft)
      expect(button('Apply').props.disabled).toBe(true)
      act(() => button('Apply').props.onClick())
      expect(change).not.toHaveBeenCalled()
    }
    selectRange({ from, to })
    expect(button('Apply').props.disabled).toBe(false)
    expect(change).not.toHaveBeenCalled()
    act(() => button('Apply').props.onClick())
    expect(change).toHaveBeenCalledWith({ start_time: from.toISOString(), end_time: new Date(2026, 9, 10, 23, 59, 59, 999).toISOString().replace('.999Z', '.999999Z') })
  })

  it('cancel and outside dismissal discard the draft and reopen the applied dates', async () => {
    const value = { start_time: '2026-10-08T10:00:00.123456+02:00', end_time: '2026-10-10T11:00:00.999999+02:00' }
    await render(value)
    for (const dismiss of ['Cancel', 'dismiss-range']) {
      openRange()
      expect(renderer!.root.findByType(MockCalendar).props.selected).toEqual({ from: new Date(value.start_time), to: new Date(value.end_time) })
      selectRange({ from: new Date(2026, 8, 1), to: new Date(2026, 8, 2) })
      act(() => (dismiss === 'Cancel' ? button(dismiss) : renderer!.root.findByProps({ 'aria-label': dismiss })).props.onClick())
      expect(change).not.toHaveBeenCalled()
    }
    openRange()
    act(() => button('Apply').props.onClick())
    expect(change).toHaveBeenCalledWith(value)
  })

  it('shows invalid restored ranges and lets a calendar selection correct them', async () => {
    await render('30d', true)
    expect(renderer!.root.findAllByType('button').find((node) => node.props['aria-invalid'] === true)!.children).toContain('Pick a date range')
    expect(renderer!.root.findByProps({ role: 'alert' }).children.join('')).toContain('Choose a complete, valid date range')
    openRange()
    expect(renderer!.root.findByType(MockCalendar).props.selected).toBeUndefined()
    expect(button('Apply').props.disabled).toBe(true)
    selectRange({ from: new Date(2026, 9, 8), to: new Date(2026, 9, 8) })
    act(() => button('Apply').props.onClick())
    expect(change).toHaveBeenCalledTimes(1)
  })

  for (const scenario of [
    { zone: 'UTC', month: 9, day: 8, start: '2026-10-08T00:00:00.000Z', end: '2026-10-08T23:59:59.999999Z' },
    { zone: 'America/New_York', month: 2, day: 8, start: '2026-03-08T05:00:00.000Z', end: '2026-03-09T03:59:59.999999Z' },
    { zone: 'America/New_York', month: 10, day: 1, start: '2026-11-01T04:00:00.000Z', end: '2026-11-02T04:59:59.999999Z' },
  ]) {
    it(`includes every microsecond of ${scenario.month + 1}/${scenario.day} in ${scenario.zone}`, async () => {
      const original = process.env.TZ
      process.env.TZ = scenario.zone
      try {
        await render()
        openRange()
        const day = new Date(2026, scenario.month, scenario.day, 12)
        selectRange({ from: day, to: day })
        act(() => button('Apply').props.onClick())
        expect(change).toHaveBeenCalledWith({ start_time: scenario.start, end_time: scenario.end })
      } finally {
        if (original === undefined) delete process.env.TZ
        else process.env.TZ = original
      }
    })
  }

  for (const language of ['en', 'zh'] as const) {
    it(`localizes the trigger, dates, footer and calendar in ${language}`, async () => {
      locale = language
      const value = { start_time: '2026-10-08T08:00:00Z', end_time: '2026-10-10T09:00:00Z' }
      await render(value)
      const dateLocale = language === 'zh' ? zhCN : enUS
      const messages = (language === 'zh' ? zhDashboard : enDashboard).dashboard.timeRange
      const trigger = renderer!.root.findAllByType('button').find((node) => node.props['aria-label'] === messages.label)!
      expect(trigger.children).toContain(`${format(new Date(value.start_time), 'PPP', { locale: dateLocale })} – ${format(new Date(value.end_time), 'PPP', { locale: dateLocale })}`)
      openRange()
      expect(renderer!.root.findByType(MockCalendar).props.locale.code).toBe(dateLocale.code)
      expect(button(messages.apply)).toBeDefined()
      expect(button(messages.cancel)).toBeDefined()
      expect(button(messages['90d'])).toBeDefined()
    })
  }
})
