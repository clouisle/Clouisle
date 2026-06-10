'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Sparkles, GitBranch, Loader2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { FieldError } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { normalizeValidationErrors, clearValidationError, getValidationSummaryEntries,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { agentsApi, type Agent, type AgentCreateInput } from '@/lib/api/agents'
import { workflowsApi, type Workflow, type WorkflowCreateInput } from '@/lib/api/workflows'
import type { Team } from '@/lib/api/teams'
import { useOptionalTeam } from '@/contexts/team-context'

interface AppCreateApi {
  createAgent: (data: AgentCreateInput) => Promise<Agent>
  createWorkflow: (data: WorkflowCreateInput) => Promise<Workflow>
}

interface AppCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
  api?: AppCreateApi
  teamId?: string
  teams?: Team[]
  initialType?: AppType
  allowedTypes?: AppType[]
  agentEditHref?: (id: string) => string
  workflowEditHref?: (id: string) => string
}

type AppType = 'agent' | 'workflow'

const EMPTY_TEAMS: Team[] = []

export function AppCreateDialog({
  open,
  onOpenChange,
  onSuccess,
  api = {
    createAgent: agentsApi.createAgent,
    createWorkflow: workflowsApi.createWorkflow,
  },
  teamId,
  teams = EMPTY_TEAMS,
  initialType = 'agent',
  allowedTypes = ['agent', 'workflow'],
  agentEditHref = (id: string) => `/app/apps/${id}`,
  workflowEditHref = (id: string) => `/app/apps/workflow/${id}`,
}: AppCreateDialogProps) {
  const t = useTranslations('apps')
  const tCommon = useTranslations('common')
  const router = useRouter()
  const teamContext = useOptionalTeam()
  const currentTeam = teamContext?.currentTeam

  const [appType, setAppType] = React.useState<AppType>('agent')
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [selectedTeamId, setSelectedTeamId] = React.useState(teamId || teams[0]?.id || '')
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})

  // Reset form when dialog opens
  React.useEffect(() => {
    if (open) {
      setAppType(initialType)
      setSelectedTeamId(teamId || teams[0]?.id || '')
      setName('')
      setDescription('')
      setFieldErrors({})
    }
  }, [open, initialType, teamId, teams])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!name.trim()) {
      setFieldErrors({ name: t('nameRequired') })
      return
    }

    const targetTeamId = teamId || selectedTeamId || currentTeam?.id
    if (!targetTeamId) {
      setFieldErrors({ team_id: t('teamRequired') })
      return
    }

    setIsSubmitting(true)
    setFieldErrors({})

    try {
      if (appType === 'agent') {
        const agent = await api.createAgent({
          team_id: targetTeamId,
          name: name.trim(),
          description: description.trim() || undefined,
        })
        toast.success(t('appCreated'))
        onSuccess?.()
        router.push(agentEditHref(agent.id))
      } else {
        const workflow = await api.createWorkflow({
          team_id: targetTeamId,
          name: name.trim(),
          description: description.trim() || undefined,
        })
        toast.success(t('appCreated'))
        onSuccess?.()
        router.push(workflowEditHref(workflow.id))
      }
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['team_id', 'name', 'description']),
    [fieldErrors]
  )

  const appTypes = [
    {
      type: 'agent' as const,
      icon: Sparkles,
      title: t('types.agent.title'),
      description: t('types.agent.description'),
    },
    {
      type: 'workflow' as const,
      icon: GitBranch,
      title: t('types.workflow.title'),
      description: t('types.workflow.description'),
    },
  ]

  const availableAppTypes = appTypes.filter((item) => allowedTypes.includes(item.type))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t('createApp')}</DialogTitle>
            <DialogDescription>{t('createAppDescription')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-6 py-4">
            {summaryEntries.length > 0 && (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
                {summaryEntries.map(([field, message]) => (
                  <FieldError key={field}>
                    {formatValidationSummaryMessage(field, message)}
                  </FieldError>
                ))}
              </div>
            )}
            {availableAppTypes.length > 1 && (
              <div className="space-y-3">
                <Label>{t('selectType')}</Label>
                <RadioGroup
                  value={appType}
                  onValueChange={(v) => setAppType(v as AppType)}
                  className="grid grid-cols-2 gap-3"
                >
                  {availableAppTypes.map((item) => {
                    const Icon = item.icon
                    return (
                      <label
                        key={item.type}
                        className={cn(
                          'flex flex-col items-center gap-2 rounded-lg border-2 p-4 cursor-pointer transition-all',
                          appType === item.type
                            ? 'border-primary bg-primary/5'
                            : 'border-muted hover:border-muted-foreground/50'
                        )}
                      >
                        <RadioGroupItem
                          value={item.type}
                          className="sr-only"
                        />
                        <div
                          className={cn(
                            'flex h-10 w-10 items-center justify-center rounded-lg',
                            appType === item.type
                              ? 'bg-primary text-primary-foreground'
                              : 'bg-muted text-muted-foreground'
                          )}
                        >
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="text-center">
                          <div className="font-medium text-sm">{item.title}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {item.description}
                          </div>
                        </div>
                      </label>
                    )
                  })}
                </RadioGroup>
              </div>
            )}

            {teams.length > 0 && !teamId && (
              <div className="space-y-2">
                <Label htmlFor="team_id">{t('team')}</Label>
                <Select
                  value={selectedTeamId}
                  onValueChange={(value) => {
                    if (!value) return
                    setSelectedTeamId(value)
                    setFieldErrors((prev) => clearValidationError(prev, 'team_id'))
                  }}
                >
                  <SelectTrigger id="team_id" aria-invalid={!!fieldErrors.team_id} className="min-w-64">
                    <SelectValue>{teams.find((team) => team.id === selectedTeamId)?.name || t('teamRequired')}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {teams.map((team) => (
                      <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError>{fieldErrors.team_id}</FieldError>
              </div>
            )}

            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="name">{t('name')}</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'name'))
                }}
                placeholder={t('namePlaceholder')}
                maxLength={100}
                aria-invalid={!!fieldErrors.name}
              />
              <FieldError>{fieldErrors.name}</FieldError>
            </div>

            {/* Description */}
            <div className="space-y-2">
              <Label htmlFor="description">
                {t('descriptionLabel')}{' '}
                <span className="text-muted-foreground text-xs">({t('optional')})</span>
              </Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'description'))
                }}
                placeholder={t('descriptionPlaceholder')}
                rows={3}
                maxLength={500}
                aria-invalid={!!fieldErrors.description}
              />
              <FieldError>{fieldErrors.description}</FieldError>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              {tCommon('cancel')}
            </Button>
            <Button type="submit" disabled={isSubmitting || !name.trim()}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {tCommon('create')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
