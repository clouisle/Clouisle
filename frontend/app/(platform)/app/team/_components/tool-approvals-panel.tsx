'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  AlertTriangle,
  Loader2,
  Lock,
  Pencil,
  RefreshCw,
  Search,
} from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  ToolApprovalPolicyEditor,
  getToolApprovalPolicy,
  hasLegacyApprovalAudiences,
  normalizeToolApprovalPolicy,
} from '@/components/tools/tool-policy-editor'
import { toolsApi } from '@/lib/api'
import type { Tool, ToolApprovalPolicy } from '@/lib/api/tools'

type TeamToolApprovalsRole = 'owner' | 'admin' | 'member' | 'viewer'

interface TeamToolApprovalsProps {
  teamId: string
  /** Only fetch while the hosting tab is active. */
  enabled: boolean
  currentUserId?: string
  isSuperuser: boolean
  membershipRole?: TeamToolApprovalsRole
  canReadTools: boolean
  /** True when the user holds `tool:update` and permissions have loaded. */
  canUpdateTools: boolean
}

type ReadOnlyReason =
  | 'sharedTool'
  | 'permissionDenied'
  | 'viewerOnly'
  | 'privateTool'
  | 'teamAdminOnly'
  | 'policyUnavailable'

const DECISION_BADGE_VARIANT: Record<
  ToolApprovalPolicy['default_decision'],
  'outline' | 'secondary' | 'destructive'
> = {
  allow: 'outline',
  deny: 'destructive',
  require_approval: 'secondary',
}

