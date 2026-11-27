'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2, Lock, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { apiKeysApi, type APIKey } from '@/lib/api/api-keys'
import { teamsApi, type TeamMember } from '@/lib/api/teams'
import {
  workflowsApi,
  type WorkflowAccessDecision,
  type WorkflowAccessGate,
  type WorkflowAccessOperation,
  type WorkflowAccessOperationPolicy,
  type WorkflowAccessPolicyDocument,
} from '@/lib/api/workflows'

const OPERATIONS: WorkflowAccessOperation[] = ['view', 'run', 'edit', 'publish', 'delete']
const ROLES = ['owner', 'admin', 'member', 'viewer'] as const

type Decision = WorkflowAccessOperationPolicy['decision'] | 'inherit'

interface Audience {
  roles: string[]
  userIds: string[]
  apiKeyIds: string[]
}

const EMPTY_AUDIENCE: Audience = { roles: [], userIds: [], apiKeyIds: [] }

/** Split the gates of one operation into the three audiences the editor edits. */
export function splitGates(policy?: WorkflowAccessOperationPolicy): Audience {
  if (!policy?.gates?.length) return { ...EMPTY_AUDIENCE }
  const audience: Audience = { roles: [], userIds: [], apiKeyIds: [] }
  for (const gate of policy.gates) {
    if (gate.kind === 'team_role') audience.roles.push(...(gate.roles ?? []))
    if (gate.kind === 'user') audience.userIds.push(...(gate.user_ids ?? []))
    if (gate.kind === 'api_key') audience.apiKeyIds.push(...(gate.api_key_ids ?? []))
  }
  return audience
}

/** Rebuild a policy document from the editor state; empty audience drops the gates. */
export function buildPolicyDocument(
  decisions: Record<WorkflowAccessOperation, Decision>,
  audiences: Record<WorkflowAccessOperation, Audience>,
): WorkflowAccessPolicyDocument {
  const operations: WorkflowAccessPolicyDocument['operations'] = {}
  for (const operation of OPERATIONS) {
    const decision = decisions[operation]
    if (decision === 'inherit') continue
    const audience = audiences[operation] ?? EMPTY_AUDIENCE
    const gates: WorkflowAccessGate[] = []
    if (decision === 'allow') {
      if (audience.roles.length) gates.push({ kind: 'team_role', roles: audience.roles })
      if (audience.userIds.length) gates.push({ kind: 'user', user_ids: audience.userIds })
      if (audience.apiKeyIds.length) gates.push({ kind: 'api_key', api_key_ids: audience.apiKeyIds })
    }
    operations[operation] = gates.length
      ? { decision, gates }
      : { decision }
  }
  return { operations }
}

function effectiveTone(decision: WorkflowAccessDecision): string {
  if (decision.source === 'inherit') return 'text-muted-foreground'
  return decision.allowed ? 'text-emerald-600' : 'text-destructive'
}

export interface AccessPolicyEditorProps {
  workflowId: string
  teamId: string | null
  readOnly?: boolean
}

