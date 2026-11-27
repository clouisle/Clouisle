'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { apiKeysApi, type APIKey } from '@/lib/api/api-keys'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useDebounce } from '@/hooks/use-debounce'

/**
 * Option label for one key: name, public prefix, and, when it can no longer
 * authenticate, its state.
 *
 * A revoked or expired key keeps its history and stays selectable so that
 * history can still be filtered, but it must not read as a live credential.
 */
export function formatHistoryKeyLabel(
  key: Pick<APIKey, 'name' | 'key_prefix' | 'is_active' | 'expires_at'>,
  labels: { inactive: string; expired: string },
): string {
  const state = !key.is_active
    ? labels.inactive
    : key.expires_at && new Date(key.expires_at).getTime() <= Date.now()
      ? labels.expired
      : null
  return `${key.name} (${key.key_prefix})${state ? ` · ${state}` : ''}`
}

/** Search only keys the caller can list; the history endpoint still enforces its own access rules. */
export function ApiKeyHistoryFilter({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const t = useTranslations('common.historyKeyFilter')
  const [search, setSearch] = React.useState('')
  const [keys, setKeys] = React.useState<APIKey[]>([])
  const [selected, setSelected] = React.useState<APIKey | null>(null)
  const [failed, setFailed] = React.useState(false)
  const debounced = useDebounce(search, 300)

  React.useEffect(() => {
    let live = true
    // The caller usually lacks ``apikey:read``; a refusal is handled by the
    // inline notice below, so a toast per request (and per keystroke of the
    // debounced search) would only duplicate it.
    apiKeysApi.getAPIKeys({
      page: 1,
      pageSize: 100,
      search: debounced || undefined,
      silent: true,
    })
      .then((result) => { if (live) { setKeys(result.items); setFailed(false) } })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [debounced])

  const options = selected && !keys.some((key) => key.id === selected.id) ? [selected, ...keys] : keys
  const labels = { inactive: t('inactive'), expired: t('expired') }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input aria-label={t('search')} placeholder={t('search')} value={search} onChange={(event) => setSearch(event.target.value)} className="h-9 w-44" />
      <Select value={value || 'all'} onValueChange={(next) => {
        if (!next) return
        setSelected(options.find((key) => key.id === next) || null)
        onChange(next === 'all' ? '' : next)
      }}>
        <SelectTrigger className="w-48" aria-label={t('label')}>
          <SelectValue>
            {(() => {
              const current = value ? options.find((key) => key.id === value) : null
              return current ? formatHistoryKeyLabel(current, labels) : t('all')
            })()}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t('all')}</SelectItem>
          {options.map((key) => (
            <SelectItem key={key.id} value={key.id}>
              {formatHistoryKeyLabel(key, labels)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {failed && <span role="status" className="text-sm text-muted-foreground">{t('loadFailed')}</span>}
    </div>
  )
}
