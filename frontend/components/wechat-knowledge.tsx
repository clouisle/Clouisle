'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { QRCodeSVG } from 'qrcode.react'
import { HelpCircle, Loader2, RefreshCw, Square } from 'lucide-react'
import {
  wechatKnowledgeApi,
  WECHAT_ACTIVE_RUN_STATUSES,
  type WeChatAgentConfigSummary,
  type WeChatAgentOption,
  type WeChatAgentVariable,
  type WeChatBinding,
  type WeChatCollection,
  type WeChatLogin,
  type WeChatFeatures,
  type WeChatModel,
  type WeChatModels,
  type WeChatPurpose,
  type WeChatPurposeInput,
  type WeChatTarget,
} from '@/lib/api/wechat-knowledge'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectEmpty, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

function targetLabel(target: WeChatTarget) { return `${target.team_name} / ${target.name}` }

function isActiveRunStatus(status: string | null) {
  return Boolean(status && (WECHAT_ACTIVE_RUN_STATUSES as readonly string[]).includes(status))
}

function CollectionSummary({ collection }: { collection: WeChatCollection | null }) {
  const t = useTranslations('settings.wechat')
  if (!collection) return <p className="text-sm text-muted-foreground">{t('collectionInactive')}</p>
  return <p className="text-sm text-muted-foreground">{t('collectionActive', { target: collection.knowledge_base_name ?? t('targetMissing') })}</p>
}

function AgentSummary({ config }: { config: WeChatAgentConfigSummary | null }) {
  const t = useTranslations('settings.wechat')
  if (!config?.agent_id) return <p className="text-sm text-muted-foreground">{t('agentInactive')}</p>
  return <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
    <p className="text-muted-foreground">{config.agent_name ?? t('targetMissing')}</p>
    {config.run_status && <p className="text-muted-foreground">{t('agentRunStatus', { status: t(`runStatus.${config.run_status}`) })}</p>}
  </div>
}

type VariableValue = string | boolean | number

function initialVariables(agent: WeChatAgentOption | null, saved: Record<string, unknown>): Record<string, VariableValue> {
  const values: Record<string, VariableValue> = {}
  for (const definition of agent?.variables ?? []) {
    if (definition.hidden) continue
    const stored = saved[definition.name]
    if (stored !== undefined && stored !== null) { values[definition.name] = stored as VariableValue; continue }
    if (definition.default !== undefined && definition.default !== null && definition.default !== '') {
      values[definition.name] = definition.type === 'checkbox' ? definition.default === 'true' : definition.default
      continue
    }
    values[definition.name] = definition.type === 'checkbox' ? false : ''
  }
  return values
}

function variableError(definition: WeChatAgentVariable, value: VariableValue, t: (key: string) => string): string | null {
  const empty = value === '' || value === undefined || value === null
  if (empty) return definition.required ? t('variablesRequired') : null
  if (definition.type === 'number') {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return t('variableNumberInvalid')
    if (definition.min !== null && definition.min !== undefined && parsed < definition.min) return t('variableNumberInvalid')
    if (definition.max !== null && definition.max !== undefined && parsed > definition.max) return t('variableNumberInvalid')
    return null
  }
  if (definition.options && definition.options.length > 0 && !definition.options.includes(String(value))) return t('variableOptionInvalid')
  if (definition.maxLength && String(value).length > definition.maxLength) return t('variableTooLong')
  return null
}