export function TeamToolApprovalsPanel({
  teamId,
  enabled,
  currentUserId,
  isSuperuser,
  membershipRole,
  canReadTools,
  canUpdateTools,
}: TeamToolApprovalsProps) {
  const t = useTranslations('teams.toolApprovals')

  const [tools, setTools] = React.useState<Tool[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState(false)
  const [search, setSearch] = React.useState('')

  const [editingTool, setEditingTool] = React.useState<Tool | null>(null)
  const [draftPolicy, setDraftPolicy] = React.useState<ToolApprovalPolicy | null>(null)
  const [isSaving, setIsSaving] = React.useState(false)
  const [saveError, setSaveError] = React.useState<string | null>(null)
  // Monotonic token: a response from a previous team/refresh must never
  // overwrite the tools of the current team.
  const requestToken = React.useRef(0)

  const loadTools = React.useCallback(async () => {
    const token = ++requestToken.current
    if (!canReadTools) {
      setTools([])
      setLoadError(false)
      return
    }
    setIsLoading(true)
    setLoadError(false)
    try {
      const response = await toolsApi.list(teamId)
      if (token !== requestToken.current) return
      setTools([...response.builtin, ...response.custom, ...response.mcp])
    } catch {
      if (token !== requestToken.current) return
      // The API client already surfaced the error message.
      setLoadError(true)
    } finally {
      if (token === requestToken.current) setIsLoading(false)
    }
  }, [canReadTools, teamId])

  React.useEffect(() => {
    if (!enabled) return
    void loadTools()
    return () => {
      // Invalidate the in-flight request when the tab or team changes.
      requestToken.current += 1
    }
  }, [enabled, loadTools])

  const visibleTools = React.useMemo(() => {
    const query = search.trim().toLowerCase()
    return tools
      .filter((tool) => {
        // Builtins are team-scoped registry entries even when `/tools/legacy`
        // omits the definition visibility or the definition could not be
        // materialized; never hide them behind the private-tool rule.
        if (tool.type === 'builtin') return true
        // Defense in depth: the API already omits other members' private
        // tools, and the UI must never surface one either.
        if (tool.visibility === 'private') {
          return isSuperuser || tool.created_by_id === currentUserId
        }
        return true
      })
      .filter((tool) => {
        if (!query) return true
        return (
          tool.display_name.toLowerCase().includes(query) ||
          tool.name.toLowerCase().includes(query)
        )
      })
      .sort((a, b) => a.display_name.localeCompare(b.display_name))
  }, [tools, search, isSuperuser, currentUserId])

  const readOnlyReason = (tool: Tool): ReadOnlyReason | null => {
    // A missing id or policy cannot be written back; never offer an edit that
    // would silently no-op or invent a default decision.
    if (!tool.id || !tool.approval_policy) return 'policyUnavailable'
    if (isSuperuser) return null
    // Shared tools are always administered by the owning team; never claim
    // or display which team that is.
    if (tool.is_owned === false) return 'sharedTool'
    if (!canUpdateTools) return 'permissionDenied'
    if (membershipRole === 'viewer') return 'viewerOnly'
    // `/tools/legacy` does not copy the builtin definition's TEAM visibility
    // into the response, but every builtin row is team-scoped by construction.
    if (tool.type === 'builtin') {
      return membershipRole === 'owner' || membershipRole === 'admin'
        ? null
        : 'teamAdminOnly'
    }
    if (tool.visibility === 'private') {
      return tool.created_by_id === currentUserId ? null : 'privateTool'
    }
    if (tool.created_by_id && tool.created_by_id === currentUserId) return null
    if (membershipRole === 'owner' || membershipRole === 'admin') return null
    return 'teamAdminOnly'
  }

  const editTool = (tool: Tool) => {
    setEditingTool(tool)
    setDraftPolicy(getToolApprovalPolicy(tool))
    setSaveError(null)
  }

  const closeEditor = () => {
    if (isSaving) return
    setEditingTool(null)
    setDraftPolicy(null)
    setSaveError(null)
  }

  const legacyBlocked = draftPolicy ? hasLegacyApprovalAudiences(draftPolicy) : false

  const savePolicy = async () => {
    const toolId = editingTool?.id
    if (!toolId || !draftPolicy || legacyBlocked || isSaving) return
    const policy = normalizeToolApprovalPolicy(draftPolicy)
    setIsSaving(true)
    setSaveError(null)
    try {
      await toolsApi.update(toolId, { approval_policy: policy })
      setTools((current) =>
        current.map((tool) =>
          tool.id === toolId ? { ...tool, approval_policy: policy } : tool
        )
      )
      toast.success(t('saved'))
      setEditingTool(null)
      setDraftPolicy(null)
    } catch {
      setSaveError(t('saveFailed'))
    } finally {
      setIsSaving(false)
    }
  }

  if (!enabled) return null

  const renderToolRow = (tool: Tool) => {
    // Only a persisted definition carries an authoritative policy. `/tools/legacy`
    // leaves the registry default on entries whose definition failed to load;
    // never present that default as the saved decision.
    const policy =
      tool.id && tool.approval_policy ? getToolApprovalPolicy(tool) : null
    const reason = readOnlyReason(tool)
    // `/tools/legacy` sets `is_owned=false` explicitly for cross-team shares
    // and `true` for owned custom/MCP rows (builtins default to true).
    const isShared = tool.is_owned === false
    const scope =
      tool.type === 'builtin' ? 'team' : isShared ? 'shared' : tool.visibility
    const typeKey =
      tool.type === 'builtin' || tool.type === 'mcp' || tool.type === 'skill'
        ? tool.type
        : 'custom'

    return (
      <div
        key={tool.id ?? tool.name}
        data-testid={`tool-approval-row-${tool.id ?? tool.name}`}
        className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{tool.display_name}</span>
            <Badge variant="outline" className="text-[10px]">
              {t(`types.${typeKey}`)}
            </Badge>
            <Badge variant="secondary" className="text-[10px]">
              {t(`visibility.${scope}`)}
            </Badge>
            {policy ? (
              <Badge
                variant={DECISION_BADGE_VARIANT[policy.default_decision]}
                className="text-[10px]"
                data-testid={`tool-approval-decision-${tool.id ?? tool.name}`}
              >
                {t(`decisions.${policy.default_decision}`)}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">
                {t('policyUnavailable')}
              </Badge>
            )}
            {policy && hasLegacyApprovalAudiences(policy) && (
              <Badge variant="destructive" className="text-[10px]">
                {t('legacyBadge')}
              </Badge>
            )}
          </div>
          <code className="block truncate text-xs text-muted-foreground">{tool.name}</code>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {reason ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Lock className="h-3.5 w-3.5" />
                {t(`readOnly.${reason}`)}
              </span>
              {reason === 'policyUnavailable' && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  data-testid={`reload-tool-approval-${tool.id ?? tool.name}`}
                  onClick={() => void loadTools()}
                >
                  <RefreshCw className="mr-1 h-3.5 w-3.5" />
                  {t('retry')}
                </Button>
              )}
            </div>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              data-testid={`edit-tool-approval-${tool.id ?? tool.name}`}
              onClick={() => editTool(tool)}
            >
              <Pencil className="mr-1 h-3.5 w-3.5" />
              {t('edit')}
            </Button>
          )}
        </div>
      </div>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4">
        <div className="space-y-1">
          <CardTitle className="text-lg">{t('title')}</CardTitle>
          <CardDescription>{t('description')}</CardDescription>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('retry')}
          disabled={isLoading || !canReadTools}
          onClick={() => void loadTools()}
        >
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {!canReadTools ? (
          <div className="rounded-md border p-8 text-center text-sm text-muted-foreground">
            {t('readDenied')}
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative w-full max-w-sm">
                <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder={t('searchPlaceholder')}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  className="h-9 pl-8"
                />
              </div>
              {!isLoading && !loadError && (
                <span className="text-xs text-muted-foreground">
                  {t('count', { count: visibleTools.length })}
                </span>
              )}
            </div>

            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((index) => (
                  <div key={index} className="rounded-md border p-4">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="mt-2 h-3 w-32" />
                  </div>
                ))}
              </div>
            ) : loadError ? (
              <div className="flex flex-col items-center gap-3 rounded-md border p-8 text-center">
                <AlertTriangle className="h-8 w-8 text-yellow-500" />
                <p className="text-sm text-muted-foreground">{t('loadFailed')}</p>
                <Button type="button" size="sm" variant="outline" onClick={() => void loadTools()}>
                  {t('retry')}
                </Button>
              </div>
            ) : visibleTools.length === 0 ? (
              <div className="rounded-md border p-8 text-center text-sm text-muted-foreground">
                <p>{search.trim() ? t('noMatches') : t('empty')}</p>
                {!search.trim() && (
                  <p className="mt-1 text-xs">{t('emptyHint')}</p>
                )}
              </div>
            ) : (
              <div className="divide-y rounded-md border">{visibleTools.map(renderToolRow)}</div>
            )}
          </>
        )}
      </CardContent>

      <Dialog open={!!editingTool} onOpenChange={(open) => !open && closeEditor()}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {t('editTitle', { name: editingTool?.display_name ?? '' })}
            </DialogTitle>
            <DialogDescription>{t('editDescription')}</DialogDescription>
          </DialogHeader>

          {draftPolicy && editingTool && (
            <div className="max-h-[min(70vh,640px)] overflow-y-auto pr-1">
              <ToolApprovalPolicyEditor
                approvalPolicy={draftPolicy}
                onApprovalPolicyChange={setDraftPolicy}
                operationNames={
                  editingTool.type === 'mcp' ||
                  Object.keys(draftPolicy.operation_overrides ?? {}).length > 0
                    ? []
                    : undefined
                }
              />
            </div>
          )}

          {legacyBlocked && (
            <p role="alert" className="text-xs text-destructive">
              {t('legacyBlocked')}
            </p>
          )}
          {saveError && (
            <p role="alert" className="text-xs text-destructive">
              {saveError}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeEditor} disabled={isSaving}>
              {t('cancel')}
            </Button>
            <Button
              type="button"
              data-testid="save-tool-approval"
              onClick={() => void savePolicy()}
              disabled={isSaving || !draftPolicy || legacyBlocked}
            >
              {isSaving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              {isSaving ? t('saving') : t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
