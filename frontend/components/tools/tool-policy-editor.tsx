'use client'

import { useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Plus, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ToolApprovalGate,
  ToolApprovalPolicy,
  ToolConnectionField,
  ToolDetail,
  ToolIdentityPolicy,
} from '@/lib/api/tools'

export const TOOL_IDENTITY_POLICIES: ToolIdentityPolicy[] = [
  'none',
  'team_only',
  'personal_only',
  'selectable',
]

export const TOOL_APPROVAL_DECISIONS: ToolApprovalPolicy['default_decision'][] = [
  'allow',
  'deny',
  'require_approval',
]

/**
 * Gate kinds that predate caller-only confirmation. They remain in the read
 * model so legacy saved policies can be surfaced, but the backend rejects any
 * write that still contains them: they must never become an allow or a caller
 * gate without an explicit administrator decision.
 */
export const LEGACY_APPROVAL_GATE_KINDS = ['user', 'team_role'] as const
export type LegacyApprovalGateKind = (typeof LEGACY_APPROVAL_GATE_KINDS)[number]

const CONNECTION_FIELD_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/

function createCallerGate(): ToolApprovalGate {
  return {
    kind: 'caller',
    user_ids: [],
    roles: [],
    allow_self_approval: false,
  }
}

export function createDefaultApprovalPolicy(): ToolApprovalPolicy {
  return {
    default_decision: 'allow',
    gates: [],
    operation_overrides: {},
  }
}

export function getToolIdentityPolicy(tool?: ToolDetail | null): ToolIdentityPolicy {
  return tool?.identity_policy ?? 'none'
}

export function getToolConnectionFields(tool?: ToolDetail | null): ToolConnectionField[] {
  return (tool?.connection_fields ?? []).map((field) => ({
    ...field,
    name: field.name,
    label: field.label,
    required: field.required ?? true,
    secret: field.secret ?? true,
  }))
}

export function getToolApprovalPolicy(tool?: ToolDetail | null): ToolApprovalPolicy {
  const policy = tool?.approval_policy
  if (!policy) return createDefaultApprovalPolicy()
  return {
    default_decision: policy.default_decision ?? 'allow',
    gates: (policy.gates ?? []).map((gate) => ({
      kind: gate.kind,
      user_ids: [...(gate.user_ids ?? [])],
      roles: [...(gate.roles ?? [])],
      allow_self_approval: gate.allow_self_approval ?? false,
    })),
    operation_overrides: { ...(policy.operation_overrides ?? {}) },
  }
}

function isLegacyGateKind(kind: string): kind is LegacyApprovalGateKind {
  return (LEGACY_APPROVAL_GATE_KINDS as readonly string[]).includes(kind)
}

export interface LegacyApprovalAudience {
  /** Empty string for the tool-level policy, otherwise the exact operation name. */
  operation: string
  kinds: LegacyApprovalGateKind[]
}

/**
 * Collect every saved ``user``/``team_role`` gate, including nested
 * per-operation overrides. Returned paths are used only to explain the
 * remediation an administrator must take; nothing is rewritten here.
 */
export function findLegacyApprovalAudiences(
  policy: ToolApprovalPolicy,
  operation = ''
): LegacyApprovalAudience[] {
  const audiences: LegacyApprovalAudience[] = []
  const kinds = [
    ...new Set(
      (policy.gates ?? [])
        .map((gate) => gate.kind)
        .filter((kind): kind is LegacyApprovalGateKind => isLegacyGateKind(kind))
    ),
  ]
  if (kinds.length > 0) audiences.push({ operation, kinds })
  for (const [name, override] of Object.entries(policy.operation_overrides ?? {})) {
    audiences.push(...findLegacyApprovalAudiences(override, name))
  }
  return audiences
}

export function hasLegacyApprovalAudiences(policy: ToolApprovalPolicy): boolean {
  return findLegacyApprovalAudiences(policy).length > 0
}

/**
 * Explicitly replace every unsupported audience with caller confirmation.
 *
 * Call this only from a deliberate administrator action. Legacy audiences are
 * never translated automatically because that would silently change who can
 * approve an operation.
 */
export function resetLegacyApprovalAudiences(policy: ToolApprovalPolicy): ToolApprovalPolicy {
  const operationOverrides: Record<string, ToolApprovalPolicy> = {}
  for (const [name, override] of Object.entries(policy.operation_overrides ?? {})) {
    operationOverrides[name] = resetLegacyApprovalAudiences(override)
  }
  const decision = TOOL_APPROVAL_DECISIONS.includes(policy.default_decision)
    ? policy.default_decision
    : 'require_approval'
  return {
    default_decision: decision,
    gates: decision === 'require_approval' ? [createCallerGate()] : [],
    operation_overrides: operationOverrides,
  }
}