function VariableFields({ agent, values, errors, disabled, onChange }: { agent: WeChatAgentOption; values: Record<string, VariableValue>; errors: Record<string, string>; disabled: boolean; onChange: (name: string, value: VariableValue) => void }) {
  const t = useTranslations('settings.wechat')
  const uid = React.useId()
  return <div className="grid gap-3 sm:grid-cols-2">
    {agent.variables.filter(definition => !definition.hidden).map(definition => {
      const value = values[definition.name] ?? (definition.type === 'checkbox' ? false : '')
      const error = errors[definition.name]
      return <div key={definition.name} className={`min-w-0 space-y-1${definition.type === 'paragraph' ? ' sm:col-span-2' : ''}`}>
        <Label htmlFor={`${uid}-${definition.name}`}>{definition.label || definition.name}{definition.required && <span className="ml-1 text-destructive">*</span>}</Label>
        {definition.type === 'select' ? <Select value={String(value)} disabled={disabled} onValueChange={next => onChange(definition.name, next ?? '')}>
          <SelectTrigger id={`${uid}-${definition.name}`} className="w-full" aria-invalid={Boolean(error)}><SelectValue>{definition.options?.find(option => option === value) ?? t('variablePlaceholder')}</SelectValue></SelectTrigger>
          <SelectContent>{(definition.options ?? []).map(option => <SelectItem key={option} value={option}>{option}</SelectItem>)}</SelectContent>
        </Select> : definition.type === 'checkbox' ? <div className="flex items-center gap-2">
          <Input id={`${uid}-${definition.name}`} type="checkbox" className="size-4" checked={Boolean(value)} disabled={disabled} onChange={event => onChange(definition.name, event.target.checked)} />
          {definition.description && <span className="text-xs text-muted-foreground">{definition.description}</span>}
        </div> : definition.type === 'paragraph' ? <Textarea id={`${uid}-${definition.name}`} rows={3} value={String(value)} disabled={disabled} aria-invalid={Boolean(error)} placeholder={definition.description || t('variablePlaceholder')} onChange={event => onChange(definition.name, event.target.value)} /> : <Input id={`${uid}-${definition.name}`} type={definition.type === 'number' ? 'number' : 'text'} value={String(value)} min={definition.min ?? undefined} max={definition.max ?? undefined} disabled={disabled} aria-invalid={Boolean(error)} placeholder={definition.description || t('variablePlaceholder')} onChange={event => onChange(definition.name, event.target.value)} />}
        {definition.description && definition.type !== 'checkbox' && definition.type !== 'paragraph' && <p className="text-xs text-muted-foreground">{definition.description}</p>}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    })}
  </div>
}

