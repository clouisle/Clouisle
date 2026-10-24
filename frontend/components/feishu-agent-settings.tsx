'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { HelpCircle, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ApiError } from '@/lib/api/client'
import { feishuAgentApi, type FeishuAgentPreference, type FeishuPersonalAgent } from '@/lib/api/feishu-agent'

export function FeishuAgentSettings({ active = true }: { active?: boolean }) {
  const t = useTranslations('settings.feishu')
  const [config, setConfig] = React.useState<FeishuAgentPreference | null>(null)
  const [agents, setAgents] = React.useState<FeishuPersonalAgent[]>([])
  const [selected, setSelected] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState('')
  const [notice, setNotice] = React.useState('')
  const generation = React.useRef(0)
  const id = React.useId()
  const load = React.useCallback(async () => {
    const current = ++generation.current
    setLoading(true); setError(''); setNotice('')
    try {
      const [next, candidates] = await Promise.all([feishuAgentApi.config(), feishuAgentApi.agents()])
      if (current !== generation.current) return
      setConfig(next); setAgents(candidates); setSelected(next.agent_id ?? '')
    } catch (err) {
      if (current === generation.current) { setConfig(null); setError(err instanceof ApiError ? err.message : t('failed')) }
    } finally { if (current === generation.current) setLoading(false) }
  }, [t])
  React.useEffect(() => {
    const requests = generation
    if (active) void load()
    return () => { requests.current++ }
  }, [active, load])
  const save = async (agentId: string | null) => {
    const current = generation.current
    setSaving(true); setError(''); setNotice('')
    try {
      const next = await feishuAgentApi.update(agentId)
      if (current !== generation.current) return
      setConfig(next); setSelected(next.agent_id ?? ''); setNotice(t('saved'))
    } catch (err) {
      if (current === generation.current) setError(err instanceof ApiError ? err.message : t('failed'))
    } finally { setSaving(false) }
  }
  const toggleEnabled = async (enabled: boolean) => {
    const current = generation.current
    setSaving(true); setError(''); setNotice('')
    try {
      const next = await feishuAgentApi.setEnabled(enabled)
      if (current !== generation.current) return
      setConfig(next); setNotice(t('saved'))
    } catch (err) {
      if (current === generation.current) setError(err instanceof ApiError ? err.message : t('failed'))
    } finally { setSaving(false) }
  }
  if (!active) return null
  const candidate = agents.find(agent => agent.id === selected)
  const label = candidate ? `${candidate.name} · ${candidate.team_name}` : selected ? (config?.agent_name ?? t('unavailable')) : t('choose')
  const canChoose = Boolean(config?.enabled && config.linked) && !loading && !saving
  const statusHint = !config ? null
    : !config.enabled ? 'disabled'
    : !config.linked ? 'unlinked'
    : config.agent_id && !config.agent_available ? 'unavailable'
    : agents.length === 0 ? 'empty'
    : !config.agent_id ? 'selectBeforeEnable'
    : null
  return <section className="space-y-3" aria-labelledby={`${id}-title`}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 id={`${id}-title`} className="font-medium">{t('title')}</h3><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div>
      <Button variant="ghost" size="icon" aria-label={t('refresh')} title={t('refresh')} disabled={loading || saving} onClick={() => void load()}><RefreshCw className="size-4" /></Button>
    </div>
    {error && <Alert variant="destructive"><AlertDescription role="alert">{error}</AlertDescription></Alert>}
    {!error && (statusHint || notice) && !loading && <p role="status" className="text-sm text-muted-foreground">{statusHint ? t(statusHint) : notice}</p>}
    {loading ? <Loader2 className="size-5 animate-spin" aria-label={t('loading')} /> : config && <Card size="sm" className="gap-3">
      <CardContent className="space-y-3">
      <div className="flex items-center justify-between gap-4 border-b pb-3">
        <Label htmlFor={`${id}-enabled`}>{t('enable')}</Label>
        <Switch id={`${id}-enabled`} aria-label={t('enable')} checked={config.is_enabled}
          disabled={saving || (!config.is_enabled && (!config.enabled || !config.linked || !config.agent_available))}
          onCheckedChange={value => void toggleEnabled(value)} />
      </div>
      <div className="min-w-0 space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Label htmlFor={`${id}-agent`}>{t('agent')}</Label>
          <Tooltip>
            <TooltipTrigger type="button" aria-label={t('help')} className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <HelpCircle className="size-3.5" aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="top" align="start" className="max-w-[min(28rem,calc(100vw-2rem))] space-y-2 text-left leading-relaxed">
              <p>{t('enableHint')}</p>
              <p>{t('switchHint')}</p>
            </TooltipContent>
          </Tooltip>
        </div>
        <Select value={selected} disabled={!canChoose} onValueChange={value => { if (value) setSelected(value) }}>
          <SelectTrigger id={`${id}-agent`} className="w-full"><SelectValue>{label}</SelectValue></SelectTrigger>
          <SelectContent>{agents.map(agent => <SelectItem key={agent.id} value={agent.id}>{`${agent.name} · ${agent.team_name}`}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
        <Button size="sm" variant="outline" disabled={!config.agent_id || loading || saving} onClick={() => void save(null)}>{t('clear')}</Button>
        <Button size="sm" disabled={!canChoose || !candidate || selected === (config.agent_id ?? '')} onClick={() => void save(selected)}>{saving && <Loader2 className="mr-2 size-4 animate-spin" />}{t('save')}</Button>
      </div>
      </CardContent>
    </Card>}
  </section>
}