export function normalizeConnectionFields(fields: ToolConnectionField[]): ToolConnectionField[] {
  const normalized: ToolConnectionField[] = []
  const seen = new Set<string>()
  for (const field of fields) {
    const name = field.name.trim()
    const label = field.label.trim()
    if (!name && !label) continue
    if (!CONNECTION_FIELD_NAME_PATTERN.test(name) || !label || seen.has(name)) continue
    seen.add(name)
    normalized.push({
      ...field,
      name,
      label,
      required: field.required,
      secret: field.secret,
    })
  }
  return normalized
}

function normalizeApprovalGate(gate: ToolApprovalGate): ToolApprovalGate {
  if (gate.kind === 'caller') return createCallerGate()
  if (gate.kind === 'user') {
    return {
      kind: 'user',
      user_ids: [...new Set((gate.user_ids ?? []).map((id) => id.trim()).filter(Boolean))],
      roles: [],
      allow_self_approval: gate.allow_self_approval ?? false,
    }
  }
  if (gate.kind === 'team_role') {
    return {
      kind: 'team_role',
      user_ids: [],
      roles: [...new Set((gate.roles ?? []).map((role) => role.trim().toLowerCase()).filter(Boolean))],
      allow_self_approval: gate.allow_self_approval ?? false,
    }
  }
  // Unknown kinds are preserved rather than guessed at.
  return { ...gate }
}

/**
 * Produce a policy the backend accepts.
 *
 * ``allow``/``deny`` drop caller confirmation gates, and
 * ``require_approval`` keeps exactly one caller gate. Legacy ``user`` and
 * ``team_role`` gates are preserved verbatim, including inside operation
 * overrides, so the backend rejects the write with an actionable configuration
 * error. They are never translated into caller confirmation or dropped into a
 * silent allow; remediation is an explicit administrator action.
 */
export function normalizeToolApprovalPolicy(policy: ToolApprovalPolicy): ToolApprovalPolicy {
  const decision = TOOL_APPROVAL_DECISIONS.includes(policy.default_decision)
    ? policy.default_decision
    : 'require_approval'

  const normalizedGates = (policy.gates ?? []).map(normalizeApprovalGate)
  const hasLegacyGates = normalizedGates.some((gate) => gate.kind !== 'caller')
  const gates: ToolApprovalGate[] = hasLegacyGates
    ? normalizedGates
    : decision !== 'require_approval'
      ? []
      : [normalizedGates.find((gate) => gate.kind === 'caller') ?? createCallerGate()]

  const operationOverrides: Record<string, ToolApprovalPolicy> = {}
  for (const [rawName, override] of Object.entries(policy.operation_overrides ?? {})) {
    const operation = rawName.trim()
    if (!operation || operation === '*') continue
    operationOverrides[operation] = normalizeToolApprovalPolicy(override)
  }

  return {
    default_decision: decision,
    gates,
    operation_overrides: operationOverrides,
  }
}

interface ToolPolicyEditorProps {
  identityPolicy: ToolIdentityPolicy
  onIdentityPolicyChange: (policy: ToolIdentityPolicy) => void
  connectionFields: ToolConnectionField[]
  onConnectionFieldsChange: (fields: ToolConnectionField[]) => void
  approvalPolicy: ToolApprovalPolicy
  onApprovalPolicyChange: (policy: ToolApprovalPolicy) => void
  /**
   * Exact internal operation names shown as per-operation override rows.
   * Only MCP tools pass this; other tools keep the configured overrides.
   */
  operationNames?: string[]
  operationTools?: Array<{ name: string; description?: string }>
  toolsLoaded?: boolean
  showIdentityAndConnections?: boolean
}

interface ToolApprovalPolicyEditorProps {
  approvalPolicy: ToolApprovalPolicy
  onApprovalPolicyChange: (policy: ToolApprovalPolicy) => void
  operationNames?: string[]
}

/** Approval-only surface for policy administration pages. */
export function ToolApprovalPolicyEditor({
  approvalPolicy,
  onApprovalPolicyChange,
  operationNames,
}: ToolApprovalPolicyEditorProps) {
  return (
    <ToolPolicyEditor
      identityPolicy="none"
      onIdentityPolicyChange={() => {}}
      connectionFields={[]}
      onConnectionFieldsChange={() => {}}
      approvalPolicy={approvalPolicy}
      onApprovalPolicyChange={onApprovalPolicyChange}
      operationNames={operationNames}
      showIdentityAndConnections={false}
    />
  )
}