function PurposeForm({ binding, features, busy, onCancel, onSaved, run }: { binding: WeChatBinding; features: WeChatFeatures | null; busy: boolean; onCancel: () => void; onSaved: () => Promise<void>; run: (action: () => Promise<void>) => Promise<void> }) {
  const t = useTranslations('settings.wechat')
  const [purpose, setPurpose] = React.useState<WeChatPurpose>(binding.purpose)
  const [targets, setTargets] = React.useState<WeChatTarget[]>([])
  const [agents, setAgents] = React.useState<WeChatAgentOption[]>([])
  const [target, setTarget] = React.useState(binding.collection?.knowledge_base_id ?? '')
  const [vision, setVision] = React.useState(binding.collection?.vision_model_id ?? 'none')
  const [stt, setStt] = React.useState(binding.collection?.stt_model_id ?? 'none')
  const [agentId, setAgentId] = React.useState(binding.agent_config?.agent_id ?? '')
  const [agentStt, setAgentStt] = React.useState(binding.agent_config?.stt_model_id ?? 'none')
  const [variables, setVariables] = React.useState<Record<string, VariableValue>>({})
  const [variableErrors, setVariableErrors] = React.useState<Record<string, string>>({})
  const [models, setModels] = React.useState<WeChatModels>({ vision: [], stt: [] })
  const [agentModels, setAgentModels] = React.useState<WeChatModel[]>([])
  const [targetsLoading, setTargetsLoading] = React.useState(false)
  const [agentsLoading, setAgentsLoading] = React.useState(false)
  const [modelsLoading, setModelsLoading] = React.useState(false)
  const [agentModelsLoading, setAgentModelsLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const initializedAgentIdRef = React.useRef<string | null>(null)
  const savedAgentConfigRef = React.useRef(binding.agent_config)
  const uid = React.useId()
  const fail = React.useCallback((err: unknown) => setError(err instanceof ApiError ? err.message : t('failed')), [t])
  const selectedAgent = agents.find(item => item.id === agentId) ?? null
  const collectionEnabled = features?.knowledge_collection === true
  const agentEnabled = features?.agent_chat === true
  const purposeEnabled = purpose === 'none' || (purpose === 'agent' ? agentEnabled : collectionEnabled)

  React.useEffect(() => {
    if (purpose !== 'knowledge_collection' || !collectionEnabled) return
    let cancelled = false
    setTargetsLoading(true)
    void wechatKnowledgeApi.targets().then(choices => { if (!cancelled) setTargets(choices) }).catch(err => { if (!cancelled) fail(err) }).finally(() => { if (!cancelled) setTargetsLoading(false) })
    return () => { cancelled = true }
  }, [purpose, collectionEnabled, fail])

  React.useEffect(() => {
    if (purpose !== 'agent' || !agentEnabled) return
    let cancelled = false
    setAgentsLoading(true)
    void wechatKnowledgeApi.agents().then(choices => { if (!cancelled) setAgents(choices) }).catch(err => { if (!cancelled) fail(err) }).finally(() => { if (!cancelled) setAgentsLoading(false) })
    return () => { cancelled = true }
  }, [purpose, agentEnabled, fail])

  React.useEffect(() => {
    if (purpose !== 'knowledge_collection' || !target || !collectionEnabled) { setModels({ vision: [], stt: [] }); return }
    let cancelled = false
    setModelsLoading(true)
    void wechatKnowledgeApi.models(target).then(value => { if (!cancelled) setModels(value) }).catch(err => { if (!cancelled) fail(err) }).finally(() => { if (!cancelled) setModelsLoading(false) })
    return () => { cancelled = true }
  }, [purpose, target, collectionEnabled, fail])

  React.useEffect(() => {
    if (purpose !== 'agent' || !agentId || !agentEnabled) { setAgentModels([]); return }
    let cancelled = false
    setAgentModelsLoading(true)
    void wechatKnowledgeApi.agentModels(agentId).then(value => { if (!cancelled) setAgentModels(value.stt) }).catch(err => { if (!cancelled) fail(err) }).finally(() => { if (!cancelled) setAgentModelsLoading(false) })
    return () => { cancelled = true }
  }, [purpose, agentId, agentEnabled, fail])

  React.useEffect(() => {
    if (!selectedAgent || initializedAgentIdRef.current === selectedAgent.id) return
    initializedAgentIdRef.current = selectedAgent.id
    const savedAgentConfig = savedAgentConfigRef.current
    setVariables(initialVariables(selectedAgent, savedAgentConfig?.agent_id === selectedAgent.id ? savedAgentConfig.variables : {}))
    setVariableErrors({})
    setAgentStt(savedAgentConfig?.agent_id === selectedAgent.id ? savedAgentConfig.stt_model_id ?? 'none' : 'none')
  }, [selectedAgent])

  const changeVariable = (name: string, value: VariableValue) => {
    setVariables(current => ({ ...current, [name]: value }))
    setVariableErrors(current => {
      if (!current[name]) return current
      const next = { ...current }
      delete next[name]
      return next
    })
  }

  const validateVariables = () => {
    const next: Record<string, string> = {}
    for (const definition of selectedAgent?.variables ?? []) {
      if (definition.hidden) continue
      const message = variableError(definition, variables[definition.name] ?? (definition.type === 'checkbox' ? false : ''), t)
      if (message) next[definition.name] = message
    }
    setVariableErrors(next)
    return Object.keys(next).length === 0
  }

  const save = () => run(async () => {
    if (!purposeEnabled) return
    if (purpose === 'knowledge_collection' && !target) return
    if (purpose === 'agent' && !agentId) return
    if (purpose === 'agent' && !validateVariables()) return
    const payload: WeChatPurposeInput = { purpose }
    if (purpose === 'knowledge_collection') {
      payload.knowledge_base_id = target
      payload.vision_model_id = vision === 'none' ? null : vision
      payload.stt_model_id = stt === 'none' ? null : stt
    } else if (purpose === 'agent') {
      payload.agent_id = agentId
      payload.variables = variables
      payload.stt_model_id = agentStt === 'none' ? null : agentStt
    }
    await wechatKnowledgeApi.purpose(binding.id, payload)
    await onSaved()
  })

  const saveDisabled = busy
    || !purposeEnabled
    || (purpose === 'knowledge_collection' && (!target || targetsLoading || modelsLoading))
    || (purpose === 'agent' && (!agentId || agentsLoading || agentModelsLoading))
  return <div className="grid gap-3 border-t pt-3 sm:grid-cols-2">
    {error && <Alert variant="destructive" className="sm:col-span-2"><AlertDescription role="alert">{error}</AlertDescription></Alert>}
    {!purposeEnabled && <p role="status" className="text-sm text-muted-foreground sm:col-span-2">{t('featurePaused')}</p>}
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={`${uid}-purpose`}>{t('purposeLabel')}</Label>
      <Select value={purpose} disabled={busy} onValueChange={value => setPurpose((value as WeChatPurpose) ?? 'none')}>
        <SelectTrigger id={`${uid}-purpose`} className="w-full"><SelectValue>{t(`purpose${purpose === 'none' ? 'None' : purpose === 'knowledge_collection' ? 'KnowledgeCollection' : 'Agent'}`)}</SelectValue></SelectTrigger>
        <SelectContent>
          <SelectItem value="none">{t('purposeNone')}</SelectItem>
          <SelectItem value="knowledge_collection" disabled={!collectionEnabled}>{t('purposeKnowledgeCollection')}</SelectItem>
          <SelectItem value="agent" disabled={!agentEnabled}>{t('purposeAgent')}</SelectItem>
        </SelectContent>
      </Select>
    </div>
    {purpose === 'knowledge_collection' && collectionEnabled && <>
      <div className="min-w-0 space-y-1.5"><Label htmlFor={`${uid}-target`}>{t('target')}</Label><Select value={target} disabled={busy || targetsLoading} onValueChange={value => { setTarget(value ?? ''); setVision('none'); setStt('none') }}>
        <SelectTrigger id={`${uid}-target`} className="w-full"><SelectValue>{targets.find(item => item.id === target) ? targetLabel(targets.find(item => item.id === target)!) : t('selectTarget')}</SelectValue></SelectTrigger><SelectContent>{targets.map(item => <SelectItem key={item.id} value={item.id}>{targetLabel(item)}</SelectItem>)}<SelectEmpty>{t('noTargets')}</SelectEmpty></SelectContent>
      </Select>{targetsLoading ? <Loader2 className="size-4 animate-spin" aria-label={t('loading')} /> : targets.length === 0 && <p className="text-sm text-muted-foreground">{t('noTargets')}</p>}</div>
      {(['vision', 'stt'] as const).map(kind => {
        const selected = kind === 'vision' ? vision : stt
        const label = models[kind].find(item => item.id === selected)?.name ?? t('notConfigured')
        return <div key={kind} className="min-w-0 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Label htmlFor={`${uid}-${kind}`}>{t(kind)}</Label>
            {kind === 'vision' && <Tooltip>
              <TooltipTrigger type="button" aria-label={t('modelHelp')} className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <HelpCircle className="size-3.5" aria-hidden="true" />
              </TooltipTrigger>
              <TooltipContent side="top" align="start" className="max-w-[min(28rem,calc(100vw-2rem))] text-left leading-relaxed">{t('modelHint')}</TooltipContent>
            </Tooltip>}
          </div>
          <Select value={selected} disabled={!target || modelsLoading || busy} onValueChange={value => (kind === 'vision' ? setVision : setStt)(value ?? 'none')}><SelectTrigger id={`${uid}-${kind}`} className="w-full"><SelectValue>{label}</SelectValue></SelectTrigger><SelectContent><SelectItem value="none">{t('notConfigured')}</SelectItem>{models[kind].map(item => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select>
        </div>
      })}
    </>}
    {purpose === 'agent' && agentEnabled && <>
      <div className="min-w-0 space-y-1.5"><Label htmlFor={`${uid}-agent`}>{t('purposeAgent')}</Label><Select value={agentId} disabled={busy || agentsLoading} onValueChange={value => setAgentId(value ?? '')}>
        <SelectTrigger id={`${uid}-agent`} className="w-full"><SelectValue>{selectedAgent ? `${selectedAgent.team_name} / ${selectedAgent.name}` : t('agentSelect')}</SelectValue></SelectTrigger><SelectContent>{agents.map(item => <SelectItem key={item.id} value={item.id}>{`${item.team_name} / ${item.name}`}</SelectItem>)}<SelectEmpty>{t('noAgents')}</SelectEmpty></SelectContent>
      </Select>{agentsLoading ? <Loader2 className="size-4 animate-spin" aria-label={t('loading')} /> : agents.length === 0 && <p className="text-sm text-muted-foreground">{t('noAgents')}</p>}</div>
      {selectedAgent && selectedAgent.variables.length > 0 && <div className="space-y-2 sm:col-span-2">
        <h5 className="text-sm font-medium">{t('agentVariables')}</h5>
        <p className="text-xs text-muted-foreground">{t('agentVariablesHint')}</p>
        <VariableFields agent={selectedAgent} values={variables} errors={variableErrors} disabled={busy} onChange={changeVariable} />
      </div>}
      <div className="space-y-2"><Label htmlFor={`${uid}-agent-stt`}>{t('agentStt')}</Label><Select value={agentStt} disabled={!agentId || agentModelsLoading || busy} onValueChange={value => setAgentStt(value ?? 'none')}><SelectTrigger id={`${uid}-agent-stt`} className="w-full"><SelectValue>{agentModels.find(item => item.id === agentStt)?.name ?? t('notConfigured')}</SelectValue></SelectTrigger><SelectContent><SelectItem value="none">{t('notConfigured')}</SelectItem>{agentModels.map(item => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent></Select></div>
    </>}
    <div className="flex flex-wrap justify-end gap-2 sm:col-start-2 sm:self-end">
      <Button size="sm" variant="outline" disabled={busy} onClick={onCancel}>{t('cancel')}</Button>
      <Button size="sm" disabled={saveDisabled} onClick={() => void save()}>{busy && <Loader2 className="mr-2 size-4 animate-spin" />}{t('save')}</Button>
    </div>
  </div>
}

export function WeChatKnowledge({ active = true }: { active?: boolean }) {
  const t = useTranslations('settings.wechat')
  const [bindings, setBindings] = React.useState<WeChatBinding[]>([])
  const [features, setFeatures] = React.useState<WeChatFeatures | null>(null)
  const canConnect = features?.agent_chat === true || features?.knowledge_collection === true
  const [login, setLogin] = React.useState<WeChatLogin | null>(null)
  const [configuring, setConfiguring] = React.useState<{ id: string; open: number } | null>(null)
  const [disconnecting, setDisconnecting] = React.useState<WeChatBinding | null>(null)
  const [verifyCode, setVerifyCode] = React.useState('')
  const [busy, setBusy] = React.useState(false)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState('')
  const [notice, setNotice] = React.useState('')
  const requestGeneration = React.useRef(0)
  const uid = React.useId()
  const fail = React.useCallback((err: unknown) => setError(err instanceof ApiError ? err.message : t('failed')), [t])
  const loadBindings = React.useCallback(async () => {
    const [rows, enabled] = await Promise.all([wechatKnowledgeApi.bindings(), wechatKnowledgeApi.features().catch(() => null)])
    setBindings(rows)
    setFeatures(enabled)
  }, [])
  const run = React.useCallback(async (action: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (err) { fail(err) } finally { setBusy(false) }
  }, [fail])

  React.useEffect(() => {
    if (!active) { requestGeneration.current++; setLogin(null); setFeatures(null); setConfiguring(null); return }
    let cancelled = false
    setLoading(true)
    void loadBindings().catch(err => { if (!cancelled) fail(err) }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [active, loadBindings, fail])

  React.useEffect(() => {
    if (!active) return
    let cancelled = false
    let inFlight = false
    const timer = window.setInterval(() => {
      if (inFlight) return
      inFlight = true
      void wechatKnowledgeApi.features().then(value => { if (!cancelled) setFeatures(value) }).catch(() => { if (!cancelled) setFeatures(null) }).finally(() => { inFlight = false })
    }, 5000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [active])

  React.useEffect(() => {
    if (canConnect) return
    requestGeneration.current++
    setLogin(null)
  }, [canConnect])

  React.useEffect(() => {
    const pendingLogin = login
    if (!active || !pendingLogin || !['wait', 'scaned'].includes(pendingLogin.status)) return
    let cancelled = false
    const generation = requestGeneration.current
    async function poll() {
      if (cancelled || !pendingLogin) return
      if (Date.now() >= Date.parse(pendingLogin.expires_at)) { setLogin({ ...pendingLogin, status: 'expired' }); return }
      try {
        const next = await wechatKnowledgeApi.poll(pendingLogin.id)
        if (cancelled || requestGeneration.current !== generation) return
        setLogin(next)
        if (next.status === 'confirmed') { setNotice(t('bound')); await loadBindings(); return }
      } catch (err) { if (!cancelled) { fail(err); setLogin(null) } }
    }
    const timer = window.setTimeout(poll, 500)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [active, login, fail, loadBindings, t])

  React.useEffect(() => {
    if (!active || !bindings.some(binding => isActiveRunStatus(binding.agent_config?.run_status ?? null))) return
    let cancelled = false
    const timer = setInterval(() => {
      if (cancelled) return
      void wechatKnowledgeApi.bindings().then(rows => { if (!cancelled) setBindings(rows) }).catch(() => {})
    }, 5000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [active, bindings])

  function configure(binding: WeChatBinding) {
    setConfiguring(current => ({ id: binding.id, open: current?.id === binding.id ? current.open + 1 : 1 }))
  }
  function closeForm() { setConfiguring(null) }
  if (!active) return null
  return <div className="space-y-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-1.5">
          <h3 className="font-medium">{t('title')}</h3>
          <Tooltip>
            <TooltipTrigger type="button" aria-label={t('help')} className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              <HelpCircle className="size-3.5" aria-hidden="true" />
            </TooltipTrigger>
            <TooltipContent side="top" align="start" className="max-w-[min(28rem,calc(100vw-2rem))] space-y-2 text-left leading-relaxed">
              <p>{t('bindingRule')}</p><p>{t('purposeHint')}</p><p>{t('agentInput')}</p><p>{t('collectionHint')}</p><p>{t('replyHint')}</p>
            </TooltipContent>
          </Tooltip>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{t('description')}</p>
      </div>
      <div className="flex items-center gap-1">
        <Button size="sm" disabled={busy || loading || Boolean(login) || !canConnect} onClick={() => void run(async () => { if (!canConnect) return; const generation = ++requestGeneration.current; const result = await wechatKnowledgeApi.login(); if (requestGeneration.current === generation) setLogin(result) })}>{busy && <Loader2 className="mr-2 size-4 animate-spin" />}{t('showQr')}</Button>
        <Button variant="ghost" size="icon" aria-label={t('refresh')} title={t('refresh')} disabled={busy || loading} onClick={() => void run(loadBindings)}><RefreshCw className="size-4" /></Button>
      </div>
    </div>
    {error && <Alert variant="destructive"><AlertDescription role="alert">{error}</AlertDescription></Alert>}
    {!error && (!loading && !canConnect ? <p role="status" className="text-sm text-muted-foreground">{t('featuresDisabled')}</p> : notice && <p role="status" className="text-sm">{notice}</p>)}
    {loading ? <Loader2 className="size-5 animate-spin" aria-label={t('loading')} /> : <>
        {login && <div className="space-y-3" aria-live="polite">
          {['wait', 'scaned', 'need_verifycode'].includes(login.status) && <div className="w-fit rounded-lg bg-white p-3"><QRCodeSVG value={login.qrcode_content} size={192} title={t('qrLabel')} /></div>}
          <p className="text-sm">{t(`login.${login.status}`)}</p>
          {login.status === 'need_verifycode' && <div className="space-y-2"><Label htmlFor={`${uid}-code`}>{t('verifyCode')}</Label><Input id={`${uid}-code`} inputMode="numeric" value={verifyCode} onChange={event => setVerifyCode(event.target.value.replace(/\D/g, ''))} maxLength={32} /><Button disabled={busy || !verifyCode} onClick={() => void run(async () => { const generation = requestGeneration.current; const next = await wechatKnowledgeApi.poll(login.id, verifyCode); if (generation !== requestGeneration.current) return; setLogin(next); setVerifyCode(''); if (next.status === 'confirmed') { setNotice(t('bound')); await loadBindings() } })}>{t('verify')}</Button></div>}
          <Button variant="outline" onClick={() => { requestGeneration.current++; setLogin(null) }}>{t('closeQr')}</Button>
        </div>}
      <div className="space-y-3">
        {bindings.length === 0 && canConnect && <p className="text-sm text-muted-foreground">{t('empty')}</p>}
        {bindings.map(binding => {
        const formOpen = configuring?.id === binding.id ? configuring.open : 0
        const agentConfig = binding.agent_config
        return <Card key={binding.id} size="sm" className="gap-3">
          <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
            <div className="min-w-0 space-y-1">
              <CardTitle className="break-all text-sm">{binding.bot_id}</CardTitle>
              <p className="text-xs text-muted-foreground">{t('lastReceived')}: {binding.last_received_at ? new Date(binding.last_received_at).toLocaleString() : t('never')}</p>
            </div>
            <span className="shrink-0 rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">{t(`status.${binding.status}`)}</span>
          </CardHeader>
          <CardContent className="space-y-3">
            {binding.status === 'error' ? <p role="status" className="text-sm text-destructive">{binding.last_error || t('connectionError')}</p> : binding.last_error && <p className="text-sm text-destructive">{binding.last_error}</p>}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-1">
              <h4 className="text-xs font-medium text-muted-foreground">{t('purposeTitle')} · {binding.purpose === 'none' ? t('purposeNone') : binding.purpose === 'knowledge_collection' ? t('purposeKnowledgeCollection') : t('purposeAgent')}</h4>
              {binding.purpose === 'knowledge_collection' && <CollectionSummary collection={binding.collection} />}
              {binding.purpose === 'agent' && <AgentSummary config={agentConfig} />}
              {canConnect && binding.status !== 'error' && binding.purpose !== 'none' && !(binding.purpose === 'agent' ? features?.agent_chat : features?.knowledge_collection) && <p role="status" className="text-sm text-muted-foreground">{t('featurePaused')}</p>}
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <Button size="sm" variant="outline" disabled={busy} onClick={() => configure(binding)}>{t('change')}</Button>
                {binding.purpose === 'agent' && isActiveRunStatus(agentConfig?.run_status ?? null) && agentConfig?.run_id && agentConfig?.agent_id && <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(async () => { await wechatKnowledgeApi.stopRun(agentConfig.agent_id!, agentConfig.run_id!); await loadBindings() })}><Square className="mr-2 size-4" />{t('stop')}</Button>}
                <Button size="sm" variant="ghost" className="text-muted-foreground" disabled={busy || binding.status === 'disconnected'} onClick={() => setDisconnecting(binding)}>{t('disconnect')}</Button>
              </div>
            </div>
            {formOpen > 0 && <PurposeForm key={`${binding.id}-${formOpen}`} binding={binding} features={features} busy={busy} run={run} onCancel={closeForm} onSaved={async () => { closeForm(); setNotice(t('saved')); await loadBindings() }} />}
          </CardContent>
        </Card>
      })}
      </div>
    </>}
    <AlertDialog open={Boolean(disconnecting)} onOpenChange={open => { if (!open && !busy) setDisconnecting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t('disconnect')}</AlertDialogTitle><AlertDialogDescription>{t('disconnectHint')}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>{t('cancel')}</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={() => void run(async () => { if (!disconnecting) return; await wechatKnowledgeApi.disconnect(disconnecting.id); setDisconnecting(null); await loadBindings() })}>{t('disconnect')}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>
}
