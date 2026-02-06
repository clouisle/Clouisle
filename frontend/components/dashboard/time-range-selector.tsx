'use client'

import { useTranslations } from 'next-intl'
import { Calendar } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from '@/components/ui/select'

export type TimeRange = '7d' | '30d' | '90d' | 'all'

interface TimeRangeSelectorProps {
  value: TimeRange
  onChange: (value: TimeRange) => void
  className?: string
}

export function TimeRangeSelector({
  value,
  onChange,
  className,
}: TimeRangeSelectorProps) {
  const t = useTranslations('dashboard.timeRange')

  const options: { value: TimeRange; label: string }[] = [
    { value: '7d', label: t('7d') },
    { value: '30d', label: t('30d') },
    { value: '90d', label: t('90d') },
    { value: 'all', label: t('all') },
  ]

  // 获取当前选中项的标签
  const selectedLabel = options.find(opt => opt.value === value)?.label || value

  return (
    <div className={className}>
      <Select value={value} onValueChange={(v) => v && onChange(v as TimeRange)}>
        <SelectTrigger className="w-[180px]">
          <Calendar className="mr-2 h-4 w-4" />
          <span>{selectedLabel}</span>
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
