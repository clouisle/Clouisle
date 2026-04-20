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
import { FieldError } from '@/components/ui/field'
import { cn } from '@/lib/utils'
import { normalizeValidationErrors, clearValidationError, getValidationSummaryEntries,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { agentsApi } from '@/lib/api/agents'
import { workflowsApi } from '@/lib/api/workflows'
import { useTeam } from '@/contexts/team-context'

interface AppCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

type AppType = 'agent' | 'workflow'

export function AppCreateDialog({ open, onOpenChange, onSuccess }: AppCreateDialogProps) {
  const t = useTranslations('apps')
  const tCommon = useTranslations('common')
  const router = useRouter()
  const { currentTeam } = useTeam()

  const [appType, setAppType] = React.useState<AppType>('agent')
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})

  // Reset form when dialog opens
  React.useEffect(() => {
    if (open) {
      setAppType('agent')
      setName('')
      setDescription('')
      setFieldErrors({})
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!name.trim()) {
      setFieldErrors({ name: t('nameRequired') })
      return
    }

    if (!currentTeam) {
      setFieldErrors({ __all__: t('teamRequired') })
      return
    }

    setIsSubmitting(true)
    setFieldErrors({})

    try {
      if (appType === 'agent') {
        const agent = await agentsApi.createAgent({
          team_id: currentTeam.id,
          name: name.trim(),
          description: description.trim() || undefined,
        })
        toast.success(t('appCreated'))
        onSuccess?.()
        // Navigate to app config page
        router.push(`/app/apps/${agent.id}`)
      } else {
        // Create workflow
        const workflow = await workflowsApi.createWorkflow({
          team_id: currentTeam.id,
          name: name.trim(),
          description: description.trim() || undefined,
        })
        toast.success(t('appCreated'))
        onSuccess?.()
        // Navigate to workflow editor page
        router.push(`/app/apps/workflow/${workflow.id}`)
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
    () => getValidationSummaryEntries(fieldErrors, ['name', 'description']),
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
            {/* App Type Selection */}
            <div className="space-y-3">
              <Label>{t('selectType')}</Label>
              <RadioGroup
                value={appType}
                onValueChange={(v) => setAppType(v as AppType)}
                className="grid grid-cols-2 gap-3"
              >
                {appTypes.map((item) => {
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
