'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Pencil, Plus, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  ToolApprovalPolicyEditor,
  createDefaultApprovalPolicy,
  normalizeToolApprovalPolicy,
} from '@/components/tools/tool-policy-editor'
import { useCanPerform } from '@/components/permission-guard'
import { usePermissions } from '@/hooks/use-permissions'
import { useTeam } from '@/contexts/team-context'
import {
  toolApprovalPoliciesApi,
  type ToolApprovalPolicyCreateInput,
  type ToolApprovalPolicyEntrypointKind,
  type ToolApprovalPolicyRow,
  type ToolApprovalPolicyScope,
} from '@/lib/api'
import type { ToolApprovalPolicy } from '@/lib/api/tools'

interface PolicyDraft {
  row: ToolApprovalPolicyRow | null
  scope: ToolApprovalPolicyScope
  teamId: string | null
  entrypointKind: ToolApprovalPolicyEntrypointKind
  entrypointId: string
  toolId: string
  policy: ToolApprovalPolicy
}

const ENTRYPOINT_KINDS: ToolApprovalPolicyEntrypointKind[] = ['agent', 'workflow', 'api_key']

function policyDecisionKey(decision: ToolApprovalPolicy['default_decision']): string {
  if (decision === 'allow') return 'allow'
  if (decision === 'deny') return 'deny'
  return 'requireApproval'
}

function shortId(value: string | null): string {
  if (!value) return '—'
  return value.length > 12 ? `${value.slice(0, 8)}…` : value
}

/**
 * Authorized editor for persisted mandatory approval layers.
 *
 * The listing endpoint returns `can_edit` per row; only those rows show edit
 * and delete controls. Authorization is still enforced by the server, and
 * layers are never merged in this component.
 */
export interface ApprovalPoliciesPanelProps {
  refreshKey?: number
}

