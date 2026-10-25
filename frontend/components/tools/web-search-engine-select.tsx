'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { toolsApi, type WebSearchDefaultEngine } from '@/lib/api'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface WebSearchEngineSelectProps {
  value: string
  onValueChange: (value: string) => void
  className?: string
}

export function WebSearchEngineSelect({ value, onValueChange, className }: WebSearchEngineSelectProps) {
  const t = useTranslations('agents.orchestration.tools.config')
  const [engines, setEngines] = useState<WebSearchDefaultEngine[]>([])

  useEffect(() => {
    let active = true
    toolsApi.getWebSearchEngines().then(
      (enabled) => { if (active) setEngines(enabled) },
      () => { if (active) setEngines([]) },
    )
    return () => { active = false }
  }, [])

  const labels: Record<string, string> = {
    auto: t('engineAuto'),
    tavily: t('engineTavily'),
    bocha: t('engineBocha'),
    searxng: t('engineSearxng'),
  }

  return (
    <Select value={value} onValueChange={(next) => { if (next) onValueChange(next) }}>
      <SelectTrigger className={className}>
        <SelectValue>{labels[value] || value}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="auto">{labels.auto}</SelectItem>
        {engines.map((engine) => (
          <SelectItem key={engine} value={engine}>{labels[engine]}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
