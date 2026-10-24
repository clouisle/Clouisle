'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { usePermissions } from '@/hooks/use-permissions'
import { feishuKnowledgeApi, type FeishuKnowledgeSource, type FeishuKnowledgeSpace, type FeishuKnowledgeTarget } from '@/lib/api/admin/feishu-knowledge'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, Loader2, Plus, RefreshCw } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
function getKnowledgeTargetLabel(item: FeishuKnowledgeTarget): string {
  return item.team_name ? `${item.team_name} / ${item.name}` : item.name
}

export function FeishuKnowledgeSync() {
  const t = useTranslations('siteSettings.feishuKnowledge')
  const { user } = usePermissions()
  const allowed = user?.is_superuser === true && user.is_active === true
  const [sources, setSources] = React.useState<FeishuKnowledgeSource[]>([])
  const [loading, setLoading] = React.useState(false)
  const [spaces, setSpaces] = React.useState<FeishuKnowledgeSpace[]>([])
  const [targets, setTargets] = React.useState<FeishuKnowledgeTarget[]>([])
  const [busy, setBusy] = React.useState(false)
  const [failed, setFailed] = React.useState(false)
  const [actionError, setActionError] = React.useState('')
  const [open, setOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<FeishuKnowledgeSource | null>(null)
  const [deleting, setDeleting] = React.useState<FeishuKnowledgeSource | null>(null)
  const [name, setName] = React.useState('')
  const [space, setSpace] = React.useState('')
  const [target, setTarget] = React.useState('')
  const [interval, setIntervalMinutes] = React.useState(60)
  const [enabled, setEnabled] = React.useState(true)
  const load = React.useCallback(async () => {
    if (!allowed) return
    setLoading(true)
    try { setSources(await feishuKnowledgeApi.sources()); setFailed(false) }
    catch { setFailed(true) }
    finally { setLoading(false) }
  }, [allowed])
  React.useEffect(() => { void load() }, [load])
  React.useEffect(() => {
    if (!allowed) return
    void feishuKnowledgeApi.spaces().then(setSpaces).catch(() => {})
  }, [allowed])
  React.useEffect(() => {
    if (!allowed || !sources.some(source => source.status === 'running' || source.status === 'queued')) return
    const timer = window.setInterval(() => { void load() }, 5000)
    return () => window.clearInterval(timer)
  }, [allowed, sources, load])
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try { await action(); await load() } catch { /* API client displays errors. */ }
    finally { setBusy(false) }
  }
  const edit = async (source: FeishuKnowledgeSource | null) => {
    setActionError('')
    setEditing(source)
    setName(source?.name ?? '')
    setIntervalMinutes(source?.interval_minutes ?? 60)
    setEnabled(source?.is_enabled ?? true)
    if (source) {
      setOpen(true)
      return
    }

    setSpace('')
    setTarget('')
    setOpen(true)
    setBusy(true)
    try {
      const [availableSpaces, availableTargets] = await Promise.all([feishuKnowledgeApi.spaces(), feishuKnowledgeApi.targets()])
      setSpaces(availableSpaces)
      setTargets(availableTargets)
    } catch (error) {
      setActionError(error instanceof ApiError ? error.message : t('loadFailed'))
    } finally {
      setBusy(false)
    }
  }
  if (!allowed) return <p className="text-muted-foreground">{t('superuserOnly')}</p>
  return <div className="space-y-6">
    <Alert variant="warning"><AlertDescription>{t('warning')}</AlertDescription></Alert>
    <p className="text-sm text-muted-foreground">{t('credentials')}</p>
    <div className="flex items-center justify-end gap-2"><Button disabled={busy} onClick={() => void edit(null)}><Plus className="mr-2 size-4" />{t('create')}</Button><Button type="button" variant="outline" size="icon" aria-label={t('refresh')} title={t('refresh')} disabled={loading || busy} onClick={() => void load()}><RefreshCw className={`size-4${loading ? ' animate-spin' : ''}`} /></Button></div>
    {actionError && <Alert variant="destructive"><AlertDescription className="whitespace-pre-wrap">{actionError}</AlertDescription></Alert>}
    {failed && <p role="alert">{t('loadFailed')}</p>}
    {loading && sources.length === 0 && <p>{t('loading')}</p>}
    {!loading && !failed && sources.length === 0 && <p className="text-muted-foreground">{t('empty')}</p>}
    {sources.map(source => <Card key={source.id} className="gap-0 py-0"><CardHeader className="flex flex-row items-center justify-between gap-3 px-4 py-3"><div className="flex min-w-0 items-center gap-2"><CardTitle className="truncate text-base">{source.name}</CardTitle><Badge variant="outline" className="shrink-0">{t(`status.${source.status}`)}</Badge></div><Label className="flex shrink-0 items-center gap-2 text-sm"><Switch checked={source.is_enabled} disabled={busy} onCheckedChange={checked => void act(() => feishuKnowledgeApi.update(source.id, { name: source.name, interval_minutes: source.interval_minutes, is_enabled: checked }))} />{t('enabled')}</Label></CardHeader><CardContent className="space-y-3 px-4 pb-3 pt-0">
      <div className="grid gap-x-4 gap-y-1 rounded-md bg-muted/40 px-3 py-2 text-sm sm:grid-cols-2"><p className="min-w-0 truncate"><span className="text-muted-foreground">{t('target')}: </span>{source.knowledge_base_name}</p><p className="min-w-0 truncate"><span className="text-muted-foreground">{t('space')}: </span>{spaces.find(item => item.space_id === source.space_id)?.name || source.space_name || source.space_id}</p><p><span className="text-muted-foreground">{t('interval')}: </span>{source.interval_minutes}</p><p><span className="text-muted-foreground">{t('lastSync')}: </span>{source.last_synced_at ? new Date(source.last_synced_at).toLocaleString() : t('never')}</p></div>
      {source.last_error && <p role="alert" className="text-sm text-destructive whitespace-pre-wrap">{source.last_error}</p>}
      {Object.keys(source.last_result ?? {}).length > 0 && <Collapsible defaultOpen={source.status === 'error' || Number(source.last_result.unsupported ?? 0) > 0} className="space-y-2"><CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-1 text-left text-sm font-medium hover:bg-muted/50">{t('result')}<ChevronDown className="size-4 transition-transform duration-200 [[data-panel-open]_&]:rotate-180" /></CollapsibleTrigger><CollapsibleContent className="space-y-3 rounded-md border bg-muted/40 p-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm"><span>{t('resultScanned')}: {Number(source.last_result.scanned ?? 0)}</span><span>{t('resultIndexed')}: {Number(source.last_result.indexed ?? 0)}</span><span>{t('resultUnchanged')}: {Number(source.last_result.unchanged ?? 0)}</span><span>{t('resultFailed')}: {Number(source.last_result.failed ?? 0)}</span><span>{t('resultUnsupported')}: {Number(source.last_result.unsupported ?? 0)}</span><span>{t('resultRemoved')}: {Number(source.last_result.removed ?? 0)}</span></div>
        {Array.isArray(source.last_result.errors) && source.last_result.errors.length > 0 && <div className="space-y-2"><h3 className="text-sm font-medium">{t('resultErrors')}</h3><ul className="space-y-2">{source.last_result.errors.map((item, index) => {
          if (!item || typeof item !== 'object') return null
          const detail = item as { error?: unknown; node_token?: unknown; node_title?: unknown; type?: unknown }
          return <li key={`${String(detail.node_token ?? 'error')}-${index}`} className="break-words rounded-md border border-destructive/30 bg-background p-2 text-sm"><p className="text-destructive">{typeof detail.error === 'string' ? detail.error : t('resultUnknownError')}</p>{typeof detail.node_token === 'string' && <p className="mt-1 text-xs text-muted-foreground">{t('resultNode')}: <a className="text-primary underline" href={`https://feishu.cn/wiki/${encodeURIComponent(detail.node_token)}`} target="_blank" rel="noopener noreferrer">{typeof detail.node_title === 'string' && detail.node_title ? detail.node_title : detail.node_token} ↗</a></p>}{typeof detail.type === 'string' && <p className="text-xs text-muted-foreground">{t('resultType')}: {detail.type}</p>}</li>
        })}</ul></div>}
        {Array.isArray(source.last_result.skipped) && source.last_result.skipped.length > 0 && <div className="space-y-2"><h3 className="text-sm font-medium">{t('resultSkipped')}</h3><ul className="space-y-2">{source.last_result.skipped.map((item, index) => {
          if (!item || typeof item !== 'object') return null
          const skipped = item as { reason?: unknown; node_token?: unknown; node_title?: unknown; type?: unknown }
          return <li key={`${String(skipped.node_token ?? 'skipped')}-${index}`} className="break-words rounded-md border bg-background p-2 text-sm"><p className="text-muted-foreground">{typeof skipped.reason === 'string' ? skipped.reason : t('resultUnsupported')}</p>{typeof skipped.node_token === 'string' && <p className="mt-1 text-xs">{t('resultNode')}: <a className="text-primary underline" href={`https://feishu.cn/wiki/${encodeURIComponent(skipped.node_token)}`} target="_blank" rel="noopener noreferrer">{typeof skipped.node_title === 'string' && skipped.node_title ? skipped.node_title : skipped.node_token} ↗</a></p>}{typeof skipped.type === 'string' && <p className="text-xs text-muted-foreground">{t('resultType')}: {skipped.type}</p>}</li>
        })}</ul></div>}
        {Array.isArray(source.last_result.warnings) && source.last_result.warnings.length > 0 && <Collapsible className="space-y-2"><CollapsibleTrigger className="flex w-full items-center justify-between text-left text-sm font-medium hover:text-foreground/80">{t('resultWarnings')} ({source.last_result.warnings.length})<ChevronDown className="size-4 transition-transform duration-200 [[data-panel-open]_&]:rotate-180" /></CollapsibleTrigger><CollapsibleContent className="pt-2"><ul className="space-y-2">{source.last_result.warnings.map((item, index) => {
          if (!item || typeof item !== 'object') return null
          const warning = item as { blocks?: unknown; node_token?: unknown; node_title?: unknown }
          return <li key={`${String(warning.node_token ?? 'warning')}-${index}`} className="break-words rounded border bg-background p-2 text-xs"><p>{t('resultNode')}: {typeof warning.node_token === 'string' ? <a className="text-primary underline" href={`https://feishu.cn/wiki/${encodeURIComponent(warning.node_token)}`} target="_blank" rel="noopener noreferrer">{typeof warning.node_title === 'string' && warning.node_title ? warning.node_title : warning.node_token} ↗</a> : '—'}</p>{Array.isArray(warning.blocks) && warning.blocks.map((block, blockIndex) => <p key={blockIndex}>{String(block)}</p>)}</li>
        })}</ul></CollapsibleContent></Collapsible>}
      </CollapsibleContent></Collapsible>}
      <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-2"><Button variant="outline" size="sm" disabled={busy} onClick={() => void edit(source)}>{t('edit')}</Button><Button variant="outline" size="sm" disabled={busy || source.status === 'queued' || source.status === 'running'} onClick={() => void act(() => feishuKnowledgeApi.sync(source.id))}>{t('sync')}</Button><Button variant="destructive" size="sm" disabled={busy || source.status === 'queued' || source.status === 'running'} onClick={() => setDeleting(source)}>{t('delete')}</Button></div>
    </CardContent></Card>)}
    <Dialog open={open} onOpenChange={value => { if (!busy) setOpen(value) }}><DialogContent><DialogHeader><DialogTitle>{editing ? t('edit') : t('create')}</DialogTitle></DialogHeader>{busy && !editing ? <div role="status" className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />{t('loadingOptions')}</div> : <form className="space-y-4" onSubmit={event => { event.preventDefault(); void act(async () => { const data = { name: name.trim(), interval_minutes: interval, is_enabled: enabled }; if (editing) await feishuKnowledgeApi.update(editing.id, data); else await feishuKnowledgeApi.create({ ...data, knowledge_base_id: target, space_id: space }); setOpen(false) }) }}>
      <div className="space-y-2"><Label htmlFor="source-name">{t('name')}</Label><Input id="source-name" required maxLength={100} value={name} onChange={event => setName(event.target.value)} /></div>
      {!editing && <><div className="space-y-2"><Label htmlFor="source-space-trigger">{t('space')}</Label><Select value={space} onValueChange={value => setSpace(value ?? '')} required><SelectTrigger id="source-space-trigger" className="w-full"><SelectValue placeholder={t('selectSpace')}>{spaces.find(item => item.space_id === space)?.name ?? ''}</SelectValue></SelectTrigger><SelectContent>{spaces.map(item => <SelectItem key={item.space_id} value={item.space_id}>{item.name}</SelectItem>)}</SelectContent></Select></div><div className="space-y-2"><Label htmlFor="source-target-trigger">{t('target')}</Label><Select value={target} onValueChange={value => setTarget(value ?? '')} required><SelectTrigger id="source-target-trigger" className="w-full"><SelectValue placeholder={t('selectTarget')}>{targets.find(item => item.id === target) ? getKnowledgeTargetLabel(targets.find(item => item.id === target)!) : ''}</SelectValue></SelectTrigger><SelectContent>{targets.map(item => <SelectItem key={item.id} value={item.id}>{getKnowledgeTargetLabel(item)}</SelectItem>)}</SelectContent></Select></div>{(spaces.length === 0 || targets.length === 0) && <p role="alert" className="text-sm text-muted-foreground">{t('noOptions')}</p>}</>}
      <div className="space-y-2"><Label htmlFor="source-interval">{t('interval')}</Label><Input id="source-interval" type="number" required min={1} max={43200} step={1} value={interval} onChange={event => setIntervalMinutes(Number(event.target.value))} /></div>
      <Label className="flex items-center gap-2"><Switch checked={enabled} onCheckedChange={setEnabled} />{t('enabled')}</Label>
      {actionError && <Alert variant="destructive"><AlertDescription className="whitespace-pre-wrap">{actionError}</AlertDescription></Alert>}
      <DialogFooter><Button type="submit" disabled={busy || !name.trim() || !Number.isInteger(interval) || interval < 1 || interval > 43200 || (!editing && (!space || !target))}>{t('save')}</Button></DialogFooter>
    </form>}</DialogContent></Dialog>
    <AlertDialog open={deleting !== null} onOpenChange={value => { if (!value && !busy) setDeleting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t('delete')}</AlertDialogTitle><AlertDialogDescription>{t('deleteConfirm', { name: deleting?.name ?? '' })}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>{t('cancel')}</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy} onClick={event => { event.preventDefault(); if (deleting) void act(async () => { await feishuKnowledgeApi.delete(deleting.id); setDeleting(null) }) }}>{t('delete')}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>
}