export function ApprovalPoliciesPanel({ refreshKey = 0 }: ApprovalPoliciesPanelProps) {
  const t = useTranslations('approvals.policy')
  const tToolsPolicy = useTranslations('tools.policy')
  const { currentTeam } = useTeam()
  const { user } = usePermissions()
  const { canPerform } = useCanPerform()
  const isSuperuser = Boolean(user?.is_superuser)
  const canManageTools = canPerform('tool:update')
  // Site writes are allowed for a superuser or a global settings administrator.
  const canManageSite = canPerform('admin:settings:update')
  const isTeamAdmin = Boolean(
    currentTeam && (currentTeam.role === 'owner' || currentTeam.role === 'admin')
  )
  const canManageTeam = Boolean(currentTeam && (isSuperuser || isTeamAdmin) && canManageTools)

  const [rows, setRows] = React.useState<ToolApprovalPolicyRow[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [draft, setDraft] = React.useState<PolicyDraft | null>(null)
  const [saving, setSaving] = React.useState(false)
  const [deletingRow, setDeletingRow] = React.useState<ToolApprovalPolicyRow | null>(null)
  const [deleting, setDeleting] = React.useState(false)
  const tRef = React.useRef(t)
  tRef.current = t

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(
        await toolApprovalPoliciesApi.list({
          team_id: currentTeam?.id,
        })
      )
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tRef.current('loadFailed'))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [currentTeam?.id])

  React.useEffect(() => {
    void load()
  }, [load, refreshKey])

  // The backend can persist a generic row (`tool_id: null`) and a
  // tool-specific row for the same scope. Both are mandatory layers; render
  // them independently and never merge or replace one with the other.
  const siteRows = rows.filter((row) => row.scope === 'site')
  const teamRows = currentTeam
    ? rows.filter((row) => row.scope === 'team' && row.team_id === currentTeam.id)
    : []
  const entrypointRows = rows.filter(
    (row) => row.scope === 'entrypoint' && (!currentTeam || row.team_id === currentTeam.id)
  )
  const hasGenericSitePolicy = siteRows.some((row) => row.tool_id === null)
  const hasGenericTeamPolicy = teamRows.some((row) => row.tool_id === null)

  const openCreate = (scope: ToolApprovalPolicyScope) => {
    setDraft({
      row: null,
      scope,
      teamId: scope === 'site' ? null : currentTeam?.id ?? null,
      entrypointKind: 'agent',
      entrypointId: '',
      toolId: '',
      policy: createDefaultApprovalPolicy(),
    })
  }

  const openEdit = (row: ToolApprovalPolicyRow) => {
    setDraft({
      row,
      scope: row.scope,
      teamId: row.team_id,
      entrypointKind: row.entrypoint_kind ?? 'agent',
      entrypointId: row.entrypoint_id ?? '',
      toolId: row.tool_id ?? '',
      policy: row.policy,
    })
  }

  const save = async () => {
    if (!draft || saving) return
    if (draft.scope !== 'site' && !draft.teamId) {
      toast.error(t('scopeRequired'))
      return
    }
    if (draft.scope === 'entrypoint' && !draft.entrypointId.trim()) {
      toast.error(t('entrypointIdRequired'))
      return
    }

    const policy = normalizeToolApprovalPolicy(draft.policy)
    setSaving(true)
    try {
      if (draft.row) {
        await toolApprovalPoliciesApi.update(draft.row.id, {
          policy,
          expected_version: draft.row.version,
        })
      } else {
        const payload: ToolApprovalPolicyCreateInput = {
          scope: draft.scope,
          policy,
        }
        if (draft.scope !== 'site') {
          payload.team_id = draft.teamId
        }
        if (draft.scope === 'entrypoint') {
          payload.entrypoint_kind = draft.entrypointKind
          payload.entrypoint_id = draft.entrypointId.trim()
        }
        payload.tool_id = draft.toolId.trim() || null
        await toolApprovalPoliciesApi.create(payload)
      }
      toast.success(t('saved'))
      setDraft(null)
      await load()
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : ''
      if (message.includes('tool_approval_policy_version_conflict')) {
        toast.error(t('versionConflict'))
      } else {
        toast.error(message || t('saveFailed'))
      }
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deletingRow || deleting) return
    setDeleting(true)
    try {
      await toolApprovalPoliciesApi.remove(deletingRow.id)
      toast.success(t('deleted'))
      setDeletingRow(null)
      await load()
    } catch (reason) {
      toast.error(reason instanceof Error && reason.message ? reason.message : t('deleteFailed'))
    } finally {
      setDeleting(false)
    }
  }

  const decisionLabel = (policy: ToolApprovalPolicy) =>
    tToolsPolicy(`approval.${policyDecisionKey(policy.default_decision)}`)

  const renderRow = (row: ToolApprovalPolicyRow) => (
    <div key={row.id} className="space-y-2 rounded-md border p-3" data-testid={`policy-row-${row.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{t(`scopes.${row.scope}`)}</Badge>
          <span className="text-sm font-medium">{decisionLabel(row.policy)}</span>
          <span className="text-xs text-muted-foreground">{t('version', { version: row.version })}</span>
          {!row.can_edit && <Badge variant="secondary">{t('readOnly')}</Badge>}
        </div>
        {row.can_edit && (
          <div className="flex gap-1.5">
            <Button size="sm" variant="outline" onClick={() => openEdit(row)}>
              <Pencil className="mr-1 h-3.5 w-3.5" />
              {t('edit')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDeletingRow(row)}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              {t('delete')}
            </Button>
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {row.tool_id ? t('toolSpecific', { toolId: shortId(row.tool_id) }) : t('anyTool')}
        {row.scope === 'entrypoint' && row.entrypoint_kind && (
          <>
            {' · '}
            {t('entrypoint', {
              kind: t(`entrypointKinds.${row.entrypoint_kind}`),
              id: shortId(row.entrypoint_id),
            })}
          </>
        )}
      </p>
      {Object.keys(row.policy.operation_overrides ?? {}).length > 0 && (
        <p className="text-[11px] text-muted-foreground">{tToolsPolicy('operations.title')}</p>
      )}
    </div>
  )

  if (loading && rows.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">{t('loading')}</span>
      </div>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-10">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('retry')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4" data-testid="approval-policies-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t('listTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('listDescription')}</p>
          <p className="mt-1 text-xs text-muted-foreground">{t('serverEnforced')}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {t('refresh')}
        </Button>
      </div>

      <Card>
        <CardContent className="space-y-2 px-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="flex items-center gap-2 font-medium">
                <ShieldCheck className="h-4 w-4" />
                {t('siteTitle')}
              </h3>
              <p className="text-xs text-muted-foreground">{t('siteDescription')}</p>
            </div>
            {!hasGenericSitePolicy && canManageSite && (
              <Button size="sm" onClick={() => openCreate('site')}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t('addSite')}
              </Button>
            )}
          </div>
          {siteRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('noSite')}</p>
          ) : (
            <div className="space-y-2">{siteRows.map(renderRow)}</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 px-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-medium">{t('teamTitle')}</h3>
              <p className="text-xs text-muted-foreground">
                {currentTeam
                  ? t('teamDescription', { team: currentTeam.name })
                  : t('scopeRequired')}
              </p>
            </div>
            {!hasGenericTeamPolicy && currentTeam && canManageTeam && (
              <Button size="sm" onClick={() => openCreate('team')}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t('addTeam')}
              </Button>
            )}
          </div>
          {teamRows.length === 0 ? (
            currentTeam ? <p className="text-xs text-muted-foreground">{t('noTeam')}</p> : null
          ) : (
            <div className="space-y-2">{teamRows.map(renderRow)}</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-2 px-4">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-medium">{t('entrypointTitle')}</h3>
              <p className="text-xs text-muted-foreground">{t('entrypointDescription')}</p>
            </div>
            {currentTeam && canManageTeam && (
              <Button size="sm" onClick={() => openCreate('entrypoint')}>
                <Plus className="mr-1 h-3.5 w-3.5" />
                {t('addEntrypoint')}
              </Button>
            )}
          </div>
          {entrypointRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t('noEntrypoint')}</p>
          ) : (
            <div className="space-y-2">{entrypointRows.map(renderRow)}</div>
          )}
        </CardContent>
      </Card>

      <Dialog open={draft !== null} onOpenChange={(open) => { if (!open && !saving) setDraft(null) }}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{draft?.row ? t('editorTitleEdit') : t('editorTitleCreate')}</DialogTitle>
            <DialogDescription>{t('editorDescription')}</DialogDescription>
          </DialogHeader>

          {draft && draft.scope === 'entrypoint' && !draft.row && (
            <div className="space-y-2">
              <div className="space-y-1">
                <Label htmlFor="policy-entrypoint-kind">{t('entrypointKind')}</Label>
                <Select
                  value={draft.entrypointKind}
                  onValueChange={(value) =>
                    setDraft((current) => current
                      ? { ...current, entrypointKind: value as ToolApprovalPolicyEntrypointKind }
                      : current)
                  }
                >
                  <SelectTrigger id="policy-entrypoint-kind">
                    <SelectValue>{t(`entrypointKinds.${draft.entrypointKind}`)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {ENTRYPOINT_KINDS.map((kind) => (
                      <SelectItem key={kind} value={kind}>
                        {t(`entrypointKinds.${kind}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="policy-entrypoint-id">{t('entrypointId')}</Label>
                <Input
                  id="policy-entrypoint-id"
                  value={draft.entrypointId}
                  placeholder={t('entrypointIdPlaceholder')}
                  onChange={(event) =>
                    setDraft((current) => current
                      ? { ...current, entrypointId: event.target.value }
                      : current)
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="policy-tool-id">{t('toolId')}</Label>
                <Input
                  id="policy-tool-id"
                  value={draft.toolId}
                  placeholder={t('toolIdPlaceholder')}
                  onChange={(event) =>
                    setDraft((current) => current
                      ? { ...current, toolId: event.target.value }
                      : current)
                  }
                />
              </div>
            </div>
          )}

          {draft && (
            <ToolApprovalPolicyEditor
              approvalPolicy={draft.policy}
              onApprovalPolicyChange={(policy) =>
                setDraft((current) => current ? { ...current, policy } : current)
              }
            />
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDraft(null)} disabled={saving}>
              {t('cancel')}
            </Button>
            <Button onClick={() => void save()} disabled={saving}>
              {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {saving ? t('saving') : t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deletingRow !== null}
        onOpenChange={(open) => { if (!open && !deleting) setDeletingRow(null) }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={deleting} onClick={() => void confirmDelete()}>
              {deleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {deleting ? t('deleting') : t('confirmDelete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