export function AccessPolicyEditor({ workflowId, teamId, readOnly = false }: AccessPolicyEditorProps) {
  const t = useTranslations('workflow.accessPolicy')
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [decisions, setDecisions] = React.useState<Record<WorkflowAccessOperation, Decision>>(
    { view: 'inherit', run: 'inherit', edit: 'inherit', publish: 'inherit', delete: 'inherit' },
  )
  const [audiences, setAudiences] = React.useState<Record<WorkflowAccessOperation, Audience>>({
    view: { ...EMPTY_AUDIENCE },
    run: { ...EMPTY_AUDIENCE },
    edit: { ...EMPTY_AUDIENCE },
    publish: { ...EMPTY_AUDIENCE },
    delete: { ...EMPTY_AUDIENCE },
  })
  const [effective, setEffective] = React.useState<Record<WorkflowAccessOperation, WorkflowAccessDecision> | null>(null)
  const [members, setMembers] = React.useState<TeamMember[]>([])
  const [keys, setKeys] = React.useState<APIKey[]>([])

  const applyResponse = React.useCallback(
    (policy: WorkflowAccessPolicyDocument, effectiveMap: Record<WorkflowAccessOperation, WorkflowAccessDecision>) => {
      const nextDecisions = { ...decisions }
      const nextAudiences = { ...audiences }
      for (const operation of OPERATIONS) {
        const entry = policy.operations?.[operation]
        nextDecisions[operation] = entry?.decision ?? 'inherit'
        nextAudiences[operation] = splitGates(entry)
      }
      setDecisions(nextDecisions)
      setAudiences(nextAudiences)
      setEffective(effectiveMap)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  React.useEffect(() => {
    let live = true
    workflowsApi
      .getWorkflowAccessPolicy(workflowId)
      .then((result) => {
        if (!live) return
        applyResponse(result.policy, result.effective)
      })
      // A refusal here already has a page-level error state; no toast storm.
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [workflowId, applyResponse])

  React.useEffect(() => {
    let live = true
    if (teamId) {
      teamsApi
        .getTeam(teamId)
        .then((team) => { if (live) setMembers(team.members ?? []) })
        .catch(() => { if (live) setMembers([]) })
    }
    apiKeysApi
      .getAPIKeys({ pageSize: 100, silent: true })
      .then((page) => { if (live) setKeys(page.items) })
      .catch(() => { if (live) setKeys([]) })
    return () => { live = false }
  }, [teamId])

  const toggle = (operation: WorkflowAccessOperation, value: string, kind: keyof Audience) => {
    setAudiences((current) => {
      const audience = current[operation]
      const values = audience[kind]
      return {
        ...current,
        [operation]: {
          ...audience,
          [kind]: values.includes(value) ? values.filter((item) => item !== value) : [...values, value],
        },
      }
    })
  }

  const save = async () => {
    setSaving(true)
    try {
      const result = await workflowsApi.updateWorkflowAccessPolicy(
        workflowId,
        buildPolicyDocument(decisions, audiences),
      )
      applyResponse(result.policy, result.effective)
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    setDecisions({ view: 'inherit', run: 'inherit', edit: 'inherit', publish: 'inherit', delete: 'inherit' })
    setAudiences({
      view: { ...EMPTY_AUDIENCE },
      run: { ...EMPTY_AUDIENCE },
      edit: { ...EMPTY_AUDIENCE },
      publish: { ...EMPTY_AUDIENCE },
      delete: { ...EMPTY_AUDIENCE },
    })
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('loading')}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-4">
        <ShieldCheck className="mt-0.5 h-5 w-5 text-primary" />
        <div className="space-y-1 text-sm">
          <p className="font-medium">{t('introTitle')}</p>
          <p className="text-muted-foreground">{t('introBody')}</p>
        </div>
      </div>

      {OPERATIONS.map((operation) => {
        const decision = decisions[operation]
        const audience = audiences[operation]
        const current = effective?.[operation]
        return (
          <section key={operation} className="space-y-3 rounded-lg border p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium">{t(`operations.${operation}`)}</h3>
                {current && (
                  <span className={`text-xs ${effectiveTone(current)}`}>
                    {current.source === 'inherit'
                      ? t('effectiveInherit')
                      : current.allowed
                        ? t('effectiveAllowed')
                        : t('effectiveDenied')}
                  </span>
                )}
              </div>
              <Select
                value={decision}
                disabled={readOnly}
                onValueChange={(value) =>
                  setDecisions((state) => ({
                    ...state,
                    [operation]: (value ?? 'inherit') as Decision,
                  }))
                }
              >
                <SelectTrigger className="w-40" aria-label={t(`operations.${operation}`)}>
                  <SelectValue>{t(`decisions.${decision}`)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit">{t('decisions.inherit')}</SelectItem>
                  <SelectItem value="allow">{t('decisions.allow')}</SelectItem>
                  <SelectItem value="deny">{t('decisions.deny')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {decision === 'allow' && (
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">{t('rolesLabel')}</Label>
                  <div className="flex flex-wrap gap-2">
                    {ROLES.map((role) => (
                      <button
                        key={role}
                        type="button"
                        disabled={readOnly}
                        onClick={() => toggle(operation, role, 'roles')}
                        className="disabled:opacity-50"
                      >
                        <Badge variant={audience.roles.includes(role) ? 'default' : 'outline'}>
                          {t(`roles.${role}`)}
                        </Badge>
                      </button>
                    ))}
                  </div>
                </div>

                {members.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">{t('usersLabel')}</Label>
                    <div className="flex flex-wrap gap-2">
                      {members.map((member) => (
                        <button
                          key={member.id}
                          type="button"
                          disabled={readOnly}
                          onClick={() => toggle(operation, member.id, 'userIds')}
                          className="disabled:opacity-50"
                        >
                          <Badge variant={audience.userIds.includes(member.id) ? 'default' : 'outline'}>
                            {member.username}
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {keys.length > 0 && (
                  <div className="space-y-2">
                    <Label className="text-xs text-muted-foreground">{t('keysLabel')}</Label>
                    <div className="flex flex-wrap gap-2">
                      {keys.map((key) => (
                        <button
                          key={key.id}
                          type="button"
                          disabled={readOnly}
                          onClick={() => toggle(operation, key.id, 'apiKeyIds')}
                          className="disabled:opacity-50"
                        >
                          <Badge variant={audience.apiKeyIds.includes(key.id) ? 'default' : 'outline'}>
                            {key.name}
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <p className="text-xs text-muted-foreground">{t('gatesHint')}</p>
              </div>
            )}
          </section>
        )
      })}

      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={save} disabled={saving}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
            {t('save')}
          </Button>
          <Button variant="outline" onClick={reset} disabled={saving}>
            <RotateCcw className="mr-2 h-4 w-4" />
            {t('reset')}
          </Button>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock className="h-3 w-3" />
            {t('saveHint')}
          </span>
        </div>
      )}
    </div>
  )
}