export function ToolPolicyEditor({
  identityPolicy,
  onIdentityPolicyChange,
  connectionFields,
  onConnectionFieldsChange,
  approvalPolicy,
  onApprovalPolicyChange,
  operationNames,
  operationTools,
  toolsLoaded = false,
  showIdentityAndConnections = true,
}: ToolPolicyEditorProps) {
  const t = useTranslations('tools.policy')
  const [newOperation, setNewOperation] = useState('')
  const [operationError, setOperationError] = useState<string | null>(null)

  const decisionLabel = (decision: ToolApprovalPolicy['default_decision']) => {
    if (decision === 'allow') return t('approval.allow')
    if (decision === 'deny') return t('approval.deny')
    return t('approval.requireApproval')
  }

  const connectionFieldError = (field: ToolConnectionField): string | null => {
    const name = field.name.trim()
    if (!name) return field.label.trim() ? t('connectionFields.nameRequired') : null
    if (!CONNECTION_FIELD_NAME_PATTERN.test(name)) return t('connectionFields.invalidName')
    if (!field.label.trim()) return t('connectionFields.labelRequired')
    return null
  }

  const overrideNames = useMemo(() => {
    const names = new Set<string>()
    for (const name of operationNames ?? []) {
      if (name.trim()) names.add(name)
    }
    for (const name of Object.keys(approvalPolicy.operation_overrides ?? {})) {
      names.add(name)
    }
    return [...names].sort((a, b) => a.localeCompare(b))
  }, [operationNames, approvalPolicy.operation_overrides])

  const discoveredTools = new Map((operationTools ?? []).map(tool => [`tool:${tool.name}`, tool]))
  const otherOperations = overrideNames.filter(name => !discoveredTools.has(name))

  const updateField = (index: number, updates: Partial<ToolConnectionField>) => {
    onConnectionFieldsChange(
      connectionFields.map((field, current) => (current === index ? { ...field, ...updates } : field))
    )
  }

  const legacyAudiences = useMemo(
    () => findLegacyApprovalAudiences(approvalPolicy),
    [approvalPolicy]
  )

  const setDecision = (decision: ToolApprovalPolicy['default_decision']) => {
    // Legacy gates are preserved so the server rejects the write instead of
    // silently converting or dropping an external audience. Caller gates only
    // exist for caller confirmation and are never carried into allow or deny.
    const legacyGates = approvalPolicy.gates.filter((gate) => gate.kind !== 'caller')
    onApprovalPolicyChange({
      ...approvalPolicy,
      default_decision: decision,
      gates:
        legacyGates.length > 0
          ? legacyGates
          : decision === 'require_approval'
            ? [createCallerGate()]
            : [],
    })
  }

  const setOperationDecision = (
    operation: string,
    decision: ToolApprovalPolicy['default_decision'] | 'inherit'
  ) => {
    const nextOverrides = { ...(approvalPolicy.operation_overrides ?? {}) }
    if (decision === 'inherit') {
      delete nextOverrides[operation]
    } else {
      nextOverrides[operation] = {
        default_decision: decision,
        gates: decision === 'require_approval' ? [createCallerGate()] : [],
        operation_overrides: {},
      }
    }
    onApprovalPolicyChange({ ...approvalPolicy, operation_overrides: nextOverrides })
  }

  const addOperation = () => {
    const operation = newOperation.trim()
    if (!operation || operation === '*' || /\s/.test(operation)) {
      setOperationError(t('operations.invalidOperation'))
      return
    }
    if (discoveredTools.has(operation) || operationNames?.includes(operation) || approvalPolicy.operation_overrides?.[operation]) {
      setOperationError(t('operations.duplicate'))
      return
    }
    setOperationError(null)
    setOperationDecision(operation, 'require_approval')
    setNewOperation('')
  }

  const duplicateFieldNames = useMemo(() => {
    const seen = new Set<string>()
    const duplicates = new Set<string>()
    for (const field of connectionFields) {
      const name = field.name.trim()
      if (!name) continue
      if (seen.has(name)) duplicates.add(name)
      seen.add(name)
    }
    return duplicates
  }, [connectionFields])

  return (
    <div className="space-y-5 border rounded-lg p-4">
      <div className="space-y-1">
        <h4 className="font-medium">{t('title')}</h4>
        <p className="text-xs text-muted-foreground">{t('description')}</p>
      </div>

      {showIdentityAndConnections && (
        <>
      {/* Identity mode */}
      <div className="space-y-2">
        <Label htmlFor="tool-identity-policy">{t('identity.label')}</Label>
        <Select
          value={identityPolicy}
          onValueChange={(value) => onIdentityPolicyChange(value as ToolIdentityPolicy)}
        >
          <SelectTrigger id="tool-identity-policy" className="w-full">
            <SelectValue>{t(`identity.options.${identityPolicy}`)}</SelectValue>
          </SelectTrigger>
          <SelectContent side="bottom" alignItemWithTrigger={false} className="w-[--anchor-width] min-w-[320px]">
            {TOOL_IDENTITY_POLICIES.map((policy) => (
              <SelectItem key={policy} value={policy}>
                {t(`identity.options.${policy}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t(`identity.hints.${identityPolicy}`)}</p>
      </div>

      {/* Connection fields */}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Label>{t('connectionFields.title')}</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onConnectionFieldsChange([
                ...connectionFields,
                { name: '', label: '', required: true, secret: true },
              ])
            }
          >
            <Plus className="h-3.5 w-3.5 mr-1" />
            {t('connectionFields.add')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('connectionFields.hint')}</p>
        {connectionFields.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2">{t('connectionFields.empty')}</p>
        ) : (
          <div className="space-y-2">
            {connectionFields.map((field, index) => {
              const trimmedName = field.name.trim()
              const nameInvalid = !!trimmedName && !CONNECTION_FIELD_NAME_PATTERN.test(trimmedName)
              const duplicate = !!trimmedName && duplicateFieldNames.has(trimmedName)
              return (
                <div key={index} className="rounded-md border p-2 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor={`connection-field-name-${index}`} className="text-xs">
                        {t('connectionFields.name')}
                      </Label>
                      <Input
                        id={`connection-field-name-${index}`}
                        value={field.name}
                        placeholder={t('connectionFields.namePlaceholder')}
                        className="font-mono"
                        onChange={(event) => updateField(index, { name: event.target.value })}
                        aria-invalid={nameInvalid || duplicate || !!connectionFieldError(field)}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`connection-field-label-${index}`} className="text-xs">
                        {t('connectionFields.label')}
                      </Label>
                      <Input
                        id={`connection-field-label-${index}`}
                        value={field.label}
                        placeholder={t('connectionFields.labelPlaceholder')}
                        onChange={(event) => updateField(index, { label: event.target.value })}
                      />
                    </div>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 text-xs">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-primary"
                          checked={field.required}
                          onChange={(event) => updateField(index, { required: event.target.checked })}
                        />
                        {t('connectionFields.required')}
                      </label>
                      <label className="flex items-center gap-1.5 text-xs">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-primary"
                          checked={field.secret}
                          onChange={(event) => updateField(index, { secret: event.target.checked })}
                        />
                        {t('connectionFields.secret')}
                      </label>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={t('connectionFields.remove')}
                      onClick={() =>
                        onConnectionFieldsChange(connectionFields.filter((_, current) => current !== index))
                      }
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  {nameInvalid && <FieldError>{t('connectionFields.invalidName')}</FieldError>}
                  {!nameInvalid && duplicate && <FieldError>{t('connectionFields.duplicate')}</FieldError>}
                  {!nameInvalid && !duplicate && field.name.trim() && !field.label.trim() && (
                    <FieldError>{t('connectionFields.labelRequired')}</FieldError>
                  )}
                  {!nameInvalid && !duplicate && !field.name.trim() && field.label.trim() && (
                    <FieldError>{t('connectionFields.nameRequired')}</FieldError>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

        </>
      )}

      {/* Approval policy */}
      <div className="space-y-3 border-t pt-4">
        <div className="space-y-2">
          <Label htmlFor="tool-approval-default">{t('approval.defaultDecision')}</Label>
          <Select
            value={approvalPolicy.default_decision}
            onValueChange={(value) =>
              setDecision(value as ToolApprovalPolicy['default_decision'])
            }
          >
            <SelectTrigger
              id="tool-approval-default"
              data-testid="tool-approval-default"
              className="w-full sm:w-[280px]"
            >
              <SelectValue>{decisionLabel(approvalPolicy.default_decision)}</SelectValue>
            </SelectTrigger>
            <SelectContent side="bottom" alignItemWithTrigger={false} className="w-[--anchor-width] min-w-[280px]">
              {TOOL_APPROVAL_DECISIONS.map((decision) => (
                <SelectItem key={decision} value={decision}>
                  {decisionLabel(decision)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('approval.hint')}</p>
        </div>

        {legacyAudiences.length > 0 && (
          <div className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
            <FieldError>{t('approval.legacyTitle')}</FieldError>
            <p className="text-xs text-muted-foreground">{t('approval.legacyDescription')}</p>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {legacyAudiences.map((audience) => (
                <li key={audience.operation || 'default'} className="break-all font-mono">
                  {audience.operation || t('approval.legacyDefaultScope')}:{' '}
                  {audience.kinds.map((kind) => t(`approval.legacyKinds.${kind}`)).join(', ')}
                </li>
              ))}
            </ul>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onApprovalPolicyChange(resetLegacyApprovalAudiences(approvalPolicy))}
            >
              {t('approval.legacyReset')}
            </Button>
            <p className="text-xs text-muted-foreground">{t('approval.legacyResetHint')}</p>
          </div>
        )}

        {approvalPolicy.default_decision === 'require_approval' && legacyAudiences.length === 0 && (
          <div className="space-y-1 rounded-md border p-3">
            <Label>{t('approval.callerGate')}</Label>
            <p className="text-xs text-muted-foreground">{t('approval.callerHint')}</p>
          </div>
        )}

        {(operationNames !== undefined || operationTools !== undefined) && (
          <div className="space-y-2 border-t pt-4">
            <div>
              <Label>{t(operationTools ? 'operations.toolsTitle' : 'operations.title')}{operationTools && ` (${operationTools.length})`}</Label>
              <p className="text-xs text-muted-foreground">{t('operations.hint')}</p>
            </div>

            {discoveredTools.size + otherOperations.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('operations.empty')}</p>
            ) : (
              <div className="max-h-[min(400px,45vh)] overflow-y-auto overscroll-contain space-y-2 pr-2">
                {[...discoveredTools.keys(), ...otherOperations].map((operation, index) => (
                  <div key={operation}>
                    {operationTools && index === discoveredTools.size && otherOperations.length > 0 && (
                      <p className="text-sm font-medium pt-3 pb-2">{t('operations.otherTitle')}</p>
                    )}
                    <div className="flex flex-col gap-2 rounded-md border p-3 sm:flex-row sm:items-start">
                    <div className="flex-1 min-w-0 space-y-1">
                      <p className="text-sm font-medium break-all">{discoveredTools.get(operation)?.name ?? operation}</p>
                      {discoveredTools.has(operation) ? (
                        <>
                          <code className="text-xs text-muted-foreground break-all">{operation}</code>
                          <Tooltip>
                            <TooltipTrigger
                              render={<p tabIndex={0} />}
                              className="text-xs text-muted-foreground line-clamp-2 whitespace-pre-wrap break-words cursor-help"
                            >
                              {discoveredTools.get(operation)?.description || t('operations.noDescription')}
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm max-h-72 overflow-y-auto whitespace-pre-wrap break-words">
                              {discoveredTools.get(operation)?.description || t('operations.noDescription')}
                            </TooltipContent>
                          </Tooltip>
                        </>
                      ) : operationTools && toolsLoaded ? (
                        <p className="text-xs text-muted-foreground">{t('operations.notDiscovered')}</p>
                      ) : null}
                    </div>
                    <Select
                      value={approvalPolicy.operation_overrides?.[operation]?.default_decision ?? 'inherit'}
                      onValueChange={(value) =>
                        setOperationDecision(
                          operation,
                          value as ToolApprovalPolicy['default_decision'] | 'inherit'
                        )
                      }
                    >
                      <SelectTrigger className="w-full sm:w-[190px] shrink-0">
                        <SelectValue>
                          {approvalPolicy.operation_overrides?.[operation]
                            ? decisionLabel(approvalPolicy.operation_overrides[operation].default_decision)
                            : t('operations.inherit')}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent side="bottom" alignItemWithTrigger={false}>
                        <SelectItem value="inherit">{t('operations.inherit')}</SelectItem>
                        <SelectItem value="allow">{decisionLabel('allow')}</SelectItem>
                        <SelectItem value="deny">{decisionLabel('deny')}</SelectItem>
                        <SelectItem value="require_approval">{decisionLabel('require_approval')}</SelectItem>
                      </SelectContent>
                    </Select>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <Input
                value={newOperation}
                placeholder={t('operations.operationPlaceholder')}
                className="font-mono"
                onChange={(event) => {
                  setNewOperation(event.target.value)
                  setOperationError(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    addOperation()
                  }
                }}
                aria-invalid={!!operationError}
              />
              <Button type="button" variant="outline" size="sm" onClick={addOperation}>
                <Plus className="h-3.5 w-3.5 mr-1" />
                {t('operations.addOperation')}
              </Button>
            </div>
            {operationError && <FieldError>{operationError}</FieldError>}
          </div>
        )}
      </div>
    </div>
  )
}

