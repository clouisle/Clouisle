'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { endOfDay, format, startOfDay, subDays } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'
import { CalendarIcon } from 'lucide-react'
import type { DateRange } from 'react-day-picker'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export type TimeRange = '7d' | '30d' | '90d' | 'all' | { start_time: string; end_time: string }

const PRESETS = ['7d', '30d', '90d', 'all'] as const

interface TimeRangeSelectorProps {
  value: TimeRange
  onChange: (value: TimeRange) => void
  className?: string
  invalid?: boolean
}

export function TimeRangeSelector({
  value,
  onChange,
  className,
  invalid = false,
}: TimeRangeSelectorProps) {
  const t = useTranslations('dashboard.timeRange')
  const locale = useLocale()
  const calendarLocale = locale.startsWith('zh') ? zhCN : enUS
  const descriptionId = React.useId()
  const [open, setOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<DateRange | undefined>()
  const [draftChanged, setDraftChanged] = React.useState(false)
  const validDraft = Boolean(draft?.from && draft.to
    && Number.isFinite(draft.from.getTime()) && Number.isFinite(draft.to.getTime())
    && startOfDay(draft.from) <= startOfDay(draft.to))

  const openRange = () => {
    const end = new Date()
    setDraft(invalid || value === 'all' ? undefined : typeof value === 'object'
      ? { from: new Date(value.start_time), to: new Date(value.end_time) }
      : { from: subDays(end, Number.parseInt(value, 10) - 1), to: end })
    setDraftChanged(false)
    setOpen(true)
  }

  const applyRange = () => {
    if (!validDraft || !draft?.from || !draft.to) return
    onChange(!draftChanged && !invalid && typeof value === 'object' ? value : {
      start_time: startOfDay(draft.from).toISOString(),
      end_time: endOfDay(draft.to).toISOString().replace('.999Z', '.999999Z'),
    })
    setOpen(false)
  }

  const label = invalid ? t('pickDate') : typeof value === 'object'
    ? `${format(new Date(value.start_time), 'PPP', { locale: calendarLocale })} – ${format(new Date(value.end_time), 'PPP', { locale: calendarLocale })}`
    : t(value)

  return (
    <div className={className}>
      <Popover open={open} onOpenChange={(nextOpen) => nextOpen ? openRange() : setOpen(false)}>
        <PopoverTrigger render={<Button variant="outline" className="w-auto justify-start font-normal" aria-label={t('label')} aria-invalid={invalid} />}>
          <CalendarIcon className="mr-2 h-4 w-4" />
          {label}
        </PopoverTrigger>
        <PopoverContent className="w-auto max-w-[calc(100vw-2rem)] overflow-x-auto p-0" align="end" aria-describedby={descriptionId}>
          <p id={descriptionId} className="px-4 pt-4 text-sm text-muted-foreground">{t('description')}</p>
          <Calendar mode="range" selected={draft} onSelect={(range) => { setDraft(range); setDraftChanged(true) }} defaultMonth={draft?.from} numberOfMonths={2} locale={calendarLocale} />
          {draft?.from && !validDraft && <p role="alert" className="px-4 text-sm text-destructive">{t('invalid')}</p>}
          <div className="flex justify-end gap-2 px-4 pb-4">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t('cancel')}</Button>
            <Button type="button" onClick={applyRange} disabled={!validDraft}>{t('apply')}</Button>
          </div>
          <div className="space-y-2 border-t p-4">
            <p className="text-xs font-medium text-muted-foreground">{t('presets')}</p>
            <div className="flex flex-wrap gap-2">{PRESETS.map((preset) => (
              <Button key={preset} type="button" variant={!invalid && value === preset ? 'secondary' : 'outline'} size="sm" onClick={() => { onChange(preset); setOpen(false) }}>{t(preset)}</Button>
            ))}</div>
          </div>
        </PopoverContent>
      </Popover>
      {invalid && <p role="alert" className="text-sm text-destructive">{t('invalid')}</p>}
    </div>
  )
}
